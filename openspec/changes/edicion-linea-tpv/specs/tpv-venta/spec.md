# Delta for tpv-venta

## MODIFIED Requirements

### Requirement: Cálculo de líneas en servidor con precio e IVA congelados

El sistema MUST calcular cada línea en el servidor con `Decimal` y la función
única de redondeo (half-up por línea), congelando el PVP y el porcentaje de
IVA vigente del artículo en el momento del cálculo. El frontend MUST NOT
hacer aritmética de importes. Cuando el ítem incluye un `pvp` override, el
sistema MUST usar ese PVP para la línea en lugar del PVP de catálogo,
independientemente de si el artículo tiene marcado `precio_libre`.
(Previously: el override de `pvp` solo se aplicaba a artículos con
`precio_libre`; en cualquier otro artículo se ignoraba en silencio y se
usaba siempre el PVP de catálogo.)

#### Scenario: Cálculo de totales vía API
- GIVEN un artículo con PVP 2,50 € y cantidad 2
- WHEN POST `/tpv/api/calcular`
- THEN el total es `"5.00"` (string decimal exacto)

#### Scenario: Artículo de precio libre
- GIVEN un artículo `precio_libre` con `pvp` explícito en el ítem
- WHEN se calcula la línea
- THEN se usa ese PVP (no el de catálogo) y se expone `requiere_cites`

#### Scenario: Override de precio en línea de artículo no precio_libre
- GIVEN un artículo NO `precio_libre` con PVP de catálogo 3,00 € y cantidad 1
- WHEN se calcula la línea con un `pvp` override de 2,00 € en el ítem
- THEN la línea usa 2,00 € como PVP, no el de catálogo

#### Scenario: Sin override, la línea usa el PVP de catálogo
- GIVEN un artículo NO `precio_libre` con PVP de catálogo 3,00 € y cantidad 1
- WHEN se calcula la línea sin `pvp` override en el ítem
- THEN la línea usa 3,00 € (PVP de catálogo), igual que antes del cambio

**Tests**: `tests/test_tpv_api.py::test_calcular_totales_en_servidor`,
`::test_calcular_precio_libre`,
`::test_calcular_override_pvp_articulo_no_precio_libre` (NUEVO),
`::test_calcular_sin_override_usa_pvp_catalogo` (NUEVO)

## ADDED Requirements

### Requirement: Congelado de línea editada y auditoría de precio manual al emitir

El sistema MUST congelar en `VentaLinea`, en el momento de emitir, los
valores editados en el carrito pre-emisión: si el ítem trae un `pvp`
override, `VentaLinea.pvp_unitario` MUST ser ese valor; si trae una
`descripcion` override, `VentaLinea.descripcion` MUST ser ese texto (si no,
`articulo.nombre` como hoy); `VentaLinea.cantidad` MUST ser la cantidad del
ítem. Si el `pvp_unitario` congelado de una línea de un artículo **NO**
`precio_libre` difiere del PVP de catálogo del artículo en ese momento, el
sistema MUST registrar un evento en `LogAuditoria` con `accion="precio_manual_venta"`
y `detalle` indicando el PVP de catálogo y el PVP cobrado. Los artículos
`precio_libre` MUST NOT generar evento de auditoría de precio: ingresar su
precio es su funcionamiento normal, no un override anómalo. Si no hay
diferencia (o el artículo es `precio_libre`), el sistema MUST NOT registrar
ningún evento de auditoría por esa línea. Un carrito editado que nunca se
emite MUST NOT generar ningún evento de auditoría.

#### Scenario: Precio override se congela en pvp_unitario al emitir
- GIVEN un ítem con `pvp` override de 2,00 € sobre un artículo NO
  `precio_libre` con PVP de catálogo 3,00 €
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

#### Scenario: Precio manual distinto del catálogo genera evento de auditoría
- GIVEN un ítem con `pvp` override de 2,00 € sobre un artículo con PVP de
  catálogo 3,00 €
- WHEN se emite la venta
- THEN existe 1 registro en `LogAuditoria` con `accion="precio_manual_venta"` y
  `detalle` que referencia catálogo 3,00 € -> cobrado 2,00 €

#### Scenario: Precio sin diferencia no genera evento de auditoría
- GIVEN un ítem sin override de `pvp` (o con `pvp` igual al de catálogo)
- WHEN se emite la venta
- THEN no existe ningún registro en `LogAuditoria` con `accion="precio_manual_venta"`
  para esa línea

#### Scenario: Artículo precio_libre no genera evento de auditoría de precio
- GIVEN un ítem `precio_libre` con `pvp` override de 5,00 € (PVP de catálogo nominal 0,00 €)
- WHEN se emite la venta
- THEN no existe ningún registro en `LogAuditoria` con `accion="precio_manual_venta"`
  para esa línea (ingresar el precio de un `precio_libre` es lo normal, no un override)

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_congela_pvp_override_no_precio_libre` (NUEVO),
`::test_emitir_venta_congela_descripcion_override` (NUEVO),
`::test_emitir_venta_congela_cantidad_editada` (NUEVO),
`::test_emitir_venta_registra_auditoria_precio_manual` (NUEVO),
`::test_emitir_venta_sin_diferencia_precio_no_registra_auditoria` (NUEVO),
`::test_emitir_venta_precio_libre_no_registra_auditoria` (NUEVO)

## Constraints (no debilitar)

- Edición SOLO pre-emisión (venta `aparcada`); ninguna venta emitida se
  edita ni se borra (ADR-0003).
- Auditoría append-only (invariante 4): el evento de `precio_manual_venta` se
  registra en la misma transacción de emisión, nunca se edita ni se borra.
