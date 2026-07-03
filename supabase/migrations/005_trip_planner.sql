-- ============================================================
-- 005_trip_planner.sql
--
-- Trip Planner: a user can create cruise trips (trips),
-- each with one day per calendar day (trip_days).
-- Days with city_slug link to existing guides; NULL = at sea.
--
-- Apply with: supabase db push
-- ============================================================

CREATE TABLE trips (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title         text NOT NULL,
  cruise_line   text NOT NULL,
  ship_name     text NOT NULL,
  start_date    date NOT NULL,
  end_date      date NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT end_after_start CHECK (end_date > start_date)
);

CREATE TABLE trip_days (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id             uuid NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  day_number          int NOT NULL,
  date                date NOT NULL,
  city_slug           text REFERENCES cities(slug) ON DELETE SET NULL,
  time_arrival        time,
  time_departure      time,
  departure_next_day  boolean NOT NULL DEFAULT false,
  UNIQUE (trip_id, day_number)
);

CREATE INDEX idx_trips_user_id        ON trips(user_id);
CREATE INDEX idx_trip_days_trip_id    ON trip_days(trip_id);
CREATE INDEX idx_trip_days_city_slug  ON trip_days(city_slug);

-- RLS
ALTER TABLE trips     ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_days ENABLE ROW LEVEL SECURITY;

-- trips: el usuario solo ve los suyos
CREATE POLICY trips_owner ON trips
  USING (user_id = auth.uid());

-- trip_days: el usuario solo ve días de sus trips
CREATE POLICY trip_days_owner ON trip_days
  USING (
    EXISTS (
      SELECT 1 FROM trips
      WHERE trips.id = trip_days.trip_id
        AND trips.user_id = auth.uid()
    )
  );
