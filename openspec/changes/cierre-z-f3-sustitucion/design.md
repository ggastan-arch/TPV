# Design: Cuadre del Cierre Z ante sustituciones F3

## Technical Approach

Approach 2 (A-refined), bloqueado en la propuesta. Un único cambio de filtro en
`RepositorioCierresZSQL.cobradas_por_rango_orden`
(`app/infraestructura/persistencia/repositorios.py:438-486`): incluir los orígenes
`sustituida` (que conservan total y `Pago` reales congelados) y excluir el lado
sustituto F3 (total en papel, cero pagos). El join a `RegistroFiscal` por rango de
`orden` (tipo `alta`) y toda la agregación posterior (`desglose_pago`, `desglose_iva`,
`num_tickets`, totales) quedan intactos. Sin esquema, sin migración, sin tocar el motor
fiscal. Reutiliza el patrón de subconsulta ya probado en `RepositorioVentas.convertibles()`
(mismo fichero, línea 217).

## Query change (before / after)

```python
# ANTES
.where(
    RegistroFiscal.tipo_registro == "alta",
    RegistroFiscal.orden >= desde_orden,
    RegistroFiscal.orden <= hasta_orden,
    Venta.estado == "cobrada",
)
# DESPUÉS
.where(
    RegistroFiscal.tipo_registro == "alta",
    RegistroFiscal.orden >= desde_orden,
    RegistroFiscal.orden <= hasta_orden,
    Venta.estado.in_(("cobrada", "sustituida")),
    Venta.id.notin_(select(VentaSustitucion.venta_sustituta_id)),  # excluye la F3
)
```

Nota: `convertibles()` excluye `venta_sustituida_id` (orígenes ya sustituidos); aquí se
excluye `venta_sustituta_id` (la F3). Es el mismo patrón, columna espejo.

## Architecture Decisions

| Decisión | Elegido | Rechazado | Razón |
|----------|---------|-----------|-------|
| Fuente del efectivo en Z | Incluir orígenes `sustituida` + excluir F3 | Excluir solo F3 (A) | (A) pierde el efectivo real de conversiones del mismo periodo: origen fuera por `sustituida`, F3 fuera por sustituta → cero en TODO Z |
| Semántica de `pago` | Contar los `Pago` reales del origen tal cual | `Pago` sintético en F3 (B) | (B) dobla el efectivo cross-period y corrompe `pago` como "movimiento real de caja" |
| Modelo de datos | Sin cambios | Asiento compensatorio (C) | (C) exige columna/tabla+migración+triggers para un informe interno; sobreingeniería |

## Data Flow

```
Venta T (cobrada) --emite--> RegistroFiscal alta (orden=n)  --> incluida en Z(n)
      │ convertir_en_factura_f3
      ▼
estado: cobrada -> sustituida   (total y Pago CONGELADOS)   --> SIGUE incluida en Z(n)
Venta F3 (cobrada, 0 Pago) --> RegistroFiscal alta (orden=m) --> EXCLUIDA (venta_sustituta_id)
```

## Por qué cuadra (prueba)

Cada venta incluida aporta simultáneamente su total y sus `Pago` reales, y a nivel de
venta `sum(pagos) == total_con_iva` (invariante de cobro). El origen `sustituida`
reintroduce ese par total+pago; la F3 —la única fila con total pero sin `Pago`— es lo
único que se retira. Por tanto `sum(desglose_pago) == sum(total)` en TODO rango: MUST
"Cuadre de totales y desgloses" se mantiene.

## Correctitud cross-period

El efectivo real vive en el origen y se cuenta **una sola vez**, en la ventana de `orden`
del propio origen (mismo periodo o años después). La F3 (orden posterior) se excluye en su
periodo → no hay doble conteo del total. Contraste con excluir-solo-F3: en conversiones del
mismo periodo el origen ya es `sustituida` y el filtro estricto `== "cobrada"` lo dejaría
fuera, perdiendo caja real; incluir `sustituida` lo evita.

## Dependencia de inmutabilidad

Se apoya en `trg_venta_no_update` (`app/infraestructura/persistencia/ddl.py:87-99`), que
permite `cobrada -> sustituida` SOLO si las columnas congeladas (`base_total`,
`cuota_total`, `total_con_iva`, `cliente_id`, …) no cambian. La conversión solo altera
`estado`; los `Pago` del origen nunca se tocan. Así, incluir `sustituida` cuenta cifras
congeladas, no mutadas.

## Edge cases

- **N→1 merge**: los N orígenes `sustituida` entran cada uno por su `orden`; `num_tickets`
  refleja las N ventas reales; la única F3 se excluye. No colapsa ni infla.
- **Z del origen ya cerrado antes de la conversión**: ese Z es inmutable (totales
  persistidos). Re-consultar su rango sigue incluyendo el origen (`sustituida`, dentro de
  rango, no sustituto) → resultado idéntico, idempotente, no reabre.
- **Periodo que solo contiene el alta de la F3**: la F3 se excluye → sin total fantasma. El
  efectivo real de esa venta ya se contó en el periodo del origen. Cualquier OTRO origen
  cuyo `orden` caiga en ese rango sí se cuenta (por su propio `orden`), con su caja real.
- **Anulaciones (`anulada_con_rastro`)**: estado distinto, NO se añade al set incluido; el
  comportamiento actual (la venta anulada desaparece limpia del Z, su registro de anulación
  cae en su propio rango) queda intacto — solo sumamos `sustituida`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/infraestructura/persistencia/repositorios.py` | Modify | Filtro de `cobradas_por_rango_orden` (~5-8 líneas) |
| `openspec/specs/cierre-z/spec.md` | Modify | Scenario F3 en "Cuadre de totales y desgloses" |
| `openspec/changes/convertir-en-factura-f3/design.md` (+ Non-goal del spec) | Modify | Nota de supersesión del "doble conteo… ACEPTADO" |
| `tests/test_cierre_z_f3_sustitucion.py` | New | Cuadre mismo periodo + cross-period + N→1 |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration | Cuadre mismo periodo (T origen + F3 en el mismo rango) | `sum(desglose_pago) == sum(total)` MUST; `num_tickets` cuenta orígenes, no F3 |
| Integration | Cross-period (origen en Z1, F3 en Z2) | Z1 con pago real; Z2 excluye F3; efectivo contado 1 vez, sin doble conteo |
| Integration | N→1 merge | `num_tickets == N`, cuadre intacto |
| Regression | `tests/test_cierre_z_generar.py` | Todos verdes (Z sin F3 inalterado) |

## Migration / Rollout

No migration required. Confirmado: sin cambios de esquema y sin tocar el motor fiscal
(huella, cadena, correlativos, triggers, `motor.emit`).

**Gate de merge**: este slice DEBE aterrizar antes de que el tracker de
`convertir-en-factura-f3` mergee a `main`; de lo contrario el tracker envía la regresión de
cuadre a producción.

## Open Questions

- None (bloqueantes).
