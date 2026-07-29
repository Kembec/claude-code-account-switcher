# How it works

Everything here describes **observed behaviour** of Claude Code's credential storage,
determined by watching what the shipped client does with the macOS keychain and by
reproducing its naming scheme. No Anthropic code is reproduced in this repository.
Verified against Claude Code **2.1.220**; treat it as a moving target.

## The one fact everything rests on

Claude Code stores its OAuth credential as a generic keychain item whose **service
name depends on the config directory**:

| `CLAUDE_CONFIG_DIR` | Keychain service name |
| --- | --- |
| unset | `Claude Code-credentials` |
| set | `Claude Code-credentials-<first 8 hex of SHA-256 of the NFC-normalised path>` |

The item's account field is your `$USER`. The stored value is JSON:

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

Two consequences fall out of that table, and `ccp` is built entirely from them:

1. **Isolation.** Point `CLAUDE_CONFIG_DIR` at a different directory and you get a
   different keychain item. Two accounts can be logged in simultaneously without
   either one clobbering the other. No `/logout` anywhere.
2. **Sharing.** Every `claude` started without `CLAUDE_CONFIG_DIR` reads the *same*
   unsuffixed item. Change that item's contents and you have changed the credential
   for every one of those processes at once.

## The model: one live credential, N parked

```
LIVE entry      Claude Code-credentials                    ← every plain `claude`
slot 1 parked   Claude Code-credentials-<hash of ~/.claude-slots/1>
slot 2 parked   Claude Code-credentials-<hash of ~/.claude-slots/2>
…
```

- `~/.claude` stays exactly what it was: the directory every normal session runs in.
- `~/.claude-slots/N` exists so that account N can be *logged in* — a real `/login`,
  writing a real credential into N's own keychain item — without disturbing the live
  entry. It doubles as the parking space for that account's credential and identity.
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

> **Each keychain entry is read by exactly one family of processes.**
> The live entry belongs to plain `claude` sessions. Slot N's entry belongs to
> `ccp login N` and `ccp pin N`, and only while N is not live.

Break that and you get two processes refreshing the same grant from two different
places, which ends with one of them holding a dead refresh token.

## Why open sessions notice

Two separate mechanisms, both part of how Claude Code copes with several instances
running at once:

- It **watches its credential store for changes it didn't make** and drops its
  in-memory token cache when it sees one. Without this, two concurrent sessions would
  fight over refreshes.
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

A slot directory is almost entirely symlinks back into `~/.claude`. Everything is
shared except account identity and per-process state:

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
as it was — the keychain item name is derived from the path, which hasn't changed.
