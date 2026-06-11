# bonvivant-api

FastAPI backend for Bon Vivant — offline city guides for cruise passengers.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Service role key (never expose to client) |
| `JWT_SECRET` | yes | Supabase JWT secret |
| `MAPBOX_TOKEN` | no | Enables geocoding on import; falls back to null geocoder |
| `DEBUG` | no | `true` exposes `/docs` (Swagger UI) |

## Run locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Docs: http://localhost:8000/docs  (only if DEBUG=true)
```

## Database migrations

```bash
supabase db push
```

Migrations live in `supabase/migrations/` and are applied in order. Run this after pulling changes that add new migration files.

## Import a city guide

Guides are JSON files in `guides/`. Each file maps to one city.

```bash
source .venv/bin/activate
python scripts/import_guide.py guides/yokohama.json           # first import
python scripts/import_guide.py guides/yokohama.json --replace # overwrite existing draft
```

`--replace` only works on draft cities. A published city must be unpublished via the admin API before it can be reimported.

## Deploy

Auto-deploys to Railway on merge to `main`.
