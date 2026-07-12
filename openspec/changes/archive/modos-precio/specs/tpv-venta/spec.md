# Delta for tpv-venta

## MODIFIED Requirements

### Requirement: Cálculo de líneas en servidor con precio e IVA congelados

El sistema MUST calcular cada línea en el servidor con `Decimal` y la función única de
redondeo (half-up por línea), congelando el PVP y el porcentaje de IVA vigente del
artículo en el momento del cálculo. El frontend MUST NOT hacer aritmética de importes.
Cuando el ítem incluye un `pvp` override, el sistema MUST usar ese PVP para la línea en
lugar del PVP de catálogo, independientemente del `modo_precio` del artículo. En
`modo_precio == "al_peso"`, el sistema MUST tratar la `cantidad` del ítem como el peso
ingresado (en kg) y el `pvp` de catálogo (o su override) como precio por kg; el total de
línea sigue siendo `cantidad x pvp_unitario` (misma fórmula, sin cambios).
(Previously: el override de `pvp` se describía en términos del booleano `precio_libre`;
ahora se describe en términos de `modo_precio`, y se añade el modo `al_peso`, que
reutiliza la misma fórmula con `cantidad` = peso.)

#### Scenario: Cálculo de totales vía API
- GIVEN un artículo con PVP 2,50 € y cantidad 2
- WHEN POST `/tpv/api/calcular`
- THEN el total es `"5.00"` (string decimal exacto)

#### Scenario: Artículo en modo libre
- GIVEN un artículo con `modo_precio = "libre"` y `pvp` explícito en el ítem
- WHEN se calcula la línea
- THEN se usa ese `pvp` (no el de catálogo) y se expone `requiere_cites`

#### Scenario: Override de precio en línea de artículo en modo fijo
- GIVEN un artículo con `modo_precio = "fijo"`, PVP de catálogo 3,00 € y cantidad 1
- WHEN se calcula la línea con un `pvp` override de 2,00 € en el ítem
- THEN la línea usa 2,00 € como PVP, no el de catálogo

#### Scenario: Sin override, la línea usa el PVP de catálogo
- GIVEN un artículo en modo fijo con PVP de catálogo 3,00 € y cantidad 1
- WHEN se calcula la línea sin `pvp` override
- THEN la línea usa 3,00 € (PVP de catálogo), igual que antes del cambio

#### Scenario: Cálculo en modo al_peso con peso decimal (NUEVO)
- GIVEN un artículo con `modo_precio = "al_peso"` y `pvp` (precio/kg) 4,50 €
- WHEN se calcula la línea con `cantidad` = 1,250 (peso en kg)
- THEN el total de línea es `"5.63"` (4,50 × 1,250, half-up)

**Tests**: `tests/test_tpv_api.py::test_calcular_totales_en_servidor`,
`::test_calcular_modo_libre`, `::test_calcular_override_pvp_articulo_modo_fijo`,
`::test_calcular_sin_override_usa_pvp_catalogo`,
`::test_calcular_modo_al_peso_con_peso_decimal` (NUEVO)

### Requirement: Congelado de línea editada y auditoría de precio manual al emitir

El sistema MUST congelar en `VentaLinea`, al emitir, los valores editados en el carrito
pre-emisión: si el ítem trae un `pvp` override, `VentaLinea.pvp_unitario` MUST ser ese
valor; si trae una `descripcion` override, `VentaLinea.descripcion` MUST ser ese texto
(si no, `articulo.nombre` como hoy, salvo en `modo_precio == "libre"`, ver requisito de
descripción obligatoria); `VentaLinea.cantidad` MUST ser la cantidad del ítem (en
`modo_precio == "al_peso"`, el peso ingresado). Si el `pvp_unitario` congelado de una
línea de un artículo con `modo_precio` en `{"fijo", "al_peso"}` difiere del PVP de
catálogo en ese momento, el sistema MUST registrar un evento en `LogAuditoria` con
`accion="precio_manual_venta"`. Los artículos con `modo_precio == "libre"` MUST NOT
generar evento de auditoría de precio. Si no hay diferencia (o el artículo está en modo
libre), el sistema MUST NOT registrar ningún evento. Un carrito editado que nunca se
emite MUST NOT generar ningún evento.
(Previously: la exclusión de auditoría se basaba en el booleano `precio_libre`; ahora se
basa en `modo_precio == "libre"`, y se aclara que `al_peso` audita igual que `fijo`.)

#### Scenario: Precio override se congela en pvp_unitario al emitir
- GIVEN un ítem con `pvp` override de 2,00 € sobre un artículo en modo fijo con PVP de
  catálogo 3,00 €
- WHEN se emite la venta
- THEN `VentaLinea.pvp_unitario` es 2,00 €

