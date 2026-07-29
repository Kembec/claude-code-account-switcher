# Changelog

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
