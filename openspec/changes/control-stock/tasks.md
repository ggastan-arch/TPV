# Tasks: Control de stock (informativo, no bloqueante)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~700-800 (migración+modelo ~60, puertos+repos ~65, casos de uso ~90, integración EmitirVenta ~30, endpoints admin+tpv ~90, tests nuevos ~350-450) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes (repo sin PRs: entregar por tandas/commits, no chained PRs literales) |
| Suggested split | Tanda 1 (Fases 1-3, base de datos) → Tanda 2 (Fase 4, integración EmitirVenta) → Tanda 3 (Fases 5-6, endpoints+cierre) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

Nota: este repo no usa PRs (commit directo a `main`). "Chained PRs" se traduce a **tandas de `sdd-apply` con checkpoint verde** (suite + `make arch`) entre cada una, igual que se entregó `cierre-z`. No hacer todo en una sola tanda: la Fase 4 (SAVEPOINT en `EmitirVenta`) es el punto de mayor riesgo fiscal y merece su propio checkpoint aislado.

### Suggested Work Units

| Unit | Goal | Tanda | Notes |
|---|---|---|---|
| 1 | Fases 1-3: migración 0004, `ConfiguracionEmpresa`, `RepositorioConfiguracion`, `RepositorioStock`, casos de uso | Tanda 1 | Sin tocar `EmitirVenta`; checkpoint: suite+`make arch` verde |
| 2 | Fase 4: `_efecto_stock` en `EmitirVenta` con SAVEPOINT | Tanda 2 | Depende de Unit 1; checkpoint obligatorio en test 4.3 (fallo no aborta venta) |
| 3 | Fases 5-6: endpoints admin/tpv + verificación final | Tanda 3 | Depende de Unit 2 |

## Phase 1: Configuración de empresa (modelo + migración)

- [x] 1.1 RED: modelo `ConfiguracionEmpresa` (`id` pk, `control_stock_activo` bool default False) con `create_all` efímero — `tests/test_config_empresa.py` (patrón `test_cierre_z_modelos.py`)
- [x] 1.2 GREEN: `app/infraestructura/persistencia/modelos/configuracion.py`; exportar en `modelos/__init__.py`
- [x] 1.3 RED: migración crea tabla + fila singleton `id=1, control_stock_activo=false` + índice `ix_movimiento_stock_articulo` en `movimiento_stock.articulo_id` — mismo `tests/test_config_empresa.py`; `tests/test_esquema.py` cubre paridad modelo/migración sin cambios
- [x] 1.4 GREEN: `migrations/versions/0004_configuracion_empresa.py` (`down_revision="0003_cierre_z"`): `create_table` + `INSERT` fila id=1 + `create_index`; sin triggers (tabla mutable)

## Phase 2: Repositorio de configuración y de stock

- [x] 2.1 RED: `RepositorioConfiguracion.control_stock_activo()` False por defecto; `fijar_control_stock(True)` persiste — `tests/test_repositorios.py`
- [x] 2.2 RED: `RepositorioStock.stock_actual` con entrada(+10)/venta(-3)/merma(-2) = 5 en Decimal; `rastreados_en_negativo` solo artículos <0 — mismo fichero
- [x] 2.3 GREEN: puertos `RepositorioConfiguracion` y `RepositorioStock` en `app/dominio/puertos.py`; `RepositorioConfiguracionSQL`/`RepositorioStockSQL` en `repositorios.py` (agregación Python/Decimal, nunca `SUM` SQL); wiring `uow.configuracion`/`uow.stock` en `unidad_de_trabajo.py`

## Phase 3: Casos de uso de stock

- [x] 3.1 RED: `RegistrarEntrada`/`RegistrarMerma` persisten y auditan (`log_auditoria`); `RegistrarMerma` sin motivo → `MotivoRequerido` sin persistir; cantidad ≤0 → `CantidadInvalida`; artículo con `control_stock=false` → `ArticuloNoRastreado` — nuevo `tests/test_stock_casos_uso.py`
- [x] 3.2 GREEN: `app/aplicacion/stock.py`: `RegistrarEntrada`, `RegistrarMerma`, `ConsultarStock` + excepciones; `flush()`+auditoría+`commit()`; independientes del toggle global (solo exigen `Articulo.control_stock=true`)

## Phase 4: Integración no bloqueante en EmitirVenta

- [ ] 4.1 RED: toggle apagado ⇒ venta con líneas rastreadas no crea `MovimientoStock` — `tests/test_emitir_venta.py`
- [ ] 4.2 RED: toggle encendido ⇒ solo líneas `control_stock=true` generan movimiento `venta`
- [ ] 4.3 RED (INNEGOCIABLE): `uow.stock.agregar` lanza dentro del SAVEPOINT ⇒ venta `cobrada`+registro fiscal encadenado, sin `MovimientoStock`, sin abortar
- [ ] 4.4 RED: sobreventa (stock 1, vende 5) ⇒ saldo -4 y `rastreados_en_negativo` la cuenta
- [ ] 4.5 GREEN: `_efecto_stock(venta, usuario_id)` en `app/aplicacion/emitir_venta.py`, llamado tras `motor.emit` y antes de `commit`; gateado por `uow.configuracion.control_stock_activo()`; por línea rastreada `with session.begin_nested(): uow.stock.agregar(...)`; `except Exception` capturada (log warning), nunca propagada

## Phase 5: Endpoints

- [ ] 5.1 RED: `/admin` — POST `/api/stock/ajuste`, POST `/api/stock/entrada`, POST `/api/stock/merma`, GET `/api/stock`, GET `/api/stock/{id}/movimientos`, GET `/api/stock/estado`; incl. 401 sin sesión — nuevo `tests/test_stock_admin_api.py`
- [ ] 5.2 GREEN: endpoints en `app/presentacion/admin.py` (auditados, rol administración, `_origen`)
- [ ] 5.3 RED: `/tpv` GET `/api/stock/alarma` → `{control_activo, articulos_en_negativo}`, informativa, con PIN — `tests/test_tpv_api.py`
- [ ] 5.4 GREEN: endpoint en `app/presentacion/tpv.py` (patrón alarma de cola de remisión)

## Phase 6: Verificación final

- [ ] 6.1 Suite completa verde: `.venv/Scripts/python -m pytest` (219 previos + nuevos, sin regresión)
- [ ] 6.2 `make arch` verde (dominio sin import de ORM/FastAPI)
