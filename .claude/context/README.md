# .claude/context/ — rastro de memoria del backend

Carpeta dedicada **solo a `bon-vivant-api`**. Objetivo: que cualquier sesión de
Claude (o tú mismo dentro de unos meses) pueda retomar el trabajo sin releer
todo el historial de git ni el chat.

Diferencia con el resto de `.claude/`:

- **`../standards.md`** = las normas — cómo se debe escribir código aquí, siempre.
- **`../README.md`** = qué es cada archivo de config de Claude Code.
- **`context/` (esta carpeta)** = el porqué — decisiones tomadas, qué se
  investigó, qué quedó pendiente y por qué. Es historial, no reglas.

Cuando una entrada de aquí quede obsoleta (ej. un TODO ya resuelto), actualízala
en el momento — no dejes que el rastro mienta.

## Índice por tema

| Carpeta | Contenido |
|---|---|
| [`security/`](security/) | Auditoría de seguridad 2026-07-03 y hardening aplicado (RLS, rate limiting, admin role) · Auditoría 2026-10-04 (`2026-10-audit.md`): pasos premium sin Pass y dependencias |
| [`payments/`](payments/) | Validación de compras IAP (Apple/Google): qué está implementado, qué falta configurar |
| [`features/`](features/) | Trip planner: gating por Pass, modelo de días · Tipografía por guía (`guide-fonts.md`, migración 007) |

Lo que queda por hacer, consolidado: [`pendientes.md`](pendientes.md).

## Siguiente paso (pendiente, no hecho aún)

Cablear esto en `standards.md` / `settings.json` para que cada sesión lo lea
automáticamente al empezar, en vez de tener que decírselo cada vez.
