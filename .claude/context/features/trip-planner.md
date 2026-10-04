# Trip planner — gating por Pass y modelo de días

**Schema:** `supabase/migrations/005_trip_planner.sql` (`trips`, `trip_days`,
RLS "owner sees only their own rows").
**Commit del gating:** `98754ab` — *feat: trip planner with server-side Pass
enforcement*.

## Por qué existe el gating server-side

Detectado durante la [auditoría de seguridad](../security/2026-07-audit-and-hardening.md):
el planner es una feature exclusiva del Pass (pack ilimitado), pero
`create_trip` no comprobaba nada — el único control era un *blur* visual en
`saved.tsx` del móvil. Se podía crear un trip sin Pass llamando la API
directamente, saltándose el paywall.

## Cómo funciona ahora (`app/services/trips_service.py`)

`create_trip()` llama primero `access_service.has_active_pass(client,
user_id)`. Si no tiene Pass → `403 pass_required` antes de tocar nada más.
`has_active_pass` (antes se llamaba `_user_has_pass`, privada — se
renombró a pública al reutilizarse fuera de `access_service`) comprueba
`user_purchases` contra los packs con `is_unlimited=true`.

## Modelo de datos — auto-fill de días en el mar (cambio en curso, sin commitear)

Al momento de escribir esto (`git status` muestra `app/models/trip.py`,
`app/services/trips_service.py`, `tests/test_trips.py` modificados y sin
commitear) el modelo de creación de trip cambió de forma:

- **Antes**: el cliente mandaba un día por cada `day_number` del rango
  completo (incluidos los días en el mar), y el backend validaba que el
  conteo y la secuencia de `day_number` cuadraran exactamente.
- **Ahora**: el cliente solo manda los días que tienen escala en puerto
  (`city_slug` no nulo); los días de navegación son implícitos. El backend
  indexa lo recibido **por fecha** (no por `day_number` — ese campo del
  input ya no se usa, se deriva de la posición dentro del rango), valida
  que cada fecha esté dentro de `[start_date, end_date]` y no haya
  duplicados, y rellena automáticamente los huecos como días "at sea"
  (`city_slug: null`).

Motivo del cambio: menos payload desde el móvil y menos superficie de
error (antes había tres validaciones distintas para que el conteo de días
cuadrase; ahora el backend construye el calendario completo él mismo a
partir de `start_date`/`end_date`).

**Si retomas este trabajo:** confirma si estos cambios ya se commitearon
(`git log -1 -- app/services/trips_service.py`) antes de asumir que este
documento describe el estado final — si siguen sin commitear, revisa que
`tests/test_trips.py` pase completo y decide el mensaje de commit
(probablemente `refactor: trip days derived from dates, auto-fill sea days`).

## Tests

`tests/test_trips.py::test_create_trip_without_pass_returns_403` cubre el
gating. El resto de tests siembran un Pass válido por defecto
(`_make_db(with_pass=True)`, que es el default) para no tener que repetir
el seed en cada test que no es sobre el gating en sí.
