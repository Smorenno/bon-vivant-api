-- ============================================================
-- 001_initial_schema.sql
-- ============================================================

-- profiles -------------------------------------------------
CREATE TABLE profiles (
  id                    uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email                 text,
  full_name             text,
  cruise_departure_date date,
  onboarding_completed  boolean DEFAULT false,
  created_at            timestamptz DEFAULT now()
);

-- cities ---------------------------------------------------
CREATE TABLE cities (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                  text UNIQUE NOT NULL,
  name                  text,
  country               text,
  region                text,
  cover_image_url       text,
  overview_text         text,
  port_distance_km      decimal,
  estimated_budget_eur  int,
  transport_info        text,
  is_free_tier          boolean DEFAULT false,
  is_published          boolean DEFAULT false
);

-- packs ----------------------------------------------------
CREATE TABLE packs (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text,
  price_eur        decimal,
  city_count       int,
  is_unlimited     boolean DEFAULT false,
  store_product_id text
);

-- pack_cities ----------------------------------------------
CREATE TABLE pack_cities (
  pack_id uuid NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  city_id uuid NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  PRIMARY KEY (pack_id, city_id)
);

-- user_purchases -------------------------------------------
CREATE TABLE user_purchases (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  pack_id      uuid NOT NULL REFERENCES packs(id),
  purchased_at timestamptz DEFAULT now(),
  receipt_data text,
  is_valid     boolean DEFAULT true
);

-- spots ----------------------------------------------------
CREATE TABLE spots (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id               uuid NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  name                  text,
  category              text CHECK (category IN ('restaurant','activity','cafe','bar')),
  description           text,
  manuel_quote          text,
  price_range           int,
  price_min_eur         int,
  price_max_eur         int,
  distance_from_port_km decimal,
  latitude              decimal,
  longitude             decimal,
  image_url             text,
  rank_order            int
);

-- itineraries ----------------------------------------------
CREATE TABLE itineraries (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id        uuid NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  duration_hours int,
  title          text,
  description    text
);

-- itinerary_steps ------------------------------------------
CREATE TABLE itinerary_steps (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  itinerary_id   uuid NOT NULL REFERENCES itineraries(id) ON DELETE CASCADE,
  spot_id        uuid REFERENCES spots(id) ON DELETE SET NULL,
  order_index    int,
  time_from      time,
  time_to        time,
  title          text,
  description    text
);

-- manuel_tips ----------------------------------------------
CREATE TABLE manuel_tips (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id     uuid REFERENCES cities(id) ON DELETE CASCADE,
  content     text,
  order_index int
);

-- city_warnings --------------------------------------------
CREATE TABLE city_warnings (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  city_id     uuid NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  content     text,
  order_index int
);

-- ============================================================
-- Row Level Security
-- ============================================================

ALTER TABLE profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cities         ENABLE ROW LEVEL SECURITY;
ALTER TABLE packs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE pack_cities    ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE spots          ENABLE ROW LEVEL SECURITY;
ALTER TABLE itineraries    ENABLE ROW LEVEL SECURITY;
ALTER TABLE itinerary_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE manuel_tips    ENABLE ROW LEVEL SECURITY;
ALTER TABLE city_warnings  ENABLE ROW LEVEL SECURITY;

-- Basic RLS policies:
-- profiles: users can only read/update their own row
CREATE POLICY "profiles: own row" ON profiles
  USING (auth.uid() = id);

-- public read for published content
CREATE POLICY "cities: public read published" ON cities
  FOR SELECT USING (is_published = true);

CREATE POLICY "packs: public read" ON packs
  FOR SELECT USING (true);

CREATE POLICY "pack_cities: public read" ON pack_cities
  FOR SELECT USING (true);

CREATE POLICY "spots: public read" ON spots
  FOR SELECT USING (true);

CREATE POLICY "itineraries: public read" ON itineraries
  FOR SELECT USING (true);

CREATE POLICY "itinerary_steps: public read" ON itinerary_steps
  FOR SELECT USING (true);

CREATE POLICY "manuel_tips: public read" ON manuel_tips
  FOR SELECT USING (true);

CREATE POLICY "city_warnings: public read" ON city_warnings
  FOR SELECT USING (true);

-- user_purchases: users see only their own
CREATE POLICY "user_purchases: own rows" ON user_purchases
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "user_purchases: insert own" ON user_purchases
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- ============================================================
-- Indexes on foreign keys
-- ============================================================

CREATE INDEX idx_pack_cities_pack_id        ON pack_cities(pack_id);
CREATE INDEX idx_pack_cities_city_id        ON pack_cities(city_id);
CREATE INDEX idx_user_purchases_user_id     ON user_purchases(user_id);
CREATE INDEX idx_user_purchases_pack_id     ON user_purchases(pack_id);
CREATE INDEX idx_spots_city_id              ON spots(city_id);
CREATE INDEX idx_itineraries_city_id        ON itineraries(city_id);
CREATE INDEX idx_itinerary_steps_itinerary  ON itinerary_steps(itinerary_id);
CREATE INDEX idx_itinerary_steps_spot       ON itinerary_steps(spot_id);
CREATE INDEX idx_manuel_tips_city_id        ON manuel_tips(city_id);
CREATE INDEX idx_city_warnings_city_id      ON city_warnings(city_id);

-- ============================================================
-- Trigger: auto-create profile on new auth user
-- ============================================================

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, created_at)
  VALUES (NEW.id, NEW.email, now())
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
