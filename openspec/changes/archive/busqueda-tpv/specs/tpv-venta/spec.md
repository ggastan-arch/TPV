# Delta for tpv-venta

## ADDED Requirements

### Requirement: Búsqueda incremental de artículos por nombre

El sistema MUST exponer un endpoint de solo lectura `GET /tpv/api/buscar?q=...`
sin efectos secundarios (no modifica estado). El universo de búsqueda MUST ser
todos los artículos con `activo = True` (no se filtra por familia ni por
`visible_en_tactil`). El sistema MUST considerar coincidencia cuando `q`
aparece como subcadena, case-insensitive, dentro de `nombre` **o** de
`nombre_corto` del artículo. El sistema MUST NOT buscar por código de barras
(ese universo lo cubre `GET /tpv/api/articulo/por-codigo/{codigo}`). Cada
artículo devuelto MUST tener la misma forma que produce `_articulo_dto`
(`id`, `nombre`, `nombre_corto`, `pvp`, `tipo_iva`, `precio_libre`,
`requiere_cites`, `color`, `imagen`), para poder agregarse al carrito sin
transformación adicional.

#### Scenario: Coincidencia por nombre, case-insensitive

- GIVEN un artículo activo con `nombre = "Betta Splendens Macho"`
- WHEN GET `/tpv/api/buscar?q=BETTA`
- THEN la respuesta incluye ese artículo con la forma `_articulo_dto`

#### Scenario: Coincidencia por nombre_corto

- GIVEN un artículo activo cuyo `nombre` no contiene "xyz" pero cuyo
  `nombre_corto` sí lo contiene
- WHEN GET `/tpv/api/buscar?q=xyz`
- THEN la respuesta incluye ese artículo

#### Scenario: Artículo inactivo excluido

- GIVEN un artículo con `activo = False` cuyo `nombre` coincide con `q`, y
  otro artículo activo cuyo `nombre` también coincide
- WHEN GET `/tpv/api/buscar?q=guppy`
- THEN la respuesta incluye solo el artículo activo

**Tests**: `tests/test_tpv_api.py::test_buscar_coincide_por_nombre_case_insensitive`,
`::test_buscar_coincide_por_nombre_corto`,
`::test_buscar_excluye_articulos_inactivos`

### Requirement: Longitud mínima de consulta y límite de resultados

El sistema MUST NOT ejecutar ninguna coincidencia contra el catálogo cuando
`q` tiene menos de 2 caracteres (ausente, vacío o de 1 carácter), devolviendo
una lista de artículos vacía. El sistema MUST limitar el número de artículos
devueltos a un máximo de 20, aunque coincidan más artículos con `q`.

#### Scenario: Query por debajo del mínimo no ejecuta búsqueda

- WHEN GET `/tpv/api/buscar?q=a`
- THEN responde 200 con una lista de artículos vacía

#### Scenario: Query ausente no ejecuta búsqueda

- WHEN GET `/tpv/api/buscar` sin parámetro `q`
- THEN responde 200 con una lista de artículos vacía

#### Scenario: Más de 20 coincidencias se recortan al top 20

- GIVEN 25 artículos activos cuyo `nombre` contiene "pez"
- WHEN GET `/tpv/api/buscar?q=pez`
- THEN la respuesta contiene como máximo 20 artículos

**Tests**: `tests/test_tpv_api.py::test_buscar_query_corta_no_ejecuta_busqueda`,
`::test_buscar_limita_a_top_20`
