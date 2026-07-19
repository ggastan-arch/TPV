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

- [ ] 1.1 RED `tests/test_repositorios.py` (o nuevo `tests/test_ventas_convertibles.py`):
  crear 3 T — cobrada sin sustituir, cobrada ya sustituida (vía `VentaSustitucion`),
  aparcada — assert `RepositorioVentasSQL.convertibles()` devuelve solo la primera
- [ ] 1.2 GREEN `app/dominio/puertos.py`: `def convertibles(self) -> list["Venta"]: ...`
  en el Protocol `RepositorioVentas`
- [ ] 1.3 GREEN `app/infraestructura/persistencia/repositorios.py`:
  `RepositorioVentasSQL.convertibles()` — `select(Venta).where(Venta.serie == "T",
  Venta.estado == "cobrada", Venta.id.notin_(select(VentaSustitucion.venta_sustituida_id)))`

## Fase 2: Caso de uso `ConvertirEnFacturaF3` (Requirement: Conversión atómica 1..N→1 F3 + Transición sin borrado + Destinatario inline + Auditoría + Integridad de cadena — conversion-factura-f3 spec — dep. Fase 1)

- [ ] 2.1 RED `tests/test_convertir_en_factura_f3.py` (nuevo)
  `::test_elegibilidad_rechaza_no_cobrada_no_t_o_inexistente` — id inexistente, id
  aparcada, id serie F → `SimplificadaNoElegible`
- [ ] 2.2 GREEN `app/aplicacion/convertir_en_factura_f3.py` (nuevo): dataclasses
  `DatosDestinatario(nif, nombre, domicilio)`, `ResultadoConversion`; excepciones
  `SinSimplificadas`, `SimplificadaNoElegible`, `YaSustituida`, `DestinatarioInvalido`;
  `ConvertirEnFacturaF3(uow, motor).ejecutar(usuario_id, origen, simplificada_ids,
  destinatario)` — por cada id: `uow.ventas.buscar(id)`; si `None`/`serie != "T"`/
  `estado` fuera de `{"cobrada","sustituida"}` → `SimplificadaNoElegible`
- [ ] 2.3 RED `::test_convertir_dos_veces_una_t_falla` — T ya `sustituida` →
  `YaSustituida` (no `IntegrityError` crudo)
- [ ] 2.4 GREEN: distinguir en 2.2 el caso `estado == "sustituida"` → `YaSustituida`
  del resto de casos no elegibles → `SimplificadaNoElegible`
- [ ] 2.5 RED `::test_nif_destinatario_invalido` — NIF con dígito de control
  incorrecto → `DestinatarioInvalido`, nada persistido
- [ ] 2.6 GREEN: validar `destinatario.nif` con `validar_documento` (dominio/servicios/
  validadores) ANTES de cualquier `INSERT`; sin ids no vacíos ni destinatario válido
  no se toca la sesión
- [ ] 2.7 RED `::test_convertir_una_sola_simplificada_n1` — 1 T elegible → F3 con
  correlativo propio serie F, huella encadenada al último registro global, 1 entrada
  en `FacturasSustituidas`, T origen → `sustituida`
- [ ] 2.8 GREEN completar `ejecutar()`: copiar como nuevas `VentaLinea` TODAS las
  líneas de las simplificadas origen (helper `_copiar_lineas`, valores
  `base_linea/cuota_linea/total_linea` ya cuantizados, SIN recalcular); resolver
  `Cliente` (`buscar_por_nif` → si no existe, crear con `validar_documento`/
  `normalizar_documento`, fijar `f3.cliente_id`); `motor.emit(session, f3, serie="F",
  tipo_factura="F3")`; por origen `RegistroFacturaSustituida` + `VentaSustitucion`;
  transición `origen.estado = "sustituida"`; `uow.commit()`
- [ ] 2.9 RED `::test_convertir_dos_simplificadas_iva_mixto_en_una_f3` — 2 T (21% y
  10%) → 1 F3, `Desglose` separa ambos tipos, `ImporteTotal` == suma exacta de ambas
