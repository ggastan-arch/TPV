# Tasks: Búsqueda por nombre (lupa) en el TPV

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 (backend ~90-110, frontend ~40-60, tests ~60-80) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (una sola tanda) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Repo + endpoint + frontend + tests, en una sola tanda | PR 1 | Solo lectura, sin migración; base = main |

## Decisiones aplicadas (cierran Open Questions de design.md)

- Comodines LIKE (`%`, `_`) en `q` se **escapan** dentro del repo antes de armar el `ilike`, para que no actúen como wildcards.
- Acento-insensible en v1 (SQLite `ilike` no pliega diacríticos): aceptado para esta versión; el plegado de acentos queda documentado como mejora futura (no se implementa aquí).

## Phase 1: Puerto y repositorio — `buscar_por_nombre` (TDD backend)

- [x] 1.1 RED — En `tests/test_repositorios.py`, añadir tests para `RepositorioArticulosSQL.buscar_por_nombre` (deben fallar: el método no existe): match por `nombre` (subcadena interna); match por `nombre_corto`; case-insensitive; `q` de <2 chars → `[]`; respeta `limite` (crear N+1 artículos); excluye `activo=False`; orden por `nombre`; `q="%"` no devuelve todo el catálogo (comodín escapado).
- [x] 1.2 Añadir la firma `buscar_por_nombre(q: str, limite: int = 20) -> list["Articulo"]` al puerto `RepositorioArticulos` en `app/dominio/puertos.py`.
- [x] 1.3 GREEN — Implementar `buscar_por_nombre` en `RepositorioArticulosSQL` (`app/infraestructura/persistencia/repositorios.py`): guarda `len(q.strip()) < 2 → []`; escapar `%`/`_` en `q`; filtro `activo == True`; `ilike` sobre `nombre` **o** `nombre_corto`; `order_by(nombre)`; `limit(limite)`. Ejecutar los tests de 1.1 hasta verde.
- [x] 1.4 REFACTOR — Revisar si el escapado de comodines se puede compartir con `buscar_por_codigo`; extraer helper solo si reduce duplicación real. (`buscar_por_codigo` hace match exacto sobre `CodigoBarras.codigo`, sin `LIKE`; no hay duplicación que extraer más allá del helper `_escapar_comodines_like` ya creado junto a `buscar_por_nombre`.)

## Phase 2: Endpoint `GET /tpv/api/buscar`

- [x] 2.1 RED — En `tests/test_tpv_api.py`, añadir tests que fallen (ruta inexistente → 404): `test_buscar_coincide_por_nombre_case_insensitive`, `test_buscar_coincide_por_nombre_corto`, `test_buscar_excluye_articulos_inactivos`, `test_buscar_query_corta_no_ejecuta_busqueda` (sin `q` y con `q` de 1 char), `test_buscar_limita_a_top_20` (25 artículos coincidentes → máx. 20). Verificar que la forma de cada artículo es igual a `_articulo_dto`.
- [x] 2.2 GREEN — Implementar `GET /api/buscar` en `app/presentacion/tpv.py` (bajo el router `/tpv`): parámetro `q: str = ""`, llama `uow.articulos.buscar_por_nombre(q)`, serializa con `_articulo_dto` ya existente, devuelve la lista. Confirmar verde los tests de 2.1 (spec: `Búsqueda incremental de artículos por nombre`, `Longitud mínima de consulta y límite de resultados`).

## Phase 3: Frontend — caja de búsqueda (sin tests automáticos)

- [x] 3.1 Añadir en `app/ui/tpv.html`, dentro de `.col-botonera`, una caja de texto con icono de lupa.
- [x] 3.2 Implementar `buscar()`: debounce (~250ms) sobre el input, llama `GET /tpv/api/buscar?q=...`, pinta resultados en `#grid` reutilizando el render de botón-artículo de `abrirFamilia`; `onclick` de cada sugerencia llama a `anadir(a)`. Vaciar la caja o volver a Inicio restaura la botonera.
- [ ] 3.3 Checklist de verificación manual (equipo táctil o navegador) — PENDIENTE, requiere verificación humana:
  - [ ] Tipear ≥2 caracteres muestra sugerencias tras el debounce.
  - [ ] Tipear <2 caracteres no dispara petición ni deja sugerencias.
  - [ ] Tocar una sugerencia agrega el artículo al carrito con PVP/IVA correctos.
  - [ ] El listener del escáner (wedge) no se dispara al tipear en la caja (ya ignora `INPUT`, `tpv.html:263`).
  - [ ] Vaciar la caja o volver a Inicio restaura la botonera normal.

## Phase 4: Checkpoint final

- [x] 4.1 Ejecutar `.venv/Scripts/python -m pytest` completo — 0 fallos, incluyendo los tests nuevos de repositorio y endpoint. (405 passed: 392 baseline + 13 nuevos — 8 repo + 5 endpoint.)
- [x] 4.2 Ejecutar `make arch` (`lint-imports`) — confirmar que el dominio sigue sin depender de FastAPI/ORM y que no se violó la capa hexagonal. (3 kept, 0 broken.)
- [ ] 4.3 Ejecutar el checklist manual de 3.3 antes de dar por cerrado el cambio. PENDIENTE — requiere verificación humana en equipo táctil o navegador (no automatizable).
