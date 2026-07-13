# Tasks: Robustez de la remisión VERI*FACTU (remision-robustez)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~340–420 (7 archivos de producción + 3 de test + helpers) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Tanda única (ya decidido: cambio chico, sin migración) |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Cambio completo (parseo duplicado + rechazo cabecera + reencolar + panel) | Commit único a `main` | Sin migración; `size:exception` ya aceptado por el usuario |

**Spec mapping**: R1=Transporte SOAP de remisión · R2=Cola FIFO con reintentos · R3=Recuperación manual (`requiere_intervencion`) · R4=Visibilidad persistente

## Phase 1: Fixtures de test

- [x] 1.1 `tests/_helpers.py`: extender `respuesta_remision_xml` — soporte de líneas con bloque `RegistroDuplicado`/`EstadoRegistroDuplicado`, y modo sin `RespuestaLinea` (`EstadoEnvio=Incorrecto`) para el rechazo de cabecera.

## Phase 2: Parseo del duplicado 3000 — remitente.py (R1)

- [x] 2.1 [RED] `tests/test_remitente.py::test_parsea_duplicado_correcta_es_aceptado` — 3000+`Correcta` → `resultado=aceptado`, `duplicado=True`.
- [x] 2.2 [RED] `tests/test_remitente.py::test_parsea_duplicado_aceptada_con_errores` — 3000+`AceptadaConErrores` → `aceptado_con_errores`.
- [x] 2.3 [RED] `tests/test_remitente.py::test_parsea_duplicado_anulada_requiere_intervencion` — 3000+`Anulada` → `estado_final=requiere_intervencion`.
- [x] 2.4 [GREEN] `app/infraestructura/fiscal/remitente.py` — tabla dedicada `_DUPLICADO_A_RESULTADO` (femenino); extender `ResultadoLinea` (`estado_final`, `duplicado`); parsear `RegistroDuplicado` en `_parsear_respuesta` (sin CSV propio).
- [x] 2.5 [REFACTOR] `remitente.py` — extraer helper de clasificación línea normal vs. duplicado si aporta legibilidad.

## Phase 3: Rechazo de cabecera y exclusión de la cola (R1, R2)

- [x] 3.1 [RED] `tests/test_remision.py::test_rechazo_cabecera_4109_marca_todo_el_lote` — respuesta sin líneas + `Incorrecto` → cada registro del lote en `requiere_intervencion`, motivo AEAT persistido en `remision_intento`, sin marca de incidencia.
- [x] 3.2 [RED] `tests/test_remision.py::test_requiere_intervencion_no_esta_en_pendientes` — el predicado de cola excluye el estado.
- [x] 3.3 [RED] `tests/test_remision.py::test_remitir_duplicado_sale_de_la_cola` — tras 3000 aceptado, `contar_pendientes()==0`, no se reenvía.
- [x] 3.4 [GREEN] `remitente.py` — extender `RespuestaEnvio` (`codigo_error_cabecera`, `descripcion_cabecera`); detectar `EstadoEnvio=Incorrecto` sin `RespuestaLinea`.
- [x] 3.5 [GREEN] `app/aplicacion/remitir_lote.py` — rama de rechazo de cabecera: recorrer TODO el lote, `registrar_resultado(reg, "rechazado", codigo_error=..., descripcion=..., estado_remision_final="requiere_intervencion")`, sin incidencia; aplicar `estado_remision_final` por línea normal (mapeo de duplicado).
- [x] 3.6 [GREEN] `app/infraestructura/persistencia/modelos/fiscal.py` — agregar `"requiere_intervencion"` a `ESTADOS_REMISION` (solo Python, `RESULTADOS_REMISION`/CHECK sin cambios).
- [x] 3.7 [GREEN] `app/infraestructura/persistencia/repositorios.py` — `ESTADOS_TERMINALES = ESTADOS_ACEPTADOS + ("requiere_intervencion",)` usado en `pendientes`/`contar_pendientes`/`hay_incidencia_pendiente`; `registrar_resultado(..., estado_remision_final=None)` retrocompatible.

