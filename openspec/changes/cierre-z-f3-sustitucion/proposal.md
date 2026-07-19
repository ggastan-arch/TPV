# Proposal: Cuadre del Cierre Z ante sustituciones F3

## Intent

`RepositorioCierresZSQL.cobradas_por_rango_orden` (`repositorios.py:438-486`)
agrega solo `Venta.estado == "cobrada"`. Una conversión F3 (a) marca las
simplificadas origen como `sustituida` → salen del Z junto con su pago real, y
(b) crea la F3 `cobrada` sin filas `Pago` → suma a los totales pero nada al
`desglose_pago`. Todo Z cuyo rango de `orden` incluya el alta de una F3 queda con
`sum(desglose_pago)` corto por el importe de la F3: viola la requirement MUST
"Cuadre de totales y desgloses" del spec vivo `cierre-z` (test verde
`test_cuadre_de_totales_y_desgloses`). Rompe el arqueo (efectivo en cajón vs
desglose de pago del turno) — no es cosmético, es confianza operativa.

Esto reabre **con causa** la nota "doble conteo Cierre Z entre periodos:
ACEPTADO" de `convertir-en-factura-f3` (proposal L62/84, design L69-74, Non-goal
del spec L106-109): aquella aceptación cubría solo el doble conteo del TOTAL
entre periodos; NO cubría el déficit de `desglose_pago` que ocurre en TODO Z con
F3, incluidas conversiones del mismo periodo sin Z previo del origen.

## Scope

### In Scope
- Cambiar el filtro de `cobradas_por_rango_orden`:
  `Venta.estado IN ('cobrada','sustituida')` AND
  `Venta.id NOT IN (SELECT venta_sustituta_id FROM venta_sustitucion)`
  (reutiliza el patrón de `RepositorioVentas.convertibles()`).
- Amend la requirement "Cuadre de totales y desgloses" del spec vivo `cierre-z`
  con un scenario de sustitución F3.
- Nota de supersesión en `convertir-en-factura-f3` (design + Non-goal del spec)
  que revierte el "ACEPTADO".
- Tests: mismo periodo + cross-period.

### Out of Scope
- Motor fiscal, huella/cadena/correlativos/triggers/`motor.emit`.
- Emisión de la F3 y `convertir_en_factura_f3.py`.
- Cambios de esquema o migración.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `cierre-z`: la requirement "Cuadre de totales y desgloses" incluye ventas
  `sustituida` y excluye la F3 sustituta; añade scenario F3.
- `conversion-factura-f3`: supersede el Non-goal "doble conteo… ACEPTADO"
  (documentación; sin cambio de comportamiento de emisión).

## Approach

Approach 2 (A-refined). El efectivo real lo tienen los orígenes T (total y `Pago`
congelados por triggers): se cuentan **exactamente una vez**, en la ventana de
`orden` del propio origen, sea la conversión del mismo periodo o años después. La
F3 (lado sustituto) se excluye para que su total en papel no fantasee. Corrige el
cuadre en todos los casos y `num_tickets`. Sin schema ni migración.

Rechazadas: (A) excluir solo F3 → pierde el efectivo real de conversiones del
mismo periodo; (B) `Pago` sintético en F3 → doble cuenta cross-period y corrompe
la semántica de `pago`; (C) asiento compensatorio neto → exige schema/migración,
sobreingeniería para un informe interno; (D) aceptar+documentar → insuficiente,
es una regresión contra una MUST verde.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/infraestructura/persistencia/repositorios.py` | Modified | Filtro de `cobradas_por_rango_orden` (~5-8 líneas) |
| `openspec/specs/cierre-z/spec.md` | Modified | Scenario F3 en "Cuadre de totales y desgloses" |
| `openspec/changes/convertir-en-factura-f3/{design.md,specs/…}` | Modified | Nota de supersesión del "ACEPTADO" |
| `tests/test_cierre_z_f3_sustitucion.py` | New | Cuadre con F3 mismo periodo + cross-period |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Incluir `sustituida` cuente algo mutado | Low | Columnas de importe/`Pago` congeladas por triggers; solo cambia `estado` |
| Regresión en Z sin F3 | Low | Tests `cierre-z` existentes deben quedar verdes |
| Fusionar el tracker F3 sin este slice → envía la regresión | Med | Gate de merge: este slice antes del tracker |

## Rollback Plan

`git revert` del commit del filtro. Sin migración ni datos que deshacer; el
estado previo vuelve (con la regresión de cuadre conocida).

## Dependencies

- Slice de la feature-branch-chain de F3 (`feat/cierre-z-f3-sustitucion` sobre
  `c2`). MUST aterrizar **antes** de que el tracker mergee a `main`.

## Success Criteria

- [ ] "Cuadre de totales y desgloses" se mantiene con conversiones presentes.
- [ ] Efectivo real contado exactamente una vez; F3 nunca aporta total fantasma.
- [ ] `num_tickets` deja de distorsionarse por conversiones.
- [ ] Tests `cierre-z` existentes verdes; nuevos tests mismo-periodo + cross-period verdes.
- [ ] Intactos huella/cadena/numeración/redondeo/triggers/`motor.emit`.
