-- ============================================================
-- 002_city_guide_schema.sql
-- i18n-ready guide model (Variante C).
-- Replaces the initial domain tables with the LocalizedText schema.
-- The backend resolves access (is_unlocked) in services/ — not via RLS.
-- ============================================================

-- Drop old domain tables. CASCADE removes FK-dependent objects:
-- spots, itineraries, itinerary_steps, manuel_tips, city_warnings, pack_cities.
DROP TABLE IF EXISTS cities CASCADE;
DROP TABLE IF EXISTS tips CASCADE;  -- Idempotent: recreated below.

-- ============================================================
-- Postgres enum types (idempotent)
-- ============================================================

DO $$ BEGIN CREATE TYPE spot_kind AS ENUM ('attraction', 'food');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE spot_category AS ENUM ('restaurant', 'cafe', 'bar');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE time_of_day AS ENUM ('day', 'night');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE travel_mode AS ENUM ('walk', 'transit', 'taxi');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE city_status AS ENUM ('draft', 'published');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE transport_method AS ENUM ('walk', 'metro', 'tram', 'taxi', 'train', 'ferry');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- Convention: LocalizedText (L) jsonb columns
-- Shape: {"es": text, "en": text|null, "fr": text|null}
-- Constraint: 'es' key is required and non-empty (canonical language).
-- ============================================================

-- ============================================================
-- cities
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

  -- (L) Port section
  port_description    jsonb        NOT NULL
    CHECK ((port_description->>'es') IS NOT NULL AND port_description->>'es' <> ''),
  distance_to_center  jsonb        NOT NULL
    CHECK ((distance_to_center->>'es') IS NOT NULL AND distance_to_center->>'es' <> ''),
  port_facilities     jsonb        NOT NULL
    CHECK ((port_facilities->>'es') IS NOT NULL AND port_facilities->>'es' <> ''),
  port_recommendation jsonb        NOT NULL
    CHECK ((port_recommendation->>'es') IS NOT NULL AND port_recommendation->>'es' <> ''),

  port_lat            double precision NOT NULL,
  port_lng            double precision NOT NULL,

  -- Structured jsonb arrays; sub-objects validated at the application layer.
  -- highlights:         [{label: (L), description: (L)}]
  -- transport_options:  [{method: transport_method, time_label: text, tips: (L)}]
  -- what_to_know:       [{heading: (L), text: (L)}]
  highlights          jsonb        NOT NULL DEFAULT '[]',
  transport_options   jsonb        NOT NULL DEFAULT '[]',
  what_to_know        jsonb        NOT NULL DEFAULT '[]',

  status              city_status  NOT NULL DEFAULT 'draft',
  last_verified       date,
  created_at          timestamptz  NOT NULL DEFAULT now(),
  updated_at          timestamptz  NOT NULL DEFAULT now()
);

-- Auto-update updated_at on any row modification.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER cities_updated_at
  BEFORE UPDATE ON cities
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- spots
-- ============================================================

