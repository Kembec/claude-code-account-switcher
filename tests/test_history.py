#!/usr/bin/env python3
"""End-to-end tests for a slot's account history (`ccp login`, `history`, `use <n> <acc>`).

    python3 tests/test_history.py

Same harness as test_ccp.py: throwaway HOME, file backend, the real CLI. `/login` is a
fake `claude` on PATH that writes the account named in FAKE_LOGIN ("tag:email") into
the slot's config dir, or does nothing when FAKE_LOGIN is empty (an aborted login).
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_ccp as t  # noqa: E402
from test_ccp import Sandbox, check, section  # noqa: E402

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys, time
spec = os.environ.get("FAKE_LOGIN", "")
if not spec:
    sys.exit(0)
tag, email = spec.split(":", 1)
d = os.environ["CLAUDE_CONFIG_DIR"]
cred = {"claudeAiOauth": {"accessToken": "access-" + tag, "refreshToken": "refresh-" + tag,
        "expiresAt": int((time.time() + 8 * 3600) * 1000)}}
open(os.path.join(d, ".credentials.json"), "w").write(json.dumps(cred))
p = os.path.join(d, ".claude.json")
cur = json.load(open(p)) if os.path.isfile(p) else {}
cur["oauthAccount"] = {"emailAddress": email, "organizationName": "Test"}
open(p, "w").write(json.dumps(cur))
'''


class HistSandbox(Sandbox):
    def __init__(self) -> None:
        super().__init__()
        self.bin = self.home / "fakebin"
        self.bin.mkdir()
        exe = self.bin / "claude"
        exe.write_text(FAKE_CLAUDE)
        exe.chmod(0o755)

    def run(self, *args: str, **envextra: str):
        envextra.setdefault("PATH", f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}")
        envextra.setdefault("FAKE_LOGIN", "")
        return super().run(*args, **envextra)

    def history(self, n: int) -> dict:
        r = self.run("history", str(n), "--json")
        return json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr}

    def past(self, n: int) -> list[str]:
        return [e["email"] for e in self.history(n).get("past", [])]

    def holders(self, secret: str) -> int:
        """How many files under HOME hold this token: a move leaves exactly one."""
        count = 0
        for root, _dirs, files in os.walk(self.home):
            for f in files:
                try:
                    count += secret in (Path(root) / f).read_text(errors="ignore")
                except OSError:
                    pass
        return count


def setup(sb: HistSandbox) -> None:
    sb.put_cred(None, "A")
    sb.put_identity(None, "a@example.com")
    sb.run("init")
    sb.run("add")
    sb.put_cred(2, "X")
    sb.put_identity(2, "x@example.com")


def test_login_archives(sb: HistSandbox) -> None:
    section("login archives the slot's account before /login")
    r = sb.run("login", "2", FAKE_LOGIN="Y:y@example.com")
    check(r.returncode == 0 and sb.token(2) == "access-Y", "slot2 now holds y")
    check(sb.past(2) == ["x@example.com"], "x moved to slot2's history")
    check(sb.holders("refresh-X") == 1, "x's refresh token lives in one place (the vault)")

    r = sb.run("login", "2", FAKE_LOGIN="Y2:y@example.com")
    check(r.returncode == 0 and sb.past(2) == ["x@example.com"],
          "re-login of the same account leaves no duplicate entry")

    r = sb.run("login", "2")
    check(sb.token(2) == "access-Y2" and sb.past(2) == ["x@example.com"],
          "an aborted login keeps the slot and the history as they were")
    check(sb.holders("refresh-Y2") == 1, "aborted login left no copy in the vault")


def test_history_json(sb: HistSandbox) -> None:
    section("history --json lists past accounts and never a token")
    r = sb.run("history", "2", "--json")
    check(r.returncode == 0, "history --json exits 0")
    check("access-" not in r.stdout and "refresh-" not in r.stdout, "no token in the output")
    h = json.loads(r.stdout)
    e = h["past"][0]
    check(h["current"]["email"] == "y@example.com", "current account reported")
    check(e["email"] == "x@example.com" and e["org"] == "Test", "email and org of the entry")
    check(bool(e["archived_at"]) and e["has_credential"] is True, "archive date and session flag")
    check(h["live"] is False and sb.history(1)["live"] is True, "live flag per slot")


def test_use_moves(sb: HistSandbox) -> None:
    section("use <n> <account> moves the credential, it never copies it")
    r = sb.run("use", "2", "x@example.com", "--json")
    out = json.loads(r.stdout)
    check(r.returncode == 0 and out["ok"] is True, "use exits 0 with ok")
    check(sb.token(2) == "access-X" and sb.identity(2) == "x@example.com",
          "slot2 holds x again, credential and identity")
    check(sb.past(2) == ["y@example.com"], "y moved to the history, x left it")
    check(sb.holders("refresh-X") == 1 and sb.holders("refresh-Y2") == 1,
          "each refresh token in exactly one store")
    check("refresh-" not in r.stdout, "use prints no token")

    r = sb.run("use", "2", "y@")
    check(r.returncode == 0 and sb.token(2) == "access-Y2" and sb.past(2) == ["x@example.com"],
          "and back again (A->B->A) without a login")

    r = sb.run("use", "2", "y@example.com", "--json")
    check(r.returncode != 0 and json.loads(r.stdout)["reason"] == "unknown_account",
          "the current account is not a past one")
    r = sb.run("use", "2", "nobody", "--json")
    check(r.returncode == 1 and json.loads(r.stdout)["reason"] == "unknown_account",
          "unknown account rejected")


def test_use_refuses_live(sb: HistSandbox) -> None:
    section("use <n> <account> refuses the live slot")
    r = sb.run("use", "1", "x@example.com", "--json")
    check(r.returncode == 1 and json.loads(r.stdout)["reason"] == "live", "reason is live")
    check(sb.token(1) == "access-A" and sb.token(None) == "access-A", "live slot untouched")

    r = sb.run("use", "2")
    check(r.returncode == 0 and sb.state("live") == "2", "`use <n>` alone still swaps")
    sb.run("swap", "1")


def test_failure_keeps_slot(sb: HistSandbox) -> None:
    section("a failed step leaves the slot on its account")
    slot = sb.home / ".claude-slots" / "2"
    before = (sb.token(2), sb.identity(2), sb.past(2))

    slot.chmod(stat.S_IRUSR | stat.S_IXUSR)  # the credential write fails
    try:
        r = sb.run("use", "2", "x@example.com", "--json")
    finally:
        slot.chmod(0o755)
    check(r.returncode == 1 and json.loads(r.stdout)["reason"] == "write_failed",
          "credential write failure reported")
    check((sb.token(2), sb.identity(2), sb.past(2)) == before, "slot and history unchanged")
    check(sb.holders("refresh-X") == 1, "x is still in the vault, once")

    ident = slot / ".claude.json"
    ident.chmod(stat.S_IRUSR)  # credential lands, then the identity write fails
    try:
        r = sb.run("use", "2", "x@example.com", "--json")
    finally:
        ident.chmod(0o644)
    check(r.returncode == 1 and json.loads(r.stdout)["reason"] == "write_failed",
          "identity write failure reported")
    check((sb.token(2), sb.identity(2), sb.past(2)) == before,
          "credential rolled back, slot and history unchanged")
    check(sb.holders("refresh-Y2") == 1 and sb.holders("refresh-X") == 1,
          "no token duplicated by the rollback")


def main() -> int:
    print(f"ccp history tests · {sys.platform} · python {sys.version.split()[0]}")
    sb = HistSandbox()
    print(f"sandbox: {sb.home}")
    try:
        setup(sb)
        test_login_archives(sb)
        test_history_json(sb)
        test_use_moves(sb)
        test_use_refuses_live(sb)
        test_failure_keeps_slot(sb)
    finally:
        sb.stop()
    print(f"\n{t.passed} passed, {t.failed} failed")
    return 1 if t.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
