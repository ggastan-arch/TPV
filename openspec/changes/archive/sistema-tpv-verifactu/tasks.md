# Tasks: Sistema TPV Bizkaitropik (VERI*FACTU)

> **Naturaleza**: SDD **retrospectivo**. Este documento NO es un plan de trabajo pendiente:
> es un **ledger de trazabilidad** del proceso incremental ya ejecutado (161 tests en verde,
> `make arch` en verde). Lo entregado se marca `[x]` con referencia a módulo y test. El
> trabajo futuro se lista `[ ]` sin marcar, en su propia sección al final. No hay fase de
> `sdd-apply` ni PR sobre este cambio: es documentación pura.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | N/A — no se toca `app/` ni `tests/`; solo artefactos SDD |
| 400-line budget risk | N/A |
| Chained PRs recommended | No |
| Suggested split | No aplica (documentación-única, sin apply ni PR) |
| Delivery strategy | N/A |
| Chain strategy | pending |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: N/A
```

### Suggested Work Units

No aplica. Este cambio no tiene fase de `sdd-apply` ni PR: es un ledger de documentación
sobre código ya mergeado y verificado.

## Fase 1: Fundaciones de datos (`fundaciones-datos`)

- [x] 1.1 Tipos monetarios `Decimal`/TEXT — `app/infraestructura/tipos.py::DecimalTexto` — `tests/test_redondeo.py::test_no_hay_float_en_el_camino`, `tests/test_esquema.py`
- [x] 1.2 Redondeo único half-up por línea — `tests/test_redondeo.py::test_ticket_multitipo_cuadra`, `::test_base_mas_cuota_igual_total`, `::test_descuento_por_linea`
- [x] 1.3 Validadores NIF/NIE/CIF y normalización — `tests/test_nif.py::test_documentos_validos`, `::test_documentos_invalidos`, `::test_normalizar_documento`
- [x] 1.4 Esquema BD + migraciones Alembic sincronizadas con modelos — `migrations/` — `tests/test_esquema.py::test_todas_las_tablas_y_columnas_del_modelo_existen`
- [x] 1.5 Triggers de inmutabilidad (venta/registro emitidos) — `app/infraestructura/persistencia/ddl.py` — `tests/test_inmutabilidad.py`, `tests/test_esquema.py::test_triggers_de_inmutabilidad_instalados`
- [x] 1.6 Numeración correlativa sin huecos (`BEGIN IMMEDIATE`, ADR-0004) — `tests/test_numeracion_concurrente.py::test_emisiones_concurrentes_sin_huecos_ni_duplicados`
- [x] 1.7 Log de auditoría append-only — `tests/test_auditoria_append_only.py`
- [x] 1.8 Árbol de familias de niveles ilimitados — `tests/test_familia_arbol.py::test_arbol_de_familias_n_niveles`

## Fase 2: Motor fiscal VERI*FACTU (`motor-fiscal-verifactu`)

- [x] 2.1 Puerto `MotorFiscal` (emit/cancel/verify_chain) + `NullEngine`/`VerifactuEngine` — `app/dominio/puertos.py`, `app/infraestructura/fiscal/engine.py` — `tests/test_cadena.py::test_encadenamiento_y_verificacion`, `tests/test_anulacion.py`
- [x] 2.2 Huella SHA-256 encadenada vs. vectores oficiales AEAT (art. 13, ADR-0007) — `tests/test_huella_vectores.py`
- [x] 2.3 Sustitución F2→F3 (`FacturasSustituidas`, `VentaSustitucion`) — `tests/test_sustitucion.py`
- [x] 2.4 Serialización XML validada contra XSD oficiales — `app/infraestructura/fiscal/xml.py`, `validacion.py` — `tests/test_xml_validacion.py`
- [x] 2.5 QR tributario de cotejo (arts. 20-21) — `app/infraestructura/fiscal/qr.py` — `tests/test_qr.py`
- [x] 2.6 Sobre SOAP `RegFactuSistemaFacturacion` + cliente `Remitente` — `app/infraestructura/fiscal/remitente.py` — `tests/test_envelope.py`, `tests/test_remitente.py`
- [x] 2.7 Cola de remisión FIFO con reintentos e incidencia — `tests/test_remision.py`
- [x] 2.8 Validaciones de negocio previas a remisión (límite 3.000 €, NIF, serie, fecha) — `tests/test_validaciones_negocio.py`

## Fase 3: TPV táctil (`tpv-venta`)

- [x] 3.1 Cálculo de líneas en servidor, precio/IVA congelados — `POST /tpv/api/calcular` — `tests/test_tpv_api.py::test_calcular_totales_en_servidor`, `::test_calcular_precio_libre`
- [x] 3.2 Autenticación por PIN de operador — `POST /tpv/api/login` — `tests/test_tpv_api.py::test_login_ok_y_ko`
- [x] 3.3 `EmitirVenta` atómica offline, serie/número en la misma transacción — `tests/test_emitir_venta.py`, `tests/test_tpv_api.py::test_cobrar_emite_venta`, `::test_cobrar_ticket_vacio_rechaza`
- [x] 3.4 Medios de pago múltiples y cálculo de cambio — `tests/test_emitir_venta.py::test_emitir_venta_emite_y_encadena`
- [x] 3.5 Impresión ESC/POS con QR y cajón; fallo de impresora no revierte venta — `app/infraestructura/impresion/ticket.py`, `app/presentacion/tpv.py::_imprimir_ticket_seguro` — `tests/test_ticket.py`
- [x] 3.6 Descarga del QR tributario en PNG — `GET /tpv/api/venta/{id}/qr.png` — `tests/test_tpv_api.py::test_cobrar_emite_venta` (bloque QR)

## Fase 4: Consola de administración (`consola-administracion`)

- [x] 4.1 Auth con sesión + rol `administracion` bajo `/admin/api/*` — `tests/test_admin_api.py::test_endpoint_protegido_exige_sesion`, `::test_login_solo_admin`, `::test_flujo_completo`
- [x] 4.2 Panel fiscal: cola, `verify_chain`, declaración responsable — `GET /admin/api/fiscal/estado` — `tests/test_admin_api.py::test_flujo_completo`
- [x] 4.3 Reintento de remisión respetando custodia del certificado — `POST /admin/api/fiscal/reintentar` — `tests/test_admin_api.py::test_reintentar_sin_certificado`
- [x] 4.4 Informe del día — `GET /admin/api/informes/dia` — `tests/test_admin_api.py::test_flujo_completo`
- [x] 4.5 Auditoría de accesos con origen local/remoto — `tests/test_admin_api.py::test_acceso_queda_en_auditoria`
- [x] 4.6 Hash de PIN nunca expuesto en la API — `tests/test_admin_api.py::test_maestros_usuarios_no_exponen_hash`

## Fase 5: Refactor a hexagonal pragmático (transversal, ADR-0001)

- [x] 5.1 Separación en capas `dominio`/`aplicacion`/`infraestructura`/`presentacion` — `app/dominio/`, `app/aplicacion/`, `app/infraestructura/`, `app/presentacion/`
- [x] 5.2 Puertos formales (`Protocol`) para inversión de dependencias — `app/dominio/puertos.py`
- [x] 5.3 Regla de dependencias verificada en CI — `pyproject.toml [tool.importlinter]`, `tests/test_arquitectura.py`, comando `make arch`

## Fase 6: CRUD de maestros (`maestros-crud`)

- [x] 6.1 Artículos: validación FK, auditoría de cambio de precio, borrado lógico (commit `77a3788`) — `tests/test_articulos.py`, `tests/test_admin_api.py::test_crear_articulo_tipo_iva_inexistente`, `::test_desactivar_articulo`
- [x] 6.2 Tipos de IVA: validación de porcentaje, congelado histórico en ventas emitidas (commit `9f3dd3b`) — `tests/test_tipos_iva.py`, `tests/test_admin_api.py::test_crear_tipo_iva_porcentaje_invalido`
- [x] 6.3 Familias: árbol, prevención de ciclos, bloqueo de baja con hijos activos (commit `f23a162`) — `tests/test_familias.py`, `tests/test_admin_api.py::test_reasignar_padre_ciclo_devuelve_422`, `::test_desactivar_familia_con_hijos_devuelve_409`
- [x] 6.4 Clientes: NIF opcional validado/normalizado (commit `ed4094f`) — `tests/test_clientes.py`, `tests/test_admin_api.py::test_crear_cliente_nif_invalido`
- [x] 6.5 Auditoría transversal de alta/edición/baja en los 4 maestros — `tests/test_articulos.py::test_crear_articulo_persiste_y_audita`, `tests/test_familias.py::test_crear_familia_raiz_persiste_y_audita`, `tests/test_clientes.py::test_actualizar_cliente_ok_y_audita`, `tests/test_tipos_iva.py::test_crear_tipo_iva_persiste_y_audita`

## Trabajo futuro (no entregado)

- [ ] CRUD de usuarios (alta/edición de operadores y roles; no dejar el sistema sin admin activo)
- [ ] Remisión REAL contra el entorno de la AEAT (requiere certificado electrónico; custodia en el servidor, nunca sale ni se loguea)
- [ ] Endurecer el test del informe del día (`/admin/api/informes/dia`): hoy solo verifica status 200, falta asertar el contenido del agregado (total y desglose por medio de pago)
- [ ] Editor visual de botoneras
- [ ] Cierre Z / arqueo de caja
- [ ] Control de stock y mermas
- [ ] Backup/replicación con Litestream
