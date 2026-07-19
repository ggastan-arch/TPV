# Tasks: Cliente en venta + simplificada cualificada (art. 7.2/7.3 ROF)

> STRICT TDD. Runner: `.venv/Scripts/python -m pytest`. Cada bloque: RED (test que
> falla) → GREEN (implementación mínima). Ninguna tarea arranca marcada.

**Nota de override sobre D2 (design.md)**: se sigue la Opción B de D2 (no tocar
`trg_venta_no_update` ni `_VENTA_CAMPOS_CONGELADOS`), NO el "Choice" documentado en
design.md (recrear el trigger). Razón: una venta `cobrada` ya está totalmente
congelada por el trigger vigente; ningún código cambia el flag durante las
transiciones permitidas. La migración 0009 usa `op.add_column` nativo únicamente
(mismo patrón que 0008), sin DROP+CREATE de trigger. Resto de design.md sin cambios.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~600-750 (additions+deletions; XML+ticket+validaciones ~150, cliente plumbing+endpoints+tests ~250, migración+test ~120, UI tpv.html ~100-150) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Migración + (A) Cliente plumbing; PR 2 = (B) Cualificada fiscal |
| Delivery strategy | ask-on-risk (no se recibió override explícito de esta sesión) |
| Chain strategy | pending — decisión del orquestador |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Migración 0009 + (A) Cliente plumbing: búsqueda/alta/asignación cliente, `cliente_id` opcional en cobro, endpoints y UI | PR 1 | Base: main/tracker. Autónomo: una venta sin cliente se comporta igual que hoy; verificable con `test_cobro_sin_cliente_noregresion` |
| 2 | (B) Cualificada fiscal: flag `cualificada`, XML condicional, huella, ticket, validaciones | PR 2 | Depende de `cliente_id`/`Venta.cliente` de PR 1. Base: rama de PR 1 (`feature-branch-chain`) o main (`stacked-to-main`) |

## Fase 1: Migración 0009 (Requirement: base de datos — dep. ninguna)

- [x] 1.1 RED `tests/test_migracion_cualificada.py` (nuevo, espejo de
  `test_migracion_aparcar.py`): aplicar migraciones hasta `0008`, insertar (SQL
  crudo) una venta `cobrada` + `registro_fiscal` con huella real; aplicar `head`;
  assert columna `cualificada` existe (nullable), assert los 6 triggers de
  inmutabilidad siguen presentes, assert la huella recomputada con los mismos
  campos es idéntica
- [x] 1.2 GREEN `migrations/versions/0009_venta_cualificada.py`: `op.add_column`
  NATIVO `cualificada` (Boolean, nullable, default False) sobre `venta`; NO
  `batch_alter_table`, NO recreación de `trg_venta_no_update`; `downgrade`:
  `drop_column`
- [x] 1.3 GREEN `app/infraestructura/persistencia/modelos/venta.py`: columna
  `cualificada: Mapped[bool | None]` + relationship `cliente: Mapped["Cliente | None"]`
  (para ticket/D6, `cliente_id` FK ya existe)

## Fase 2 (A): Cliente plumbing (Requirement: búsqueda/alta/asignación de cliente
— cliente-en-venta spec — dep. Fase 1 para `Venta.cliente`)

- [x] 2.1 RED `tests/test_clientes.py`: `buscar_por_nif` exacto (normalizado);
  `buscar_por_nombre` subcadena case-insensitive (mirror
  `RepositorioArticulosSQL.buscar_por_nombre`)
- [x] 2.2 GREEN `app/dominio/puertos.py`: añadir `buscar_por_nif`/`buscar_por_nombre`
  a `RepositorioClientes` (Protocol)
- [x] 2.3 GREEN `app/infraestructura/persistencia/repositorios.py`:
  `RepositorioClientesSQL.buscar_por_nif`/`buscar_por_nombre` (limite=20, escape
  de comodines LIKE)
- [x] 2.4 RED `tests/test_emitir_venta.py::test_emitir_venta_persiste_cliente_id_opcional`,
  `::test_emitir_venta_sin_cliente_id_no_regresion` (los 8 call-sites existentes deben
  seguir verdes sin `cliente_id`)
- [x] 2.5 GREEN `app/aplicacion/emitir_venta.py`: `cliente_id: int | None = None` en
  `ejecutar()`; set `Venta.cliente_id`
- [x] 2.6 RED `tests/test_tpv_api.py::test_cobrar_con_cliente_asignado`
- [x] 2.7 GREEN `app/presentacion/tpv.py`: `CobrarReq.cliente_id: int | None = None`;
  pasar a `EmitirVenta.ejecutar`
- [x] 2.8 RED `tests/test_clientes_tpv.py` (nuevo): `GET /tpv/api/clientes?q=`
  PIN-gated (401 sin PIN); coincidencia por nombre y por NIF; `POST
  /tpv/api/clientes` alta inline con `rgpd_consentimiento=true` persiste y queda
  disponible para buscar; NIF inválido → 422 sin persistir
- [x] 2.9 GREEN `app/presentacion/tpv.py`: endpoints `GET /tpv/api/clientes` (usa
  `require_pin` + `buscar_por_nombre`/`buscar_por_nif`) y `POST /tpv/api/clientes`
  (DTO `ClienteReq`, reusa `ServicioClientes.crear`/`DatosCliente`, PIN-gated,
  `NifInvalido` → 422)