CREATE TABLE spots (
  id                    uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id               uuid           NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  kind                  spot_kind      NOT NULL,
  category              spot_category,              -- Only for kind='food'
  name                  text           NOT NULL,
  address               text           NOT NULL,
  latitude              double precision NOT NULL,
  longitude             double precision NOT NULL,
  distance_from_port_km numeric        NOT NULL,
  rank_order            int            NOT NULL,
  website               text,

  -- (L) Common fields
  manuel_quote          jsonb          NOT NULL
    CHECK ((manuel_quote->>'es') IS NOT NULL AND manuel_quote->>'es' <> ''),
  reservation           jsonb
    CHECK (reservation IS NULL
      OR ((reservation->>'es') IS NOT NULL AND reservation->>'es' <> '')),

  -- (L) kind='attraction' only (nullable; kind validated at app layer)
  what_it_is            jsonb
    CHECK (what_it_is IS NULL
      OR ((what_it_is->>'es') IS NOT NULL AND what_it_is->>'es' <> '')),
  why_it_matters        jsonb
    CHECK (why_it_matters IS NULL
      OR ((why_it_matters->>'es') IS NOT NULL AND why_it_matters->>'es' <> '')),
  good_to_know          jsonb
    CHECK (good_to_know IS NULL
      OR ((good_to_know->>'es') IS NOT NULL AND good_to_know->>'es' <> '')),

  -- (L) kind='food' only (nullable; kind validated at app layer)
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

-- Composite index to support city feed sorted by kind+rank.
CREATE INDEX idx_spots_city_kind_rank ON spots(city_id, kind, rank_order);

-- ============================================================
-- itineraries
-- ============================================================

CREATE TABLE itineraries (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id          uuid        NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  theme            text        NOT NULL,
  time_of_day      time_of_day NOT NULL,

  -- (L) Editorial fields
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

  -- (L) Flexibility note shown to the user
  flex_note        jsonb       NOT NULL
    CHECK ((flex_note->>'es') IS NOT NULL AND flex_note->>'es' <> ''),

  is_recommended   boolean     NOT NULL DEFAULT false,
  -- Night routes (is_premium=true) require the Pass pack.
  is_premium       boolean     NOT NULL DEFAULT false,
  rank_order       int         NOT NULL
);

CREATE INDEX idx_itineraries_city_rank ON itineraries(city_id, rank_order);

-- ============================================================
-- itinerary_steps
-- ============================================================

CREATE TABLE itinerary_steps (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  itinerary_id          uuid        NOT NULL REFERENCES itineraries(id) ON DELETE CASCADE,
  rank_order            int         NOT NULL,
  spot_id               uuid        REFERENCES spots(id) ON DELETE SET NULL,

  -- (L) title only populated when the step has no spot
  title                 jsonb
    CHECK (title IS NULL
      OR ((title->>'es') IS NOT NULL AND title->>'es' <> '')),

  description           jsonb       NOT NULL
    CHECK ((description->>'es') IS NOT NULL AND description->>'es' <> ''),
  bon_vivant_notes      jsonb       NOT NULL
    CHECK ((bon_vivant_notes->>'es') IS NOT NULL AND bon_vivant_notes->>'es' <> ''),

  -- rank_order=1 means distance from port; NULL = no movement
  distance_from_prev_km numeric,
  travel_mode           travel_mode,

  time_on_site_min      int         NOT NULL,
  time_on_site_max      int         NOT NULL
);

CREATE INDEX idx_itinerary_steps_itinerary_rank ON itinerary_steps(itinerary_id, rank_order);

-- ============================================================
-- tips (replaces manuel_tips + city_warnings from migration 001)
-- city_id NULL  → home carousel (general tips)
-- city_id set   → city-specific tip
-- ============================================================

CREATE TABLE tips (
  id          uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id     uuid  REFERENCES cities(id) ON DELETE CASCADE,
  title       jsonb NOT NULL
    CHECK ((title->>'es') IS NOT NULL AND title->>'es' <> ''),
  body        jsonb NOT NULL
    CHECK ((body->>'es') IS NOT NULL AND body->>'es' <> ''),
  rank_order  int   NOT NULL
);

CREATE INDEX idx_tips_city_rank ON tips(city_id, rank_order);

-- ============================================================
-- pack_cities (recreated with FK to new cities table)
-- ============================================================

CREATE TABLE pack_cities (
  pack_id uuid NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  city_id uuid NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  PRIMARY KEY (pack_id, city_id)
);

CREATE INDEX idx_pack_cities_pack_id ON pack_cities(pack_id);
CREATE INDEX idx_pack_cities_city_id ON pack_cities(city_id);

-- ============================================================
-- Row Level Security
-- The backend uses service_role (bypasses RLS) for all queries.
-- These policies are a defence-in-depth layer for direct DB access.
-- Access control (is_unlocked) is computed in app/services/access_service.py.
-- ============================================================

ALTER TABLE cities          ENABLE ROW LEVEL SECURITY;
ALTER TABLE spots           ENABLE ROW LEVEL SECURITY;
ALTER TABLE itineraries     ENABLE ROW LEVEL SECURITY;
ALTER TABLE itinerary_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE tips            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pack_cities     ENABLE ROW LEVEL SECURITY;

-- Authenticated users see only published cities.
CREATE POLICY "cities: authenticated read published"
  ON cities FOR SELECT TO authenticated
  USING (status = 'published');
COMMENT ON POLICY "cities: authenticated read published" ON cities IS
  'Draft cities are invisible to authenticated users. The backend uses service_role.';

-- Spots belong to a city; only visible when the city is published.
CREATE POLICY "spots: authenticated read published city"
  ON spots FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );
COMMENT ON POLICY "spots: authenticated read published city" ON spots IS
  'Spots are accessible only when their parent city is published.';

-- Itineraries follow the same rule as spots.
CREATE POLICY "itineraries: authenticated read published city"
  ON itineraries FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );
COMMENT ON POLICY "itineraries: authenticated read published city" ON itineraries IS
  'Itineraries are accessible only when their parent city is published.';

-- Steps require the parent itinerary city to be published.
CREATE POLICY "itinerary_steps: authenticated read published city"
  ON itinerary_steps FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM itineraries i
      JOIN cities c ON c.id = i.city_id
      WHERE i.id = itinerary_id AND c.status = 'published'
    )
  );
COMMENT ON POLICY "itinerary_steps: authenticated read published city" ON itinerary_steps IS
  'Steps are accessible only when their grandparent city is published.';

-- Home carousel tips (city_id IS NULL) are always visible.
-- City-specific tips require the city to be published.
CREATE POLICY "tips: authenticated read"
  ON tips FOR SELECT TO authenticated
  USING (
    city_id IS NULL
    OR EXISTS (
      SELECT 1 FROM cities c
      WHERE c.id = city_id AND c.status = 'published'
    )
  );
COMMENT ON POLICY "tips: authenticated read" ON tips IS
  'General tips (city_id NULL) are always visible; city tips require published status.';

-- Pack-city mappings are public — clients need them to display pack contents.
CREATE POLICY "pack_cities: public read"
  ON pack_cities FOR SELECT
  USING (true);
COMMENT ON POLICY "pack_cities: public read" ON pack_cities IS
  'Pack contents are public; actual access is controlled via user_purchases.';
