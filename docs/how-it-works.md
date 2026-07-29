# How it works

Everything here describes **observed behaviour** of Claude Code's credential storage,
determined by watching what the shipped client does and by reproducing how it addresses
its own credential. No Anthropic code is reproduced in this repository. Verified against
Claude Code **2.1.220**; treat it as a moving target.

The macOS keychain path is verified on real hardware. The Linux and Windows file path is
verified by the test suite, which runs the real CLI against that backend, but has not yet
been exercised on those operating systems — see the README.

## The one fact everything rests on

**Claude Code scopes its OAuth credential to the config directory.** How it does that
depends on the platform.

On macOS the credential is a generic keychain item whose service name is derived from
the config directory:

| `CLAUDE_CONFIG_DIR` | Keychain service name |
| --- | --- |
| unset | `Claude Code-credentials` |
| set | `Claude Code-credentials-<first 8 hex of SHA-256 of the NFC-normalised path>` |

The item's account field is your `$USER`.

On Linux and Windows there is no keychain: the credential is `.credentials.json`
inside the config directory, mode 600. Scoping is then trivially by path.

Either way the stored value is the same JSON:

```json
{
  "claudeAiOauth": {
    "accessToken": "…",
    "refreshToken": "…",
    "expiresAt": 1750000000000,
    "refreshTokenExpiresAt": 1752000000000,
    "scopes": ["user:inference", "user:profile", "…"],
    "subscriptionType": "…",
    "rateLimitTier": "…"
  }
}
```

`expiresAt` is milliseconds since the epoch. Access tokens are issued with roughly an
eight hour lifetime; refresh tokens last weeks.

Two consequences fall out of that, and `ccp` is built entirely from them:

1. **Isolation.** Point `CLAUDE_CONFIG_DIR` at a different directory and you get a
   different credential store. Two accounts can be logged in simultaneously without
   either one clobbering the other. No `/logout` anywhere.
2. **Sharing.** Every `claude` started without `CLAUDE_CONFIG_DIR` reads the *same*
   store. Change its contents and you have changed the credential for every one of
   those processes at once.

## The model: one live credential, N parked

```
                macOS                                       Linux / Windows
live store      Claude Code-credentials                     ~/.claude/.credentials.json
slot 1 parked   Claude Code-credentials-<hash of slot 1>     ~/.claude-slots/1/.credentials.json
slot 2 parked   Claude Code-credentials-<hash of slot 2>     ~/.claude-slots/2/.credentials.json
…
```

`ccp` picks the backend from the platform; `CCP_BACKEND=keychain|file` overrides it.
File writes go through a temp file plus an atomic replace, so a reader never sees a
torn file and the replace bumps the mtime — which is precisely the signal Claude Code
watches for.

- `~/.claude` stays exactly what it was: the directory every normal session runs in.
- `~/.claude-slots/N` exists so that account N can be *logged in* — a real `/login`,
  writing a real credential into N's own store — without disturbing the live one. It
  doubles as the parking space for that account's credential and identity.
- `~/.claude-profiles/` holds `ccp`'s own state: one `slotN.dir` file per slot and a
  `live` file naming the slot currently loaded into the live entry.

`ccp login 2` therefore has zero effect on your running sessions, which is what makes
it safe to set up a second account in the middle of a working day.

## A swap, step by step

`ccp swap 2`, with slot 1 live:

1. Read the live entry. Write it into **slot 1's** entry. Write the `oauthAccount`
   block from `~/.claude.json` into `~/.claude-slots/1/.claude.json`.
2. Read slot 2's entry. Backdate `expiresAt` on that copy. Write it into the live
   entry. Restore slot 2's identity block into `~/.claude.json`.
3. Record `live = 2`.

Every write is read back and compared before the step is considered done, and a blob
that doesn't parse as JSON containing an `accessToken` is refused outright — a bad
write to the live entry would break every open session at once.

### Why park before load

Refresh tokens rotate: when a session refreshes, it gets a *new* refresh token and the
old one stops working. While slot 1 is live, all that rotation happens in the live
entry — slot 1's parked copy goes stale the moment the first refresh lands.

