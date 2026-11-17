# CLAUDE.md — claude-code-account-switcher

```regla
REGLA      un agente lee y prueba este repo; nunca ejecuta `bin/ccp`, `install.*` ni `uninstall.*` contra la HOME real
APLICA     toda sesión sobre este repo, abierto solo o dentro de su monorepo
PROHIBIDO  correrlo con `sudo` · leer o volcar la credencial viva, el llavero o `~/.claude.json` · probar fuera de `tests/test_ccp.py`
PRUEBA     python3 tests/test_ccp.py
REF        ./docs/security.md · ./docs/how-it-works.md
```

`ccp` — switches which Claude account an open Claude Code session uses, from another terminal,
without closing the session or logging out. Works by swapping the live credential and letting the
session's next token refresh pick up the new account.

**Stack:** Python 3 (`bin/ccp`), a Python statusline helper (`bin/ccp-statusline.py`), install
scripts in shell and PowerShell. Tests: `python3 tests/test_ccp.py` (throwaway HOME, file backend).

## Reglas

Este repo es un submódulo de `kembec-base`. Las reglas compartidas viven en
`../../../.claude/rules/` de la raíz y aplican acá: handoff entre agentes concurrentes
(`agent-coordination.md`), git en un monorepo de submódulos (`monorepo-git.md`), ruteo de
modelos (`model-routing.md`) y convenciones de repo (`repo-conventions.md`).

Abierto por su cuenta, sin el monorepo arriba, este archivo es lo único que hay: no asumas
que el padre está presente.

Un cambio acá son tres commits: el de este repo, el del puntero en `Personal` y el de `Personal` en la raíz.

**Antes de editar:** `python3 ../../../.claude/scripts/coord.py board` y `claim`. Varios agentes
trabajan este árbol a la vez.

## Lo particular de este repo

**Nunca correrlo con `sudo`.** El fix del commit `de5c520` existe porque `sudo` lee el store de
credenciales de otro usuario en silencio — sin error, solo el estado equivocado — y eso llevó a
diagnosticar mal qué cuenta estaba realmente activa. El script ahora se niega a correr bajo `sudo`
en vez de seguir con datos de la cuenta incorrecta.

**Un agente no lo corre contra la HOME real.** `bin/ccp` (cualquier subcomando), `install.sh`,
`uninstall.sh` y sus `.ps1` leen o reemplazan la credencial viva y el llavero: los ejecuta solo
la persona dueña de las cuentas. Un agente lee el código y prueba con `python3 tests/test_ccp.py`,
que redirige HOME y usa el backend de archivo.