- [ ] 2.10 RED `::test_totales_f3_reconcilian_sin_deriva` — 3+ líneas con decimales
  de borde → `CuotaTotal`/`ImporteTotal` de la F3 == Σ de las sustituidas al céntimo
  (JAMÁS re-redondeo; confirma que sumar `Decimal` ya cuantizados es exacto)
- [ ] 2.11 RED `::test_rechazo_atomico_si_una_t_no_es_elegible` — 2 ids, uno ya
  `sustituida` → excepción, CERO `Venta`/`RegistroFacturaSustituida`/
  `VentaSustitucion` nuevos persistidos (rollback total)
- [ ] 2.12 RED `::test_conversion_registra_auditoria_conversion_f3` —
  `LogAuditoria(accion="conversion_f3")` referencia las T origen y la F3
- [ ] 2.13 GREEN: `uow.auditoria.registrar(accion="conversion_f3", entidad="venta",
  entidad_id=str(f3.id), detalle=<num_serie de cada T origen>, usuario_id=usuario_id,
  origen=origen)` dentro de la misma transacción, antes del `commit()`
- [ ] 2.14 RED `::test_verify_chain_ok_tras_conversion_f3` — `motor.verify_chain(session)`
  sigue `ok=True` tras convertir, incluyendo el nuevo registro F3 (+1 registro)
- [ ] 2.15 RED (regresión) `::test_importes_t_congelados_tras_sustituir` — intentar
  modificar `total_con_iva` de una T ya `sustituida` → `sa.exc.DatabaseError` (trigger
  existente, invariante 1; sin código nuevo)

## Fase 3: Bloque `Destinatarios` en XML (Requirement: Bloque Destinatarios/IDDestinatario condicional F1/F3 — motor-fiscal-verifactu spec — dep. ninguna, en paralelo a Fase 2)

- [ ] 3.1 RED (golden, regresión) `tests/test_xml_validacion.py::test_xml_simplificada_t_byte_identica`
  — F2/T sin destinatario → XML idéntico al actual (`destinatario=None`)
- [ ] 3.2 RED `tests/test_xml_validacion.py::test_xml_f3_con_destinatarios_valida_xsd`
  — F3 con `Destinatario(nombre, nif)` → bloque `Destinatarios/IDDestinatario`
  presente tras el bloque `FacturaSimplificadaArt7273`/`DescripcionOperacion` y
  antes de `Desglose`; valida contra el XSD oficial
- [ ] 3.3 GREEN `app/infraestructura/fiscal/xml.py`: dataclass
  `Destinatario(nombre: str, nif: str)`; `registro_alta_xml(..., destinatario:
  Destinatario | None = None)`; bloque `if destinatario is not None:` insertado
  tras el bloque `cualificada` (línea ~134) y antes de `Desglose` (línea ~136)
- [ ] 3.4 RED `tests/test_huella_vectores.py::test_huella_f3_independiente_del_destinatario`
  — 2 registros F3 con mismos importes/fecha, destinatario distinto → huella idéntica
  (`huella_alta` no recibe destinatario; frontera fiscal confirmada)
- [ ] 3.5 RED (integración) `tests/test_remitir_lote.py` (o fichero equivalente):
  `test_remitir_lote_resuelve_destinatario_para_f1_f3` — registro F3 con
  `venta.cliente_id` fijado → `registro_alta_xml` recibe `Destinatario` resuelto;
  registro F2/T (sin cliente asignado o `tipo_factura` fuera de `{F1,F3}`) →
  `destinatario=None`
- [ ] 3.6 GREEN `app/aplicacion/remitir_lote.py`: para `reg.tipo_factura in {"F1",
  "F3"}` resolver `venta = uow.ventas.buscar(reg.venta_id)`; si `venta.cliente` no
  es `None`, construir `Destinatario(nombre=cliente.nombre, nif=cliente.nif)`;
  pasar a `registro_alta_xml`; para el resto, `destinatario=None`
- [ ] 3.7 RED `tests/test_xml_validacion.py::test_xml_f2_nunca_recibe_destinatario`
  — confirma que el camino real (`RemitirLote`) nunca pasa `destinatario` para
  F2 aunque exista `venta.cliente_id` (no regresión del invariante "T inalterada")

