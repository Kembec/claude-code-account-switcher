# Security notes

`ccp` moves OAuth credentials between stores that belong to you — entries in your own
login keychain on macOS, files under your own home directory elsewhere. That deserves a
straight account of what it touches, so here it is.

## What it does and doesn't do

**Does**

- On macOS: read and write generic-password items in the current user's login
  keychain, through `/usr/bin/security` — the same interface Claude Code itself uses.
- On Linux and Windows: read and write `<config dir>/.credentials.json`, created mode
  600, written atomically via a temp file and a replace.
- Read and patch `~/.claude.json` and `~/.claude-slots/*/.claude.json`, touching only
  the `oauthAccount`, `userID` and `hasAvailableSubscription` keys, plus UI preferences
  when seeding a new slot.
- Create links inside `~/.claude-slots/*/` pointing back into `~/.claude` — symlinks,
  or directory junctions and hardlinks on a Windows box without Developer Mode.
- Append one clearly delimited block to your shell rc file or PowerShell profile, and
  set `statusLine` in `~/.claude/settings.json` (installer only).
- On Windows, add the install directory to your **user** PATH environment variable
  (installer only; `uninstall.ps1` removes it again). Never the machine-wide PATH.

**Doesn't**

- Send anything over the network. `ccp` makes no network calls whatsoever.
- Write credentials anywhere Claude Code wouldn't. On macOS tokens go
  keychain-to-keychain and exist only in the process's memory in between. On Linux and
  Windows the credential *is* a mode-600 file — that is Claude Code's own design, and
  `ccp` writes slot copies the same way, in the same kind of location, with the same
  permissions. It never adds a plaintext copy on a platform that has a keychain.
- Require root. There is no `sudo` anywhere in this project.
- Defeat, weaken or bypass any authentication. It moves credentials you already hold
  and that your own account already grants you access to.
- Cross OS user accounts. Credentials are stored per user — a separate login keychain on
  macOS, a file under each user's home elsewhere — and `ccp` respects that boundary.

## Things worth knowing

**Argument-visible writes (macOS).** Writing a keychain item uses
`security add-generic-password -X <hex>`, so the credential is briefly visible as a
process argument — anyone able to run `ps` on the machine at that instant could see it.
This is the same call the official client makes, and a keychain item's contents are
readable by that user anyway, so it doesn't widen your exposure. It is worth knowing if
you share a machine with people you don't trust; on such a machine, so is running
Claude Code at all.

**Keychain access prompts (macOS).** Reading these items via `security` works without a
prompt because that's how Claude Code created them. If macOS ever does prompt, it's your
own keychain asking you to confirm — deny it and `ccp` fails cleanly rather than
proceeding.

**File permissions (Linux, Windows).** Without a keychain, credentials sit in a file.
`ccp` creates it mode 600 and preserves that on every write, matching what Claude Code
does. On Windows, POSIX modes are advisory; the file inherits the ACL of your user
profile directory, which is normally you-only. If your home directory is on a share with
looser permissions, that applies to Claude Code's own credential file just as much as to
ccp's copies.

**A shared install directory.** `install.sh --shared` writes to `/Users/Shared/ccp` on
macOS, or a directory you name on Linux. Files land owned by the installing user with
mode 755, so other local users can execute but not modify them. `/Users/Shared` is
world-writable with the sticky bit, which means another local user could add files there
but not alter yours. If that matters in your setup, install per-user instead — it's the
default, and it is the only mode `install.ps1` offers on Windows.

**Blast radius of a bug.** The worst realistic outcome is a corrupted live credential,
which logs you out. `ccp` guards against it: every write is read back and
compared, and a payload that doesn't parse as JSON with an `accessToken` is rejected
before any write happens. Recovery is a normal `/login`.

**Interrupted swap.** A swap parks before it loads, in that order deliberately. If it
dies between the two steps, the outgoing account's credential is already safely in its
slot and the live store is untouched — re-run the swap. There is no window where a
credential exists in neither place.

**Rotation.** Refresh tokens rotate on use. `ccp` keeps exactly one authoritative copy
of any given grant: the live store while that account is live, the slot's store
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
