-- ============================================================
-- 002_city_guide_schema.sql
-- i18n city guide schema — Variante C (backend serialises
-- LocalizedText as-is; client resolves language).
--
-- Runs on top of 001_initial_schema.sql.
-- Drops desaligned content tables; keeps profiles, packs,
-- user_purchases and the auth trigger intact.
-- ============================================================

-- ============================================================
-- 1. Drop old content tables (explicit list + CASCADE for any
--    remaining FK-dependent objects).
-- ============================================================

DROP TABLE IF EXISTS pack_cities        CASCADE;
DROP TABLE IF EXISTS city_warnings      CASCADE;
DROP TABLE IF EXISTS manuel_tips        CASCADE;
DROP TABLE IF EXISTS itinerary_steps    CASCADE;
DROP TABLE IF EXISTS itineraries        CASCADE;
DROP TABLE IF EXISTS spots              CASCADE;
DROP TABLE IF EXISTS images             CASCADE;
DROP TABLE IF EXISTS tips               CASCADE;
DROP TABLE IF EXISTS cities             CASCADE;

-- ============================================================
-- 2. Enums (idempotent — EXCEPTION duplicate_object swallows
--    the error if the enum already exists from a partial run)
-- ============================================================

DO $$ BEGIN
  CREATE TYPE spot_kind AS ENUM ('attraction', 'food');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE spot_category AS ENUM ('restaurant', 'cafe', 'bar');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE transport_method AS ENUM ('walk', 'metro', 'tram', 'taxi', 'train', 'ferry');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE travel_mode AS ENUM ('walk', 'transit', 'taxi');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE time_of_day AS ENUM ('day', 'night');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE city_status AS ENUM ('draft', 'published');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- image_slot is intentionally minimal; extend via ALTER TYPE … ADD VALUE in future migrations.
DO $$ BEGIN
  CREATE TYPE image_slot AS ENUM ('cover', 'overview_1', 'overview_2', 'spot');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 3. updated_at trigger helper
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- ============================================================
-- 4. cities
-- Convention: (L) = jsonb with CHECK that 'es' is present and
-- non-empty. The backend never resolves language — it serialises
-- LocalizedText as-is and the client picks the right key.
-- ============================================================

CREATE TABLE cities (
  id                  uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                text         UNIQUE NOT NULL,
  name                text         NOT NULL,
  country_code        text         NOT NULL,

  -- (L) Editorial content
  tagline             jsonb        NOT NULL
    CHECK ((tagline->>'es') IS NOT NULL AND tagline->>'es' <> ''),
  intro               jsonb        NOT NULL
    CHECK ((intro->>'es') IS NOT NULL AND intro->>'es' <> ''),
  historical_context  jsonb        NOT NULL
    CHECK ((historical_context->>'es') IS NOT NULL AND historical_context->>'es' <> ''),

  -- Structured jsonb array: [{label: (L), description: (L)}]
  highlights          jsonb        NOT NULL DEFAULT '[]',

  -- (L) Port section
  port_description    jsonb        NOT NULL
    CHECK ((port_description->>'es') IS NOT NULL AND port_description->>'es' <> ''),
  distance_to_center  jsonb        NOT NULL
    CHECK ((distance_to_center->>'es') IS NOT NULL AND distance_to_center->>'es' <> ''),
  port_facilities     jsonb        NOT NULL
    CHECK ((port_facilities->>'es') IS NOT NULL AND port_facilities->>'es' <> ''),
  port_recommendation jsonb        NOT NULL
    CHECK ((port_recommendation->>'es') IS NOT NULL AND port_recommendation->>'es' <> ''),

  -- Structured jsonb arrays
  -- transport_options: [{method: transport_method, time_label: text, tips: (L)}]
  -- what_to_know:      [{heading: (L), text: (L)}]
  transport_options   jsonb        NOT NULL DEFAULT '[]',
  what_to_know        jsonb        NOT NULL DEFAULT '[]',

  -- Port coordinates (nullable until verified by content team)
  port_lat            double precision,
  port_lng            double precision,

  status              city_status  NOT NULL DEFAULT 'draft',
  last_verified       date,
  created_at          timestamptz  NOT NULL DEFAULT now(),
  updated_at          timestamptz  NOT NULL DEFAULT now()
);

-- Auto-stamp updated_at on every modification.
CREATE TRIGGER cities_set_updated_at
  BEFORE UPDATE ON cities
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 5. spots
-- ============================================================

