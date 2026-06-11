-- ============================================================
-- 004_itinerary_steps_nullable_fields.sql
--
-- Make bon_vivant_notes, time_on_site_min and time_on_site_max
-- nullable in itinerary_steps.
--
-- Motivation: transit-only steps ("back to ship") have no
-- editorial notes or visit duration. Blocking the import for
-- missing data that genuinely does not exist is wrong.
--
-- Apply with:  supabase db push
--   or manually via the Supabase SQL editor.
-- ============================================================

ALTER TABLE itinerary_steps ALTER COLUMN bon_vivant_notes DROP NOT NULL;
ALTER TABLE itinerary_steps DROP CONSTRAINT IF EXISTS itinerary_steps_bon_vivant_notes_check;
ALTER TABLE itinerary_steps ALTER COLUMN time_on_site_min  DROP NOT NULL;
ALTER TABLE itinerary_steps ALTER COLUMN time_on_site_max  DROP NOT NULL;
