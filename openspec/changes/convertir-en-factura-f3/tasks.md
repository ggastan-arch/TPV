# Tasks: Convertir simplificadas en factura completa de sustitución (F3)

> STRICT TDD. Runner: `.venv/Scripts/python -m pytest`. Cada bloque: RED (test que
> falla) → GREEN (implementación mínima). Ninguna tarea arranca marcada.

**Nota de alcance sobre `validaciones_negocio.py`**: el fichero YA implementa
`FALTA_DESTINATARIO`/`DESTINATARIO_NO_PERMITIDO`/`FACTURAS_SUSTITUIDAS_SOLO_F3`
(líneas 125-133) pero — igual que el kwarg `cualificada_incompleta` — NO está
cableado a `NullEngine.emit` ni a `RemitirLote` en el camino real (confirmado por
el propio comentario del fichero, Judgment Day W-1). Este cambio NO modifica
`validaciones_negocio.py` ni lo conecta al flujo de emisión/remisión: solo añade
un test de confirmación (Fase 4). Cablearlo queda fuera de alcance — evaluar el
riesgo fiscal de tocar ese camino no es parte de este cambio.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~800-900 (caso de uso+tests ~360; puertos/repo+tests ~40; XML Destinatarios+tests ~115; remitir_lote+tests ~55; confirmación validaciones ~15; admin endpoints+tests ~170; UI admin.html+tests ~120) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Fases 1-2 (caso de uso `conversion-factura-f3`); PR 2 = Fases 3-4 (`motor-fiscal-verifactu`: Destinatarios+remisión); PR 3 = Fases 5-6 (`consola-administracion`: endpoints+panel) |
| Delivery strategy | ask-on-risk (sin override explícito recibido en esta sesión) |
| Chain strategy | pending — decisión del orquestador/usuario |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Fases 1-2: `RepositorioVentas.convertibles()` + caso de uso `ConvertirEnFacturaF3` completo (elegibilidad, N→1, destinatario, auditoría, cadena) | PR 1 | Base: main/tracker. Autónomo y verificable sin endpoint (tests de caso de uso puro, sin HTTP) |
| 2 | Fases 3-4: bloque `Destinatarios/IDDestinatario` en XML + resolución en `remitir_lote` + confirmación de `validaciones_negocio` | PR 2 | SIN dependencia de código de PR 1 (el destinatario se resuelve desde `venta.cliente_id`, ya existente); puede revisarse en paralelo. Base: main si `stacked-to-main`, o rama de PR 1 si `feature-branch-chain` |
| 3 | Fases 5-6: endpoints admin (`GET/POST /admin/api/ventas/...`) + panel Nocturne | PR 3 | Depende de PR 1 (usa `ConvertirEnFacturaF3`); para corrección fiscal end-to-end en producción también requiere PR 2 mergeado antes de remitir de verdad. Base: rama de PR 2 (o PR 1) según estrategia |

## Fase 1: Elegibilidad — puerto + repositorio (Requirement: Elegibilidad de simplificadas convertibles — conversion-factura-f3 spec — dep. ninguna)

- [x] 1.1 RED `tests/test_repositorios.py` (o nuevo `tests/test_ventas_convertibles.py`):
  crear 3 T — cobrada sin sustituir, cobrada ya sustituida (vía `VentaSustitucion`),
  aparcada — assert `RepositorioVentasSQL.convertibles()` devuelve solo la primera
- [x] 1.2 GREEN `app/dominio/puertos.py`: `def convertibles(self) -> list["Venta"]: ...`
  en el Protocol `RepositorioVentas`
- [x] 1.3 GREEN `app/infraestructura/persistencia/repositorios.py`:
  `RepositorioVentasSQL.convertibles()` — `select(Venta).where(Venta.serie == "T",
  Venta.estado == "cobrada", Venta.id.notin_(select(VentaSustitucion.venta_sustituida_id)))`

## Fase 2: Caso de uso `ConvertirEnFacturaF3` (Requirement: Conversión atómica 1..N→1 F3 + Transición sin borrado + Destinatario inline + Auditoría + Integridad de cadena — conversion-factura-f3 spec — dep. Fase 1)

- [x] 2.1 RED `tests/test_convertir_en_factura_f3.py` (nuevo)
  `::test_elegibilidad_rechaza_no_cobrada_no_t_o_inexistente` — id inexistente, id
  aparcada, id serie F → `SimplificadaNoElegible`