CREATE TABLE spots (
  id                    uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id               uuid           NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  kind                  spot_kind      NOT NULL,
  category              spot_category,               -- food spots only; NULL for attractions
  name                  text           NOT NULL,
  address               text           NOT NULL,
  latitude              double precision NOT NULL,
  longitude             double precision NOT NULL,
  distance_from_port_km numeric,                     -- nullable: unknown until verified
  rank_order            int            NOT NULL,
  website               text,

  -- (L) required
  manuel_quote          jsonb          NOT NULL
    CHECK ((manuel_quote->>'es') IS NOT NULL AND manuel_quote->>'es' <> ''),

  -- (L) nullable
  reservation           jsonb
    CHECK (reservation IS NULL
      OR ((reservation->>'es') IS NOT NULL AND reservation->>'es' <> '')),

  -- (L) attraction-only nullable fields
  what_it_is            jsonb
    CHECK (what_it_is IS NULL
      OR ((what_it_is->>'es') IS NOT NULL AND what_it_is->>'es' <> '')),
  why_it_matters        jsonb
    CHECK (why_it_matters IS NULL
      OR ((why_it_matters->>'es') IS NOT NULL AND why_it_matters->>'es' <> '')),
  good_to_know          jsonb
    CHECK (good_to_know IS NULL
      OR ((good_to_know->>'es') IS NOT NULL AND good_to_know->>'es' <> '')),

  -- (L) food-only nullable fields
  cuisine_type          jsonb
    CHECK (cuisine_type IS NULL
      OR ((cuisine_type->>'es') IS NOT NULL AND cuisine_type->>'es' <> '')),
  category_label        jsonb
    CHECK (category_label IS NULL
      OR ((category_label->>'es') IS NOT NULL AND category_label->>'es' <> '')),
  must_try              jsonb
    CHECK (must_try IS NULL
      OR ((must_try->>'es') IS NOT NULL AND must_try->>'es' <> '')),
  best_time             jsonb
    CHECK (best_time IS NULL
      OR ((best_time->>'es') IS NOT NULL AND best_time->>'es' <> ''))
);

-- Composite index for city feed sorted by kind then rank.
CREATE INDEX idx_spots_city_kind_rank ON spots (city_id, kind, rank_order);

-- ============================================================
-- 6. itineraries
-- ============================================================

CREATE TABLE itineraries (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id          uuid        NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  theme            text        NOT NULL,
  time_of_day      time_of_day NOT NULL,

  -- (L) required editorial fields
  title            jsonb       NOT NULL
    CHECK ((title->>'es') IS NOT NULL AND title->>'es' <> ''),
  catchy_phrase    jsonb       NOT NULL
    CHECK ((catchy_phrase->>'es') IS NOT NULL AND catchy_phrase->>'es' <> ''),
  best_for         jsonb       NOT NULL
    CHECK ((best_for->>'es') IS NOT NULL AND best_for->>'es' <> ''),

  duration_min_hrs numeric     NOT NULL,
  duration_max_hrs numeric     NOT NULL,
  total_walk_km    numeric     NOT NULL,
  total_transit_km numeric,

  -- (L) required — flexibility note shown to the user
  flex_note        jsonb       NOT NULL
    CHECK ((flex_note->>'es') IS NOT NULL AND flex_note->>'es' <> ''),

  is_recommended   boolean     NOT NULL DEFAULT false,
  -- Night routes (is_premium=true) require the Pass pack.
  is_premium       boolean     NOT NULL DEFAULT false,
  rank_order       int         NOT NULL
);

CREATE INDEX idx_itineraries_city_rank ON itineraries (city_id, rank_order);

-- ============================================================
-- 7. itinerary_steps
-- ============================================================

CREATE TABLE itinerary_steps (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  itinerary_id          uuid        NOT NULL REFERENCES itineraries(id) ON DELETE CASCADE,
  rank_order            int         NOT NULL,
  spot_id               uuid        REFERENCES spots(id) ON DELETE SET NULL,

  -- (L) title populated only when the step has no linked spot
  title                 jsonb
    CHECK (title IS NULL
      OR ((title->>'es') IS NOT NULL AND title->>'es' <> '')),

  address               text,

  -- (L) required
  description           jsonb       NOT NULL
    CHECK ((description->>'es') IS NOT NULL AND description->>'es' <> ''),
  bon_vivant_notes      jsonb       NOT NULL
    CHECK ((bon_vivant_notes->>'es') IS NOT NULL AND bon_vivant_notes->>'es' <> ''),

  -- (L) nullable
  must_try              jsonb
    CHECK (must_try IS NULL
      OR ((must_try->>'es') IS NOT NULL AND must_try->>'es' <> '')),
  reservation           jsonb
    CHECK (reservation IS NULL
      OR ((reservation->>'es') IS NOT NULL AND reservation->>'es' <> '')),

  website               text,
  distance_from_prev_km numeric,
  travel_mode           travel_mode,
  time_on_site_min      smallint    NOT NULL,
  time_on_site_max      smallint    NOT NULL
);

