# Delta for maestros-crud

## ADDED Requirements

### Requirement: Modo de precio del artículo (fijo | libre | al peso)

El sistema MUST exponer un campo `modo_precio` en `Articulo`, con valores excluyentes
`fijo`, `libre` o `al_peso`, que sustituye al booleano `precio_libre`. El sistema MUST
rechazar cualquier valor fuera de ese conjunto (422 vía API) sin persistir el artículo.
Si no se indica `modo_precio` al crear, el sistema MUST persistir `fijo` por defecto.
El campo MUST ser editable tanto al crear (`ServicioArticulos.crear` / `ArticuloReq`)
como al actualizar (`ServicioArticulos.actualizar`), y su edición MUST auditarse igual
que el resto de campos (`crear_articulo` / `actualizar_articulo`). En modo `al_peso` el
artículo MUST reutilizar `pvp` como precio por kg (sin columna nueva).

#### Scenario: Crear artículo sin indicar modo_precio usa el default
- GIVEN una petición de alta sin `modo_precio` en el payload
- WHEN se ejecuta `ServicioArticulos.crear`
- THEN el artículo persiste con `modo_precio = "fijo"`

#### Scenario: Crear artículo en modo al_peso
- GIVEN una petición de alta con `modo_precio = "al_peso"` y `pvp` como precio/kg
- WHEN se ejecuta `ServicioArticulos.crear`
- THEN el artículo persiste con ese `modo_precio` y ese `pvp`

#### Scenario: Actualizar el modo de precio de un artículo existente
- GIVEN un artículo existente con `modo_precio = "fijo"`
- WHEN se ejecuta `ServicioArticulos.actualizar` con `modo_precio = "libre"`
- THEN el artículo queda con `modo_precio = "libre"`
- AND existe 1 log `actualizar_articulo` con el `entidad_id` del artículo

#### Scenario: Valor de modo_precio inválido se rechaza
- WHEN se crea o actualiza un artículo con `modo_precio = "otro"` (fuera del enum)
- THEN se lanza `ModoPrecioInvalido` (422 vía API); no se persiste el cambio

#### Scenario: Migración de artículos existentes (precio_libre → modo_precio)
- GIVEN artículos previos a la migración, unos con `precio_libre = True` y otros con
  `precio_libre = False`
- WHEN se aplica la migración Alembic de este cambio
- THEN los primeros quedan con `modo_precio = "libre"` y los segundos con
  `modo_precio = "fijo"`

**Tests**: `tests/test_articulos.py::test_crear_articulo_sin_modo_precio_usa_default_fijo`,
`::test_crear_articulo_modo_al_peso`, `::test_actualizar_modo_precio_y_audita`,
`::test_modo_precio_invalido_falla_y_no_persiste`,
`::test_migracion_precio_libre_a_modo_precio` (NUEVO);
`tests/test_admin_api.py::test_crear_articulo_modo_precio_invalido` (NUEVO)

Nota: `modo_precio` es un valor único excluyente — nunca coexisten "libre" y "al_peso"
para el mismo artículo (evita estados ilegales de precio).