- [x] 2.2 GREEN `app/aplicacion/convertir_en_factura_f3.py` (nuevo): dataclasses
  `DatosDestinatario(nif, nombre, domicilio)`, `ResultadoConversion`; excepciones
  `SinSimplificadas`, `SimplificadaNoElegible`, `YaSustituida`, `DestinatarioInvalido`;
  `ConvertirEnFacturaF3(uow, motor).ejecutar(usuario_id, origen, simplificada_ids,
  destinatario)` — por cada id: `uow.ventas.buscar(id)`; si `None`/`serie != "T"`/
  `estado` fuera de `{"cobrada","sustituida"}` → `SimplificadaNoElegible`
- [x] 2.3 RED `::test_convertir_dos_veces_una_t_falla` — T ya `sustituida` →
  `YaSustituida` (no `IntegrityError` crudo)
- [x] 2.4 GREEN: distinguir en 2.2 el caso `estado == "sustituida"` → `YaSustituida`
  del resto de casos no elegibles → `SimplificadaNoElegible`
- [x] 2.5 RED `::test_nif_destinatario_invalido` — NIF con dígito de control
  incorrecto → `DestinatarioInvalido`, nada persistido
- [x] 2.6 GREEN: validar `destinatario.nif` con `validar_documento` (dominio/servicios/
  validadores) ANTES de cualquier `INSERT`; sin ids no vacíos ni destinatario válido
  no se toca la sesión
- [x] 2.7 RED `::test_convertir_una_sola_simplificada_n1` — 1 T elegible → F3 con
  correlativo propio serie F, huella encadenada al último registro global, 1 entrada
  en `FacturasSustituidas`, T origen → `sustituida`
- [x] 2.8 GREEN completar `ejecutar()`: copiar como nuevas `VentaLinea` TODAS las
  líneas de las simplificadas origen (helper `_copiar_lineas`, valores
  `base_linea/cuota_linea/total_linea` ya cuantizados, SIN recalcular); resolver
  `Cliente` (`buscar_por_nif` → si no existe, crear con `validar_documento`/
  `normalizar_documento`, fijar `f3.cliente_id`); `motor.emit(session, f3, serie="F",
  tipo_factura="F3")`; por origen `RegistroFacturaSustituida` + `VentaSustitucion`;
  transición `origen.estado = "sustituida"`; `uow.commit()`
- [x] 2.9 RED `::test_convertir_dos_simplificadas_iva_mixto_en_una_f3` — 2 T (21% y
  10%) → 1 F3, `Desglose` separa ambos tipos, `ImporteTotal` == suma exacta de ambas
- [x] 2.10 RED `::test_totales_f3_reconcilian_sin_deriva` — 3+ líneas con decimales
  de borde → `CuotaTotal`/`ImporteTotal` de la F3 == Σ de las sustituidas al céntimo
  (JAMÁS re-redondeo; confirma que sumar `Decimal` ya cuantizados es exacto)
- [x] 2.11 RED `::test_rechazo_atomico_si_una_t_no_es_elegible` — 2 ids, uno ya
  `sustituida` → excepción, CERO `Venta`/`RegistroFacturaSustituida`/
  `VentaSustitucion` nuevos persistidos (rollback total)
- [x] 2.12 RED `::test_conversion_registra_auditoria_conversion_f3` —
  `LogAuditoria(accion="conversion_f3")` referencia las T origen y la F3
- [x] 2.13 GREEN: `uow.auditoria.registrar(accion="conversion_f3", entidad="venta",
  entidad_id=str(f3.id), detalle=<num_serie de cada T origen>, usuario_id=usuario_id,
  origen=origen)` dentro de la misma transacción, antes del `commit()`
- [x] 2.14 RED `::test_verify_chain_ok_tras_conversion_f3` — `motor.verify_chain(session)`
  sigue `ok=True` tras convertir, incluyendo el nuevo registro F3 (+1 registro)
- [x] 2.15 RED (regresión) `::test_importes_t_congelados_tras_sustituir` — intentar
  modificar `total_con_iva` de una T ya `sustituida` → `sa.exc.DatabaseError` (trigger
  existente, invariante 1; sin código nuevo)

## Fase 3: Bloque `Destinatarios` en XML (Requirement: Bloque Destinatarios/IDDestinatario condicional F1/F3 — motor-fiscal-verifactu spec — dep. ninguna, en paralelo a Fase 2) — [APLICADO, PR2]

- [x] 3.1 RED (golden, regresión) `tests/test_xml_validacion.py::test_xml_simplificada_t_byte_identica`
  — F2/T sin destinatario → XML idéntico al actual (`destinatario=None`)
- [x] 3.2 RED `tests/test_xml_validacion.py::test_xml_f3_con_destinatarios_valida_xsd`
  — F3 con `Destinatario(nombre, nif)` → bloque `Destinatarios/IDDestinatario`
  presente tras el bloque `FacturaSimplificadaArt7273`/`DescripcionOperacion` y
  antes de `Desglose`; valida contra el XSD oficial
