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

> macOS only. Not affiliated with, endorsed by, or sponsored by Anthropic.
> Intended for one person switching between accounts they personally own — see
> [Intended use](#intended-use).

---

## Why

If you have a work account and a personal account, Claude Code gives you one
credential slot. The usual workaround is `/logout`, `/login`, pick the other account,
and repeat every time you switch — plus a browser round-trip each way. Sessions you
had open keep running on the old account until their token happens to expire, so you
can't tell which account a given window is billing.

`ccp` parks each account's credential in its own keychain entry and swaps the one
entry that live sessions actually read. One command, every session, and a statusline
that tells you which account you're on.

## Install

Requires macOS, Python 3.9+ (system Python is fine), and Claude Code on your `PATH`.

```console
git clone https://github.com/Kembec/claude-code-account-switcher.git
cd claude-code-account-switcher
sh install.sh
```

That symlinks `ccp` into `~/.local/bin`, adds a small block to your `~/.zshrc`,
configures the statusline, and parks the account you're already logged in with as
`slot1`. Open a new terminal afterwards.

<details>
<summary>Multi-user Macs</summary>

```console
sh install.sh --shared          # → /Users/Shared/ccp
```

Then run `sh install.sh` once from each other macOS account. Every user gets their
own login keychain, so **every user keeps their own slots and their own logins**.
Credentials never cross user accounts; that's an OS boundary, not a `ccp` choice.

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
| `ccp sync [n]` | Rebuild the shared symlinks (idempotent) |
| `ccp rm <n>` | Unregister a slot (`--purge` also deletes dir + credential) |
| `ccp doctor` | Self-check the environment and state |

`<n>` accepts `2`, `slot2`, or the account's email — `ccp swap me@work.example` works.

### Two ways to run

- **Plain `claude`** uses the live credential. This is what makes one swap reach every
  session, so it's the default and you shouldn't override it.
- **`ccp pin 2`** (or `CCP=2 claude`) nails one process to slot 2. Swaps don't touch
  it. Use this when you want two accounts running side by side.

`ccp pin`, `ccp logout` and `ccp rm` refuse to operate on the live slot, because two
families of processes refreshing the same credential from different entries is how
you get a diverged refresh token.

### Statusline

The installer sets a statusline so you can always see which account a session is on,
with one colour per slot:

```
 slot1 · me@work.example · my-project · Opus 4.6
 slot2 · me@personal.example · my-project · Opus 4.6
 slot3 pin · me@other.example · scratch · Sonnet 4.6
```

It reads the live slot from state, so **after a swap every open session shows the new
account**. Already-running sessions won't display it until you restart them once —
`settings.json` is read at startup.

## How it works

Claude Code derives its keychain item name from the config directory: the item is
`Claude Code-credentials` when `CLAUDE_CONFIG_DIR` is unset, and gets a suffix
derived from that directory's path when it is set. So pointing `CLAUDE_CONFIG_DIR` at
a per-slot directory gives each account a private credential that can't clobber the
others — that's how `ccp login` parks an account without disturbing your live session.

Every plain `claude` runs in `~/.claude` and reads the one unsuffixed entry. `ccp
swap` copies the live entry's contents back into the outgoing slot's entry, then
copies the incoming slot's entry into the live one. Claude Code watches for
credential changes it didn't make — that's how concurrent instances stay consistent
when one of them refreshes a token — so live sessions pick the new credential up on
their own.

Access tokens last about eight hours and a running session holds one in memory, so a
swap would otherwise take hours to land. `ccp` backdates `expiresAt` on the credential
it installs: the next token check decides a refresh is due, refreshes with the
incoming account's refresh token, and adopts that identity. Nothing is revoked.

Slots share your whole Claude Code setup — `commands/`, `agents/`, `skills/`,
`plugins/`, `settings.json`, and `projects/` — through symlinks, so there's one
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

`ccp` never transmits credentials anywhere. Everything stays in your login keychain
on your machine.

## Limitations

- **macOS only.** Credentials go through `/usr/bin/security`. On Linux, Claude Code
  stores them in `~/.claude/.credentials.json` instead; a file backend would be
  straightforward but isn't implemented, and shipping code I can't test seemed worse
  than saying so.
- **It rides on undocumented internals.** The keychain naming scheme and credential
  layout were determined by observing Claude Code's own behaviour, verified against
  **2.1.220**. A future release could change either. `ccp doctor` tells you whether
  the assumptions still hold; if they don't, uninstalling leaves you with a normal,
  working Claude Code login.
- **Swaps aren't instantaneous.** They land on each session's next token check, not
  the same millisecond. Seconds to minutes in practice.
- **One live account at a time** across plain sessions. If you want two accounts at
  once, use `ccp pin`.
- Per-slot `.claude.json` keeps its own account identity, but a session that was
  already running may show the previous account in `/status` until it refetches its
  profile. The statusline is the reliable indicator.

## Troubleshooting

```console
ccp doctor
```

**"no live credential in the keychain"** — run `claude`, `/login` normally, then
`ccp init`.

**A swap didn't seem to land.** Send any message in the open session to make it talk
to the API, then check `ccp live`. If it still hasn't moved, `ccp doctor` will show
whether the live entry actually holds the new token.

**A slot lost its login.** `ccp login <n>` again. Parked credentials are only stale if
something outside `ccp` overwrote a keychain entry.

**Removing it.** `sh uninstall.sh` takes out the command, the shell block and the
statusline. It never touches the live entry, so you stay signed in to whatever account
is live. `--purge` also deletes the slot directories and parked credentials.

## License

MIT — see [LICENSE](LICENSE).

Claude and Claude Code are trademarks of Anthropic PBC. This project is an
independent tool that interoperates with Claude Code; it is not an Anthropic product
and carries no endorsement.
