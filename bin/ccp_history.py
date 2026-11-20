"""ccp history — the accounts a slot held before, and putting one of them back.

A slot is a stable position whose account can change over time (a re-login, a seat
reassigned by the provider). Without this module `ccp login N` overwrites the slot's
credential and the previous account is gone. Here the outgoing credential is MOVED
into a per-slot vault, so it can come back later with `ccp use <n> <account>`.

Layout: ~/.claude-profiles/history/slot<N>/<key>/ is a config dir per past account:
    .claude.json      identity keys (oauthAccount, userID, hasAvailableSubscription)
    .ccp-entry.json   email, org, archived_at, from_slot
    credential        in the store ccp derives from that dir (keychain item or file)

INVARIANTS
- Move, never copy: after any command a refresh token lives in exactly one store
  (the slot's or one vault entry). Refresh tokens rotate; two holders diverge.
- A credential is never printed: history shows identity and validity only.
- restore refuses the live slot (every open session reads it), like logout and pin.
- restore (`ccp use <n> <account>`) leaves the slot either on the target account or on its previous one.
  Exit 2 means the rollback itself failed; the previous credential is then still
  in the vault, never lost.

The module is loaded by bin/ccp, which passes itself as `core`. `login` and `use` live
here because both change which account a slot holds.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

META = ".ccp-entry.json"
LOCK_STALE_S = 300


class Refused(Exception):
    """A refusal that left the slot untouched (exit 1), or a failed rollback (exit 2)."""

    def __init__(self, reason: str, detail: str, code: int = 1) -> None:
        super().__init__(detail)
        self.reason, self.detail, self.code = reason, detail, code


class History:
    def __init__(self, core) -> None:
        self.c = core
        self.root = core.REG / "history"

    # -- layout ------------------------------------------------------------- #

    def slot_root(self, n: int) -> Path:
        return self.root / f"slot{n}"

    @staticmethod
    def key_of(email: str, org: str | None) -> str:
        return sha256(f"{email.lower()}|{org or ''}".encode()).hexdigest()[:12]

    def identity(self, config_dir: Path) -> tuple[str, str | None, dict]:
        """(email, org, identity keys) of a config dir; email is '-' when unknown."""
        d = self.c.read_json(config_dir / ".claude.json")
        oa = d.get("oauthAccount") or {}
        keys = {k: d[k] for k in self.c.ID_KEYS if k in d}
        return oa.get("emailAddress") or "-", oa.get("organizationName"), keys

    def entries(self, n: int) -> list[dict]:
        root = self.slot_root(n)
        if not root.is_dir():
            return []
        out = []
        for d in root.iterdir():
            meta = self.c.read_json(d / META) if d.is_dir() else {}
            if not meta:
                continue
            blob = self.c.store_for(d).read()
            out.append({"key": d.name, "email": meta.get("email", "-"),
                        "org": meta.get("org"), "archived_at": meta.get("archived_at"),
                        "has_credential": self.c.valid_blob(blob), "dir": str(d)})
        return sorted(out, key=lambda e: e["archived_at"] or "", reverse=True)

    # -- primitives ----------------------------------------------------------- #

    def _put(self, store, blob: str) -> bool:
        """Write and read back; a store that does not return the same bytes failed."""
        return bool(store.write(blob)) and store.read() == blob

    def archive(self, n: int) -> str | None:
        """Move-in half of a move: the slot's credential goes to its vault entry.

        Returns the entry key, or None when the slot holds no valid credential.
        The caller removes the slot's copy (or overwrites it) to finish the move.
        """
        blob = self.c.slot_store(n).read()
        if not self.c.valid_blob(blob):
            return None
        email, org, keys = self.identity(self.c.slot_dir(n))
        key = self.key_of(email, org)
        entry = self.slot_root(n) / key
        entry.mkdir(parents=True, exist_ok=True)
        os.chmod(entry, 0o700)
        if not self._put(self.c.store_for(entry), blob):
            self.drop(n, key)
            raise Refused("write_failed", f"could not archive slot{n}'s credential")
        (entry / ".claude.json").write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
        meta = {"email": email, "org": org, "from_slot": n,
                "archived_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        (entry / META).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return key

    def drop(self, n: int, key: str) -> None:
        entry = self.slot_root(n) / key
        self.c.store_for(entry).delete()
        shutil.rmtree(entry, ignore_errors=True)

    def find(self, n: int, token: str) -> dict:
        es = self.entries(n)
        hits = [e for e in es if e["key"] == token] or \
               [e for e in es if e["email"].lower().startswith(token.lower())]
        if len(hits) == 1:
            return hits[0]
        if hits:
            raise Refused("unknown_account", f"'{token}' matches several past accounts of slot{n}")
        raise Refused("unknown_account", f"'{token}' is not a past account of slot{n}")

    # -- lock ----------------------------------------------------------------- #

    def lock(self, n: int) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.root / f"slot{n}.lock"
        for _ in range(2):
            try:
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, f"{os.getpid()} {int(time.time())}\n".encode())
                os.close(fd)
                return p
            except FileExistsError:
                try:
                    age = time.time() - p.stat().st_mtime
                except OSError:
                    continue
                if age < LOCK_STALE_S:
                    raise Refused("busy", f"another change of slot{n} is in progress")
                p.unlink(missing_ok=True)
        raise Refused("busy", f"another change of slot{n} is in progress")

    # -- login hooks ---------------------------------------------------------- #

    def before_login(self, n: int):
        """Archive the account a login is about to overwrite."""
        key = self.archive(n)
        return None if key is None else (key, self.identity(self.c.slot_dir(n))[:2])

    def after_login(self, n: int, archived) -> None:
        """Same account logged in again (or nothing changed): the archive is a stale
        duplicate of what the slot now holds, so it goes. A different account, or a
        login that left no credential, keeps it: that is the history."""
        if archived is None:
            return
        key, ident = archived
        if not self.c.valid_blob(self.c.slot_store(n).read()):
            return
        if self.identity(self.c.slot_dir(n))[:2] == ident:
            self.drop(n, key)

    # -- restore -------------------------------------------------------------- #

    def restore(self, n: int, token: str) -> dict:
        if n == self.c.live_slot():
            raise Refused("live", f"slot{n} is live: every open session uses it. "
                                  f"Swap to another slot first (`ccp swap <m>`).")
        lock = self.lock(n)
        try:
            return self._restore(n, token)
        finally:
            lock.unlink(missing_ok=True)

    def _restore(self, n: int, token: str) -> dict:
        target = self.find(n, token)
        tdir = Path(target["dir"])
        tblob = self.c.store_for(tdir).read()
        if not self.c.valid_blob(tblob):
            raise Refused("no_credential", f"{target['email']} has no saved session in "
                                           f"slot{n}'s history: it needs a login")
        sdir, sstore = self.c.slot_dir(n), self.c.slot_store(n)
        cur_blob = sstore.read()
        cur_email, cur_org, cur_keys = self.identity(sdir)
        cur_valid = self.c.valid_blob(cur_blob)
        if cur_valid and self.key_of(cur_email, cur_org) == target["key"]:
            raise Refused("same_account", f"slot{n} already holds {cur_email}")

        new_key = self.archive(n) if cur_valid else None
        tkeys = self.c.read_json(tdir / ".claude.json")
        try:
            if not self._put(sstore, tblob):
                raise OSError("slot store write failed")
            self._set_identity(sdir / ".claude.json", tkeys)
        except OSError as e:
            self._rollback(n, cur_blob if cur_valid else None, cur_keys, new_key, e)
        self.drop(n, target["key"])
        return {"ok": True, "slot": n,
                "from": {"email": cur_email, "org": cur_org} if cur_valid else None,
                "to": {"email": target["email"], "org": target["org"]}}

    def _set_identity(self, path: Path, keys: dict) -> None:
        """Exactly these identity keys: one the other account had must not linger."""
        d = self.c.read_json(path)
        for k in self.c.ID_KEYS:
            if k in keys:
                d[k] = keys[k]
            else:
                d.pop(k, None)
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if any(self.c.read_json(path).get(k) != keys.get(k) for k in self.c.ID_KEYS):
            raise OSError(f"{path.name} did not read back")

    def _rollback(self, n: int, blob, keys: dict, new_key, err: Exception) -> None:
        sstore, sjson = self.c.slot_store(n), self.c.slot_dir(n) / ".claude.json"
        now = sstore.read()
        if blob:
            back = now == blob or self._put(sstore, blob)
        else:
            back = now is None or (sstore.delete() and sstore.read() is None)
        cur = self.c.read_json(sjson)
        if any(cur.get(k) != keys.get(k) for k in self.c.ID_KEYS):
            try:
                self._set_identity(sjson, keys)
            except OSError:
                back = False
        if not back:
            raise Refused("rollback_failed", f"slot{n} could not be put back after: {err}. "
                          f"Its previous credential is kept in the history", code=2)
        if new_key:
            self.drop(n, new_key)
        raise Refused("write_failed", f"slot{n} unchanged: {err}")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _emit(as_json: bool, payload: dict, text: str) -> None:
    print(json.dumps(payload, ensure_ascii=False) if as_json else text)


def cmd_history(core, args: list[str]) -> None:
    pos = [a for a in args if not a.startswith("-")]
    if not pos:
        core.die("usage: ccp history <n> [--json]")
    n, h = core.resolve(pos[0]), History(core)
    email, org, _ = h.identity(core.slot_dir(n))
    has = core.valid_blob(core.slot_store(n).read())
    current = {"email": email, "org": org, "has_credential": has,
               "dir": str(core.slot_dir(n))} if has or email != "-" else None
    past = h.entries(n)
    payload = {"slot": n, "live": n == core.live_slot(), "current": current, "past": past}
    lines = [f"slot{n} now: {email}" + (f" ({org})" if org else "")]
    lines += [f"  {e['archived_at']}  {e['email']}" + (f" ({e['org']})" if e["org"] else "")
              + ("" if e["has_credential"] else "  [no saved session]") for e in past]
    _emit("--json" in args, payload, "\n".join(lines if past else lines + ["  (no past accounts)"]))


def cmd_restore(core, args: list[str]) -> None:
    pos = [a for a in args if not a.startswith("-")]
    as_json = "--json" in args
    if len(pos) < 2:
        core.die("usage: ccp use <n> <account> [--json]")
    n = core.resolve(pos[0])
    try:
        out = History(core).restore(n, pos[1])
    except Refused as r:
        _emit(as_json, {"ok": False, "slot": n, "reason": r.reason, "detail": r.detail},
              f"ccp: {r.detail}")
        raise SystemExit(r.code)
    _emit(as_json, out, f"OK slot{n} now holds {out['to']['email']}"
          + (f"; {out['from']['email']} moved to its history" if out["from"] else ""))


def cmd_use(core, args: list[str]) -> None:
    """`use <n>` is swap; `use <n> <account>` moves a past account back into slot n."""
    if len([a for a in args if not a.startswith("-")]) >= 2:
        cmd_restore(core, args)
    else:
        core.cmd_swap(args)


def cmd_login(core, args: list[str]) -> None:
    """A login replaces the slot's account, so the outgoing one is archived first."""
    C = core.C
    if not args:
        core.die("usage: ccp login <n>")
    n = core.resolve(args[0])
    core.sync(n, quiet=True)
    lv = core.live_slot()
    if n == lv:
        # the live store holds the freshest refresh token; archive that one
        core.copy_cred(core.live_store(), core.slot_store(n), f"parking slot{n}")
        core.park_identity(n)
    hist = History(core)
    try:
        archived = hist.before_login(n)  # the account this login may overwrite
    except Refused as r:
        core.die(f"{r.detail} - login not started")
    print(f"{C['d']}opening claude in slot{n} -> run /login and pick the account{C['0']}")
    core.run_claude(["/login"], core.slot_env(n))
    hist.after_login(n, archived)
    if not core.valid_blob(core.slot_store(n).read()):
        core.die(f"slot{n} still has no credential - the login did not complete")
    print(f"{C['g']}OK{C['0']} slot{n} · {core.account_of(n)}")
    if n == lv:
        # the slot we just logged into was already live: refresh the live store
        core.copy_cred(core.slot_store(n), core.live_store(), f"refreshing live from slot{n}")
        core.load_identity(n)
        print(f"{C['d']}  slot{n} was live -> live credential updated{C['0']}")
    else:
        print(f"  to use it in your open sessions: {C['c']}ccp swap {n}{C['0']}")
