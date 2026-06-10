-- ============================================================
-- 003_spots_nullable_coords.sql
--
-- Make spots.latitude and spots.longitude nullable.
--
-- Motivation: guide addresses are sometimes approximate and
-- geocoding is best-effort. Inserting with null coordinates
-- and flagging for review is preferable to blocking the whole
-- import. (itinerary_steps and cities.port_lat/lng already
-- allow null and are not touched by this migration.)
--
-- Apply with:  supabase db push
--   or manually via the Supabase SQL editor.
-- ============================================================

ALTER TABLE spots ALTER COLUMN latitude  DROP NOT NULL;
ALTER TABLE spots ALTER COLUMN longitude DROP NOT NULL;
