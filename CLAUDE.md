# CLAUDE.md — claude-code-account-switcher

`ccp` — switches which Claude account an open Claude Code session uses, from another terminal,
without closing the session or logging out. Works by swapping the live credential and letting the
session's next token refresh pick up the new account.

**Stack:** shell (`bin/ccp`), a Python statusline helper (`bin/ccp-statusline.py`).

## Reglas

Este repo es un submódulo de `kembec-base`. Las reglas compartidas viven en
`../../.claude/rules/` de la raíz y aplican acá: handoff entre agentes concurrentes
(`agent-coordination.md`), git en un monorepo de submódulos (`monorepo-git.md`), ruteo de
modelos (`model-routing.md`) y convenciones de repo (`repo-conventions.md`).

Abierto por su cuenta, sin el monorepo arriba, este archivo es lo único que hay: no asumas
que el padre está presente.

Un cambio acá son dos commits: el de este repo y el del puntero en la raíz.

**Antes de editar:** `python3 ../../.claude/scripts/coord.py board` y `claim`. Varios agentes
trabajan este árbol a la vez.

## Lo particular de este repo

**Nunca correrlo con `sudo`.** El fix del commit `de5c520` existe porque `sudo` lee el store de
credenciales de otro usuario en silencio — sin error, solo el estado equivocado — y eso llevó a
diagnosticar mal qué cuenta estaba realmente activa. El script ahora se niega a correr bajo `sudo`
en vez de seguir con datos de la cuenta incorrecta.
