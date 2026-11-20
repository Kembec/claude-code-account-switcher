# Changelog

## 1.2.0

- **A slot now keeps the accounts it held before.** `ccp login <n>` used to overwrite
  the slot's credential, so going back from account B to A needed a new `/login`. Now
  the outgoing account is moved into a per-slot vault (`~/.claude-profiles/history/`)
  first; re-logging the same account, or an aborted login, leaves no duplicate.
- `ccp history <n> [--json]` lists the slot's past accounts: email, org, archive date and
  whether the session is still there. It never prints a token.
- `ccp use <n> <account>` puts a past account back and moves the current one into the
  history. The credential is moved, never copied, so a rotating refresh token has one
  holder; every write is read back, and a failed step rolls the slot back to its
  account (exit 2 only if the rollback itself fails, with the credential still in the
  vault). It refuses the live slot, like `logout` and `pin`. `ccp use <n>` alone still
  swaps.
- Logging in to the live slot first parks the live credential, so the archived copy
  carries the latest refresh token.
- The installers place and remove the new `bin/ccp_history.py` next to `ccp`.
- `tests/test_history.py`: 29 checks for all of the above, including both rollback paths.

## 1.1.3

- **`ccp` and `install.sh` now refuse to run under `sudo`.** `sudo` leaves `HOME`
  pointing at the calling user but sets `USER=root`, so the config directory and the
  keychain account came from different users. The symptom was quiet and wrong rather
  than loud: `ccp ls` reported a slot as having no login while its credential sat there
  untouched, and a write would have landed under root's account where no session reads.
  Hit for real on a multi-user Mac. Five new checks cover it.
- `ccp doctor` prints the keychain account it is using and warns when that account does
  not match the home directory, so the general form of the mismatch is visible.
- README documents it under Troubleshooting.

## 1.1.2

- **Both installers now replace an existing ccp block instead of skipping it.** The old
  behaviour left a stale block in place, so moving or renaming a shared install
  directory silently broke every user pointing at it: their `PATH` and statusline kept
  referencing a directory that no longer existed, with no warning. Re-running the
  installer now repairs it. Verified against a disposable HOME on both shells — one
  block, surrounding lines untouched, idempotent on a second run.
- README documents that caveat, since nothing warns a user whose shared install moved.

## 1.1.1

- **`uninstall.ps1`** — 1.1.0 shipped a Windows installer with no uninstaller, and the
  README pointed Windows users at `uninstall.sh`. It removes the command, the profile
  block, the statusline and the user PATH entry, and like its shell counterpart never
  touches the live credential. `-Purge` clears parked credentials through
  `ccp rm --purge`.
- Docs: several statements were still macOS-only after 1.1.0 — most importantly a claim
  that credentials never touch the disk, which is false where the credential *is* a
  file. Also documents that `.credentials.json` is deliberately never shared into a
  slot, since with the file backend that file is the credential.

## 1.1.0

Cross-platform support.

- **Linux and Windows.** The credential store is now a backend: the macOS login
  keychain, or `<config dir>/.credentials.json` off macOS, picked automatically and
  overridable with `CCP_BACKEND`. File writes are atomic and mode 600, and the replace
  bumps the mtime, which is the change signal Claude Code watches for.
- **`install.ps1`** for Windows: places a `ccp.cmd` shim, adds the bin dir to the user
  PATH, defines the `claude` function in the PowerShell profile, and configures the
  statusline.
- **`install.sh` covers Linux**, and `--shared` now asks for an explicit directory
  where `/Users/Shared` does not exist.
- **Windows link fallback.** Symlinks need Developer Mode there, so `ccp sync` falls
  back to directory junctions and file hardlinks, reports which it used, and warns
  about anything it could not link.
- **Test suite** — `python3 tests/test_ccp.py`, 53 checks against a throwaway `HOME`
  using the file backend, so the non-macOS store is exercised on every run on any
  platform. Covers the parking order, rotation survival, backdating and `--lazy`, the
  live-slot guards, slot resolution, and refusal to write a malformed credential.
- `ccp doctor` names the platform, backend and Python version.
- `uninstall.sh --purge` clears parked credentials through `ccp rm --purge`, so it is
  correct on both backends and still refuses to touch the live one.

## 1.0.0

First public release.

- `ccp swap <n>` switches the account for every open Claude Code session at once, by
  exchanging the contents of the single credential store those sessions read.
- Numbered slots: each account gets its own config dir and its own credential store, so
  `ccp login` never disturbs a running session.
- Parks the outgoing credential before loading the incoming one, so rotating refresh
  tokens never diverge between the live store and a slot's copy.
- Backdates the incoming access token so open sessions adopt the new account on their
  next token check instead of hours later; `--lazy` opts out.
- `ccp pin <n>` runs a session nailed to one slot, immune to swaps.
- Statusline showing the live slot and account, one colour per slot.
- Slots share `commands/`, `agents/`, `skills/`, `plugins/`, `settings.json` and
  `projects/` by link — one toolbox and one transcript history across accounts.
- `ccp doctor` self-checks the environment, since the tool depends on undocumented
  internals.
- Per-user or shared multi-user install; `uninstall.sh` that never logs you out.

Verified against Claude Code 2.1.220.