- [x] 2.10 `app/ui/tpv.html`: botón "Cliente en venta" → panel buscar/crear/asignar;
  `cliente_id` en el payload de `/api/cobrar`; cliente asignado visible en el carrito
  (smoke manual, sin test automatizado — estático sin motor de plantillas). Ademas
  se anadio marcaje `cualificada` en el mismo panel (checkbox condicionado a
  cliente asignado) para poder ejercitar el smoke 4.3 end-to-end; se actualizaron
  los tests estaticos existentes que asumian el boton `disabled`
  (`test_admin_ui.py`, `test_main.py`)

## Fase 3 (B): Cualificada fiscal (Requirement: marcaje condicional
FacturaSimplificadaArt7273 — motor-fiscal-verifactu + tpv-venta specs — dep. Fase 1)

- [x] 3.1 RED (regresión) `tests/test_validaciones_negocio.py::test_f2_con_destinatario_sigue_rechazado`:
  confirma que `DESTINATARIO_NO_PERMITIDO` sigue intacto (no debe requerir código
  nuevo; guarda contra que el trabajo de cualificada introduzca `Destinatarios`)
- [x] 3.2 RED `tests/test_validaciones_negocio.py::test_cualificada_sin_nif_domicilio_rechaza`
- [x] 3.3 GREEN `app/dominio/servicios/validaciones_negocio.py`: kwarg en
  `validar_alta` (p.ej. `cualificada_incompleta: bool = False`, mirror
  `tiene_destinatario`) → `Incidencia("CUALIFICADA_SIN_NIF_DOMICILIO", ..., "rechazo")`
- [x] 3.4 RED `tests/test_emitir_venta.py::test_cualificada_sin_nif_o_domicilio_rechaza`
  (`CualificadaSinDatos`), `::test_cualificada_con_datos_completos_marca_venta`
- [x] 3.5 GREEN `app/aplicacion/emitir_venta.py`: `cualificada: bool = False`;
  excepción `CualificadaSinDatos`; precondición `cliente.nif` y
  `cliente.domicilio` no vacíos si `cualificada`; set `Venta.cualificada`
- [x] 3.6 GREEN `app/presentacion/tpv.py`: `CobrarReq.cualificada: bool = False`;
  `except CualificadaSinDatos → HTTPException(422)`
- [x] 3.7 RED (golden) `tests/test_xml_validacion.py::test_simplificada_normal_xml_byte_identico`:
  sin flag, XML byte-idéntico al actual
- [x] 3.8 RED `tests/test_xml_validacion.py::test_cualificada_emite_flag_s_valida_xsd`:
  F2 cualificada → `FacturaSimplificadaArt7273=S` entre `DescripcionOperacion` y
  `Desglose`; valida contra XSD oficial
- [x] 3.9 GREEN `app/infraestructura/fiscal/xml.py`: `registro_alta_xml(...,
  cualificada: bool = False)`; elemento condicional en esa posición exacta,
  omitido si `False`
- [x] 3.10 RED `tests/test_huella_vectores.py::test_flag_cualificada_no_altera_huella`:
  misma huella con y sin flag para los mismos campos fiscales (`huella_alta` no
  recibe el flag — confirma que sigue así)
- [x] 3.11 GREEN `app/aplicacion/remitir_lote.py`: resolver
  `self.uow.ventas.buscar(reg.venta_id).cualificada` y pasarlo a
  `registro_alta_xml`
- [x] 3.12 RED `tests/test_ticket.py::test_ticket_cualificada_incluye_nif_domicilio_cuota_separada`,
  `::test_ticket_no_cualificado_sin_cambios` (golden, no cualificada = idéntico a hoy)
- [x] 3.13 GREEN `app/infraestructura/impresion/ticket.py`: `imprimir_ticket(...,
  cliente: "Cliente | None" = None)`; si `venta.cualificada` y `cliente`, bloque
  destinatario (nombre+NIF+domicilio) tras el emisor; desglose ya imprime cuota
  separada (sin cambios)
- [x] 3.14 GREEN `app/presentacion/tpv.py`: `_imprimir_ticket_seguro` carga
  `venta.cliente` y lo pasa a `imprimir_ticket`

## Fase 4: Verificación final (dep. Fases 1-3)

- [x] 4.1 `.venv/Scripts/python -m pytest`: suite completa verde — sin regresión
  en los 8 call-sites de cobro existentes ni en tickets/XML no cualificados
  (568 passed, 0 failed; baseline era 536 passed, +32 tests nuevos)
- [x] 4.2 `make arch` (import-linter): capas hexagonal intactas (3 contracts kept,
  0 broken)
- [x] 4.3 Smoke manual: buscar/crear/asignar cliente → marcar cualificada con
  NIF+domicilio completos → cobrar → ticket con destinatario + cuota separada.
  NOTA: verificado mediante el flujo automatizado equivalente (no hay acceso a
  navegador en este entorno de ejecucion) —
  `test_clientes_tpv.py` (buscar/crear/alta inline con RGPD),
  `test_tpv_api.py::test_cobrar_cualificada_con_datos_completos_marca_venta` (asignar +
  marcar cualificada + cobrar), `test_ticket.py::test_ticket_cualificada_incluye_nif_domicilio_cuota_separada`
  (ticket con destinatario + cuota separada). El wiring de `tpv.html` (panel
  "Cliente en venta" con checkbox de cualificada) queda pendiente de un smoke
  manual real en navegador antes de release a produccion.
