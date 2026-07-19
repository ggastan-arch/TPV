# Tasks: Aparcar / Desaparcar tickets

> STRICT TDD. Runner `.venv/Scripts/python -m pytest`. Cada tarea de implementación va
> precedida de su RED. Frontera fiscal: `EmitirVenta`/`emit`/numeración/registro/huella/
> triggers SIN CAMBIOS; la columna nueva NO entra en la huella (invariantes 1-7).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~600-750 (additions+deletions: migración+tests+3 capas+frontend) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 migración → PR2 casos de uso → PR3 endpoints → PR4 frontend |
| Delivery strategy | ask-on-risk (no se recibió override explícito) |
| Chain strategy | pending |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Migración Alembic 0008 + modelo `venta` + test de triggers/huella | PR 1 | Base=main; ~100-130 líneas; sin comportamiento nuevo visible |
| 2 | `RepositorioVentas` (+2 métodos) + 3 casos de uso `app/aplicacion` + tests unitarios/frontera fiscal | PR 2 | Base=PR1 (stacked) o main si `feature-branch-chain`; ~300-350 líneas |
| 3 | Endpoints `/tpv/api/aparcar\|aparcadas` + tests API (incl. no-regresión cobro) | PR 3 | Base=PR2; ~180-220 líneas |
| 4 | `tpv.html` (botones+overlay+JS) + rename `FUNCIONES` | PR 4 | Base=PR3; ~90-120 líneas; sin test automatizado de render (solo contrato backend) |

## Fase 1: Migración Alembic — columna no fiscal (dep: ninguna)

- [x] 1.1 RED `tests/test_migracion_aparcar.py` (nuevo): emitir venta en revisión `0007` con `NullEngine`, capturar `registro.huella`/campos usados por `huella_alta`; `upgrade head` (0008); assert columna `etiqueta_aparcada` existe, NULL-able y NULL en esa fila (`PRAGMA table_info`); assert `sqlite_master` conserva `trg_venta_no_update/no_delete`, `trg_venta_linea_no_update/no_delete`, `trg_pago_no_update/no_delete`; recomputar `huella_alta` tras upgrade con los mismos campos y assert idéntica
- [x] 1.2 GREEN `migrations/versions/0008_venta_etiqueta_aparcada.py` (nuevo): `revision="0008_venta_etiqueta_aparcada"`, `down_revision="0007_modo_precio_articulo"`; `upgrade` = `op.add_column("venta", sa.Column("etiqueta_aparcada", sa.String(), nullable=True))` NATIVO (nunca `batch_alter_table`); `downgrade` = `op.drop_column("venta","etiqueta_aparcada")`
- [x] 1.3 GREEN `app/infraestructura/persistencia/modelos/venta.py`: añadir `etiqueta_aparcada: Mapped[str | None] = mapped_column(String, nullable=True)`
- [x] 1.4 Verificación: `tests/test_esquema.py` y `tests/test_alembic_url.py` siguen verdes con el nuevo head

## Fase 2: Casos de uso aparcar/listar/recuperar (dep: Fase 1)

- [x] 2.1 RED `tests/test_aparcar_venta.py` (nuevo): `AparcarVenta(uow).ejecutar(usuario_id, items, etiqueta="Mostrador 2")` persiste `Venta(estado='aparcada')`+3 `VentaLinea`+etiqueta; sin etiqueta → `None` (escenarios: con/sin etiqueta)
- [x] 2.2 RED mismo archivo: `items=[]` → `TicketVacio`, cero filas persistidas (escenario: carrito vacío)
- [x] 2.3 RED mismo archivo — frontera fiscal: tras aparcar, `venta.serie/numero/num_serie_factura/fecha_hora_huso` son `None`, no existe `RegistroFiscal`, `ContadorSerie` sin cambios; `AparcarVenta.__init__(uow)` no acepta `motor` (escenario: aparcar no crea identidad fiscal)
- [x] 2.4 GREEN `app/aplicacion/lineas.py`: extraer `construir_lineas(resueltas) -> list[VentaLinea]`; `EmitirVenta` lo adopta sin cambiar objetos (guardia: `tests/test_emitir_venta.py` sigue verde)
- [x] 2.5 GREEN `app/aplicacion/aparcar_venta.py` (nuevo): `class AparcarVenta` (uow, sin motor): `ejecutar(*, usuario_id, items, etiqueta=None) -> int`; usa `resolver_items(exigir_descripcion_libre=False)` + `construir_lineas`; `TicketVacio` si vacío
- [x] 2.6 RED mismo archivo: `ListarAparcadas(uow).ejecutar()` devuelve solo `estado='aparcada'` con etiqueta/total/n_lineas, orden `id` DESC, sin límite (escenario: listado de distintos usuarios)
- [x] 2.7 GREEN `app/dominio/puertos.py` (`RepositorioVentas`): `+listar_por_estado(estado) -> list[Venta]`; `app/infraestructura/persistencia/repositorios.py` (`RepositorioVentasSQL`): impl SQL (`order by id desc`)
- [x] 2.8 GREEN `app/aplicacion/aparcar_venta.py`: `class ListarAparcadas(uow)` + `AparcadaDTO(venta_id, etiqueta, total, n_lineas)`
- [x] 2.9 RED mismo archivo: `RecuperarAparcada(uow).ejecutar(venta_id)` devuelve líneas (articulo_id/cantidad/pvp/descripcion) y BORRA venta+líneas (cascade); mismo id otra vez → `BorradorNoEncontrado` sin duplicar (escenarios: desaparcar / desaparcar dos veces)
- [x] 2.10 GREEN `puertos.py`: `+eliminar(venta) -> None`; `repositorios.py`: impl (`session.delete`; triggers eximen `aparcada`)
- [x] 2.11 GREEN `app/aplicacion/aparcar_venta.py`: `class RecuperarAparcada(uow)` + `LineaCarritoDTO` + `BorradorNoEncontrado`