- [x] 3.3 GREEN `app/infraestructura/fiscal/xml.py`: dataclass
  `Destinatario(nombre: str, nif: str)`; `registro_alta_xml(..., destinatario:
  Destinatario | None = None)`; bloque `if destinatario is not None:` insertado
  tras el bloque `cualificada` (línea ~134) y antes de `Desglose` (línea ~136)
- [x] 3.4 RED `tests/test_huella_vectores.py::test_huella_f3_independiente_del_destinatario`
  — 2 registros F3 con mismos importes/fecha, destinatario distinto → huella idéntica
  (`huella_alta` no recibe destinatario; frontera fiscal confirmada)
- [x] 3.5 RED (integración) `tests/test_remision.py` (fichero equivalente a
  `test_remitir_lote.py` — ya contiene toda la infraestructura `RemitirLote`):
  `test_remitir_lote_resuelve_destinatario_para_f1_f3` — registro F3 con
  `venta.cliente_id` fijado → `registro_alta_xml` recibe `Destinatario` resuelto;
  registro F2/T (sin cliente asignado o `tipo_factura` fuera de `{F1,F3}`) →
  `destinatario=None`
- [x] 3.6 GREEN `app/aplicacion/remitir_lote.py`: para `reg.tipo_factura in {"F1",
  "F3"}` resolver `venta = uow.ventas.buscar(reg.venta_id)`; si `venta.cliente` no
  es `None`, construir `Destinatario(nombre=cliente.nombre, nif=cliente.nif)`;
  pasar a `registro_alta_xml`; para el resto, `destinatario=None`
- [x] 3.7 RED `tests/test_remision.py::test_xml_f2_nunca_recibe_destinatario`
  (nota de ubicación: tasks.md original referenciaba `test_xml_validacion.py`,
  pero esta prueba necesita la infraestructura `RemitirLote`/`Remitente` ya
  presente en `test_remision.py`, junto a 3.5/3.6) — confirma que el camino real
  (`RemitirLote`) nunca pasa `destinatario` para F2 aunque exista
  `venta.cliente_id` (no regresión del invariante "T inalterada")

### Fase 3 (bis): correcciones de revisión fiscal (Judgment Day) — snapshot congelado del destinatario — [APLICADO, review-driven, rama `-c2`]

> Hallazgo: `ConvertirEnFacturaF3` solo congelaba `venta.cliente_id` (la FK); la
> remisión (`RemitirLote`, cola FIFO asíncrona) resolvía el destinatario EN VIVO
> desde `venta.cliente.nombre/nif` en el momento del envío. Un admin editando el
> cliente entre la emisión y la remisión hacía que la AEAT recibiera un
> destinatario DISTINTO del emitido/impreso en la F3 (documento fiscal, debe ser
> inmutable); un NIF vaciado producía un `<NIF/>` vacío (inválido contra el XSD)
> que bloquearía toda la cola FIFO.

- [x] 3.8 RED/GREEN `migrations/versions/0010_venta_destinatario_f3.py` (patrón
  exacto de `0009_venta_cualificada.py`, `op.add_column` NATIVO, sin
  `batch_alter_table`): columnas nullable `destinatario_nombre`/`destinatario_nif`
  en `venta`. Test `tests/test_migracion_destinatario_f3.py`
  (`test_migracion_0010_no_rompe_triggers_ni_huella`, mirror de
  `test_migracion_cualificada.py`): los 6 triggers de inmutabilidad sobreviven,
  huella de una venta ya emitida no cambia, UPDATE ilegal (incl. intento de
  "colar" un destinatario) sigue rechazado. D2 override documentado (mismo
  patrón 0009): NO se recrea `trg_venta_no_update`, columnas fuera de
  `_VENTA_CAMPOS_CONGELADOS` (ver ADR en `ddl.py` y en la propia migración) — una
  venta `cobrada` ya está bloqueada para cualquier UPDATE que no sea la
  transición de estado controlada, y ningún código escribe estas columnas
  durante esa transición.
- [x] 3.9 GREEN `app/infraestructura/persistencia/modelos/venta.py`: columnas
  `destinatario_nombre`/`destinatario_nif` (`str | None`) en el modelo `Venta`.
- [x] 3.10 RED `tests/test_convertir_en_factura_f3.py::test_conversion_congela_destinatario_resuelto_en_la_f3`
  + `::test_editar_cliente_tras_conversion_no_afecta_snapshot_f3` (prueba directa
  del hallazgo: editar el `Cliente` DESPUÉS de convertir no afecta el snapshot) →
  GREEN `app/aplicacion/convertir_en_factura_f3.py`: tras `_resolver_cliente`, fija
  `f3.destinatario_nombre = cliente.nombre` / `f3.destinatario_nif = cliente.nif`
  en el mismo `Venta(...)` que fija `cliente_id`, mientras la F3 aún está
  `aparcada` (antes de `motor.emit`) — congela el valor REALMENTE usado, inmune a
  ediciones posteriores del cliente.
