# Delta for tpv-venta

## ADDED Requirements

### Requirement: Drill-down de subfamilias filtra por visibilidad táctil

El sistema MUST listar, en `GET /tpv/api/familia/{familia_id}`, únicamente las
subfamilias con `visible_en_tactil = True` y `activo = True`. Una subfamilia
con `visible_en_tactil = False` MUST NOT aparecer en el listado de
`subfamilias`, aunque esté activa. Este filtro gobierna solo el listado de
navegación por familias; MUST NOT afectar al render de botones explícitos de
la botonera (`GET /api/botonera`) que apunten a una familia no visible: un
botón que referencia directamente una familia no visible se sigue mostrando
y funcionando con normalidad, porque el flag controla el drill-down, no el
botón.

#### Scenario: Subfamilia no visible queda excluida

- GIVEN una familia con dos subfamilias activas, una con
  `visible_en_tactil = True` y otra con `visible_en_tactil = False`
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN `subfamilias` incluye solo la que tiene `visible_en_tactil = True`

#### Scenario: Familias existentes (default True) no sufren regresión

- GIVEN subfamilias activas creadas antes de este cambio, todas con
  `visible_en_tactil = True` por el `server_default` de la migración
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN todas siguen apareciendo en `subfamilias`, igual que antes del cambio

#### Scenario: Subfamilia inactiva sigue excluida (comportamiento previo)

- GIVEN una subfamilia con `visible_en_tactil = True` pero `activo = False`
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN no aparece en `subfamilias`

#### Scenario: Botón explícito a familia no visible se respeta

- GIVEN un botón de botonera que apunta a una familia con
  `visible_en_tactil = False`
- WHEN GET `/api/botonera`
- THEN el botón aparece igual que si la familia fuera visible; el flag no
  afecta el render de botones, solo el listado de `subfamilias`

**Tests**: `tests/test_tpv_api.py::test_familia_excluye_subfamilias_no_visibles_en_tactil`,
`::test_familia_incluye_subfamilias_visibles_y_activas`,
`::test_botonera_respeta_boton_explicito_a_familia_no_visible`

## Constraints (no debilitar)

- El filtro no altera el listado de `articulos` de la familia (`Articulo.activo`
  sigue siendo el único criterio ahí).
- No introduce dependencias de red ni afecta el cobro offline.
