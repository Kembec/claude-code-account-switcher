#!/bin/sh
# Install ccp for the user running this script. Idempotent - safe to re-run.
# macOS and Linux; on Windows use install.ps1.
#
#   sh install.sh                 # install into ~/.local/bin (symlinks to this repo)
#   sh install.sh --copy          # copy the files instead of symlinking
#   sh install.sh --shared        # macOS: /Users/Shared/ccp, for multi-user machines
#   sh install.sh --shared DIR    # ...or into DIR (required on Linux)
#
# On a machine with several user accounts, run it once with --shared from any account,
# then run it again (no flags needed) from each other account: credentials are stored
# per user - macOS gives every user their own login keychain, and on Linux the
# credential file lives under each user's home. So every user keeps their own slots and
# their own logins, and credentials never cross accounts.

set -e

REPO=$(cd "$(dirname "$0")" && pwd)
MARK='# >>> ccp'
MODE=link
BINDIR="$HOME/.local/bin"
OS=$(uname -s)

# sudo splits identity: HOME stays yours but USER becomes root, so ccp would end up
# using root's credential store, and anything created lands root-owned in your home.
if [ -n "${SUDO_USER:-}" ]; then
  echo "!! do not run this with sudo." >&2
  echo "   sudo sets USER=root while HOME stays \$HOME, so ccp would use root's" >&2
  echo "   credential store instead of yours, and new files would be root-owned." >&2
  echo "   Run it as yourself: sh $0 $*" >&2
  exit 1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --copy)   MODE=copy ;;
    --shared) MODE=copy
              if [ -n "$2" ] && [ "${2#-}" = "$2" ]; then BINDIR="$2"; shift
              elif [ "$OS" = Darwin ]; then BINDIR="/Users/Shared/ccp"
              else echo "!! --shared needs a directory on $OS, e.g. --shared /opt/ccp" >&2
                   exit 1; fi ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

case "$OS" in
  Darwin) STORE="login keychain" ;;
  Linux)  STORE="~/.claude/.credentials.json" ;;
  *) echo "!! unsupported OS: $OS (Windows: use install.ps1)" >&2; exit 1 ;;
esac

command -v python3 >/dev/null 2>&1 || {
  echo "!! python3 is not on PATH. Install it and re-run." >&2
  exit 1
}

command -v claude >/dev/null 2>&1 || {
  echo "!! 'claude' is not on this user's PATH." >&2
  echo "   Install Claude Code first: https://docs.claude.com/en/docs/claude-code" >&2
  exit 1
}

echo "==> installing ccp for $(id -un) on $OS"
echo "    source:      $REPO"
echo "    bindir:      $BINDIR"
echo "    credentials: $STORE"

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

BLOCK_FILE=$(mktemp)
trap 'rm -f "$BLOCK_FILE"' EXIT
cat > "$BLOCK_FILE" <<BLOCK
# >>> ccp - Claude Code account slots >>>
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

# An existing block is REPLACED, not left alone. Leaving a stale block behind is how a
# moved or renamed install directory silently breaks a user: their PATH and statusline
# keep pointing at a directory that no longer exists.
python3 - "$RC" "$BLOCK_FILE" <<'PY'
import pathlib, sys
rc, want = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]).read_text().rstrip("\n")
OPEN, CLOSE = "# >>> ccp", "# <<< ccp <<<"
lines, kept, block, skip = rc.read_text().splitlines(), [], [], False
for ln in lines:
    if not skip and ln.startswith(OPEN):
        skip = True
    if skip:
        block.append(ln)
        if ln.rstrip() == CLOSE:
            skip = False
        continue
    kept.append(ln)
existing = "\n".join(block).rstrip("\n")
if existing == want:
    print(f"    {rc}: ccp block already current")
    raise SystemExit(0)
body = "\n".join(kept).rstrip("\n")
rc.write_text((body + "\n" if body else "") + "\n" + want + "\n")
print(f"    {rc}: ccp block " + ("updated" if existing else "added"))
PY

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
else:
    replaced = bool(d.get("statusLine"))
    d["statusLine"] = want
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print("    settings.json: statusLine "
          + ("replaced (previous one was overwritten)" if replaced else "configured"))
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
