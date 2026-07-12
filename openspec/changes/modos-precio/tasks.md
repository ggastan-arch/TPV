# Tasks: Modo de precio por artículo (fijo | libre | al_peso)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450-550 (Tanda 1: ~280-320 · Tanda 2: ~150-220) |
| 400-line budget risk | High (conjunto) / Low por tanda individual |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Tanda 1 (backend+migración+seed, TDD) · PR 2 = Tanda 2 (frontend manual) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend + migración 0007 + seed, strict TDD, suite verde por sí sola | PR 1 | Fiscal-adyacente; incluye tests y `make arch` |
| 2 | Frontend (`admin.html`, `tpv.html`), sin tests automáticos | PR 2 | Base = PR 1 (o main tras merge); checklist manual |

## Tanda 1 — Backend + migración + seed (strict TDD, rojo→verde)

### Fase 1: Modelo `modo_precio` + migración 0007
- [x] 1.1 RED: test esquema — `Articulo.modo_precio` existe, default `"fijo"`, rechaza valor fuera de `{fijo,libre,al_peso}` (CheckConstraint) en `tests/test_esquema.py`
- [x] 1.2 RED: `tests/test_articulos.py::test_migracion_precio_libre_a_modo_precio` — `upgrade("0006_articulo_imagen"→"0007")` mapea `precio_libre=True→'libre'`, `False→'fijo'`, elimina columna `precio_libre`; `downgrade` inverso (usa `_aplicar_migraciones` de `tests/conftest.py`)
- [x] 1.3 GREEN: `app/infraestructura/persistencia/modelos/maestros.py` — quitar `precio_libre`, añadir `modo_precio: Mapped[str]` (`String`, default `"fijo"`) + `CheckConstraint("modo_precio IN ('fijo','libre','al_peso')", name="ck_articulo_modo_precio")`
- [x] 1.4 GREEN: crear `migrations/versions/0007_modo_precio_articulo.py` (`down_revision="0006_articulo_imagen"`) — batch add `modo_precio` nullable → `UPDATE ... CASE precio_libre` → NOT NULL + check constraint → `drop_column precio_libre`; downgrade inverso
- [x] 1.5 Confirmar 1.1-1.2 en verde

### Fase 2: Reemplazo de `precio_libre` en dominio/aplicación
- [x] 2.1 RED: actualizar helpers/fixtures de `tests/test_emitir_venta.py` y `tests/test_tpv_api.py` que instancian artículos con `precio_libre=` → `modo_precio=` (no-regresión)
- [x] 2.2 GREEN: `app/aplicacion/emitir_venta.py::_auditar_precios_manuales` — `lr.articulo.precio_libre` → `lr.articulo.modo_precio == "libre"`; actualizar docstring
- [x] 2.3 Confirmar suite existente (`test_emitir_venta.py`, `test_tpv_api.py`) sigue en verde tras el reemplazo

### Fase 3: Al peso — total = pvp (€/kg) × peso
- [x] 3.1 RED: `tests/test_tpv_api.py::test_calcular_modo_al_peso_con_peso_decimal` — pvp 4,50 €/kg, `cantidad`=1,250 → total `"5.63"`
- [x] 3.2 GREEN: confirmar que `resolver_items`/`calcular_linea` no requieren cambio (misma fórmula `cantidad × pvp_unitario`); ajustar solo si el test falla
- [x] 3.3 RED+GREEN: `tests/test_emitir_venta.py::test_emitir_venta_registra_auditoria_precio_manual_modo_al_peso` — `al_peso` audita igual que `fijo` si `pvp_unitario` difiere del catálogo

### Fase 4: Libre fuerza descripción al emitir
- [x] 4.1 RED: `tests/test_emitir_venta.py::test_emitir_venta_modo_libre_sin_descripcion_rechaza` — descripción vacía/whitespace → `DescripcionRequerida`, no persiste venta ni registro fiscal
- [x] 4.2 RED: `::test_emitir_venta_modo_libre_con_descripcion_ok` — con descripción, emite y congela `VentaLinea.descripcion`
- [x] 4.3 RED: `tests/test_tpv_api.py::test_calcular_modo_libre_sin_descripcion_no_bloquea` — `/api/calcular` NO rechaza
- [x] 4.4 RED: `::test_cobrar_modo_libre_sin_descripcion_devuelve_422` — `/api/cobrar` sí rechaza (HTTP 422)
- [x] 4.5 GREEN: `app/aplicacion/lineas.py` — añadir `class DescripcionRequerida(Exception)` y parámetro `resolver_items(..., exigir_descripcion_libre=False)`; si `True` y `modo_precio=="libre"` y descripción vacía/whitespace → raise
- [x] 4.6 GREEN: `app/aplicacion/emitir_venta.py` — invocar `resolver_items(..., exigir_descripcion_libre=True)`
- [x] 4.7 GREEN: `app/presentacion/tpv.py::/api/cobrar` — capturar `DescripcionRequerida` → `HTTPException(422)`; `/api/calcular` sigue con `exigir_descripcion_libre=False`
- [x] 4.8 RED+GREEN: `tests/test_emitir_venta.py::test_emitir_venta_articulo_migrado_modo_libre_no_regresion` — artículo migrado (`precio_libre=True` antes) se emite igual que antes

