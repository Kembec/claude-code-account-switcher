#!/bin/sh
# Remove ccp for the user running this script.
#
#   sh uninstall.sh            # remove the command, shell block and statusline
#   sh uninstall.sh --purge    # ...and delete slot dirs + parked credentials
#
# Neither mode ever touches the LIVE keychain entry, so you stay logged into
# whichever account is live right now. --purge only deletes the parked copies, which
# means the accounts in the other slots will need a normal /login again.

set -e

MARK_OPEN='# >>> ccp'
MARK_CLOSE='# <<< ccp <<<'
PURGE=no
[ "$1" = "--purge" ] && PURGE=yes

case "${SHELL##*/}" in
  bash) RC="$HOME/.bashrc" ;;
  *)    RC="$HOME/.zshrc" ;;
esac

echo "==> removing ccp for $(id -un)"

# Which account will you be left on?
if [ -r "$HOME/.claude-profiles/live" ]; then
  LIVE=$(cat "$HOME/.claude-profiles/live")
  EMAIL=$(python3 -c "
import json,pathlib,sys
p=pathlib.Path.home()/'.claude-slots'/sys.argv[1]/'.claude.json'
try: print((json.loads(p.read_text()).get('oauthAccount') or {}).get('emailAddress') or '?')
except Exception: print('?')
" "$LIVE" 2>/dev/null || echo '?')
  echo "    live account stays signed in: slot$LIVE ($EMAIL)"
fi

# --- shell block ------------------------------------------------------------ #
if [ -f "$RC" ] && grep -qF "$MARK_OPEN" "$RC"; then
  python3 - "$RC" "$MARK_OPEN" "$MARK_CLOSE" <<'PY'
import sys, pathlib
rc, open_m, close_m = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines, out, skip = rc.read_text().splitlines(True), [], False
for ln in lines:
    if not skip and ln.startswith(open_m):
        skip = True
        continue
    if skip:
        if ln.rstrip() == close_m:
            skip = False
        continue
    out.append(ln)
rc.write_text("".join(out).rstrip("\n") + "\n")
print(f"    {rc}: ccp block removed")
PY
else
  echo "    $RC: no ccp block found"
fi

# --- statusline ------------------------------------------------------------- #
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".claude" / "settings.json"
try:
    d = json.loads(p.read_text())
except (OSError, ValueError):
    raise SystemExit(0)
sl = d.get("statusLine") or {}
if "ccp-statusline" in str(sl.get("command", "")):
    d.pop("statusLine", None)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print("    settings.json: statusLine removed")
else:
    print("    settings.json: statusLine is not ccp's, left alone")
PY

# --- the command itself ----------------------------------------------------- #
for d in "$HOME/.local/bin" /Users/Shared/ccp /Users/Shared/claude-ccp; do
  for f in ccp ccp-statusline.py statusline-slot.py; do
    [ -e "$d/$f" ] || [ -L "$d/$f" ] || continue
    rm -f "$d/$f"
    echo "    removed $d/$f"
  done
done

# --- optional purge --------------------------------------------------------- #
if [ "$PURGE" = yes ]; then
  python3 - <<'PY'
import json, os, re, subprocess, unicodedata
from hashlib import sha256
from pathlib import Path
home, acct = Path.home(), os.environ.get("USER", "claude-code-user")
reg = home / ".claude-profiles"
for f in sorted(reg.glob("slot*.dir")):
    m = re.match(r"^slot(\d+)$", f.stem)
    if not m:
        continue
    d = home / ".claude-slots" / m.group(1)
    svc = "Claude Code-credentials-" + sha256(
        unicodedata.normalize("NFC", str(d)).encode()).hexdigest()[:8]
    subprocess.run(["security", "delete-generic-password", "-a", acct, "-s", svc],
                   capture_output=True)
    print(f"    slot{m.group(1)}: parked credential deleted")
PY
  rm -rf "$HOME/.claude-slots" "$HOME/.claude-profiles"
  echo "    removed ~/.claude-slots and ~/.claude-profiles"
  echo "    NOTE: the live keychain entry was left intact — you are still signed in."
fi

cat <<EOF

==> done. Open a new terminal so the shell function goes away.
    ~/.claude was never modified beyond the statusLine setting.

EOF
