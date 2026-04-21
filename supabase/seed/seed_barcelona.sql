-- ============================================================
-- seed_barcelona.sql
-- Run AFTER 001_initial_schema.sql
-- ============================================================

-- ============================================================
-- City: Barcelona
-- ============================================================

INSERT INTO cities (
  id, slug, name, country, region,
  cover_image_url, overview_text,
  port_distance_km, estimated_budget_eur,
  transport_info,
  is_free_tier, is_published
) VALUES (
  'a1000000-0000-0000-0000-000000000001',
  'barcelona',
  'Barcelona',
  'Spain',
  'Catalonia',
  'https://images.unsplash.com/photo-1579282240050-352db0a14c21?w=1200',
  'Barcelona is a city that lives outdoors. From the Barceloneta beach to the winding lanes of the Gothic Quarter, every corner rewards the curious. The port of Barcelona is right in the heart of the action — you can walk to the Ramblas in 15 minutes.',
  0.8,
  80,
  'The port is a 15-min walk to La Barceloneta and Las Ramblas. Metro L3 (green line) from Drassanes station covers the whole city. Day pass is €11.35. Taxis are metered and reliable.',
  true,
  true
);

-- ============================================================
-- Spots (3): 1 restaurant, 1 activity, 1 cafe
-- ============================================================

-- 1. Restaurant
INSERT INTO spots (
  id, city_id, name, category, description, manuel_quote,
  price_range, price_min_eur, price_max_eur,
  distance_from_port_km, latitude, longitude,
  image_url, rank_order
) VALUES (
  'b1000000-0000-0000-0000-000000000001',
  'a1000000-0000-0000-0000-000000000001',
  'Bar del Pla',
  'restaurant',
  'A beloved Catalan tapas bar in the Born neighbourhood. Order the croquetas and the patatas bravas — they are genuinely among the best in the city.',
  'Ignore the tourists and grab a stool at the bar. The croquetas here changed how I think about croquetas.',
  2,
  15,
  35,
  2.1,
  41.3841,
  2.1797,
  'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800',
  1
);

-- 2. Activity
INSERT INTO spots (
  id, city_id, name, category, description, manuel_quote,
  price_range, price_min_eur, price_max_eur,
  distance_from_port_km, latitude, longitude,
  image_url, rank_order
) VALUES (
  'b1000000-0000-0000-0000-000000000002',
  'a1000000-0000-0000-0000-000000000001',
  'Park Güell',
  'activity',
  'Gaudí''s mosaic terrace and gingerbread gatehouses sit above the city with sweeping views over Barcelona and out to the sea. Book timed entry tickets online — the queue without them is brutal.',
  'Go right when the gates open at 9:30. The main terrace is magical before the crowds arrive. Skip the paid zone if you''re short on time — the free park is worth the walk alone.',
  2,
  10,
  10,
  5.8,
  41.4145,
  2.1527,
  'https://images.unsplash.com/photo-1583422409516-2895a77efded?w=800',
  2
);

-- 3. Cafe
INSERT INTO spots (
  id, city_id, name, category, description, manuel_quote,
  price_range, price_min_eur, price_max_eur,
  distance_from_port_km, latitude, longitude,
  image_url, rank_order
) VALUES (
  'b1000000-0000-0000-0000-000000000003',
  'a1000000-0000-0000-0000-000000000001',
  'Cafè de l''Acadèmia',
  'cafe',
  'A hidden gem tucked into a small square in the Gothic Quarter. Stone walls, wooden beams, and some of the best coffee in the old city. Ideal for a mid-morning break.',
  'One espresso here and you''ll never go back to hotel coffee. Ask for a glass of water — they always bring it cold.',
  1,
  3,
  8,
  1.2,
  41.3826,
  2.1764,
  'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800',
  3
);

-- ============================================================
-- Itinerary: 4-hour Barcelona highlights
-- ============================================================

INSERT INTO itineraries (
  id, city_id, duration_hours, title, description
) VALUES (
  'c1000000-0000-0000-0000-000000000001',
  'a1000000-0000-0000-0000-000000000001',
  4,
  'Barcelona in 4 Hours',
  'The perfect port-day loop: Gothic Quarter coffee, Born tapas, and Barceloneta sunset. All walkable from the cruise terminal.'
);

