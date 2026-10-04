# Tipografía por guía

**Fecha:** 2026-10-04 · **Schema:** `supabase/migrations/007_guide_fonts.sql` ·
**Commits:** `4ea4f78` (back), `38f776a` (móvil) · migración aplicada 2026-10-04

## Por qué

Cada guía tiene su fuente de título (Yokohama → "Pathos"); las de texto se
reutilizan entre guías. Se decidió servirlas desde el back y no empaquetarlas
en la app: con 50+ destinos el bundle crecería varios MB y cada ciudad nueva
obligaría a publicar versión en la store. Las fuentes globales de la app (logo,
UI) sí van empaquetadas en el móvil.

## Modelo

- `fonts` — una fila por familia (`family` UNIQUE = nombre que registra el móvil).
- `font_files` — un fichero por peso/estilo (`weight` 100–900, `style`
  normal|italic, `format` ttf|otf, `storage_path` en el bucket `guides`).
  ON DELETE CASCADE desde `fonts`.
- `cities.title_font_id` / `cities.body_font_id` → `fonts`, nullable,
  ON DELETE SET NULL (NULL = fuente por defecto de la app).
- RLS habilitado sin policies (solo service_role), igual que el contenido
  desde la 006. Las licencias pueden prohibir redistribución abierta.

## Código

- `app/models/city.py` — `FontFile`, `GuideFont`, `CityFonts`; `CityGuide.fonts`.
- `app/services/font_service.py` — `resolve_city_fonts()`: lee familias y
  ficheros en paralelo y firma todos los `storage_path` en lote con
  `image_service.sign_paths` (24 h; desde `a2a8494`, antes uno a uno).
  Ficheros que faltan en Storage se omiten;
  familia sin ficheros → `None`.
- `guide_service.get_city_guide()` lo llama → sale en `GET /cities/{slug}` y
  en `/offline` (misma forma).
- Tests: `tests/test_font_service.py` (5). `fake_supabase` ganó la cascada
  `font_files → fonts`.

## Alta de una fuente (manual, no hay endpoint admin)

1. Subir el fichero al bucket `guides`, p. ej. `media/fonts/pathos/pathos_400.otf`.
2. SQL:

```sql
WITH f AS (INSERT INTO fonts (family) VALUES ('Pathos') RETURNING id)
INSERT INTO font_files (font_id, weight, style, format, storage_path)
SELECT id, 400, 'normal', 'otf', 'media/fonts/pathos/pathos_400.otf' FROM f;

UPDATE cities SET title_font_id = (SELECT id FROM fonts WHERE family = 'Pathos')
WHERE slug = 'yokohama';
```

## Pendiente

Resumen vivo en [`../pendientes.md`](../pendientes.md).


- [x] `007` aplicada en Supabase con `supabase db push` (2026-10-04).
- [ ] Licencia de Pathos (y de cada fuente) — confirmar que permite servirla
      desde servidor a una app; si no, esa fuente va empaquetada en el móvil.
- [ ] Subir Pathos y asignarla a Yokohama (SQL de arriba).
- [ ] Decidir fuentes de texto reutilizables y asignarlas (`body_font_id`).
- Nota: el móvil cachea por familia+peso+estilo; reemplazar un fichero con el
  mismo peso/estilo no se refleja → usar ruta/familia nueva.
- Nota: `pytest` a secas falla al recopilar (pytest-asyncio 0.23 + paquete
  `tests/`), preexistente. Usar `pytest tests/test_*.py`.