- [x] 3.11 RED `tests/test_remision.py::test_remitir_lote_usa_snapshot_congelado_no_cliente_editado_despues`
  (edita el cliente tras emitir, antes de remitir; asserta que el XML remitido
  sigue llevando el destinatario ORIGINAL) + `::test_remitir_lote_f1_f3_sin_destinatario_congelado_marca_requiere_intervencion`
  + `::test_remitir_lote_excluye_solo_el_registro_invalido_resto_del_lote_sigue`
  → GREEN `app/aplicacion/remitir_lote.py`: la resolución de `Destinatario` para
  F1/F3/R1-R4 lee `venta.destinatario_nombre`/`venta.destinatario_nif` (snapshot),
  NUNCA `venta.cliente` en vivo. Guarda: si `destinatario_nif` es falsy para un
  tipo con destinatario obligatorio, el registro se marca `requiere_intervencion`
  (nunca se remite un `<NIF/>` vacío/ausente) y se EXCLUYE del sobre — el resto
  del lote sigue su curso normal (`lote_valido` separado de `lote`).
- [x] 3.12 (item 5, golden real) RED/GREEN `tests/test_xml_validacion.py::test_xml_simplificada_t_byte_identica`
  reescrito: el test anterior comparaba una llamada por defecto contra
  `destinatario=None` explícito — idénticas por construcción, nunca podía
  fallar. Reemplazado por un `RegistroFiscal` fijo/determinístico (sin
  `motor.emit`) comparado byte-a-byte contra una constante `_GOLDEN_XML_F2`
  pinneada, capturada del serializador actual. Verificado manualmente que SÍ
  detecta regresiones (se reordenaron dos elementos, el test falló; revertido).
- [x] 3.13 (item 6) GREEN `app/infraestructura/fiscal/xml.py`: `Destinatario.nif`
  tipado `str | None` (honesto); `registro_alta_xml` omite el bloque
  `Destinatarios` ENTERO si `destinatario.nif` es falsy (nunca `<NIF/>` vacío) —
  defensa en profundidad, la guarda primaria vive en 3.11. Test
  `tests/test_xml_validacion.py::test_registro_alta_xml_omite_destinatario_con_nif_vacio`.
- [x] 3.14 (item 7) GREEN `app/dominio/servicios/validaciones_negocio.py`: alias
  público `TIPOS_CON_DESTINATARIO = _CON_DESTINATARIO`; `remitir_lote.py` deriva
  `_TIPOS_CON_DESTINATARIO` de ese alias (antes hardcodeaba `{"F1","F3"}`,
  divergiendo de `{"F1","F3","R1","R2","R3","R4"}`). Seguro de expandir hoy
  gracias a la guarda de 3.11 (cualquier R1-R4 sin snapshot queda
  `requiere_intervencion`, nunca se remite sin destinatario). Test
  `tests/test_remision.py::test_tipos_con_destinatario_alineado_con_validaciones_negocio`.
- [x] 3.15 (item 8) RED/GREEN (confirmatorio, sin cambio de código — lxml ya
  escapa el contenido de texto) `tests/test_xml_validacion.py::test_xml_destinatario_con_caracteres_especiales_escapa_correctamente`
  — nombre de destinatario con `&`/`<`/`>`/`"` escapa correctamente y el XML
  sigue siendo válido contra el XSD.

### Fase 3 (bis, round 2): el snapshot congelado NO era inmutable a nivel de BD — [APLICADO, review-driven (judgment-day), rama `-c2`]

> Hallazgo CRÍTICO (ambos jueces, empíricamente probado): `trg_venta_no_update`
> exime la transición de estado permitida (`cobrada -> {anulada_con_rastro,
> sustituida}`) y SOLO re-verifica los campos listados en
> `_VENTA_CAMPOS_CONGELADOS` durante esa transición. `destinatario_nombre`/
> `destinatario_nif` (migración 0010) y `cualificada` (migración 0009) NO
> estaban en esa lista: un UPDATE que combinara la transición PERMITIDA con un
> cambio de esos campos, en la MISMA sentencia, se colaba SIN ser rechazado —
> violando el invariante 1 de CLAUDE.md (ninguna venta emitida se edita, ni a
> nivel de BD) para el snapshot congelado de una F1/F3 ya expedida. El D2
> override de las migraciones 0009/0010 (documentado en `ddl.py`) partía de un
> análisis incompleto: "una venta `cobrada` ya está totalmente bloqueada salvo
> `estado`" era falso para el UPDATE combinado.