So the parked copy is only ever trusted for a slot that is **not** live, and the very
first thing a swap does is refresh the outgoing slot's parked copy from the live entry.
The parked credential you load tomorrow is the one that was valid when you swapped
away, not a stale snapshot from whenever you logged in.

That is also why `ccp pin`, `ccp logout` and `ccp rm` refuse to operate on the live
slot. The invariant is:

> **Each credential store is read by exactly one family of processes.**
> The live store belongs to plain `claude` sessions. Slot N's store belongs to
> `ccp login N` and `ccp pin N`, and only while N is not live.

Break that and you get two processes refreshing the same grant from two different
places, which ends with one of them holding a dead refresh token.

## Why open sessions notice

Two separate mechanisms, both part of how Claude Code copes with several instances
running at once:

- It **watches its credential store for changes it didn't make** and drops its
  in-memory token cache when it sees one. Without this, two concurrent sessions would
  fight over refreshes. With the file backend this is an explicit mtime watch on
  `.credentials.json`, which is more direct than the keychain path.
- On a **401**, it re-reads the store, and if the token there differs from the one it
  tried, it adopts it and retries.

`ccp` only needs the first. But there's a catch: a running session holds a valid access
token and, with roughly eight hours on the clock, has no reason to look at storage.
So a plain content swap could sit unnoticed for most of a working day — which is
exactly the failure mode of the `/logout`-in-another-terminal trick, where the session
keeps billing the old account until its token lapses.

The fix is to make the incoming credential look due for renewal. `ccp` writes it with
`expiresAt` set sixty seconds in the past. The next token check therefore decides a
refresh is needed, performs it **with the incoming account's refresh token**, and in
doing so adopts that account. Pass `--lazy` to skip the backdating.

Nothing is revoked, so the operation is reversible: the outgoing account's parked
credential is untouched and still valid.

## What slots share

A slot directory is almost entirely links back into `~/.claude`. Everything is shared
except account identity and per-process state:

**Private per slot** — `.claude.json` (account identity and subscription caches),
`sessions/`, `shell-snapshots/`, `session-env/`, `ide/`, `daemon/`, `statsig/`,
`cache/`, `paste-cache/`, `backups/`, `metrics/`, `debug/`, `uploads/`,
`history.jsonl`, the MCP and policy caches, and anything ending in `.log` or `.lock`.

**Shared** — everything else, notably `commands/`, `agents/`, `skills/`, `plugins/`,
`settings.json`, `CLAUDE.md`, and `projects/`.

Sharing `projects/` means one transcript history across accounts, so `claude --resume`
finds a conversation regardless of which account was live when it started. `ccp sync`
rebuilds the links and is safe to run any time; it never overwrites real files a slot
owns.

## State on disk

```
~/.claude-profiles/
  slot1.dir        absolute path of slot 1's config dir
  slot2.dir
  live             slot number currently loaded into the live entry
~/.claude-slots/
  1/  2/  3/       per-slot config dirs (mostly symlinks + .claude.json)
```

Slot numbers are stable and never renumbered. `ccp rm 3` without `--purge` leaves the
directory and the parked credential in place, so `ccp add 3` restores that slot exactly
as it was — the credential is addressed by path, which hasn't changed.

## Sharing on Windows

Slot content is shared with symlinks, which on Windows require Developer Mode or
elevation. Without either, `ccp` falls back to what needs no privilege: directory
junctions via `mklink /J`, and hardlinks for files. `ccp sync` reports which strategy
it used and warns about anything it could not link — a slot with unlinked items still
works, it simply does not share those.

## A trap worth knowing about

A nested Claude Code client can receive an OAuth token from its parent through an
inherited file descriptor. That means running `claude -p` from inside another Claude
Code session is **not** a valid test of whether a credential works: the child can
authenticate through the inherited token even when the credential under test is
garbage. Verify credential behaviour by inspecting the store itself — which token is
there, and whether `expiresAt` moved — not by whether a nested client answered.
