# Changelog

## 1.0.0

First public release.

- `ccp swap <n>` switches the account for every open Claude Code session at once, by
  exchanging the contents of the single keychain entry those sessions read.
- Numbered slots: each account gets its own config dir and its own keychain entry, so
  `ccp login` never disturbs a running session.
- Parks the outgoing credential before loading the incoming one, so rotating refresh
  tokens never diverge between the live entry and a slot's copy.
- Backdates the incoming access token so open sessions adopt the new account on their
  next token check instead of hours later; `--lazy` opts out.
- `ccp pin <n>` runs a session nailed to one slot, immune to swaps.
- Statusline showing the live slot and account, one colour per slot.
- Slots share `commands/`, `agents/`, `skills/`, `plugins/`, `settings.json` and
  `projects/` by symlink — one toolbox and one transcript history across accounts.
- `ccp doctor` self-checks the environment, since the tool depends on undocumented
  internals.
- Per-user or shared multi-user install; `uninstall.sh` that never logs you out.

Verified against Claude Code 2.1.220 on macOS.