- [x] 3.16 (CRÍTICO) RED `tests/test_inmutabilidad.py::test_no_se_puede_colar_destinatario_ni_cualificada_en_transicion_permitida`
  (vector combinado: `venta.estado = 'anulada_con_rastro'` +
  `destinatario_nombre`/`destinatario_nif`/`cualificada` en el MISMO flush →
  hoy NO lanza excepción, RED confirmado) + `tests/test_migracion_destinatario_f3.py`
  bloque 3c) (mismo vector vía SQL crudo) → GREEN:
  - `app/infraestructura/persistencia/ddl.py`: `cualificada`,
    `destinatario_nombre`, `destinatario_nif` añadidas a
    `_VENTA_CAMPOS_CONGELADOS_V2` (lista SEPARADA de la histórica
    `_VENTA_CAMPOS_CONGELADOS`, que alimenta la migración 0001 y NO se toca —
    ver nota inline: tocarla in-place rompe cualquier migración desde cero,
    porque 0001 crearía un trigger referenciando columnas que no existen hasta
    0009/0010, y SQLite revalida triggers existentes en cuanto CUALQUIER otra
    migración usa `batch_alter_table` sobre cualquier tabla — probado
    empíricamente, documentado en el propio `ddl.py`).
  - `migrations/versions/0011_venta_trigger_campos_congelados.py` (nueva):
    `DROP TRIGGER` + `CREATE TRIGGER` de ÚNICAMENTE `trg_venta_no_update`
    (nunca `batch_alter_table`, nunca recreación de tabla — preserva los otros
    15 triggers), cuerpo nuevo importado de `ddl.TRIGGER_VENTA_NO_UPDATE_V2`
    (fuente única de verdad); `downgrade()` restaura el cuerpo ANTERIOR
    (literal histórico fijo en la propia migración). Test adicional
    `test_migracion_0011_downgrade_restaura_trigger_anterior`: confirma que el
    downgrade REALMENTE reactiva el vector combinado bajo el trigger de 0010
    (prueba que el downgrade hace lo que dice).
  - Confirmado (y cubierto por el mismo test) que los DOS caminos legítimos que
    SÍ hacen la transición permitida siguen funcionando: (a) T origen
    `cobrada -> sustituida` sin destinatario (permanece `NULL`); (b)
    `motor.cancel()` `cobrada -> anulada_con_rastro` sin tocar destinatario.
- [x] 3.17 (hardening) RED `tests/test_remision.py::test_remitir_lote_f1_f3_con_nif_pero_sin_nombre_marca_requiere_intervencion`
  (NIF presente, `destinatario_nombre` ausente → hoy se remitiría igual, RED) →
  GREEN `app/aplicacion/remitir_lote.py`: la guarda de snapshot ausente ahora
  exige AMBOS `destinatario_nif` Y `destinatario_nombre` (antes solo NIF) —
  `NombreRazon` es obligatorio en el XSD igual que NIF.
- [x] 3.18 (hardening) RED `tests/test_xml_validacion.py::test_registro_alta_xml_omite_destinatario_con_nombre_vacio`
  (nombre vacío/None con NIF presente → hoy emite `<NombreRazon/>` vacío, RED)
  → GREEN `app/infraestructura/fiscal/xml.py`: `Destinatario.nombre` tipado
  `str | None` (honesto); `registro_alta_xml` omite el bloque `Destinatarios`
  ENTERO si `destinatario.nombre` es falsy (simétrico con la guarda de NIF ya
  existente, 3.13).
- [x] 3.19 (hardening, preserva FIFO/cadena) RED `tests/test_remision.py::test_remitir_lote_registro_invalido_no_es_el_ultimo_detiene_el_lote_ahi`
  (registro inválido NO es el último del lote → hoy los posteriores igual se
  remiten, RED) → GREEN `app/aplicacion/remitir_lote.py`: ante CUALQUIER
  exclusión por guarda (`requiere_intervencion`), el bucle se DETIENE en ese
  `orden` (`break` en vez de `continue`) — se remite el PREFIJO válido
  contiguo anterior, pero los registros POSTERIORES (aunque serían válidos por
  sí solos) quedan DIFERIDOS, intactos, para un intento futuro. Evita que un
  sucesor referencie, en su propio `Encadenamiento`, un `huella_anterior` que
  la AEAT nunca recibió (hueco de cadena en la remisión), preservando la regla
  FIFO de orden de generación (CLAUDE.md). El test previo
  `test_remitir_lote_excluye_solo_el_registro_invalido_resto_del_lote_sigue`
  (registro inválido SÍ es el último) sigue verde sin cambios: coincide con el
  nuevo comportamiento cuando no hay nada posterior que diferir.

