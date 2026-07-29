#!/bin/sh
# Install ccp for the user running this script. Idempotent — safe to re-run.
#
#   sh install.sh                 # install into ~/.local/bin (symlinks to this repo)
#   sh install.sh --copy          # copy the files instead of symlinking
#   sh install.sh --shared        # install into /Users/Shared/ccp, for multi-user Macs
#   sh install.sh --shared DIR    # ...or into DIR
#
# On a Mac with several user accounts, run it once with --shared from any account,
# then run it again (no flags needed) from each other account: macOS gives every user
# their own login keychain, so every user keeps their own slots and their own logins.
# Credentials never cross user accounts — that is an OS boundary, not a ccp choice.

set -e

REPO=$(cd "$(dirname "$0")" && pwd)
MARK='# >>> ccp'
MODE=link
BINDIR="$HOME/.local/bin"

while [ $# -gt 0 ]; do
  case "$1" in
    --copy)   MODE=copy ;;
    --shared) MODE=copy
              if [ -n "$2" ] && [ "${2#-}" = "$2" ]; then BINDIR="$2"; shift
              else BINDIR="/Users/Shared/ccp"; fi ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

[ "$(uname -s)" = "Darwin" ] || {
  echo "!! macOS only: ccp keeps credentials in the login keychain." >&2
  exit 1
}

command -v claude >/dev/null 2>&1 || {
  echo "!! 'claude' is not on this user's PATH." >&2
  echo "   Install Claude Code first: https://docs.claude.com/en/docs/claude-code" >&2
  exit 1
}

echo "==> installing ccp for $(id -un)"
echo "    source: $REPO"
echo "    bindir: $BINDIR"

mkdir -p "$BINDIR"
for f in ccp ccp-statusline.py; do
  rm -f "$BINDIR/$f"
  if [ "$MODE" = copy ]; then cp "$REPO/bin/$f" "$BINDIR/$f"
  else ln -s "$REPO/bin/$f" "$BINDIR/$f"; fi
  chmod 755 "$BINDIR/$f" 2>/dev/null || true
done
echo "    placed ccp and ccp-statusline.py"

# --- shell integration ------------------------------------------------------ #
# `claude` must always run in the live config dir, because that is what makes one
# swap reach every open session. CCP=<n> pins a single invocation to a slot.
case "${SHELL##*/}" in
  bash) RC="$HOME/.bashrc" ;;
  *)    RC="$HOME/.zshrc" ;;
esac
touch "$RC"

if grep -qF "$MARK" "$RC"; then
  echo "    $RC: ccp block already present, left untouched"
else
  cat >> "$RC" <<BLOCK

# >>> ccp — Claude Code account slots >>>
case ":\$PATH:" in *":$BINDIR:"*) ;; *) export PATH="$BINDIR:\$PATH" ;; esac
# Plain \`claude\` always runs on the live credential (~/.claude); that is what lets
# one \`ccp swap\` change the account for every open session. CCP=2 pins one run.
claude() {
  _ccp_n="\${CCP:-}"
  _ccp_d="\$HOME/.claude-slots/\${_ccp_n#slot}"
  if [ -n "\$_ccp_n" ] && [ -d "\$_ccp_d" ]; then
    CLAUDE_CONFIG_DIR="\$_ccp_d" command claude "\$@"
  else
    env -u CLAUDE_CONFIG_DIR claude "\$@"
  fi
}
# <<< ccp <<<
BLOCK
  echo "    $RC: ccp block added"
fi

# --- statusline ------------------------------------------------------------- #
python3 - "$BINDIR" <<'PY'
import json, pathlib, sys
bindir = sys.argv[1]
p = pathlib.Path.home() / ".claude" / "settings.json"
p.parent.mkdir(parents=True, exist_ok=True)
try:
    d = json.loads(p.read_text())
except (OSError, ValueError):
    d = {}
want = {"type": "command", "command": f"{bindir}/ccp-statusline.py", "padding": 0}
if d.get("statusLine") == want:
    print("    settings.json: statusLine already configured")
elif "statusLine" in d and d["statusLine"]:
    d["statusLine"] = want
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print("    settings.json: statusLine replaced (previous one was overwritten)")
else:
    d["statusLine"] = want
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print("    settings.json: statusLine configured")
PY

# --- park the current login ------------------------------------------------- #
echo
"$BINDIR/ccp" init

cat <<EOF

==> done. Open a new terminal (or: . $RC), then:

    ccp add          create the next slot
    ccp login <n>    /login another account into that slot
    ccp swap <n>     switch the account for EVERY open session
    ccp doctor       self-check

EOF