## Fase 3: Endpoints `/tpv/api/*` (dep: Fase 2)

- [x] 3.1 RED `tests/test_tpv_api.py`: `POST /tpv/api/aparcar {usuario_id,items,etiqueta}` → 200 `{venta_id,etiqueta,total,n_lineas}`; `items=[]` → 400
- [x] 3.2 GREEN `app/presentacion/tpv.py`: `AparcarReq(BaseModel)`; endpoint delega en `AparcarVenta`, captura `TicketVacio`/`ArticuloNoExiste`
- [x] 3.3 RED mismo archivo: `GET /tpv/api/aparcadas` → lista `[{venta_id,etiqueta,total,n_lineas}]` orden `id` DESC
- [x] 3.4 GREEN `tpv.py`: endpoint delega en `ListarAparcadas`
- [x] 3.5 RED mismo archivo: `DELETE /tpv/api/aparcadas/{id}` → 200 `{lineas:[...]}` enriquecidas con `modo_precio`/`nombre_corto` (join `Articulo`); id ya consumido → 404 sin duplicar
- [x] 3.6 GREEN `tpv.py`: endpoint delega en `RecuperarAparcada`, enriquece cada línea con `Articulo.modo_precio/nombre_corto`
- [x] 3.7 RED+GREEN mismo archivo: flujo aparcar→desaparcar→`POST /tpv/api/cobrar` con esas líneas emite venta nueva (serie+número+registro+huella) igual que un cobro desde cero (escenario: cobrar un carrito recuperado); no regresión: `tests/test_emitir_venta.py` y demás tests de cobrar existentes siguen verdes sin tocar `EmitirVenta`

## Fase 4: Frontend `tpv.html` (dep: Fase 3)

- [x] 4.1 RED `tests/test_tpv_api.py` (contenido estático): `GET /tpv/` sirve `tpv.html` sin `disabled` en "Aparcar ticket"/"Desaparcar" y referenciando `/tpv/api/aparcar`, `/tpv/api/aparcadas`
- [x] 4.2 GREEN `app/ui/tpv.html`: quitar `disabled`/`title="Próximamente"` de ambos botones del footer
- [x] 4.3 GREEN `tpv.html`: `ejecutarFuncion(f)` añade `'aparcar'` (prompt etiqueta opcional → POST aparcar → vaciar carrito) y `'desaparcar'` (GET aparcadas → overlay etiqueta+total+n_lineas → click → DELETE → repuebla `carrito` con `editado:true` → `recalcular()`)
- [x] 4.4 GREEN `app/dominio/servicios/botonera.py`: `FUNCIONES` rename `recuperar`→`desaparcar`; `app/infraestructura/persistencia/modelos/botonera.py`: actualizar docstring (grep confirma que ningún test/seed usa `'recuperar'`; ademas se actualizo la etiqueta del desplegable `FUNCIONES_BOTONERA` en `app/ui/admin.html`, que si referenciaba el valor `'recuperar'`)
- [x] 4.5 Verificación manual: aparcar con etiqueta → listar → desaparcar → líneas repobladas en carrito → cobrar (cubierto end-to-end por `test_cobrar_un_carrito_recuperado_emite_venta_nueva`)

## Fase 5: Verificación final (dep: todas)

- [x] 5.1 `.venv/Scripts/python -m pytest`: suite completa verde (530 tests, incluye 161+ previos sin regresión + nuevos de Fases 1-4)
- [x] 5.2 `make arch`: import-linter sin romper la regla hexagonal (nuevo `app/aplicacion/aparcar_venta.py`) — "Contracts: 3 kept, 0 broken"
- [x] 5.3 Confirmar sin diff en `EmitirVenta`/`engine.py`/`ddl.py`: `engine.py` y `ddl.py` con diff vacío; `emitir_venta.py` solo cambia por adoptar `construir_lineas` (mismos objetos `VentaLinea`, misma semantica; guardia: `tests/test_emitir_venta.py` sigue verde) — el `emit`/numeración/huella no se tocan

### Nota de proceso (Review Workload Guard)

El forecast marcaba `Chained PRs recommended: Yes` / `Decision needed before apply: Yes`
con `chain_strategy: pending`. El orquestador instruyó explícitamente ejecutar las 5 fases
en UN solo batch de apply, sin commit (revisión de contexto fresco antes de cualquier commit
o división en PRs). Se registra como decisión explícita de la orquestación, no como un olvido
del guardarraíl: los commits/PRs encadenados, si se deciden, se organizarán a partir de este
mismo diff en la fase de commit/PR posterior.
