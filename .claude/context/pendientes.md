# Pendientes — bon-vivant-api

> Lista viva. Cuando cierres algo, bórralo. Cuando aparezca algo nuevo,
> añádelo con el archivo concreto. Última actualización: 2026-10-04.

## Tipografía por guía — en pausa

Detalle completo en [`features/guide-fonts.md`](features/guide-fonts.md).
El código y la migración están hechos; falta contenido y decisiones.

- [x] Migración `007_guide_fonts.sql` aplicada en Supabase (2026-10-04).
- [ ] **Licencia de Pathos.** Tiene que permitir servirla desde servidor a una
      app, no solo embeberla. Hay dos tipografías con ese nombre: la de
      R-Typography (Rui Abreu, comercial) y la de Federico Paviani (proyecto
      ECAL 2018, sin venta pública). Confirmar con Mathias cuál es.
- [ ] Subir el fichero al bucket `guides` (`media/fonts/pathos/pathos_400.otf`)
      y lanzar el SQL de alta de `guide-fonts.md` para asignarla a Yokohama.
- [ ] Decidir qué fuentes de texto se reutilizan entre guías, darlas de alta
      y asignarlas con `cities.body_font_id`.
- [ ] Si alguna licencia no permite servirla desde servidor, esa fuente va
      empaquetada en el móvil y no se da de alta aquí.

## Rendimiento de la guía

Hecho el 2026-10-04 (`a2a8494`): firma de URLs en lote y queries en paralelo
en `guide_service.py`. Sergio lo probó en local con el móvil y va rápido
("va como un tiro"); **no hay cifras de antes/después** — no se midió con
`curl` ni contra producción. En el front: bundle offline con
stale-while-revalidate y `cacheKey` en imágenes (ver contexto del móvil,
`city-guides/README.md`). Lo que queda:

- [ ] **Bucket `guides` público para las fotos** (`media/media-guias/`). Son
      fotos de marketing, no hay datos sensibles; el acceso a la guía lo sigue
      controlando el 403. Ventaja: URL fija → caché de CDN y del móvil sin
      truco de `cacheKey`, y sin firmar nada. Las fuentes con licencia se
      quedan privadas y firmadas (separarlas a otro bucket o mantener
      `sign_paths` solo para ellas). Requiere cambio en el panel de Supabase
      y pasar `image_service.py` a `get_public_url`.
- [ ] Si tras medir sigue lenta: caché en memoria (TTL de minutos) del
      contenido de cada ciudad en `guide_service.py`, con el acceso calculado
      por usuario.

## Seguridad (auditoría 2026-10-04)

Detalle en [`security/2026-10-audit.md`](security/2026-10-audit.md) y en
`../SEGURIDAD.md` (carpeta paraguas).

- [ ] **Reembolsos.** No hay endpoint para App Store Server Notifications V2
      ni Google RTDN: una compra devuelta sigue con `is_valid=true`. Al tener
      las cuentas: `POST /webhooks/apple` (verificar el JWS con la cadena de
      `store_verifier`) y `POST /webhooks/google`, poniendo `is_valid=false`
      por `store_transaction_id`.
- [ ] **Rate limit.** `core/rate_limit.py` usa el primer valor de
      `X-Forwarded-For`, que controla el cliente. Comprobar qué cabecera fija
      pone Railway y usarla (o el último valor).
- [ ] Activar `VERIFY_APPLE_CERT_CHAIN` en sandbox y luego en producción.
- [ ] Ligar compras al usuario: `appAccountToken` (iOS) y
      `obfuscatedAccountId` (Android).
- [ ] `profiles`: limitar el `update` a `full_name` y `cruise_departure_date`
      con grants por columna (migración nueva).
- [ ] Fijar por SHA las acciones de `.github/workflows/ci.yml`.
- [ ] Comprobar en el Supabase de producción que la migración 006 está
      aplicada y que el bucket `guides` es privado.

## Infra / deploy — sin verificar (2026-10-04)

- [ ] **Confirmar que el deploy en Railway existe de verdad.** El repo tiene
      `railway.toml` y el `CLAUDE.md` dice "auto-deploy en merge a `main`",
      pero Sergio no tiene claro si llegó a montarlo ("hay cosas automáticas
      que no he verificado"). Mirar en railway.app si hay proyecto
      `bon-vivant-api` conectado al repo y cuál es su URL pública. Si no
      existe, los push a `main` solo suben a GitHub.
- [ ] La URL de producción no está apuntada en ningún sitio. El móvil
      (`.env` → `EXPO_PUBLIC_API_BASE_URL`) apunta a `http://localhost:8000`,
      así que hoy la app solo funciona contra el backend local.

## Observabilidad — aplazado (2026-10-04)

- [ ] Propuesto **Sentry** (plan gratuito) para tiempos por endpoint, cascada
      de llamadas a Supabase y errores, en back (`sentry-sdk` + `SENTRY_DSN`,
      `send_default_pii=False`, filtrar `Authorization`) y móvil. Sergio
      decidió **"de momento no"**. Mientras tanto: Supabase → Reports →
      Query Performance / API, y Railway → Metrics/Logs si existe.

## Herramientas

- [ ] `pytest` a secas falla al recopilar (pytest-asyncio 0.23 + paquete
      `tests/`). Mientras tanto usar `pytest tests/test_*.py`. Arreglo
      probable: subir pytest-asyncio.
