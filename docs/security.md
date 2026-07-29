# Security notes

`ccp` moves OAuth credentials between entries in your own login keychain. That
deserves a straight account of what it touches, so here it is.

## What it does and doesn't do

**Does**

- Read and write generic-password items in the current user's login keychain, through
  `/usr/bin/security` — the same interface Claude Code itself uses.
- Read and patch `~/.claude.json` and `~/.claude-slots/*/.claude.json`, touching only
  the `oauthAccount`, `userID` and `hasAvailableSubscription` keys, plus UI preferences
  when seeding a new slot.
- Create symlinks inside `~/.claude-slots/*/` pointing back into `~/.claude`.
- Append one clearly delimited block to your shell rc file, and set `statusLine` in
  `~/.claude/settings.json` (installer only).

**Doesn't**

- Send anything over the network. `ccp` makes no network calls whatsoever.
- Write credentials to disk in plaintext. Tokens go keychain-to-keychain and exist only
  in the process's memory in between.
- Require root. There is no `sudo` anywhere in this project.
- Defeat, weaken or bypass any authentication. It moves credentials you already hold
  and that your own keychain already grants you access to.
- Cross macOS user accounts. Each user's keychain is separate and `ccp` respects that.

## Things worth knowing

**Argument-visible writes.** Writing a keychain item uses
`security add-generic-password -X <hex>`, so the credential is briefly visible as a
process argument — anyone able to run `ps` on the machine at that instant could see it.
This is the same call the official client makes, and a keychain item's contents are
readable by that user anyway, so it doesn't widen your exposure. It is worth knowing if
you share a machine with people you don't trust; on such a machine, so is running
Claude Code at all.

**Keychain access prompts.** Reading these items via `security` works without a prompt
because that's how Claude Code created them. If macOS ever does prompt, it's your own
keychain asking you to confirm — deny it and `ccp` fails cleanly rather than proceeding.

**A shared install directory.** `install.sh --shared` writes to `/Users/Shared/ccp` by
default. Files land owned by the installing user with mode 755, so other local users
can execute but not modify them. `/Users/Shared` is world-writable with the sticky bit,
which means another local user could add files there but not alter yours. If that
matters in your setup, install per-user instead — it's the default.

**Blast radius of a bug.** The worst realistic outcome is a corrupted live keychain
entry, which logs you out. `ccp` guards against it: every write is read back and
compared, and a payload that doesn't parse as JSON with an `accessToken` is rejected
before any write happens. Recovery is a normal `/login`.

**Interrupted swap.** A swap parks before it loads, in that order deliberately. If it
dies between the two steps, the outgoing account's credential is already safely in its
slot and the live entry is untouched — re-run the swap. There is no window where a
credential exists in neither place.

**Rotation.** Refresh tokens rotate on use. `ccp` keeps exactly one authoritative copy
of any given grant: the live entry while that account is live, the slot's entry
otherwise. The commands that could break this rule (`pin`, `logout`, `rm` against the
live slot) refuse to run.

## Account terms

`ccp` is built for one person switching between accounts they personally own. It does
not pool quota, share credentials between people, or alter usage limits — each account's
limits apply normally while it's live. Whether your particular accounts permit what
you're doing is between you and the applicable terms; if an account belongs to an
employer, their policy applies too.

## Reporting something

Open an issue. If you'd rather not do that publicly for a security problem, say so in
an issue without details and I'll follow up.