## Phase 4: Reencolar (recuperación manual + auditoría) (R3)

- [x] 4.1 [RED] `tests/test_remision.py::test_reencolar_devuelve_a_pendiente_y_audita` — `requiere_intervencion`→`pendiente`, `LogAuditoria` creado, reaparece en `pendientes()`.
- [x] 4.2 [GREEN] `repositorios.py` — método `reencolar(registro)` (→ `estado_remision="pendiente"`).
- [x] 4.3 [GREEN] `app/presentacion/admin.py` — endpoint `POST /api/fiscal/reencolar` (`require_admin`) + `LogAuditoria(accion="reencolar_remision", origen=...)`. (Auditoría implementada dentro de `repositorios.reencolar`, invocada desde el endpoint; 3 tests HTTP añadidos: 404, 401 y flujo completo.)

## Phase 5: Visibilidad persistente del panel fiscal (R4)

- [x] 5.1 [RED] `tests/test_admin_api.py::test_fiscal_estado_expone_ultimo_error` — conteo `requiere_intervencion` y último código/descripción visibles entre refrescos sin nueva remisión.
- [x] 5.2 [GREEN] `repositorios.py` — método `ultimo_error()` (último `remision_intento` con `codigo_error`/`descripcion`, o `None`). Incluye `contar_requiere_intervencion()` (necesario para `cola.requiere_intervencion`, no listado explícitamente en tasks.md pero requerido por el ADDED requirement de visibilidad).
- [x] 5.3 [GREEN] `admin.py` — `fiscal_estado` agrega `cola.requiere_intervencion` y `ultimo_error`.
- [x] 5.4 [GREEN] `app/ui/admin.html` — `pintarFiscal()`: alarma "REQUIERE INTERVENCIÓN" persistente + bloque de último error; botón "Reencolar y reintentar" → `POST /admin/api/fiscal/reencolar`. (Sin test JS: este stack no tiene test runner de frontend, solo pytest de backend; N/A documentado en TDD Evidence.)

## Phase 6: No regresión

- [x] 6.1 [CONFIRM] `tests/test_remision.py::test_noregresion_aceptado_incidencia_rechazo_linea` — aceptado, aceptado_con_errores, incidencia de red y rechazo de línea con código≠3000 se comportan igual que antes (siguen reintentables; fuera de alcance).
- [x] 6.2 Ejecutar `python -m pytest` completo — `test_remitente.py`/`test_remision.py`/`test_admin_api.py` existentes siguen verdes (firmas retrocompatibles). Suite completa: 446 passed, 3 failed — los 3 fallos son IDÉNTICOS a los del baseline pre-cambio (contaminación de `.env` local con certificado/NIF reales de la instalación de la titular; no relacionados con este cambio, no se tocan). Ver detalle en el reporte de apply.

## Phase 7: Fix de WARNING de verify — guarda de precondición en `reencolar` (R3)

- [x] 7.1 [RED] `tests/test_remision.py::test_reencolar_rechaza_si_no_requiere_intervencion` — `reencolar()` sobre un registro `aceptado` (no `requiere_intervencion`) levanta `ValueError` y NO muta `estado_remision` ni escribe `LogAuditoria`.
- [x] 7.2 [RED] `tests/test_admin_api.py::test_reencolar_rechaza_si_no_requiere_intervencion_via_endpoint` — `POST /api/fiscal/reencolar` sobre ese mismo caso devuelve `409` y no muta el registro.
- [x] 7.3 [GREEN] `app/infraestructura/persistencia/repositorios.py::reencolar` — guarda: si `registro.estado_remision != "requiere_intervencion"`, `raise ValueError(...)` antes de mutar nada (mismo patrón que `engine.py::cancel` para precondiciones de estado fiscal).
- [x] 7.4 [GREEN] `app/presentacion/admin.py::fiscal_reencolar` — traduce ese `ValueError` a `HTTPException(409, str(exc))` (mismo criterio 409 que `FamiliaConHijos`/`UltimoAdministrador`).
