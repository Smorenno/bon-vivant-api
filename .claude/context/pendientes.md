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

## Herramientas

- [ ] `pytest` a secas falla al recopilar (pytest-asyncio 0.23 + paquete
      `tests/`). Mientras tanto usar `pytest tests/test_*.py`. Arreglo
      probable: subir pytest-asyncio.
