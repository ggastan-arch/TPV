# Tasks: Cierre Z (informe Z inmutable)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~750-850 (código nuevo ~450 + tests nuevos ~350) |
| 400-line budget risk | High |
| Chained PRs recommended | No — repo sin flujo de PRs (commit directo a main) |
| Suggested split | Commit único cohesivo; checkpoints internos de auto-revisión (ver Work Units) |
| Delivery strategy | single-pr (equivalente de repo: commit directo) |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

Nota: sin PRs, el tamaño (~800 líneas) sigue siendo GRANDE para revisión humana en una
sola pasada. Auto-revisar por checkpoint antes del commit final, no de un tirón.

### Suggested Work Units (checkpoints de auto-revisión, no PRs)

| Checkpoint | Alcance | Depende de |
|------------|---------|------------|
| A | Fases 1-2: modelos + triggers + migración | — |
| B | Fase 3: puertos/repositorios | A |
| C | Fases 4-5: caso de uso + snapshot | B |
| D | Fase 6: endpoints | C |
| E | Fase 7: verificación final | A-D |

## Fase 1: Modelos ORM

- [x] 1.1 RED: `tests/test_cierre_z_modelos.py` — importa `CierreZ`/`CierreZDesgloseIva`/`CierreZDesglosePago`, columnas y relaciones (falla: no existen).
- [x] 1.2 GREEN: crear `app/infraestructura/persistencia/modelos/cierre_z.py` (3 clases ORM, `Dinero`/`Porcentaje`, cascade delete-orphan en hijas).
- [x] 1.3 GREEN: exportar en `app/infraestructura/persistencia/modelos/__init__.py` (`__all__`); test 1.1 verde.

## Fase 2: Triggers de inmutabilidad + migración

- [x] 2.1 RED: `tests/test_cierre_z_inmutabilidad.py` — UPDATE/DELETE sobre `cierre_z` y sus 2 hijas debe abortar (patrón `test_inmutabilidad.py`); falla.
- [x] 2.2 GREEN: `TRIGGERS_CIERRE_Z`/`DROP_TRIGGERS_CIERRE_Z` en `app/infraestructura/persistencia/ddl.py` (BEFORE UPDATE/DELETE incondicional, 3 tablas).
- [x] 2.3 GREEN: crear `migrations/versions/0003_cierre_z.py` (`revises="0002_remision"`): `create_table` x3 + índices (`uq_cierre_z_numero`) + `op.execute(TRIGGERS_CIERRE_Z)`; `downgrade` inverso.
- [x] 2.4 GREEN: test 2.1 verde; sumar nombres de triggers nuevos al set esperado en `tests/test_esquema.py`.

## Fase 3: Puertos + adaptadores

- [x] 3.1 RED: `tests/test_cierre_z_repositorio.py` — `uow.cierres_z.ultimo/agregar/buscar/listar` y `uow.registros.max_orden_alta()`; falla.
- [x] 3.2 GREEN: puerto `RepositorioCierresZ` (Protocol) en `app/dominio/puertos.py`; ampliar `RepositorioRegistros` (`max_orden_alta()`) y `UnidadDeTrabajo` (`cierres_z`).
- [x] 3.3 GREEN: `RepositorioCierresZSQL` en `app/infraestructura/persistencia/repositorios.py` (`ultimo`, `agregar`, `buscar`, `listar`, `cobradas_por_rango_orden`); `max_orden_alta()` en `RepositorioRegistrosSQL`.
- [x] 3.4 GREEN: cablear `self.cierres_z` en `UnidadDeTrabajoSQL` (`unidad_de_trabajo.py`); test 3.1 verde.

## Fase 4: Caso de uso `GenerarCierreZ`

- [x] 4.1 RED: `tests/test_cierre_z_generar.py` — numeración correlativa Z-1, Z-2… y `UniqueConstraint`; falla (no existe `GenerarCierreZ`).
- [x] 4.2 RED: sumar escenarios — rango contiguo (`desde_n = hasta_{n-1}+1`), cuadre de totales/desglose IVA y pago, Z a cero (0 tickets, totales 0.00, sin excepción), ticket aparcado emitido tras un cierre cae en el Z siguiente por `registro_fiscal.orden`.
- [x] 4.3 GREEN: crear `app/aplicacion/generar_cierre_z.py` — `GenerarCierreZ.ejecutar(usuario_id, origen="local") -> ResultadoCierreZ`: `BEGIN IMMEDIATE`, `ultimo()`, `max_orden_alta()`, `cobradas_por_rango_orden`, `agregar()`+`flush()`, `auditoria.registrar(...)`, `commit()`. Rango vacío NO lanza excepción (requisito resuelto).
- [x] 4.4 GREEN: tests 4.1/4.2 verdes.

## Fase 5: Snapshot inmutable

- [x] 5.1 RED: `tests/test_cierre_z_snapshot.py` — generar Z, `motor.cancel()` sobre venta de su rango, releer Z; totales sin cambios.
- [x] 5.2 GREEN: confirmar/ajustar que la lectura del Z solo consulta `cierre_z*` (nunca recomputa contra `venta`/`registro_fiscal`); test 5.1 verde.

## Fase 6: Endpoints `/admin`

- [x] 6.1 RED: `tests/test_cierre_z_api.py` — POST/GET sin sesión → 401 (patrón `test_admin_api.py`); falla.
- [x] 6.2 RED: sumar escenarios — POST autenticado crea `CierreZ` + fila `log_auditoria`; GET lista; GET detalle por número (404 si no existe).
- [x] 6.3 GREEN: en `app/presentacion/admin.py` — `POST /api/maestros/cierres-z`, `GET /api/maestros/cierres-z`, `GET /api/maestros/cierres-z/{numero}` con `Depends(require_admin)` + `Depends(get_uow)`, invocando `GenerarCierreZ` (ruta bajo `/api/maestros/*` por coherencia con el resto de maestros, ver Deviations en apply-progress).
- [x] 6.4 GREEN: tests 6.1/6.2 verdes.

## Fase 7: Verificación final

- [x] 7.1 `.venv/Scripts/python -m pytest` completo: 210 tests previos + 8 nuevos = 218, todo verde (sin regresión).
- [x] 7.2 `lint-imports` (import-linter): 3 contratos KEPT, `generar_cierre_z.py` solo importa puertos + modelos, capas hexagonales respetadas.
