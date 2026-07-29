#!/bin/sh
# Remove ccp for the user running this script. macOS and Linux.
#
#   sh uninstall.sh            # remove the command, shell block and statusline
#   sh uninstall.sh --purge    # ...and delete slot dirs + parked credentials
#
# Neither mode ever touches the LIVE credential, so you stay signed in to whichever
# account is live right now. --purge only deletes the parked copies, which means the
# accounts in the other slots will need a normal /login again.

set -e

MARK_OPEN='# >>> ccp'
MARK_CLOSE='# <<< ccp <<<'
PURGE=no
[ "$1" = "--purge" ] && PURGE=yes

case "${SHELL##*/}" in
  bash) RC="$HOME/.bashrc" ;;
  *)    RC="$HOME/.zshrc" ;;
esac

CCP=$(command -v ccp 2>/dev/null || true)

echo "==> removing ccp for $(id -un)"

if [ -n "$CCP" ]; then
  LIVE=$("$CCP" live 2>/dev/null || true)
  [ -n "$LIVE" ] && echo "    live account stays signed in: $LIVE"
fi

# --- optional purge (before the command goes away, so ccp can do it safely) -- #
if [ "$PURGE" = yes ]; then
  if [ -n "$CCP" ]; then
    # `ccp rm --purge` refuses the live slot, which is exactly the guarantee we want.
    for f in "$HOME"/.claude-profiles/slot*.dir; do
      [ -e "$f" ] || continue
      n=$(basename "$f" .dir | sed 's/^slot//')
      "$CCP" rm "$n" --purge >/dev/null 2>&1 && echo "    slot$n purged" || true
    done
  else
    echo "    ! ccp not on PATH; deleting slot dirs without clearing keychain items"
  fi
  rm -rf "$HOME/.claude-slots" "$HOME/.claude-profiles"
  echo "    removed ~/.claude-slots and ~/.claude-profiles"
  echo "    NOTE: the live credential was left intact - you are still signed in."
fi

# --- shell block ------------------------------------------------------------ #
if [ -f "$RC" ] && grep -qF "$MARK_OPEN" "$RC"; then
  python3 - "$RC" "$MARK_OPEN" "$MARK_CLOSE" <<'PY'
import sys, pathlib
rc, open_m, close_m = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
out, skip = [], False
for ln in rc.read_text().splitlines(True):
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
if "ccp-statusline" in str((d.get("statusLine") or {}).get("command", "")):
    d.pop("statusLine", None)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print("    settings.json: statusLine removed")
else:
    print("    settings.json: statusLine is not ccp's, left alone")
PY

# --- the command itself ----------------------------------------------------- #
for d in "$HOME/.local/bin" /Users/Shared/ccp /Users/Shared/claude-ccp /opt/ccp; do
  for f in ccp ccp.cmd ccp-statusline.py statusline-slot.py; do
    { [ -e "$d/$f" ] || [ -L "$d/$f" ]; } || continue
    rm -f "$d/$f"
    echo "    removed $d/$f"
  done
done

cat <<EOF

==> done. Open a new terminal so the shell function goes away.
    ~/.claude was never modified beyond the statusLine setting.

EOF
