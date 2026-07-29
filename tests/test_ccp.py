#!/usr/bin/env python3
"""End-to-end tests for ccp, against a throwaway HOME and the file backend.

    python3 tests/test_ccp.py

Black-box: every case shells out to the real CLI with HOME redirected, so the code
under test is exactly what users run. CCP_BACKEND=file exercises the Linux/Windows
credential store, which means these pass on macOS too and the platform-specific
surface stays honest even where the author cannot run the real thing.

Nothing here touches your real credentials, keychain, or ~/.claude.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CCP = Path(__file__).resolve().parent.parent / "bin" / "ccp"

passed = failed = 0


def check(cond: bool, label: str) -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


def section(name: str) -> None:
    print(f"\n{name}")


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #

class Sandbox:
    """A fake HOME with a fake Claude Code install, torn down afterwards."""

    def __init__(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="ccp-test-"))
        self.claude = self.home / ".claude"
        self.claude.mkdir()
        # shareable content
        (self.claude / "settings.json").write_text('{"theme":"dark"}')
        (self.claude / "commands").mkdir()
        (self.claude / "commands" / "hi.md").write_text("hello")
        (self.claude / "projects").mkdir()
        # private content that must never be linked
        (self.claude / "history.jsonl").write_text("{}\n")
        (self.claude / "sessions").mkdir()
        (self.claude / "debug.log").write_text("noise")

    def stop(self) -> None:
        shutil.rmtree(self.home, ignore_errors=True)

    # -- credentials -------------------------------------------------------- #

    def cred(self, tag: str, hours: float = 8.0) -> str:
        return json.dumps({"claudeAiOauth": {
            "accessToken": f"access-{tag}",
            "refreshToken": f"refresh-{tag}",
            "expiresAt": int((time.time() + hours * 3600) * 1000),
            "refreshTokenExpiresAt": int((time.time() + 30 * 86400) * 1000),
            "scopes": ["user:inference", "user:profile"],
            "subscriptionType": "max"}})

    def cred_path(self, slot: int | None) -> Path:
        d = self.claude if slot is None else self.home / ".claude-slots" / str(slot)
        return d / ".credentials.json"

    def put_cred(self, slot: int | None, tag: str, hours: float = 8.0) -> None:
        p = self.cred_path(slot)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.cred(tag, hours))

    def get_cred(self, slot: int | None) -> dict | None:
        p = self.cred_path(slot)
        if not p.is_file():
            return None
        return json.loads(p.read_text())["claudeAiOauth"]

    def token(self, slot: int | None) -> str | None:
        c = self.get_cred(slot)
        return c["accessToken"] if c else None

    # -- identity ----------------------------------------------------------- #

    def put_identity(self, slot: int | None, email: str) -> None:
        d = self.claude.parent if slot is None else self.home / ".claude-slots" / str(slot)
        p = (self.home / ".claude.json") if slot is None else (d / ".claude.json")
        cur = json.loads(p.read_text()) if p.is_file() else {}
        cur["oauthAccount"] = {"emailAddress": email, "organizationName": "Test"}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur))

    def identity(self, slot: int | None) -> str | None:
        p = ((self.home / ".claude.json") if slot is None
             else self.home / ".claude-slots" / str(slot) / ".claude.json")
        if not p.is_file():
            return None
        return (json.loads(p.read_text()).get("oauthAccount") or {}).get("emailAddress")

    # -- running ccp -------------------------------------------------------- #

    def run(self, *args: str, **envextra: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   CCP_BACKEND="file", NO_COLOR="1")
        env.pop("CLAUDE_CONFIG_DIR", None)
        env.pop("SUDO_USER", None)
        env.update(envextra)
        return subprocess.run([sys.executable, str(CCP), *args],
                              capture_output=True, text=True, env=env)

    def state(self, name: str) -> str | None:
        p = self.home / ".claude-profiles" / name
        return p.read_text().strip() if p.is_file() else None

    def slot_entries(self, n: int) -> list[str]:
        d = self.home / ".claude-slots" / str(n)
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


# --------------------------------------------------------------------------- #
# cases
# --------------------------------------------------------------------------- #

def test_init_and_add(sb: Sandbox) -> None:
    section("init parks the current login as slot1")
    sb.put_cred(None, "A")
    sb.put_identity(None, "a@example.com")

    r = sb.run("init")
    check(r.returncode == 0, "init exits 0")
    check(sb.state("live") == "1", "live state is slot1")
    check(sb.token(1) == "access-A", "slot1 parked the live credential")
    check(sb.identity(1) == "a@example.com", "slot1 parked the account identity")

    section("add creates a slot and shares the right things")
    r = sb.run("add")
    check(r.returncode == 0 and "slot2" in r.stdout, "add created slot2")
    entries = sb.slot_entries(2)
    check("settings.json" in entries and "commands" in entries,
          "shareable items linked into slot2")
    check("history.jsonl" not in entries and "sessions" not in entries,
          "private items not linked")
    check("debug.log" not in entries, "*.log not linked")
    check(".credentials.json" not in entries, "no credential leaked into a new slot")


def test_swap(sb: Sandbox) -> None:
    section("swap parks the outgoing account and loads the incoming one")
    sb.put_cred(2, "B")
    sb.put_identity(2, "b@example.com")

    r = sb.run("swap", "2")
    check(r.returncode == 0, "swap exits 0")
    check(sb.state("live") == "2", "live state moved to slot2")
    check(sb.token(None) == "access-B", "live store holds slot2's credential")
    check(sb.token(1) == "access-A", "slot1 still parked with its own credential")
    check(sb.identity(None) == "b@example.com", "live identity switched")

    section("the incoming access token is backdated so open sessions adopt it")
    exp = sb.get_cred(None)["expiresAt"] / 1000
    check(exp < time.time(), "live expiresAt is in the past")
    check(sb.get_cred(None)["refreshToken"] == "refresh-B",
          "refresh token was left untouched")
    check(sb.get_cred(2)["expiresAt"] / 1000 > time.time(),
          "the parked copy was not backdated")

    section("--lazy skips the backdating")
    r = sb.run("swap", "1", "--lazy")
    check(r.returncode == 0 and sb.state("live") == "1", "swapped back to slot1")
    check(sb.get_cred(None)["expiresAt"] / 1000 > time.time(),
          "live expiresAt left alone with --lazy")

    section("swapping to the live slot is a no-op")
    r = sb.run("swap", "1")
    check(r.returncode == 0 and "already live" in r.stdout, "reports already live")


def test_rotation_is_preserved(sb: Sandbox) -> None:
    section("a rotated token survives the round trip (the core invariant)")
    sb.run("swap", "2")
    # simulate Claude Code refreshing while slot2 is live: new pair in the live store
    sb.put_cred(None, "B-rotated")
    check(sb.token(2) == "access-B", "slot2's parked copy is now stale, as expected")

    sb.run("swap", "1")
    check(sb.token(2) == "access-B-rotated",
          "swapping away parked the ROTATED credential, not the stale one")
    check(sb.get_cred(2)["refreshToken"] == "refresh-B-rotated",
          "the rotated refresh token is what got parked")

    sb.run("swap", "2")
    check(sb.get_cred(None)["refreshToken"] == "refresh-B-rotated",
          "swapping back loads the rotated refresh token")
    sb.run("swap", "1")


def test_guards(sb: Sandbox) -> None:
    section("guards protect the live slot's credential store")
    check(sb.state("live") == "1", "slot1 is live for these checks")

    r = sb.run("pin", "1")
    check(r.returncode != 0 and "is live" in r.stderr, "pin refuses the live slot")

    r = sb.run("logout", "1")
    check(r.returncode != 0 and "is live" in r.stderr, "logout refuses the live slot")

    r = sb.run("rm", "1")
    check(r.returncode != 0 and "is live" in r.stderr, "rm refuses the live slot")

    r = sb.run("swap", "9")
    check(r.returncode != 0 and "does not exist" in r.stderr, "unknown slot rejected")

    r = sb.run("swap", "nobody@example.com")
    check(r.returncode != 0 and "neither a slot" in r.stderr, "unknown account rejected")


def test_resolution(sb: Sandbox) -> None:
    section("slots resolve by number, slotN, and account email")
    for token in ("2", "slot2", "b@example.com", "b@exa"):
        r = sb.run("swap", token)
        ok = r.returncode == 0 and sb.state("live") == "2"
        check(ok, f"`ccp swap {token}` resolved to slot2")
        sb.run("swap", "1")


def test_lifecycle(sb: Sandbox) -> None:
    section("logout, rm and re-add")
    r = sb.run("logout", "2")
    check(r.returncode == 0 and sb.get_cred(2) is None, "logout removed slot2's credential")

    r = sb.run("swap", "2")
    check(r.returncode != 0 and "no parked credential" in r.stderr,
          "cannot swap to a slot with no credential")

    sb.put_cred(2, "B2")
    r = sb.run("rm", "2")
    check(r.returncode == 0 and sb.state("live") == "1", "rm unregistered slot2")
    check(sb.get_cred(2) is not None, "rm without --purge kept the credential")

    r = sb.run("add", "2")
    check(r.returncode == 0 and "already there" in r.stdout,
          "re-adding slot2 finds its credential again")

    r = sb.run("rm", "2", "--purge")
    check(r.returncode == 0, "rm --purge exits 0")
    check(not (sb.home / ".claude-slots" / "2").exists(), "--purge removed the slot dir")


def test_sync_and_doctor(sb: Sandbox) -> None:
    section("sync is idempotent and never clobbers slot-owned files")
    sb.run("add", "3")
    own = sb.home / ".claude-slots" / "3" / "settings.json"
    if own.is_symlink() or own.exists():
        own.unlink()
    own.write_text('{"mine":true}')          # a real file where a link used to be
    r = sb.run("sync", "3")
    check(r.returncode == 0 and "slot-owned" in r.stdout, "sync reported slot-owned file")
    check(json.loads(own.read_text()) == {"mine": True}, "slot-owned file untouched")

    section("doctor")
    r = sb.run("doctor")
    check(r.returncode == 0, "doctor exits 0 on a healthy sandbox")
    check("backend file" in r.stdout, "doctor names the backend in use")
    check("live credential present" in r.stdout, "doctor found the live credential")

    section("ls")
    r = sb.run("ls")
    check("a@example.com" in r.stdout and "LIVE" in r.stdout, "ls shows the live account")


def test_bad_input(sb: Sandbox) -> None:
    section("a corrupt credential is never written to the live store")
    good = sb.token(None)
    sb.put_cred(4, "X")
    sb.run("add", "4")
    (sb.home / ".claude-slots" / "4" / ".credentials.json").write_text("not json{")
    r = sb.run("swap", "4")
    check(r.returncode != 0, "swap refuses an unparseable credential")
    check(sb.token(None) == good, "the live credential was left intact")

    (sb.home / ".claude-slots" / "4" / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"refreshToken": "no-access-token"}}))
    r = sb.run("swap", "4")
    check(r.returncode != 0, "swap refuses a credential with no access token")
    check(sb.token(None) == good, "the live credential is still intact")

    r = sb.run("--version")
    check(r.returncode == 0 and r.stdout.startswith("ccp "), "--version works")

    section("running under sudo is refused, not half-done")
    # sudo leaves HOME alone but sets USER=root, so the config dir and the credential
    # store would come from different users. Every command must refuse.
    for cmd in (("ls",), ("swap", "1"), ("init",), ("doctor",)):
        r = sb.run(*cmd, SUDO_USER="someone")
        ok = r.returncode != 0 and "under sudo" in r.stderr
        check(ok, f"`ccp {' '.join(cmd)}` refuses under sudo")
    r = sb.run("--version", SUDO_USER="someone")
    check(r.returncode == 0, "--version still works under sudo (reads nothing)")

    env_bad = sb.run("nonsense")
    check(env_bad.returncode != 0 and "unknown command" in env_bad.stderr,
          "unknown command rejected")


def main() -> int:
    print(f"ccp tests · {sys.platform} · python {sys.version.split()[0]}")
    sb = Sandbox()
    print(f"sandbox: {sb.home}")
    try:
        test_init_and_add(sb)
        test_swap(sb)
        test_rotation_is_preserved(sb)
        test_guards(sb)
        test_resolution(sb)
        test_lifecycle(sb)
        test_sync_and_doctor(sb)
        test_bad_input(sb)
    finally:
        sb.stop()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
