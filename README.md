# ccp — Claude Code account switcher

Switch which of **your own** Claude accounts every open Claude Code session is using,
from another terminal, without closing a single session and without logging out.

```console
$ ccp ls
  SLOT    ACCOUNT                              CREDENTIAL  STATE
▸ slot1   me@work.example                      live        LIVE — every session uses this
  slot2   me@personal.example                  parked      parked

$ ccp swap 2
  ↓ slot1 parked (me@work.example)
✓ live is now slot2 · me@personal.example
  access token deliberately expired → open sessions refresh into this account on
  their next token check. Close nothing.
```

Your open sessions keep their full context. Nothing to exit, nothing to re-open, no
browser round-trip. If you have six terminals going, all six follow the swap.

> macOS, Linux and Windows. Not affiliated with, endorsed by, or sponsored by
> Anthropic. Intended for one person switching between accounts they personally own —
> see [Intended use](#intended-use).

---

## Why

If you have a work account and a personal account, Claude Code gives you one
credential slot. The usual workaround is `/logout`, `/login`, pick the other account,
and repeat every time you switch — plus a browser round-trip each way. Sessions you
had open keep running on the old account until their token happens to expire, so you
can't tell which account a given window is billing.

`ccp` parks each account's credential in its own store and swaps the one store that
live sessions actually read. One command, every session, and a statusline
that tells you which account you're on.

## Install

Requires Python 3.9+ (system Python is fine) and Claude Code on your `PATH`.

**macOS / Linux**

```console
git clone https://github.com/Kembec/claude-code-account-switcher.git
cd claude-code-account-switcher
sh install.sh
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/Kembec/claude-code-account-switcher.git
cd claude-code-account-switcher
pwsh -ExecutionPolicy Bypass -File .\install.ps1
```

Either one places `ccp` on your `PATH`, adds a small block to your shell profile,
configures the statusline, and parks the account you're already logged in with as
`slot1`. Open a new terminal afterwards.

<details>
<summary>Machines with several user accounts</summary>

```console
sh install.sh --shared              # macOS: /Users/Shared/ccp
sh install.sh --shared /opt/ccp     # Linux: pass the directory
```

Then run `sh install.sh` once from each other account. Credentials are stored per
user — macOS gives every user their own login keychain, and on Linux and Windows the
credential file lives under each user's home — so **every user keeps their own slots
and their own logins**. Credentials never cross user accounts; that's an OS boundary,
not a `ccp` choice.

One caveat learned the hard way: the installer writes the **absolute** install path into
each user's shell profile and `settings.json`. If you later move or rename a shared
install directory, every user who pointed at it loses both the command and the
statusline until they re-run `install.sh`. Re-running it replaces a stale block rather
than leaving it in place, so the fix is one command per user — but nothing warns them
first.

</details>

<details>
<summary>Credential backends</summary>

| Platform | Where the credential lives |
| --- | --- |
| macOS | login keychain, via `/usr/bin/security` |
| Linux, Windows | `<config dir>/.credentials.json`, mode 600 |

`ccp` picks the right one automatically. `CCP_BACKEND=keychain\|file` overrides it,
which is mainly how the test suite exercises the file backend on a Mac.

</details>

## Use

```console
ccp add              # create the next slot
ccp login 2          # /login another account into slot2 — does not touch live
ccp swap 2           # switch the account for EVERY open session
```

| Command | What it does |
| --- | --- |
| `ccp ls` | Slots, the account in each, which one is live |
| `ccp swap <n>` | Park the live credential, load slot `n` as live |
| `ccp add [n]` | Create a slot (no `n`: first free number) |
| `ccp login <n>` | Run `/login` in slot `n` and park the result |
| `ccp logout <n>` | Delete slot `n`'s parked credential |
| `ccp pin <n> …` | Run a `claude` nailed to slot `n`, immune to swaps |
| `ccp live` | Which slot is live right now |
| `ccp sync [n]` | Rebuild the shared links (idempotent) |
| `ccp rm <n>` | Unregister a slot (`--purge` also deletes dir + credential) |
| `ccp doctor` | Self-check the environment and state |

`<n>` accepts `2`, `slot2`, or the account's email — `ccp swap me@work.example` works.

### Two ways to run

- **Plain `claude`** uses the live credential. This is what makes one swap reach every
  session, so it's the default and you shouldn't override it.
- **`ccp pin 2`** nails one process to slot 2. Swaps don't touch it. Use this when you
  want two accounts running side by side. The shell function honours the same thing via
  an environment variable: `CCP=2 claude` on macOS and Linux, `$env:CCP=2; claude` in
  PowerShell.

`ccp pin`, `ccp logout` and `ccp rm` refuse to operate on the live slot, because two
families of processes refreshing the same credential from different stores is how
you get a diverged refresh token.

### Statusline

The installer sets a statusline so you can always see which account a session is on,
with one colour per slot:

```
 slot1 · me@work.example · my-project · Opus 5
 slot2 · me@personal.example · my-project · Opus 5
 slot3 pin · me@other.example · scratch · Sonnet 5
```

It reads the live slot from state, so **after a swap every open session shows the new
account**. Already-running sessions won't display it until you restart them once —
`settings.json` is read at startup.

## How it works

Claude Code scopes its credential to the config directory. On macOS the keychain item
is `Claude Code-credentials` when `CLAUDE_CONFIG_DIR` is unset and gets a suffix
derived from that directory's path when it is set; on Linux and Windows the credential
is simply a file inside the config directory. Either way, pointing
`CLAUDE_CONFIG_DIR` at a per-slot directory gives each account a private credential
that can't clobber the others — that's how `ccp login` parks an account without
disturbing your live session.

Every plain `claude` runs in `~/.claude` and reads the one shared credential. `ccp
swap` copies the live credential back into the outgoing slot's store, then copies the
incoming slot's store into the live one. Claude Code watches for credential changes it
didn't make — that's how concurrent instances stay consistent when one of them
refreshes a token — so live sessions pick the new credential up on their own.

Access tokens last about eight hours and a running session holds one in memory, so a
swap would otherwise take hours to land. `ccp` backdates `expiresAt` on the credential
it installs: the next token check decides a refresh is due, refreshes with the
incoming account's refresh token, and adopts that identity. Nothing is revoked.

Slots share your whole Claude Code setup — `commands/`, `agents/`, `skills/`,
`plugins/`, `settings.json`, and `projects/` — through links, so there's one
toolbox and one transcript history regardless of which account is live.

Full detail, including the reasoning behind the parking order, is in
[docs/how-it-works.md](docs/how-it-works.md). Threat model and exactly what gets read
or written is in [docs/security.md](docs/security.md).

## Intended use

**This is for one person switching between accounts they personally own.** A work
account and a personal account, on their own machine.

It is not a way to pool quota across accounts, share one account between people, or
work around usage limits. It doesn't touch limits at all: each account's limits apply
normally while it's live, exactly as if you had logged in the ordinary way. Whether
your accounts permit what you're doing is between you and their terms of service —
check [Anthropic's terms](https://www.anthropic.com/legal/consumer-terms) and, if the
account belongs to an employer, your own organisation's policy.

`ccp` never transmits credentials anywhere. Everything stays in the store Claude Code
already uses on your machine — your login keychain on macOS, a mode-600 file elsewhere.

## What's verified, and what isn't

Being straight about this matters more than sounding confident, because the tool moves
credentials around.

**Verified on real hardware:** the macOS keychain path, end to end. Live swaps in both
directions against two real accounts, confirmed by watching the credential state
rather than by trusting output — after a swap the live access token was one neither
slot had held, produced by a refresh with the incoming account's refresh token, and
open sessions carried on without a restart.

**Verified by test suite:** all the logic — parking order, rotation survival, the
backdating, the guards, slot resolution, refusal to write a malformed credential —
plus the file backend that Linux and Windows use. `tests/test_ccp.py` runs the real CLI
against a throwaway `HOME` and passes on macOS too, so the non-macOS credential store
is exercised on every run.

```console
python3 tests/test_ccp.py      # 53 checks, no network, touches nothing real
```

**Verified under PowerShell:** `install.ps1` parses clean on pwsh 7.6.4, the block it
injects into your profile parses on its own, every cmdlet and parameter it uses exists,
and the `claude` function it defines restores a pre-existing `CLAUDE_CONFIG_DIR` instead
of leaking one.

**Not verified:** Linux and Windows on actual Linux and Windows machines. The credential
location and format there come from the client's own behaviour, and the logic and the
installer are covered by the checks above, but nobody has yet run the whole thing on
those operating systems. If you do, an issue either way is genuinely useful.

## Limitations

- **It rides on undocumented internals.** The credential naming scheme and layout were
  determined by observing Claude Code's behaviour, verified against **2.1.220**. A
  future release could change either. `ccp doctor` tells you whether the assumptions
  still hold; if they don't, uninstalling leaves you with a normal, working login.
- **Swaps aren't instantaneous.** They land on each session's next token check, not the
  same millisecond. Seconds to minutes in practice.
- **One live account at a time** across plain sessions. If you want two accounts at
  once, use `ccp pin`.
- **Windows symlinks need Developer Mode.** Without it, `ccp` shares slot content using
  directory junctions and file hardlinks instead, which need no privilege. `ccp sync`
  says so if anything couldn't be linked; the slot still works, it just won't share
  those items.
- Per-slot `.claude.json` keeps its own account identity, but a session that was
  already running may show the previous account in `/status` until it refetches its
  profile. The statusline is the reliable indicator.
- Don't judge a credential by running `claude -p` from inside another Claude Code
  session — a nested client can inherit an OAuth token through a file descriptor and
  authenticate even when the credential you meant to test is invalid. That trap cost
  me a round of bad conclusions.

## Troubleshooting

```console
ccp doctor
```

**"no live credential found"** — run `claude`, `/login` normally, then `ccp init`.

**A swap didn't seem to land.** Send any message in the open session to make it talk
to the API, then check `ccp live`. If it still hasn't moved, `ccp doctor` will show
whether the live store actually holds the new token.

**A slot lost its login.** `ccp login <n>` again. Parked credentials only go stale if
something outside `ccp` overwrote a credential store.

**Removing it.** `sh uninstall.sh` on macOS and Linux, or
`pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1` on Windows. Either takes out the
command, the shell profile block and the statusline — and the PATH entry on Windows.
Neither touches the live credential, so you stay signed in to whatever account is live.
Add `--purge` (`-Purge` in PowerShell) to also delete the slot directories and their
parked credentials.

## License

MIT — see [LICENSE](LICENSE).

Claude and Claude Code are trademarks of Anthropic PBC. This project is an
independent tool that interoperates with Claude Code; it is not an Anthropic product
and carries no endorsement.
