# Auditoría de seguridad y hardening — 2026-07-03

**Doc completo (formato largo, con tablas y checklist):**
https://elnucleo.atlassian.net/wiki/spaces/CDP/pages/32243713

**Commit de la remediación:** `34c38b8` — *fix: security hardening — RLS lockdown,
rate limiting, strict admin role*

## Por qué

El usuario pidió una auditoría de seguridad antes de meter pagos, login
Apple/Google y notificaciones — quería blindar la app antes de añadir las
piezas más sensibles. Se auditaron `bon-vivant-api` y `bon-vivant-mobile`
leyendo código real (no checklist genérica).

## Lo que se encontró

El backend en Python estaba bien construido (JWT verificado correctamente,
`{detail, code}` uniforme, lógica en `services/`). Los agujeros graves no
venían del código Python sino de las **políticas RLS de Supabase**: dejaban
una puerta lateral directa a los datos usando la *anon key* (pública por
diseño, va embebida en la app), saltándose por completo el backend.

### Crítico

1. **Auto-inserción de compras.** `user_purchases: insert own` (migración 001)
   permitía a cualquier usuario autenticado insertar filas en `user_purchases`
   directamente vía PostgREST con la anon key. Como `is_valid` tenía
   `DEFAULT true`, cualquiera se desbloqueaba todas las ciudades sin pagar.
2. **Contenido premium leíble sin comprar.** La migración 002 daba a
   `authenticated` lectura directa de `cities`/`spots`/`itineraries`/
   `itinerary_steps`/`tips`/`images` publicadas. El 403 del backend
   (`CityLockedError`) era cosmético — se podía leer todo igual consultando
   la tabla directamente.

### Alto / medio

3. Trip planner (feature de pago, Pass) sin verificación en el servidor —
   solo un blur en el cliente, saltable llamando la API directa.
4. Sesión de Supabase (access + refresh token) en `AsyncStorage` en texto
   plano en el móvil.
5. Sin rate limiting en ningún endpoint del backend.
6. `require_admin` aceptaba un fallback (`role == "admin"` a nivel top del
   JWT) que en tokens de Supabase es el rol de Postgres, no un rol de app —
   vía ambigua hacia `/admin/*`.
7. Nada impedía que el móvil consultara Supabase directamente en vez de pasar
   por la API (arquitectura, no bug puntual).

## Qué se corrigió

- **`supabase/migrations/006_security_hardening.sql`**:
  - Elimina el INSERT de `user_purchases` — ahora solo escribe el backend
    con `service_role` tras validar el receipt.
  - Retira los reads directos de contenido premium (cities/spots/itineraries/
    itinerary_steps/tips/images) — quedan con RLS activo y **cero policies**
    para `authenticated`/`anon` → deny by default. Todo pasa por la API.
  - Endurece `profiles` a `select own` / `update own` (antes el `USING` sin
    comando aplicaba a INSERT/DELETE también).
  - Añade `store_platform`, `store_transaction_id` (índice `UNIQUE` parcial),
    `validated_at` en `user_purchases` — anti-replay para receipts, usado
    después por `purchase_service.py` (ver [`../payments/`](../payments/)).
- **`app/api/deps.py`**: `require_admin` ya solo confía en
  `app_metadata.role`.
- **`app/core/rate_limit.py` + `app/main.py`**: rate limiting global
  (slowapi, 120/min por cliente, key por `X-Forwarded-For` para Railway) +
  cabeceras de seguridad (nosniff, X-Frame-Options DENY, HSTS en prod).
- **Mobile**: sesión cifrada con `expo-secure-store` (Keychain/Keystore) en
  vez de AsyncStorage en claro; regla ESLint que prohíbe `supabase.from(...)`
  en toda la app (boundary arquitectónico, no solo el fix puntual).
- **Pass gating del trip planner**: se separó en su propio commit
  `98754ab` (posterior), no en `34c38b8`. Ver
  [`../features/trip-planner.md`](../features/trip-planner.md).

## Verificado en vivo (no solo en el archivo de migración)

Las migraciones son la intención; lo que importa es el estado real de la
base de datos. Se corrió contra Supabase producción (proyecto `BonVivant`,
ref `dycumnhmkhqmmiknermb`):

```sql
SELECT schemaname, tablename, policyname, cmd, qual FROM pg_policies
WHERE tablename IN ('user_purchases','profiles','cities','spots',
                     'itineraries','itinerary_steps','tips','images');
```

Resultado (2026-07-03, después de `supabase db push`): solo aparecen
`profiles: select own`, `profiles: update own`, `user_purchases: select own`.
Ninguna policy de INSERT en `user_purchases`. Ninguna policy en las tablas de
contenido (RLS habilitado + cero policies = deny by default, confirmado).
`packs`/`pack_cities` siguen con lectura pública **a propósito** — son
nombres/precios de packs, contenido no sensible mostrado antes de comprar.

## Lo que quedó fuera del hardening (era trabajo de feature, no un bug)

- `POST /purchases/validate` no existía en el momento de la auditoría — se
  dejó la base de datos lista (columnas anti-replay) para cuando se
  construyera. **Ya está construido** — ver [`../payments/`](../payments/).
- Login Apple/Google — igual, era pendiente en el momento de la auditoría.

## Acciones manuales — estado

- [x] Migración 006 aplicada en Supabase (verificado con `pg_policies` en vivo).
- [x] `npm install` en mobile (deps de `expo-secure-store` ya en `package.json`).
- [ ] Rotar `service_role` / `JWT_SECRET` — **no hecho, y no hace falta**: se
      confirmó que `.env` nunca se commiteó (`git log --all -- .env` vacío) y
      no hay ninguna sospecha de filtración. Queda como acción disponible si
      algún día hay duda, no como pendiente activo.
