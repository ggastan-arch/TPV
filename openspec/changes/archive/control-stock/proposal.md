# Proposal: Control de stock (informativo, no bloqueante)

## Intent

El modelo ya contempla stock (`Articulo.control_stock`, `MovimientoStock` append-only con
tipos `entrada|venta|merma`), pero **falta la lógica de negocio**: nada descuenta, registra
entradas/mermas ni calcula existencias. La persona titular quiere control de existencias y mermas
justificadas, PERO conservando la libertad de **operar sin stock** si lo prefiere.

## Restricción rectora

El stock es **informativo**: NUNCA bloquea ni ralentiza el cierre offline de la venta. El
movimiento de `venta` es un **efecto secundario en la misma transacción local** que jamás
hace fallar la venta ni introduce dependencias de red (invariante de cobro offline, CLAUDE.md).

## Scope

### In Scope
- **Ajuste de empresa** (global): encender/apagar el control de stock, editable desde la consola admin.
- Con control encendido, SOLO rastrean/descuentan artículos con `control_stock = true`.
- Casos de uso **RegistrarEntrada** y **RegistrarMerma** (motivo obligatorio; ambas auditadas, invariante 4).
- **Cálculo de stock actual** por artículo (suma de movimientos).
- Integración del movimiento `venta` en `EmitirVenta` (efecto secundario no bloqueante, misma transacción).
- **Alarma visible** de stock negativo/bajo en TPV y consola (patrón de `/api/fiscal/estado`), informativa.
- Consulta/listado de stock y de movimientos.

### Out of Scope
- Valoración de inventario, pedidos a proveedores, multi-almacén, reposición automática.
- **Cualquier bloqueo o ralentización de la venta por stock** (sobreventa siempre permitida → stock negativo válido).

### Non-goals
- Que el stock condicione el cobro; que el cobro dependa de la red.

## Capabilities

### New Capabilities
- `control-stock`: ajuste de empresa, entradas/mermas auditadas, cálculo de existencias, descuento en venta y alarma no bloqueante.

### Modified Capabilities
- None. La integración en `EmitirVenta` se especifica dentro de `control-stock` (nuevo efecto secundario, sin cambiar el contrato fiscal de `tpv-venta`).

## Approach

Caso de uso fino por operación (entrada/merma/consulta) sobre repositorio de
`MovimientoStock`. `EmitirVenta` registra los movimientos `venta` de líneas rastreadas
cuando el ajuste está encendido, dentro del `commit` existente y blindado para no propagar
errores al cobro. Alarma como endpoint de estado (contador de artículos en negativo/bajo),
consumido por TPV y consola.

## A resolver en design (no aquí)
- Dónde vive el ajuste de empresa (config singleton en BD / tabla de parámetros / settings) dado que debe editarse en remoto desde la consola.
- Cómo se calcula el stock: agregación on-the-fly de movimientos vs. caché/materialización.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/aplicacion/` | New | Casos de uso `RegistrarEntrada`, `RegistrarMerma`, consulta de stock |
| `app/aplicacion/emitir_venta.py` | Modified | Efecto secundario no bloqueante: movimiento `venta` para líneas rastreadas |
| `app/dominio/puertos.py` | Modified | Puerto repositorio de movimientos + lectura del ajuste de empresa |
| `app/infraestructura/persistencia/` | Modified | Repositorio de stock; persistencia del ajuste de empresa (a definir en design) |
| `app/presentacion/admin.py` | Modified | Toggle del ajuste + endpoint de estado/alarma de stock |
| `app/presentacion/` (TPV) | Modified | Alarma visible de stock (patrón cola fiscal) |
| `migrations/` | New | Migración Alembic para persistir el ajuste de empresa |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| La lógica de stock se cuela en el camino de cobro y lo bloquea/ralentiza | Med | Efecto secundario no bloqueante, misma transacción local, sin red; tests que verifican que un fallo de stock no aborta la venta |
| Sobreventa mal interpretada como error | Low | Stock negativo es estado válido y esperado; solo dispara alarma informativa |
| Doble contabilización tras anulación/rectificativa | Med | Definir en spec el tratamiento de movimientos ante anulación (fuera del cobro) |

## Rollback Plan

Apagar el ajuste de empresa deja el sistema operando sin efectos de stock. Los movimientos
son append-only: no se borran; revertir código y migración deja `MovimientoStock` inerte
(como hoy). Ninguna venta ni registro fiscal se ve afectado.

## Dependencies

- Ninguna externa. Reutiliza `Articulo.control_stock` y `MovimientoStock` ya existentes.

## Success Criteria

- [ ] Con control apagado, ninguna operación produce efectos de stock.
- [ ] Con control encendido, las ventas descuentan solo artículos rastreados; entradas/mermas ajustan.
- [ ] Vender sin stock suficiente se permite siempre y dispara alarma (stock negativo válido).
- [ ] Mermas exigen motivo y quedan auditadas.
- [ ] Un fallo en el registro de stock NUNCA aborta ni bloquea la venta (test explícito).
- [ ] Cobertura de tests (TDD) para cada invariante de comportamiento anterior.