### Fase 5: CRUD — modo_precio editable + validación + DTO
- [x] 5.1 RED: `tests/test_articulos.py::test_crear_articulo_sin_modo_precio_usa_default_fijo`
- [x] 5.2 RED: `::test_crear_articulo_modo_al_peso`
- [x] 5.3 RED: `::test_actualizar_modo_precio_y_audita` — 1 log `actualizar_articulo`
- [x] 5.4 RED: `::test_modo_precio_invalido_falla_y_no_persiste` → `ModoPrecioInvalido`
- [x] 5.5 RED: `tests/test_admin_api.py::test_crear_articulo_modo_precio_invalido` → 422
- [x] 5.6 GREEN: `app/aplicacion/articulos.py` — `DatosArticulo.precio_libre: bool` → `modo_precio: str = "fijo"`; mapear en `crear`/`actualizar`; excepción `ModoPrecioInvalido`
- [x] 5.7 GREEN: `app/presentacion/admin.py` — `ArticuloReq.precio_libre` → `modo_precio: Literal["fijo","libre","al_peso"] = "fijo"`; `maestros_articulos` (DTO lectura) añade `"modo_precio"`; capturar `ModoPrecioInvalido` → 422
- [x] 5.8 GREEN: `app/presentacion/tpv.py::_articulo_dto` — `precio_libre` → `modo_precio`

### Fase 6: Seed — genéricos + material al_peso
- [x] 6.1 GREEN: `app/seed.py` — `tridacna.precio_libre=True` → `modo_precio="libre"`; añadir genéricos (peces/plantas/material) `modo_precio="libre"`, `pvp=0`, y un material `al_peso` de ejemplo (madera/roca)
- [x] 6.2 Test: `tests/test_seed.py` cubre presencia de los genéricos y del material `al_peso` con `pvp` > 0

### Fase 7: Checkpoint Tanda 1
- [x] 7.1 Ejecutar suite completa (`.venv/Scripts/python -m pytest`) — todo en verde, sin regresión (434 passed, baseline 416 + 18 nuevos)
- [x] 7.2 Ejecutar `make arch` — capas hexagonales intactas (dominio puro, sin fugas de FastAPI/ORM) (3 kept, 0 broken)
- [ ] 7.3 Confirmar cierre de PR 1 (Tanda 1) antes de abrir Tanda 2 (pendiente de revisión/merge humano, fuera del alcance de esta tanda de apply)

## Tanda 2 — Frontend (manual, sin tests automáticos)

### Fase 8: UI — selección de modo + entrada de peso/precio+descripción
- [ ] 8.1 `app/ui/admin.html` — CRUD de artículo: selector de `modo_precio` (fijo/libre/al_peso); etiquetar el campo `pvp` como "€/kg" cuando `modo_precio == al_peso`
- [ ] 8.2 `app/ui/tpv.html::anadir()` — rama por `modo_precio`: `libre` pide precio + descripción; `al_peso` pide peso (mapea a `cantidad`); `fijo` sin cambios
- [ ] 8.3 Checklist manual: crear artículo en cada modo desde `admin.html` y verificar persistencia
- [ ] 8.4 Checklist manual: vender un artículo `al_peso` (ingresar peso, verificar total en ticket) y un artículo `libre` (precio+descripción, con y sin descripción → debe bloquear al cobrar)

### Fase 9: Checkpoint Tanda 2
- [ ] 9.1 Ejecutar suite completa — sigue en verde (el frontend no debe romper tests de backend)
- [ ] 9.2 Ejecutar `make arch`
- [ ] 9.3 Checklist manual completo (8.3-8.4) firmado antes de cerrar PR 2
