# bonvivant-api — Claude Code Context

> Lee este archivo al inicio de cada sesión. Es la fuente de verdad del repo backend.
> Reglas de calidad y seguridad → `.claude/standards.md`.
> Dominio, contrato de endpoints y reglas que cruzan repos → `../CLAUDE.md` (paraguas).
> Si algo aquí contradice una conversación previa, gana este archivo.

## Qué es este repo

Backend de **Bon Vivant** — app de guías offline para cruceristas.
Sirve la API REST `/api/v1` que consume el repo `bon-vivant-mobile`.
El backend es la **única fuente de verdad** de accesos y pagos.

## Stack exacto

- **Framework:** FastAPI
- **Lenguaje:** Python **3.12** (Dockerfile, CI y black target `py312`)
- **Validación:** Pydantic en todos los request bodies + `response_model` en todos los endpoints
- **Auth:** JWT de Supabase Auth validado en cada request protegido
- **DB:** Supabase. `service_role` para datos críticos (pagos, admin); JWT del usuario para el resto
- **Patrón:** endpoints solo HTTP → lógica de negocio solo en `services/`
- **Async:** todas las llamadas a DB son async, siempre
- **Versionado:** `/api/v1/...`
- **Errores:** schema único `{ detail: string, code: string }`
- **Lint/format:** ruff (`E`,`F`,`I`) + black, line-length 88
- **Deploy:** Railway, auto-deploy en merge a `main`

## Comandos

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000   # dev → http://localhost:8000
pytest                                                     # tests
ruff check . && black .                                    # lint + format
```

## Estructura de carpetas (real)

```
app/
├── api/
│   ├── deps.py                 # inyección de dependencias (Auth, DB)
│   └── v1/
│       ├── router.py           # agregador central
│       └── endpoints/          # cities · packs · purchases · tips
├── core/security.py            # seguridad JWT
├── db/supabase.py              # cliente Supabase
├── models/                     # schemas Pydantic: city · pack · purchase · user
├── services/                   # lógica de negocio: city · offline · purchase
├── config.py                   # env vars (Settings)
└── main.py                     # FastAPI app instance
supabase/
├── migrations/                 # SQL versionado (DDL + RLS) — 001_initial_schema.sql
└── seed/                       # datos semilla dev (seed_barcelona.sql)
tests/                          # pytest (conftest, test_cities, test_purchases)
.github/workflows/ci.yml        # CI: tests en push/PR a main (Python 3.12)
Dockerfile · railway.toml · pyproject.toml · requirements.txt
```

## Endpoints

Contrato completo en `../CLAUDE.md`. Este repo es **autoritativo** sobre él.
Resumen: `me` · `cities` (+preview/offline/spots/itineraries/tips/warnings) ·
`itineraries/{id}` · `tips/general` · `packs` · `purchases` (validate/me/restore) ·
`admin/*` · `health`.

## Estado actual (a 2026-06) — ⚠️ divergencias con el objetivo

El repo está **scaffolded**: estructura y migración SQL listas, pero la mayoría
de `.py` son stubs de docstring (`app/` ≈ 28 líneas reales). Al implementar:

- **Endpoints presentes como fichero:** `cities`, `packs`, `purchases`, `tips`.
  **Faltan por crear:** `spots`, `itineraries`, `me`, `admin` (están en el contrato
  objetivo pero aún no existen como módulo).
- `router.py`, `main.py`, `deps.py`, `core/security.py`, `config.py`, modelos y
  services están **vacíos** → hay que rellenarlos siguiendo el patrón de arriba.
- La migración `001_initial_schema.sql` ya define `profiles`, `cities`, `packs`…
  Verifica que cubre `spots`, `itineraries`, `itinerary_steps`, `manuel_tips`,
  `city_warnings`, `user_purchases` con **RLS** antes de exponer endpoints.

## Reglas no negociables

Detalle en `.claude/standards.md`. Lo crítico del backend:

- Type hints en TODAS las funciones · `response_model` en TODOS los endpoints.
- Async en TODAS las llamadas a Supabase.
- Endpoints solo manejan HTTP; la lógica vive en `services/`; `models/` solo schemas.
- Nunca capturar `Exception` genérica — solo excepciones específicas.
- Nunca SQL por concatenación — queries parametrizadas.
- Nunca exponer stack traces — mensaje genérico + `{ detail, code }`.
- `service_role` solo aquí, jamás en frontend. RLS en todas las tablas, siempre.
- **`POST /purchases/validate`:** valida el receipt contra App Store / Google Play.
  Nunca confíes en el cliente. `is_unlocked` se calcula aquí según `user_purchases`.
- 403 (no 404) cuando el recurso existe pero el usuario no tiene acceso.

## Variables de entorno (nunca commitear valores)

```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY           # solo backend, jamás exponer
JWT_SECRET
APP_STORE_SHARED_SECRET             # validación receipt IAP iOS
GOOGLE_PLAY_SERVICE_ACCOUNT_JSON    # validación receipt IAP Android
DEBUG                               # false en prod — controla /docs
```

## Antes de escribir código, pregúntate

1. ¿Expone datos sensibles o stack traces?
2. ¿Tiene `response_model` y type hints?
3. ¿La lógica está en `services/` o se coló en el endpoint?
4. ¿Es async la llamada a Supabase?
5. ¿Qué pasa si falla la validación del receipt de pago?