-- Step 1: Cafe
INSERT INTO itinerary_steps (
  id, itinerary_id, spot_id, order_index, time_from, time_to,
  title, description
) VALUES (
  'd1000000-0000-0000-0000-000000000001',
  'c1000000-0000-0000-0000-000000000001',
  'b1000000-0000-0000-0000-000000000003',
  1,
  '09:30', '10:00',
  'Morning coffee in the Gothic Quarter',
  'Start with an espresso at Cafè de l''Acadèmia. Take five minutes to wander the tiny square outside — it looks like a film set.'
);

-- Step 2: Activity
INSERT INTO itinerary_steps (
  id, itinerary_id, spot_id, order_index, time_from, time_to,
  title, description
) VALUES (
  'd1000000-0000-0000-0000-000000000002',
  'c1000000-0000-0000-0000-000000000001',
  'b1000000-0000-0000-0000-000000000002',
  2,
  '10:15', '12:00',
  'Park Güell',
  'Take the Metro L3 from Liceu to Lesseps (20 min). Enter via the North gate to skip the main queue. Allow 90 minutes on the terrace and the free park.'
);

-- Step 3: Restaurant
INSERT INTO itinerary_steps (
  id, itinerary_id, spot_id, order_index, time_from, time_to,
  title, description
) VALUES (
  'd1000000-0000-0000-0000-000000000003',
  'c1000000-0000-0000-0000-000000000001',
  'b1000000-0000-0000-0000-000000000001',
  3,
  '13:00', '14:30',
  'Tapas lunch at Bar del Pla',
  'Head to the Born district for lunch. Bar del Pla gets busy by 13:30 — arrive on the dot or wait. Order the croquetas, patatas bravas, and a cold Estrella.'
);

-- ============================================================
-- Manuel Tips (city-specific: 2 for Barcelona)
-- ============================================================

INSERT INTO manuel_tips (id, city_id, content, order_index) VALUES (
  'e1000000-0000-0000-0000-000000000001',
  'a1000000-0000-0000-0000-000000000001',
  'The port shuttle to La Barceloneta costs €4 return and saves 20 minutes. Not worth it. The walk along the waterfront is the best part of the day.',
  1
);

INSERT INTO manuel_tips (id, city_id, content, order_index) VALUES (
  'e1000000-0000-0000-0000-000000000002',
  'a1000000-0000-0000-0000-000000000001',
  'Pickpockets are active on Las Ramblas and at La Boqueria. Keep your phone in your front pocket and your bag closed. The Gothic Quarter side streets are totally fine.',
  2
);

-- ============================================================
-- Manuel Tip (general — city_id NULL, for Home carousel)
-- ============================================================

INSERT INTO manuel_tips (id, city_id, content, order_index) VALUES (
  'e1000000-0000-0000-0000-000000000003',
  NULL,
  'A cruise port day is never enough. My job is to help you spend zero minutes deciding and every minute experiencing. Trust the itinerary — it''s been walked, timed, and eaten.',
  1
);

-- ============================================================
-- Packs (4 matching the business model)
-- ============================================================

INSERT INTO packs (id, name, price_eur, city_count, is_unlimited, store_product_id) VALUES (
  'f1000000-0000-0000-0000-000000000001',
  'Starter',
  9.99,
  3,
  false,
  'com.bonvivant.pack.starter'
);

INSERT INTO packs (id, name, price_eur, city_count, is_unlimited, store_product_id) VALUES (
  'f1000000-0000-0000-0000-000000000002',
  '5 Cities',
  19.99,
  5,
  false,
  'com.bonvivant.pack.five_cities'
);

INSERT INTO packs (id, name, price_eur, city_count, is_unlimited, store_product_id) VALUES (
  'f1000000-0000-0000-0000-000000000003',
  'Cruise Pack',
  24.99,
  7,
  false,
  'com.bonvivant.pack.cruise'
);

INSERT INTO packs (id, name, price_eur, city_count, is_unlimited, store_product_id) VALUES (
  'f1000000-0000-0000-0000-000000000004',
  'Unlimited',
  49.99,
  NULL,
  true,
  'com.bonvivant.pack.unlimited'
);

-- Link Barcelona to all packs
INSERT INTO pack_cities (pack_id, city_id) VALUES
  ('f1000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001'),
  ('f1000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000001'),
  ('f1000000-0000-0000-0000-000000000003', 'a1000000-0000-0000-0000-000000000001'),
  ('f1000000-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000001');
