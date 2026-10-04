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
en `guide_service.py`. Lo que queda:

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

## Herramientas

- [ ] `pytest` a secas falla al recopilar (pytest-asyncio 0.23 + paquete
      `tests/`). Mientras tanto usar `pytest tests/test_*.py`. Arreglo
      probable: subir pytest-asyncio.
