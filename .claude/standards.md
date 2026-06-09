# Development Standards — Bon Vivant API

Lee este archivo antes de escribir cualquier línea de código del backend.
Cada regla se cumple sin excepción. El núcleo de seguridad es compartido con
el repo mobile (ver `../../CLAUDE.md`).

---

## Seguridad

### Auth y datos
- Nunca loguear passwords, tokens, JWTs ni datos personales.
- Nunca exponer stack traces ni errores crudos en las responses → mensaje genérico.
- Todas las responses de error siguen un único schema: `{ detail: string, code: string }`.
- Todo endpoint requiere auth salvo los marcados `[public]`.
- Mismo mensaje para email incorrecto Y password incorrecto (anti-enumeración).
- Mismo response en password reset exista o no el email.
- `service_role` key solo en backend, nunca en frontend.
- Secrets solo en variables de entorno, nunca en código.
- Validar todos los request bodies con Pydantic antes de procesar.
- **403 (no 404)** cuando el recurso existe pero el usuario no tiene acceso (404 filtra info).

### Pagos (crítico — el backend es la única verdad)
- `POST /purchases/validate` valida el receipt contra App Store / Google Play.
  Nunca confiar en el cliente.
- `is_unlocked` se calcula en backend según `user_purchases`, nunca en el cliente.
- Operaciones de pago usan `service_role` (bypass RLS) de forma deliberada y acotada.

### Base de datos
- **RLS habilitado en TODAS las tablas de Supabase, siempre.**
- Nunca construir SQL por concatenación con input de usuario → queries parametrizadas.
- Mínimo privilegio: usa el JWT del usuario para sus datos; `service_role` solo
  para pagos y admin.
- Migraciones versionadas en `supabase/migrations/` con DDL + RLS.

---

## Calidad Python

- Type hints en TODAS las funciones, sin excepción.
- `response_model` definido en TODOS los endpoints.
- Async en TODAS las llamadas a Supabase.
- Endpoints solo manejan HTTP: recibir request → llamar service → devolver response.
- Lógica de negocio solo en `services/`. `models/` solo define schemas Pydantic.
- Nunca capturar `Exception` genérica — solo excepciones específicas.
- Borra código muerto, no lo comentes y lo dejes.
- Sin números mágicos — usa constantes con nombre.
- ruff (`E`,`F`,`I`) + black limpios antes de commitear (line-length 88).

---

## Git y workflow

- Conventional Commits: `feat:` / `fix:` / `chore:` / `docs:` / `refactor:`.
- Nunca commitear `.env`, `__pycache__`, `.venv`.
- Una responsabilidad por función — si hace dos cosas, divídela.

---

## Antes de escribir código, pregúntate

1. ¿Expone datos sensibles o stack traces?
2. ¿Tiene `response_model` y type hints?
3. ¿La lógica está en `services/` o se coló en el endpoint?
4. ¿Es async la llamada a Supabase?
5. ¿Qué pasa si falla la validación del receipt de pago?
