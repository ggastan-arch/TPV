# Proposal: Edición de línea en el TPV (precio, cantidad, descripción)

## Intent

La titular quiere ajustar FÁCIL una línea del ticket antes de cobrar: cambiar
**precio unitario**, **cantidad** y **descripción**. Hoy la única edición en el carrito
es sumar +1 (al re-agregar) o quitar la línea entera; el override de precio solo existe
para artículos `precio_libre` (prompt en `anadir`) y se ignora en silencio en el resto;
la descripción sale siempre de `articulo.nombre` y no hay forma de tocarla. Falta un
editor de línea que agilice la venta.

**Restricción fiscal rectora:** la edición es SIEMPRE **PRE-EMISIÓN** (venta `aparcada`,
carrito en memoria, antes de cobrar). Los valores editados se CONGELAN en `VentaLinea`
en el momento de la emisión (invariante 1, ADR-0003). Editar el carrito antes de cobrar
NO viola ningún invariante. Este cambio NO toca ventas emitidas ni la cadena de huellas.

## Scope

### In Scope
- Editar en el carrito (pre-emisión) la **cantidad**, el **precio unitario** y la
  **descripción** de una línea; esos valores editados son los que se congelan al emitir.
- Backend: `ItemVenta` y la emisión aceptan `descripcion` override y (según decisión de
  design) `pvp` override más allá de `precio_libre`.
- Frontend (`tpv.html`): UI táctil para editar la línea del carrito.

### Out of Scope
- Editar líneas de una venta YA emitida (prohibido; inmutable, ADR-0003).
- Rectificativas / anulaciones (`motor-fiscal-verifactu`; otro cambio).

## Non-Goals
- Tocar la inmutabilidad post-emisión, los triggers de BD ni la cadena de huellas.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tpv-venta`: nuevo requisito de edición de línea en el carrito (cantidad, precio y
  descripción) con congelado en `VentaLinea` al emitir.

## Approach

Extender `ItemVenta` (aplicación) con `descripcion` override y, según design, `pvp`
override general; `resolver_items`/`emitir_venta` usan esos valores al construir
`VentaLinea` (que ya tiene columnas `descripcion` y `pvp_unitario`, y una columna
`descuento` hoy dormida). El frontend añade un editor de línea que actualiza el `carrito`
en memoria y recalcula vía `/tpv/api/calcular`. Sin migraciones de esquema previstas.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `app/aplicacion/lineas.py` | Modified | `ItemVenta` + resolución con overrides |
| `app/aplicacion/emitir_venta.py` | Modified | Congelar descripción/pvp editados |
| `app/ui/tpv.html` | Modified | Editor de línea (cantidad/precio/descripción) |
| `app/presentacion/tpv.py` | Modified | DTOs de calcular/cobrar aceptan overrides |
| `tests/` | Modified | Tests de overrides congelados al emitir |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|------------|
| Confundir edición con tocar ventas emitidas | Media | Dejar CLARO que es solo pre-emisión (`aparcada`) |
| Override de precio libre choca con invariante 4 | Media | Resolver auditoría en design (ver preguntas) |

## Rollback Plan

Sin migraciones: revertir el diff (backend + `tpv.html`) restaura el comportamiento
actual. No hay datos persistidos nuevos que limpiar.

## Dependencies

- Ninguna. `VentaLinea.descripcion`, `pvp_unitario` y `descuento` ya existen; el modelo
  `LogAuditoria` (append-only) ya contempla "cambios de precio".

## Open Questions for Design (NO resolver aquí)

1. **Alcance del override de precio**: ¿cualquier línea (override libre) o solo
   artículos `precio_libre` como hoy? Si es cualquier línea, ¿es "precio manual" /
   descuento (columna `descuento` dormida)?
2. **Auditoría (invariante 4)**: ¿un cambio de precio manual se registra en
   `LogAuditoria`? El invariante 4 cita "cambios de precio" y "descuentos"; que la
   titular sea única operadora NO exime la traza.
3. **Descripción override**: cómo se persiste (`VentaLinea.descripcion` ya existe; hoy
   viene de `articulo.nombre`).
4. **Cantidad**: formalizar el editor en la UI (la API ya acepta `cantidad` arbitraria;
   la UI solo hace +1 al re-agregar).

## Success Criteria

- [ ] En el carrito se puede cambiar precio, cantidad y descripción de una línea antes de cobrar.
- [ ] Al emitir, esos valores editados quedan congelados en `VentaLinea`.
- [ ] Backend cubierto por tests; sin tocar ventas emitidas ni la cadena fiscal.
