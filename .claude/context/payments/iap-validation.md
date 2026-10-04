# Validación de compras In-App (Apple / Google)

**Commits:** `ed46d3a` (*IAP receipt validation, restore, GET /packs*),
`b333ef6` (*x5c chain verification*)

Implementa lo que la [auditoría de seguridad](../security/2026-07-audit-and-hardening.md)
dejó como hueco crítico: nunca confiar en el cliente para decidir si algo
está pagado. Cada compra se valida contra el store real antes de tocar
`user_purchases`.

## Endpoints (`app/api/v1/endpoints/purchases.py`, `packs.py`)

- `GET /packs` — [public] lista de packs con precio/ciudades, para la tienda.
- `POST /purchases/validate` — [auth] valida un receipt y desbloquea el pack.
  Rate limit propio: **10/min** (más estricto que el global de 120/min, es
  el endpoint más sensible de toda la API).
- `POST /purchases/restore` — [auth] re-sincroniza compras ya hechas en el
  store (cambio de dispositivo). Mismo rate limit.
- `GET /purchases/me` — [auth] compras válidas del usuario.

## Cómo se verifica (`app/services/store_verifier.py`)

Capa HTTP pura — nunca decide qué hacer con el resultado, solo verifica y
levanta excepciones (`ReceiptInvalidError`, `StoreUnavailableError`,
`StoreNotConfiguredError`) que `purchase_service.py` traduce al schema
público `{detail, code}`. **El motivo real del rechazo nunca llega al
cliente** — solo a los logs del servidor.

- **iOS** → App Store Server API (no el `verifyReceipt` deprecado). Se
  autentica con un JWT ES256 propio (`aud=appstoreconnect-v1`, firmado con
  la clave `.p8` de Apple). El cliente manda el `Transaction.id`
  (StoreKit 2); el backend pide el JWS firmado a Apple por ese id — los
  datos que se validan siempre vienen de Apple, nunca del cliente.
  Reintenta contra sandbox si producción da 404 (comportamiento normal para
  transacciones de TestFlight/App Review).
- **Android** → Google Play Developer API
  (`purchases.products.get`), autenticado con OAuth2 JWT-bearer usando la
  service account (sin SDK de Google). Confirma `purchaseState == 0`
  (comprado) y hace *acknowledge* server-side si falta (Google reembolsa
  automático lo no reconocido en 3 días).
- **Verificación de firma x5c (defensa en profundidad)** — detrás del flag
  `VERIFY_APPLE_CERT_CHAIN` (**off por defecto**). Off = modo "confía en
  TLS" (la respuesta ya vino de Apple por HTTPS, se decodifica el payload
  sin verificar firma local). On = verifica la cadena x5c contra la
  Apple Root CA - G3 pineada en `app/core/certs/apple_root_ca_g3.pem`
  (`app/core/apple_certs.py`) y la firma del JWS contra la leaf key. Un
  fallo aquí con el flag activo se loguea como posible tampering (MITM,
  proxy TLS corporativo) — no como error de usuario normal.

## Anti-replay (usa lo que dejó la migración 006)

`user_purchases.store_transaction_id` tiene un índice **`UNIQUE` parcial**
(`WHERE store_transaction_id IS NOT NULL`). `_record_purchase()` inserta
directamente y captura la violación de Postgres (`23505`) → `409
receipt_already_used`. Así un mismo receipt no se puede canjear dos veces
ni en cuentas distintas, sin necesidad de un `SELECT` previo (evita el
race condition de check-then-insert).

## Lo que falta configurar (no es código, son credenciales)

Todo es opcional a nivel de arranque — sin configurar, `/purchases/validate`
responde `503 validation_unavailable` de forma controlada en vez de romper.
Buscar `TODO(iap)` en el repo para la lista completa de puntos exactos:

| Variable | De dónde sale | Estado |
|---|---|---|
| `APPLE_ISSUER_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` | App Store Connect → Users and Access → Integrations → In-App Purchase keys | **Pendiente** — no existe cuenta de Apple Developer todavía |
| `VERIFY_APPLE_CERT_CHAIN` | flag propio | `false` — probar contra sandbox antes de activar en prod |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Play Console → API access → service account ("View financial data") | **Pendiente** — no existe cuenta de Play Console todavía |
| `APP_BUNDLE_ID` | fijo | ya puesto: `com.bonvivant.app` |

Plantilla con comentarios ya en `.env.example`.

## Pendientes técnicos explícitos (TODOs en código)

- Probar el fallback sandbox de Apple (404 en producción → reintento
  sandbox) con un tester real una vez exista la cuenta.
- Confirmar que el *acknowledge* de Google funciona end-to-end con una
  compra de license-tester.
- Activar `VERIFY_APPLE_CERT_CHAIN=true` después de probarlo contra
  transacciones sandbox reales — hoy va en modo trust-TLS.