### Fase 3 (bis, round 3): barrera FIFO persistente entre ciclos + footgun de las dos constantes congeladas — [APLICADO, review-driven (judgment-day round 3), rama `-c2`]

> Hallazgo CRÍTICO (ambos jueces, empíricamente probado): `requiere_intervencion`
> es un estado TERMINAL (`ESTADOS_TERMINALES`, `repositorios.py`) que
> `pendientes()` EXCLUYE. El `break` de 3.19 (commit `37843bb`) solo difiere los
> registros posteriores DENTRO del mismo ciclo de `remitir_lote` — en el ciclo
> SIGUIENTE, `pendientes()` ya no ve el registro held (por ser terminal) y sus
> sucesores de `orden` mayor SÍ se remiten, referenciando en su
> `Encadenamiento`/`RegistroAnterior`/`Huella` una huella que la AEAT NUNCA
> recibió — rotura PERMANENTE de la cadena, no solo dentro de una llamada.

- [x] 3.20 (CRÍTICO) RED de dos ciclos `tests/test_remision.py::test_remitir_lote_barrera_persiste_entre_ciclos_orden_posterior_nunca_se_remite`
  (orden 1 F3 válida, orden 2 F3 sin destinatario congelado, orden 3 F3 válida
  → CICLO 1 remite orden 1 y marca orden 2 `requiere_intervencion`; CICLO 2
  remitía orden 3 sin la barrera persistente, RED confirmado empíricamente) →
  GREEN:
  - `app/infraestructura/persistencia/repositorios.py`:
    `RepositorioRegistrosSQL.orden_minimo_requiere_intervencion()` — menor
    `orden` entre los registros en `requiere_intervencion`, o `None`.
  - `app/dominio/puertos.py`: método añadido al protocolo `RepositorioRegistros`.
  - `app/aplicacion/remitir_lote.py`: `RemitirLote.ejecutar()` filtra el lote a
    `orden < barrera` en CADA ciclo (no solo dentro del ciclo que generó el
    held), hasta que el registro held se resuelva vía `reencolar`. El test de
    un solo ciclo (3.19) sigue verde sin cambios.
- [x] 3.21 (footgun de nombres) `app/infraestructura/persistencia/ddl.py`:
  renombrado de símbolo puro `_VENTA_CAMPOS_CONGELADOS` →
  `_VENTA_CAMPOS_CONGELADOS_0001` (histórica, MUERTA a HEAD — solo alimenta la
  migración 0001; `_VENTA_CAMPOS_CONGELADOS_V2` sigue siendo la autoritativa
  desde la migración 0011). Cuerpo del trigger byte-idéntico, sin migración
  nueva. Referencias en comentarios de `migrations/versions/0008-0011` y
  `tests/test_migracion_cualificada.py`/`test_migracion_destinatario_f3.py`/
  `test_inmutabilidad.py`/`modelos/venta.py` actualizadas a `_0001` o `_V2`
  según a qué lista se referían realmente (0011 mezclaba menciones a ambas).
  Nuevo test de drift `tests/test_inmutabilidad.py::test_trigger_venta_no_update_no_diverge_de_ddl_v2`:
  construye una BD desde cero hasta `head` y compara el cuerpo VIVO de
  `trg_venta_no_update` en `sqlite_master` contra `ddl.TRIGGER_VENTA_NO_UPDATE_V2`
  byte a byte — detecta una futura columna congelada añadida sin el
  DROP+CREATE correspondiente.

## Fase 4: Confirmación de reglas ya existentes (Requirement: soporte estructural F1/F3 en validaciones — motor-fiscal-verifactu spec — dep. ninguna) — [APLICADO, PR2]

- [x] 4.1 `tests/test_validaciones_negocio.py::test_f3_con_destinatario_no_rechaza_falta_destinatario`
  — registro F3 realista + `tiene_destinatario=True` → sin `FALTA_DESTINATARIO`;
  mismo registro con `tiene_destinatario=False` → sí (ver Nota de alcance arriba;
  SIN cambio de código en `validaciones_negocio.py`)

## Fase 5: Endpoints de administración (Requirement: Listado de simplificadas elegibles + Endpoint de conversión — consola-administracion spec — dep. Fase 2) — [APLICADO, PR3]

- [x] 5.1 RED `tests/test_admin_api.py::test_listado_convertibles_exige_sesion` —
  sin sesión → 401
- [x] 5.2 RED `tests/test_admin_api.py::test_listado_convertibles_excluye_no_elegibles`
  — con sesión → 200, solo T cobradas no sustituidas
- [x] 5.3 GREEN `app/presentacion/admin.py`: `GET /api/ventas/convertibles`
  (`Depends(require_admin)`) → `uow.ventas.convertibles()` serializado
  (`id`, `num_serie_factura`, `fecha_hora_huso`, `total_con_iva`)
