-- ============================================================
-- 007_guide_fonts.sql
--
-- Per-guide typography. Each city guide has its own title font
-- (e.g. Yokohama → "Pathos") while body fonts are shared across
-- guides, so fonts live in their own reusable tables and cities
-- reference them.
--
--   fonts       one row per family ("Pathos"), reusable by any city
--   font_files  one row per weight/style file of a family, stored
--               in the `guides` Storage bucket (same as images)
--   cities      title_font_id / body_font_id → fonts
--
-- Files are delivered by the backend as signed URLs inside the
-- guide detail and the offline bundle; the client downloads and
-- caches them. A NULL font on a city means "use the app default".
--
-- Idempotent — safe to re-run.
-- ============================================================

-- ------------------------------------------------------------
-- 1. fonts — font families
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fonts (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Family name the client registers with expo-font. Must be unique
  -- so two guides never fight over the same registered name.
  family      text         UNIQUE NOT NULL
    CHECK (family <> ''),
  created_at  timestamptz  NOT NULL DEFAULT now(),
  updated_at  timestamptz  NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS fonts_set_updated_at ON fonts;
CREATE TRIGGER fonts_set_updated_at
  BEFORE UPDATE ON fonts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 2. font_files — one file per weight/style of a family
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS font_files (
  id            uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  font_id       uuid         NOT NULL REFERENCES fonts(id) ON DELETE CASCADE,
  weight        smallint     NOT NULL DEFAULT 400
    CHECK (weight BETWEEN 100 AND 900 AND weight % 100 = 0),
  style         text         NOT NULL DEFAULT 'normal'
    CHECK (style IN ('normal', 'italic')),
  format        text         NOT NULL
    CHECK (format IN ('ttf', 'otf')),
  -- Path inside the `guides` bucket, e.g. media/fonts/pathos/pathos_400.otf
  storage_path  text         UNIQUE NOT NULL
    CHECK (storage_path <> ''),
  created_at    timestamptz  NOT NULL DEFAULT now(),
  updated_at    timestamptz  NOT NULL DEFAULT now(),

  UNIQUE (font_id, weight, style)
);

CREATE INDEX IF NOT EXISTS idx_font_files_font_id ON font_files (font_id);

DROP TRIGGER IF EXISTS font_files_set_updated_at ON font_files;
CREATE TRIGGER font_files_set_updated_at
  BEFORE UPDATE ON font_files
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 3. cities — which families a guide uses
--    SET NULL on delete: removing a font degrades the guide to the
--    app default instead of breaking it.
-- ------------------------------------------------------------

ALTER TABLE cities
  ADD COLUMN IF NOT EXISTS title_font_id uuid REFERENCES fonts(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS body_font_id  uuid REFERENCES fonts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_cities_title_font_id ON cities (title_font_id);
CREATE INDEX IF NOT EXISTS idx_cities_body_font_id  ON cities (body_font_id);

-- ------------------------------------------------------------
-- 4. RLS — same model as guide content since 006: enabled with no
--    permissive policy, so anon/authenticated are denied and only
--    the service_role backend reads these tables. Font licences may
--    forbid open redistribution, so files are never publicly listable.
-- ------------------------------------------------------------

ALTER TABLE fonts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE font_files ENABLE ROW LEVEL SECURITY;
