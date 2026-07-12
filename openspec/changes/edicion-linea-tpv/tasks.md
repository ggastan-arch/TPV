# Tasks: Edición de línea en el TPV (precio, cantidad, descripción)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~350-450 (backend ~180-260, frontend ~120-200) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 backend (TDD) → PR 2 frontend (`tpv.html`) |
| Delivery strategy | ask-on-risk (no recibido explícito; asumido por defecto) |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend: override pvp/descripción, congelado, auditoría (TDD estricto) | PR 1 | Fiscal-adyacente; revisión aislada del invariante 4 |
| 2 | Frontend: editor de línea en `tpv.html` | PR 2 | Base = PR 1; sin tests automáticos, checklist manual |

**2 tandas recomendadas**: el backend es fiscal-adyacente (auditoría del invariante 4)
y verificable por tests; el frontend es UI táctil sin tests automáticos, revisado por
checklist manual. Separarlos aísla la revisión de auditoría de la revisión de UX.

**Nota (spec vs design)**: `spec.md` usa `accion="cambio_precio"` en el requisito
ADDED; `design.md` decidió `accion="precio_manual_venta"` precisamente para NO
colisionar con `accion="cambio_precio"` ya usado en `app/aplicacion/articulos.py`
(`entidad="articulo"`, cambio de PVP de catálogo, cubierto por `test_articulos.py`).
El propio nombre de test en spec.md (`..._registra_auditoria_precio_manual`) es
consistente con `precio_manual_venta`, no con `cambio_precio`. Las tareas de abajo
usan `precio_manual_venta` (design + código existente); se recomienda corregir el
texto de `spec.md` para alinear.

## Phase 1: Backend — override en `resolver_items` (`app/aplicacion/lineas.py`)

- [x] 1.1 RED: `tests/test_tpv_api.py::test_calcular_override_pvp_articulo_no_precio_libre`
  y `::test_calcular_sin_override_usa_pvp_catalogo` (deben fallar)
- [x] 1.2 GREEN: quitar `and articulo.precio_libre` en `resolver_items`
- [x] 1.3 Regresión: `::test_calcular_totales_en_servidor` y `::test_calcular_precio_libre`
  (existentes) siguen en verde
- [x] 1.4 RED: añadir `descripcion: str | None = None` a `ItemVenta`/`LineaResuelta`;
  test `::test_calcular_eco_descripcion_override` (NUEVO, no está en spec — soporta el
  eco de `design.md`)
- [x] 1.5 GREEN: `descripcion = (it.descripcion or "").strip() or articulo.nombre` en
  `resolver_items`; eco en `/api/calcular` (`app/presentacion/tpv.py`)
- [x] 1.6 REFACTOR: limpiar `resolver_items`; fase en verde

## Phase 2: Backend — congelado y auditoría (`app/aplicacion/emitir_venta.py`)

- [x] 2.1 RED: `tests/test_emitir_venta.py::test_emitir_venta_congela_pvp_override_no_precio_libre`,
  `::test_emitir_venta_congela_descripcion_override`,
  `::test_emitir_venta_congela_cantidad_editada` (deben fallar)
- [x] 2.2 GREEN: construir `VentaLinea(descripcion=lr.descripcion, ...)` (hoy usa
  `lr.articulo.nombre`); `cantidad` ya se propaga
- [x] 2.3 RED: `::test_emitir_venta_registra_auditoria_precio_manual`,
  `::test_emitir_venta_sin_diferencia_precio_no_registra_auditoria`,
  `::test_emitir_venta_precio_libre_no_registra_auditoria` (deben fallar)
- [x] 2.4 GREEN: añadir `_auditar_precios_manuales` en `EmitirVenta`, tras `motor.emit`:
  si el artículo NO es `precio_libre` y `lr.pvp != lr.articulo.pvp` → registrar
  `LogAuditoria(accion="precio_manual_venta", entidad="venta_linea", ...)`;
  `precio_libre` NUNCA audita
- [x] 2.5 REFACTOR: confirmar que la auditoría ocurre en la misma transacción que
  `motor.emit`/`commit` (invariante 4); fase en verde

## Phase 3: Backend — DTOs de endpoint (`app/presentacion/tpv.py`)

- [x] 3.1 Añadir `descripcion: str | None = None` al `ItemVenta` pydantic; mapear en
  `cobrar` a `ItemAplicacion(..., descripcion=i.descripcion)`
- [x] 3.2 Test de API: `test_cobrar_acepta_pvp_y_descripcion_override` en
  `tests/test_tpv_api.py` — overrides por ítem se congelan en la venta emitida

## Phase 4: Frontend — editor de línea en `tpv.html` (sin tests automáticos)

- [ ] 4.1 UI para editar cantidad, precio unitario y descripción de una línea del
  carrito (pre-emisión)
- [ ] 4.2 Enviar los overrides de la línea editada en el payload de `/api/calcular` y
  `/api/cobrar`
- [ ] 4.3 Una línea con precio/descripción editados NO se fusiona (+1) al retocar el
  mismo artículo; crea línea nueva
- [ ] 4.4 Checklist manual: editar cantidad recalcula el total; editar precio en
  artículo no `precio_libre` se refleja en el ticket; editar descripción aparece en el
  ticket impreso; retocar artículo tras editar no fusiona la línea

## Phase 5: Checkpoint

- [x] 5.1 `make test` en verde (suite completa) — 415 passed (baseline 405 + 10 nuevos
  de esta tanda backend)
- [x] 5.2 `make arch` (import-linter) sin violaciones — 3 kept, 0 broken
- [ ] 5.3 Checklist manual de Phase 4 completado y documentado (pendiente: Phase 4
  frontend es la tanda 2)