## Fase 4: Confirmación de reglas ya existentes (Requirement: soporte estructural F1/F3 en validaciones — motor-fiscal-verifactu spec — dep. ninguna)

- [ ] 4.1 `tests/test_validaciones_negocio.py::test_f3_con_destinatario_no_rechaza_falta_destinatario`
  — registro F3 realista + `tiene_destinatario=True` → sin `FALTA_DESTINATARIO`;
  mismo registro con `tiene_destinatario=False` → sí (ver Nota de alcance arriba;
  SIN cambio de código en `validaciones_negocio.py`)

## Fase 5: Endpoints de administración (Requirement: Listado de simplificadas elegibles + Endpoint de conversión — consola-administracion spec — dep. Fase 2)

- [ ] 5.1 RED `tests/test_admin_api.py::test_listado_convertibles_exige_sesion` —
  sin sesión → 401
- [ ] 5.2 RED `tests/test_admin_api.py::test_listado_convertibles_excluye_no_elegibles`
  — con sesión → 200, solo T cobradas no sustituidas
- [ ] 5.3 GREEN `app/presentacion/admin.py`: `GET /api/ventas/convertibles`
  (`Depends(require_admin)`) → `uow.ventas.convertibles()` serializado
  (`id`, `num_serie_factura`, `fecha_hora_huso`, `total_con_iva`)
- [ ] 5.4 RED `tests/test_admin_api.py::test_convertir_endpoint_2_ventas_devuelve_f3`
  — POST con 2 ids + destinatario válido → 200 + `num_serie` de la F3,
  `LogAuditoria(accion="conversion_f3")` persistida
- [ ] 5.5 RED `tests/test_admin_api.py::test_convertir_endpoint_rechaza_venta_no_elegible`
  — incluye una T ya `sustituida` → 409, nada persistido
- [ ] 5.6 RED `tests/test_admin_api.py::test_convertir_endpoint_rechaza_nif_invalido`
  — NIF inválido → 422, nada persistido
- [ ] 5.7 GREEN `app/presentacion/admin.py`: `POST /api/ventas/convertir`
  (`Depends(require_admin)`) — DTO `ConvertirReq(ids: list[int], nif: str, nombre:
  str, domicilio: str)`; invoca `ConvertirEnFacturaF3.ejecutar(usuario_id, origen=
  _origen(request), ...)`; mapea `SinSimplificadas`/`DestinatarioInvalido` → 422,
  `SimplificadaNoElegible`/`YaSustituida` → 409 (mensaje claro, no 500 crudo)

## Fase 6: Panel "Convertir en factura" (Requirement: Panel Convertir en factura — consola-administracion spec — dep. Fase 5)

- [ ] 6.1 `app/ui/admin.html`: panel Nocturne "Convertir en factura" — tabla de
  elegibles (`GET .../convertibles`) con checkboxes de selección múltiple 1..N,
  formulario inline NIF+nombre+domicilio, botón "Convertir"; al confirmar invoca
  `POST .../convertir`; tras éxito refresca el listado (las T convertidas
  desaparecen) y muestra el `num_serie` de la F3 (smoke manual, sin motor de
  plantillas — mismo patrón que 2.10 en `cliente-en-venta/tasks.md`)
- [ ] 6.2 `tests/test_admin_ui.py` (convención de test estático existente): assert
  el panel/botón "Convertir en factura" aparece en el HTML servido

## Fase 7: Verificación final (dep. Fases 1-6)

- [ ] 7.1 `.venv/Scripts/python -m pytest`: suite completa verde — sin regresión en
  emisión T/F2 (`test_sustitucion.py`, `test_xml_validacion.py`, `test_emitir_venta.py`)
- [ ] 7.2 `make arch` (import-linter): capas hexagonal intactas
- [ ] 7.3 Smoke manual/equivalente automatizado: listar elegibles → seleccionar 2 T
  con IVA mixto → completar destinatario → convertir → verificar F3 con
  `FacturasSustituidas` + `Destinatarios`, T origen en `sustituida`,
  `verify_chain().ok == True`

Nota: cada Work Unit (PR 1/2/3) debe correr 7.1-7.2 de forma independiente antes de
integrarse (ver skill `chained-pr`); 7.3 se ejecuta completo solo tras la última PR.