- [x] 5.4 RED `tests/test_admin_api.py::test_convertir_endpoint_2_ventas_devuelve_f3`
  — POST con 2 ids + destinatario válido → 200 + `num_serie` de la F3,
  `LogAuditoria(accion="conversion_f3")` persistida
- [x] 5.5 RED `tests/test_admin_api.py::test_convertir_endpoint_rechaza_venta_no_elegible`
  — incluye una T ya `sustituida` → 409, nada persistido
- [x] 5.6 RED `tests/test_admin_api.py::test_convertir_endpoint_rechaza_nif_invalido`
  — NIF inválido → 422, nada persistido
- [x] 5.7 GREEN `app/presentacion/admin.py`: `POST /api/ventas/convertir`
  (`Depends(require_admin)`) — DTO `ConvertirReq(ids: list[int], nif: str, nombre:
  str, domicilio: str)`; invoca `ConvertirEnFacturaF3.ejecutar(usuario_id, origen=
  _origen(request), ...)`; mapea `SinSimplificadas`/`DestinatarioInvalido` → 422,
  `SimplificadaNoElegible`/`YaSustituida` → 409 (mensaje claro, no 500 crudo)

### Fase 5 (bis): endurecimiento HTTP-boundary — destinatario nulo/ausente y mensaje
sin NIF en bruto (follow-up de revisión PR1/PR2, resuelto al construir el DTO) — [APLICADO, PR3]

> Hallazgo: `ConvertirReq` tipado con campos `str` obligatorios delega el 422 de
> `null`/campo ausente en Pydantic (safe por accidente, no por diseño); y
> `DestinatarioInvalido(destinatario.nif)` (Fase 2) hace `str(exc) == nif`, filtrando
> el NIF en bruto (potencialmente inválido) en cualquier mensaje HTTP/log futuro.

- [x] 5.8 RED `tests/test_admin_api.py::test_convertir_endpoint_nombre_nulo_da_422_no_500`
  + `::test_convertir_endpoint_domicilio_ausente_da_422_no_500` — `nombre`/`domicilio`
  nulo u omitido en el JSON → 422 controlado, nada persistido (no `AttributeError`/500)
- [x] 5.9 GREEN `app/presentacion/admin.py`: `ConvertirReq.nif/nombre/domicilio`
  tipados `str | None = None`; el handler construye `DatosDestinatario` con
  `(req.x or "").strip()` ANTES de invocar el caso de uso — la guarda real vive en
  el propio caso de uso (`DestinatarioInvalido` con cadena vacía)
- [x] 5.10 RED `tests/test_convertir_en_factura_f3.py::test_destinatario_invalido_no_expone_nif_en_bruto`
  — NIF inválido → `str(exc)` NO contiene el NIF y no está vacío
- [x] 5.11 GREEN `app/aplicacion/convertir_en_factura_f3.py`: `DestinatarioInvalido.__init__`
  con mensaje por defecto/por campo (nunca el NIF); los dos puntos de rechazo
  (`validar_documento`, nombre/domicilio vacíos) pasan un motivo textual explícito

## Fase 6: Panel "Convertir en factura" (Requirement: Panel Convertir en factura — consola-administracion spec — dep. Fase 5) — [APLICADO, PR3]

- [x] 6.1 `app/ui/admin.html`: panel Nocturne "Convertir en factura" — tabla de
  elegibles (`GET .../convertibles`) con checkboxes de selección múltiple 1..N,
  formulario inline NIF+nombre+domicilio, botón "Convertir"; al confirmar invoca
  `POST .../convertir`; tras éxito refresca el listado (las T convertidas
  desaparecen) y muestra el `num_serie` de la F3 (smoke manual, sin motor de
  plantillas — mismo patrón que 2.10 en `cliente-en-venta/tasks.md`)
- [x] 6.2 `tests/test_admin_ui.py` (convención de test estático existente): assert
  el panel/botón "Convertir en factura" aparece en el HTML servido

## Fase 7: Verificación final (dep. Fases 1-6)

- [ ] 7.1 `.venv/Scripts/python -m pytest`: suite completa verde — sin regresión en
  emisión T/F2 (`test_sustitucion.py`, `test_xml_validacion.py`, `test_emitir_venta.py`)
- [ ] 7.2 `make arch` (import-linter): capas hexagonal intactas
- [ ] 7.3 Smoke manual/equivalente automatizado: listar elegibles → seleccionar 2 T
  con IVA mixto → completar destinatario → convertir → verificar F3 con
  `FacturasSustituidas` + `Destinatarios`, T origen en `sustituida`,
  `verify_chain().ok == True`

