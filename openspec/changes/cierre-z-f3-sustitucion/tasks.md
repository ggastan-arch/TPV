# Tasks: Cuadre del Cierre Z ante sustituciones F3

> STRICT TDD. Runner: `.venv/Scripts/python -m pytest`. Arch:
> `.venv/Scripts/lint-imports`. Cada bloque: RED (test que falla) -> GREEN
> (implementacion minima). Ninguna tarea arranca marcada.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 (repositorios.py ~10-15; `tests/test_cierre_z_f3_sustitucion.py` nuevo ~140-180) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | PR unico |
| Delivery strategy | a confirmar por el orquestador (`ask-on-risk` por defecto) |
| Chain strategy | pending |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Filtro `cobradas_por_rango_orden` + tests mismo-periodo/cross-period/N->1 + regresion | PR unico | Base `feat/cierre-z-f3-sustitucion` sobre `c2`. MUST aterrizar antes de que el tracker `convertir-en-factura-f3` mergee a `main` (gate de merge, ver proposal.md) |

## Fase 1: Tests de cuadre con F3 (Requirement "Cuadre de totales y desgloses",
spec `cierre-z` — dep. ninguna)

- [ ] 1.1 RED `tests/test_cierre_z_f3_sustitucion.py` (nuevo; fixtures
  `crear_sesion`/`motor`/`datos_base`, helper `_helpers.construir_venta`):
  `test_cuadre_mismo_periodo_conversion_f3` — emite 2 T (efectivo 21%, tarjeta
  10%), convierte ambas en 1 F3 vía `ConvertirEnFacturaF3.ejecutar` (mismo
  rango de `orden`), genera el Z; HOY falla:
  `sum(desglose_pago) != base_total + cuota_total`
- [ ] 1.2 RED (mismo fichero) `test_num_tickets_no_incluye_f3_en_conversion`:
  mismo setup; HOY `num_tickets` da 1 (solo la F3) en vez de 2 (orígenes reales)
- [ ] 1.3 RED (mismo fichero) `test_cross_period_no_duplica_efectivo`: emite T,
  genera Z1 (incluye su alta); convierte T en F3 (`orden` nuevo, posterior);
  genera Z2 (solo el alta F3); HOY Z1 no cambia pero Z2 cuenta el total de la
  F3 sin `Pago` propios (desglose corto / doble conteo)

## Fase 2: Implementación del filtro (dep. Fase 1)

- [ ] 2.1 GREEN `app/infraestructura/persistencia/repositorios.py`
  (`cobradas_por_rango_orden`, ~línea 455): cambiar
  `Venta.estado == "cobrada"` por `Venta.estado.in_(("cobrada", "sustituida"))`
  y añadir `Venta.id.notin_(select(VentaSustitucion.venta_sustituta_id))`.
  **CRÍTICO**: `venta_sustituta_id` (lado F3) — NO `venta_sustituida_id` (lado
  origen, usado por `convertibles()` en el mismo fichero); invertirlo produce
  el cuadre inverso. `select`/`VentaSustitucion` ya importados
- [ ] 2.2 Confirmar 1.1, 1.2 y 1.3 en GREEN

## Fase 3: Regresión (dep. Fase 2)

- [ ] 3.1 `tests/test_cierre_z_generar.py` completo verde, en particular
  `test_cuadre_de_totales_y_desgloses` (Z sin ninguna F3 queda inalterado)
- [ ] 3.2 `.venv/Scripts/python -m pytest` — suite completa verde, sin
  regresión en ningún test existente
- [ ] 3.3 `.venv/Scripts/lint-imports` — capas hexagonal intactas (sin
  contratos rotos)

## Fase 4: Verificación documental final (dep. Fase 3)

- [ ] 4.1 Confirmar que `openspec/changes/convertir-en-factura-f3/design.md` y
  `openspec/changes/convertir-en-factura-f3/specs/conversion-factura-f3/spec.md`
  ya contienen la nota "Superseded por `cierre-z-f3-sustitucion`" (verificado
  en esta fase: ya escrita — sin acción de código pendiente)
- [ ] 4.2 Confirmar que el delta
  `openspec/changes/cierre-z-f3-sustitucion/specs/cierre-z/spec.md` ya cubre
  los 3 scenarios nuevos de esta fase (verificado: ya escrito; se fusiona al
  spec principal `openspec/specs/cierre-z/spec.md` en `sdd-archive`, no en
  `sdd-apply`)
