#!/usr/bin/env python3
"""Claude Code statusline: which account this session is using, right now.

Two cases, and the distinction matters:

  - Plain process (no CLAUDE_CONFIG_DIR): it uses the live credential. This reads
    which slot is live from ~/.claude-profiles/live, so after a `ccp swap` every open
    session shows the new account without restarting anything.
  - Pinned process (`ccp pin N`): shows its fixed slot and marks it `pin`, because
    swaps do not touch it.

The account is read from the slot's parked .claude.json rather than the live one,
because live processes rewrite the live file and it would lag behind a swap.

Claude Code pipes a JSON object on stdin (model, workspace, ...) and renders stdout.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
SLOTS = HOME / ".claude-slots"
LIVE_STATE = HOME / ".claude-profiles" / "live"

R = "\033[0m"
DIM = "\033[2m"
SEP = f"{DIM} · {R}"
# One colour per slot: the point is recognising the account at a glance.
SLOT_COLOR = {1: "\033[36m", 2: "\033[35m", 3: "\033[33m", 4: "\033[32m",
              5: "\033[34m", 6: "\033[31m"}
FALLBACK = "\033[34m"
WARN = "\033[33m"


def pinned_slot() -> int | None:
    d = os.environ.get("CLAUDE_CONFIG_DIR")
    if not d:
        return None
    p = Path(d)
    m = re.match(r"^(\d+)$", p.name)
    return int(m.group(1)) if m and p.parent == SLOTS else None


def live() -> int | None:
    try:
        t = LIVE_STATE.read_text().strip()
    except OSError:
        return None
    return int(t) if t.isdigit() else None


def account(n: int) -> str:
    try:
        data = json.loads((SLOTS / str(n) / ".claude.json").read_text())
    except (OSError, ValueError):
        return "no login"
    return (data.get("oauthAccount") or {}).get("emailAddress") or "no login"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        data = {}

    pin = pinned_slot()
    n = pin if pin is not None else live()

    if n is None:
        head = f"{WARN} no slot{R}"
    else:
        colour = SLOT_COLOR.get(n, FALLBACK)
        tag = f"{DIM} pin{R}" if pin is not None else ""
        head = f"{colour} slot{n}{R}{tag}{SEP}{colour}{account(n)}{R}"

    parts = [head]

    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd")
    if cwd:
        parts.append(f"{DIM}{Path(cwd).name}{R}")

    model = (data.get("model") or {}).get("display_name")
    if model:
        parts.append(f"{DIM}{model}{R}")

    print(SEP.join(parts))


if __name__ == "__main__":
    main()