CREATE INDEX idx_itinerary_steps_itin_rank ON itinerary_steps (itinerary_id, rank_order);

-- ============================================================
-- 8. tips  (replaces manuel_tips + city_warnings from 001)
-- city_id NULL = home carousel (always visible)
-- city_id set  = city-specific tip (visible when city is published)
-- ============================================================

CREATE TABLE tips (
  id          uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id     uuid  REFERENCES cities(id) ON DELETE CASCADE,  -- nullable
  title       jsonb NOT NULL
    CHECK ((title->>'es') IS NOT NULL AND title->>'es' <> ''),
  body        jsonb NOT NULL
    CHECK ((body->>'es') IS NOT NULL AND body->>'es' <> ''),
  rank_order  int   NOT NULL
);

CREATE INDEX idx_tips_city_rank ON tips (city_id, rank_order);

-- ============================================================
-- 9. images
-- ============================================================

CREATE TABLE images (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id      uuid        NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  spot_id      uuid        REFERENCES spots(id) ON DELETE CASCADE,  -- nullable
  slot         image_slot  NOT NULL,
  storage_path text        NOT NULL,

  -- (L) nullable
  alt_text     jsonb
    CHECK (alt_text IS NULL
      OR ((alt_text->>'es') IS NOT NULL AND alt_text->>'es' <> ''))
);

-- One image per slot per city (city-level images, no spot)
CREATE UNIQUE INDEX uq_images_city_slot
  ON images (city_id, slot)
  WHERE spot_id IS NULL;

-- One image per spot
CREATE UNIQUE INDEX uq_images_spot
  ON images (spot_id)
  WHERE spot_id IS NOT NULL;

-- ============================================================
-- 10. pack_cities  (FK to packs from 001 is preserved)
-- ============================================================

CREATE TABLE pack_cities (
  pack_id uuid NOT NULL REFERENCES packs(id)  ON DELETE CASCADE,
  city_id uuid NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  PRIMARY KEY (pack_id, city_id)
);

CREATE INDEX idx_pack_cities_pack_id ON pack_cities (pack_id);
CREATE INDEX idx_pack_cities_city_id ON pack_cities (city_id);

-- ============================================================
-- 11. Row Level Security
-- The backend uses service_role which bypasses RLS.
-- These policies are defence-in-depth for direct DB access.
-- Access control (is_unlocked) is computed in access_service.py.
-- ============================================================

ALTER TABLE cities          ENABLE ROW LEVEL SECURITY;
ALTER TABLE spots           ENABLE ROW LEVEL SECURITY;
ALTER TABLE itineraries     ENABLE ROW LEVEL SECURITY;
ALTER TABLE itinerary_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE tips            ENABLE ROW LEVEL SECURITY;
ALTER TABLE images          ENABLE ROW LEVEL SECURITY;
ALTER TABLE pack_cities     ENABLE ROW LEVEL SECURITY;

-- Authenticated users may only read published cities.
CREATE POLICY "cities: authenticated read published"
  ON cities FOR SELECT TO authenticated
  USING (status = 'published');

-- Spots are readable only when their parent city is published.
CREATE POLICY "spots: authenticated read via published city"
  ON spots FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );

-- Itineraries follow the same published-city gate as spots.
CREATE POLICY "itineraries: authenticated read via published city"
  ON itineraries FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );

-- Steps require the grandparent city to be published.
CREATE POLICY "itinerary_steps: authenticated read via published city"
  ON itinerary_steps FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM itineraries i
      JOIN cities c ON c.id = i.city_id
      WHERE i.id = itinerary_id AND c.status = 'published'
    )
  );

-- Home-carousel tips (city_id IS NULL) are always visible.
-- City-specific tips require the city to be published.
CREATE POLICY "tips: authenticated read home or published city"
  ON tips FOR SELECT TO authenticated
  USING (
    city_id IS NULL
    OR EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );

-- Images are readable only when the parent city is published.
CREATE POLICY "images: authenticated read via published city"
  ON images FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );

-- Pack-city mappings are public so clients can display pack contents before purchase.
CREATE POLICY "pack_cities: public read"
  ON pack_cities FOR SELECT
  USING (true);