**Fase 3 (bis), review-driven (rama `-c2`, tras PR2 mergeado en local)**:
- [x] 7.1 (para la corrección review-driven) `.venv/Scripts/python -m pytest`:
  591 → 599 passed (8 tests netos nuevos: 1 migración + 2 snapshot en el caso de
  uso + 2 XML (guarda NIF vacío + escapado) + 4 en `test_remision.py` (snapshot
  congelado, guarda `requiere_intervencion`, exclusión parcial del lote,
  alineación de tipos) − 1 test reemplazado en `test_remision.py`), 0 failed.
- [x] 7.2 (para la corrección review-driven) `.venv/Scripts/lint-imports`: 3/3
  contratos kept.

**Fase 3 (bis, round 2), judgment-day (rama `-c2`, tras el batch anterior)**:
- [x] 7.1 (para la corrección round 2) `.venv/Scripts/python -m pytest`:
  599 → 604 passed (5 tests nuevos: vector combinado en `test_inmutabilidad.py`
  + downgrade de la migración 0011 + guarda NIF-sin-nombre + XML NombreRazon
  vacío + lote detenido en registro no-último), 0 failed.
- [x] 7.2 (para la corrección round 2) `.venv/Scripts/lint-imports`: 3/3
  contratos kept.

**Fase 3 (bis, round 3), judgment-day (rama `-c2`, tras el batch anterior)**:
- [x] 7.1 (para la corrección round 3) `.venv/Scripts/python -m pytest`:
  604 → 606 passed (2 tests nuevos: barrera FIFO persistente de dos ciclos en
  `test_remision.py` + guarda de drift del trigger `trg_venta_no_update` en
  `test_inmutabilidad.py`), 0 failed.
- [x] 7.2 (para la corrección round 3) `.venv/Scripts/lint-imports`: 3/3
  contratos kept.

**Fase 5-6 (PR3), rama `-c3` (tras Fase 3 bis round 4 mergeado en local)**:
- [x] 7.1 (para PR3) `.venv/Scripts/python -m pytest`: 611 → 623 passed (12 tests
  nuevos: 7 en `test_admin_api.py` — Fase 5, listado + conversión + rechazos + 2
  hardening HTTP-boundary — + 1 en `test_convertir_en_factura_f3.py` — Fase 5 bis,
  `DestinatarioInvalido` sin NIF en bruto — + 4 en `test_admin_ui.py` — Fase 6,
  panel Nocturne), 0 failed.
- [x] 7.2 (para PR3) `.venv/Scripts/lint-imports`: 3/3 contratos kept.
- [ ] 7.3 Smoke manual/e2e — pendiente: cubierto parcialmente por
  `test_convertir_endpoint_2_ventas_devuelve_f3` (2 T IVA mixto → F3 vía HTTP,
  auditoría), pero sin aserción explícita de `Destinatarios` en el XML remitido ni
  de `verify_chain().ok == True` tras el POST admin (esas dos aserciones ya están
  cubiertas a nivel de caso de uso/XML en Fases 2-3; queda como smoke manual/e2e
  real, no bloquea PR3).

**Fase 3 (bis, round 4), judgment-day (rama `-c2`, tras el batch anterior)**:
- [x] Footgun de fuente compartida en el guard de drift (round 3): `upgrade()` de
  la migración `0011_venta_trigger_campos_congelados.py` importaba
  `ddl.TRIGGER_VENTA_NO_UPDATE_V2` EN VIVO, la MISMA constante que
  `test_trigger_venta_no_update_no_diverge_de_ddl_v2` usaba como `esperado` —
  editar `_VENTA_CAMPOS_CONGELADOS_V2` sin migración nueva no se detectaba.
  Corregido: `upgrade()` ahora ejecuta un literal histórico congelado
  (`_TRIGGER_VENTA_NO_UPDATE_ENDURECIDO`, byte a byte idéntico al `V2` vigente,
  sin import de `ddl.py`) y el test normaliza ambos lados (`fila[0]` y
  `esperado`) simétricamente. Probado empíricamente RED→revert→GREEN: añadir
  una columna dummy a `_VENTA_CAMPOS_CONGELADOS_V2` sin migración hace fallar
  el test de drift; al revertir, vuelve a pasar.
- [x] 7.1 (para la corrección round 4) `.venv/Scripts/python -m pytest`:
  606 → 606 passed (mismo recuento: fix sin tests nuevos, solo re-acopla el
  guard de drift existente a una fuente independiente), 0 failed.
- [x] 7.2 (para la corrección round 4) `.venv/Scripts/lint-imports`: 3/3
  contratos kept.

Nota: cada Work Unit (PR 1/2/3) debe correr 7.1-7.2 de forma independiente antes de
integrarse (ver skill `chained-pr`); 7.3 se ejecuta completo solo tras la última PR.
