-- ============================================================
-- 006_security_hardening.sql
--
-- Security audit remediation. Idempotent — safe to re-run and
-- safe whether or not the legacy 001 policies were ever applied.
--
-- Threat model: the mobile app ships the Supabase *anon* key
-- (public by design) and any logged-in user holds a valid JWT.
-- Therefore ANY RLS policy granted to `authenticated`/`anon` is
-- reachable directly via PostgREST, bypassing the FastAPI backend.
-- The backend is the only trusted actor: it uses `service_role`,
-- which bypasses RLS, and computes access (is_unlocked) in Python.
--
-- Goals:
--   1. Kill the paywall bypass: users could self-insert rows into
--      user_purchases (DEFAULT is_valid=true) and unlock everything.
--   2. Kill the content bypass: premium city content was directly
--      readable via the anon key regardless of purchase.
--   3. Tighten profiles to own-row SELECT/UPDATE only.
--   4. Prepare user_purchases for anti-replay receipt validation.
-- ============================================================

-- ------------------------------------------------------------
-- 1. user_purchases — the critical fix.
--    Remove the client INSERT capability entirely. Purchases are
--    written ONLY by the backend (service_role) after a receipt is
--    verified against App Store / Google Play. Clients may read
--    their own rows and nothing else.
-- ------------------------------------------------------------

DROP POLICY IF EXISTS "user_purchases: insert own"  ON user_purchases;
DROP POLICY IF EXISTS "user_purchases: own rows"    ON user_purchases;
DROP POLICY IF EXISTS "user_purchases: update own"  ON user_purchases;
DROP POLICY IF EXISTS "user_purchases: delete own"  ON user_purchases;

ALTER TABLE user_purchases ENABLE ROW LEVEL SECURITY;
-- Belt-and-braces: force RLS even for the table owner role.
ALTER TABLE user_purchases FORCE ROW LEVEL SECURITY;

-- Read-only for the owner. No INSERT/UPDATE/DELETE policy exists,
-- so every write from `authenticated`/`anon` is denied by default.
-- service_role bypasses RLS, so the backend still writes freely.
CREATE POLICY "user_purchases: select own"
  ON user_purchases FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- ------------------------------------------------------------
-- 2. Anti-replay / idempotency scaffolding for POST /purchases/validate.
--    A store transaction can only ever map to a single row, so the
--    same receipt cannot be redeemed twice or across accounts.
-- ------------------------------------------------------------

ALTER TABLE user_purchases
  ADD COLUMN IF NOT EXISTS store_platform       text
    CHECK (store_platform IN ('ios', 'android')),
  ADD COLUMN IF NOT EXISTS store_transaction_id text,
  ADD COLUMN IF NOT EXISTS validated_at         timestamptz;

-- One transaction id = one purchase row, globally. NULLs are allowed
-- (legacy rows) and are not deduplicated by a UNIQUE index.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_purchases_store_txn
  ON user_purchases (store_transaction_id)
  WHERE store_transaction_id IS NOT NULL;

-- ------------------------------------------------------------
-- 3. profiles — own-row SELECT + UPDATE only.
--    The old "profiles: own row" policy used a bare USING clause with
--    no command, which applies to ALL commands (incl. INSERT/DELETE).
--    Profile rows are created by the SECURITY DEFINER auth trigger and
--    deleted via the backend (DELETE /me, service_role), so clients
--    need neither INSERT nor DELETE here.
-- ------------------------------------------------------------

DROP POLICY IF EXISTS "profiles: own row"    ON profiles;
DROP POLICY IF EXISTS "profiles: select own" ON profiles;
DROP POLICY IF EXISTS "profiles: update own" ON profiles;

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles: select own"
  ON profiles FOR SELECT TO authenticated
  USING (auth.uid() = id);

CREATE POLICY "profiles: update own"
  ON profiles FOR UPDATE TO authenticated
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- ------------------------------------------------------------
-- 4. Premium content — close the direct-read bypass.
--    Migration 002 granted `authenticated` direct SELECT on published
--    cities and their children. Because the anon key is public, that
--    let any logged-in user read paid city content directly, skipping
--    the paywall the backend enforces. Remove those grants; all guide
--    content now flows exclusively through the service_role backend,
--    which decides access per purchase.
--
--    (The mobile client already reads 100% of this content via the
--    REST API, never via supabase.from(...), so nothing breaks.)
-- ------------------------------------------------------------

-- 002-era policy names:
DROP POLICY IF EXISTS "cities: authenticated read published"            ON cities;
DROP POLICY IF EXISTS "spots: authenticated read via published city"    ON spots;
DROP POLICY IF EXISTS "itineraries: authenticated read via published city"   ON itineraries;
DROP POLICY IF EXISTS "itinerary_steps: authenticated read via published city" ON itinerary_steps;
DROP POLICY IF EXISTS "tips: authenticated read home or published city" ON tips;
DROP POLICY IF EXISTS "images: authenticated read via published city"   ON images;

-- Legacy 001-era policy names (no-ops if the tables were recreated by 002):
DROP POLICY IF EXISTS "cities: public read published"     ON cities;
DROP POLICY IF EXISTS "spots: public read"                ON spots;
DROP POLICY IF EXISTS "itineraries: public read"          ON itineraries;
DROP POLICY IF EXISTS "itinerary_steps: public read"      ON itinerary_steps;

-- RLS stays enabled with no permissive policy → default deny for
-- anon/authenticated. service_role continues to bypass RLS.
ALTER TABLE cities          ENABLE ROW LEVEL SECURITY;
ALTER TABLE spots           ENABLE ROW LEVEL SECURITY;
ALTER TABLE itineraries     ENABLE ROW LEVEL SECURITY;
ALTER TABLE itinerary_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE tips            ENABLE ROW LEVEL SECURITY;
ALTER TABLE images          ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 5. packs / pack_cities — intentionally remain public read.
--    These hold only pack names, decoy pricing and city membership,
--    shown in the store BEFORE purchase. No sensitive data. Left as
--    defined in 001/002. (Documented here so the asymmetry is explicit.)
-- ------------------------------------------------------------