#### Scenario: Descripción override se congela en la línea
- GIVEN un ítem con `descripcion` override `"Guppy macho - promo"`
- WHEN se emite la venta
- THEN `VentaLinea.descripcion` es `"Guppy macho - promo"`

#### Scenario: Cantidad editada se refleja en la línea emitida
- GIVEN un ítem con `cantidad` editada a 3
- WHEN se emite la venta
- THEN `VentaLinea.cantidad` es 3

#### Scenario: Precio manual distinto del catálogo genera auditoría (modo fijo)
- GIVEN un ítem con `pvp` override de 2,00 € sobre un artículo en modo fijo con PVP de
  catálogo 3,00 €
- WHEN se emite la venta
- THEN existe 1 registro `LogAuditoria` con `accion="precio_manual_venta"`,
  catálogo 3,00 € -> cobrado 2,00 €

#### Scenario: Precio manual distinto del catálogo genera auditoría (modo al_peso) (NUEVO)
- GIVEN un ítem de un artículo `al_peso` con `pvp` override de 5,00 €/kg sobre un precio
  de catálogo de 4,50 €/kg
- WHEN se emite la venta
- THEN existe 1 registro `LogAuditoria` con `accion="precio_manual_venta"` para esa línea

#### Scenario: Precio sin diferencia no genera evento de auditoría
- GIVEN un ítem sin override de `pvp` (o igual al de catálogo)
- WHEN se emite la venta
- THEN no existe ningún registro `precio_manual_venta` para esa línea

#### Scenario: Artículo en modo libre no genera evento de auditoría de precio
- GIVEN un ítem `modo_precio = "libre"` con `pvp` override de 5,00 € (catálogo nominal
  0,00 €) y descripción
- WHEN se emite la venta
- THEN no existe ningún registro `precio_manual_venta` para esa línea

#### Scenario: No-regresión — artículo migrado de precio_libre a modo libre (NUEVO)
- GIVEN un artículo migrado (antes `precio_libre = True`, ahora `modo_precio = "libre"`)
  con `pvp` override y descripción
- WHEN se emite la venta
- THEN se emite igual que antes de la migración; no genera evento de auditoría de precio

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_congela_pvp_override_modo_fijo`,
`::test_emitir_venta_congela_descripcion_override`,
`::test_emitir_venta_congela_cantidad_editada`,
`::test_emitir_venta_registra_auditoria_precio_manual_modo_fijo`,
`::test_emitir_venta_registra_auditoria_precio_manual_modo_al_peso` (NUEVO),
`::test_emitir_venta_sin_diferencia_precio_no_registra_auditoria`,
`::test_emitir_venta_modo_libre_no_registra_auditoria`,
`::test_emitir_venta_articulo_migrado_modo_libre_no_regresion` (NUEVO)

## ADDED Requirements

### Requirement: Descripción obligatoria en modo libre al emitir

El sistema MUST rechazar la emisión completa de la venta (sin persistir nada) cuando una
línea de un artículo con `modo_precio == "libre"` resuelve una descripción vacía (sin
override, o un override compuesto solo de espacios). El sistema MUST lanzar
`DescripcionRequerida` (422 vía API) en ese caso. Esta validación solo aplica al emitir;
el cálculo/preview (`POST /tpv/api/calcular`) MUST NOT bloquearse por descripción vacía.

#### Scenario: Línea libre sin descripción se rechaza al emitir
- GIVEN un ítem de un artículo `modo_precio = "libre"` sin `descripcion` en el payload
- WHEN se ejecuta `EmitirVenta` / POST `/tpv/api/cobrar`
- THEN se lanza `DescripcionRequerida`; no se persiste venta ni registro fiscal

#### Scenario: Línea libre con descripción se emite correctamente
- GIVEN un ítem `modo_precio = "libre"` con `descripcion = "Roca decorativa 2kg"`
- WHEN se emite la venta
- THEN la venta se emite con éxito y `VentaLinea.descripcion` es `"Roca decorativa 2kg"`

#### Scenario: El cálculo/preview no bloquea por descripción vacía
- GIVEN un ítem de un artículo `modo_precio = "libre"` sin `descripcion`
- WHEN POST `/tpv/api/calcular`
- THEN la línea se calcula igual; la validación solo se aplica al emitir

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_modo_libre_sin_descripcion_rechaza`
(NUEVO), `::test_emitir_venta_modo_libre_con_descripcion_ok` (NUEVO);
`tests/test_tpv_api.py::test_calcular_modo_libre_sin_descripcion_no_bloquea` (NUEVO),
`::test_cobrar_modo_libre_sin_descripcion_devuelve_422` (NUEVO)
