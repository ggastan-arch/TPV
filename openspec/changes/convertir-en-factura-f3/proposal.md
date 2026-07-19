# Proposal: Convertir simplificadas en factura completa de sustitución (F3)

## Intent

Cuando un cliente empresario pide factura completa de una compra ya cobrada como ticket
(simplificada serie T), hoy NO existe flujo: el modelo (`VentaSustitucion`,
`RegistroFacturaSustituida`, estado `sustituida`, triggers) y el motor (`emit` acepta
`serie="F", tipo_factura="F3"` y encadena huella) están listos desde la migración 0001,
pero nadie los orquesta. La conversión es, por normativa (art. 7.2/7.3 ROF; Orden
HAC/1177/2024 L2), un alta NUEVA F3 que sustituye a las T referenciadas —nunca "reimprimir
la T con NIF". Además el bloque `Destinatarios/IDDestinatario` (obligatorio F1/F3) NO está
implementado: sin él la F3 sería rechazada por la AEAT (`FALTA_DESTINATARIO`) aunque
encadene bien en local. Este es el cambio más crítico fiscalmente del roadmap.

## Scope

### In Scope
- Caso de uso `ConvertirEnFacturaF3`: valida elegibilidad, construye UNA F3 sumando
  bases/cuotas por tipo (regla de redondeo única), emite vía `emit(serie="F",
  tipo_factura="F3")` con bloques `FacturasSustituidas` + `Destinatarios`, persiste
  `VentaSustitucion` + `RegistroFacturaSustituida` (N→1), transiciona las T origen a
  `estado='sustituida'` (jamás DELETE) y escribe entrada de auditoría `conversion_f3`.
- Bloque XML `Destinatarios/IDDestinatario` CONDICIONAL (solo F1/F3; inerte en T/F2).
- Admin: endpoint para LISTAR simplificadas elegibles (serie T, `cobrada`, no `sustituida`)
  + endpoint de conversión; panel de consola "Convertir en factura" con multiselección
  1..N y formulario inline de destinatario (NIF + nombre + domicilio).
- Pre-checks de elegibilidad/idempotencia con errores amigables (no `IntegrityError` crudo).

### Out of Scope
- Cliente-en-venta / seleccionar cliente guardado (aquí el destinatario es inline).
- Disparo desde el TPV (botón footer sigue `disabled` en v1).
- Cambios en emisión de simplificadas T, algoritmo de huella, numeración de series
  existentes o triggers de inmutabilidad.
- Mecánica real de remisión AEAT (la F3 fluye por la cola existente).
- Reversibilidad de una F3 (deshacer vía rectificativa).

## Non-Goals
- Que la F3 quede acotada por el límite de 3.000 € (ese límite es de simplificadas; una
  factura completa lo supera por diseño).
- Bloquear la conversión por Cierre Z: se permite en cualquier momento (Z inmutable).

## Capabilities

### New Capabilities
- `conversion-factura-f3`: flujo end-to-end (caso de uso, elegibilidad/idempotencia,
  sustitución N→1, captura inline de destinatario, auditoría, disclosure de doble conteo Z).

### Modified Capabilities
- `motor-fiscal-verifactu`: añadir bloque `Destinatarios/IDDestinatario` (condicional F1/F3);
  el requisito estructural F3 existente pasa a estar respaldado por un flujo real. La huella
  NO cambia (se calcula sobre el subconjunto fijo del art. 13, no sobre el XML completo).
- `consola-administracion`: endpoints de listado de elegibles + conversión, y panel de UI.

## Approach

Un único caso de uso hexagonal (patrón `emitir_venta.py` / `generar_cierre_z.py`) invocado
por routers finos de admin. Nueva query en `RepositorioVentas` para elegibles (cobrada + T +
no en `venta_sustitucion.venta_sustituida_id`). La emisión reutiliza `emit` sin tocarlo: la
F3 obtiene su correlativo propio en serie F y encadena la huella al último registro global
como cualquier alta, y entra en la cola de remisión existente. `Destinatarios` se serializa
condicionalmente cableando `tiene_destinatario=True` (la regla ya vive en
`validaciones_negocio.py`). Doble conteo Cierre Z entre periodos: ACEPTADO y documentado.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/aplicacion/convertir_en_factura_f3.py` | New | Caso de uso orquestador |
| `app/dominio/puertos.py` | Modified | Query de simplificadas elegibles |
| `app/infraestructura/persistencia/repositorios.py` | Modified | Implementa la query |
| `app/infraestructura/fiscal/xml.py` | Modified | Bloque `Destinatarios` condicional |
| `app/dominio/servicios/validaciones_negocio.py` | Modified | Cablea `tiene_destinatario` |
| `app/presentacion/admin.py` | Modified | Endpoints listar + convertir |
| `app/ui/admin.html` | Modified | Panel "Convertir en factura" |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `Destinatarios` ausente → rechazo AEAT F1/F3 | High (impacto) | Implementar el bloque en este cambio, fuera de la huella |
| `Destinatarios` entra en la huella por error | Low/High | Huella sobre subconjunto fijo (art. 13); test: huella F3 idéntica con/sin destinatario |
| Tocar `xml.py` rompe emisión de T | Low | Bloque estrictamente condicional (F1/F3); test de regresión de T |
| T ya sustituida → `IntegrityError` crudo | Med | Pre-check amigable antes del INSERT |
| Doble conteo Cierre Z entre periodos | Med | Decisión cerrada: aceptar y documentar (nota de conciliación en informe de módulos) |

## Rollback Plan

Aditivo: revertir = quitar endpoints, caso de uso, panel de UI y la rama condicional
`Destinatarios` (inerte para T/F2). No hay migración (modelo y triggers existen desde 0001).
NOTA: las F3 ya emitidas son inmutables (invariante 1) y NO se pueden borrar; el rollback
solo deshabilita crear nuevas conversiones.

## Dependencies

- Modelo `VentaSustitucion` + `RegistroFacturaSustituida` + estado `sustituida` + triggers (0001).
- `emit` (acepta serie F / tipo F3, encadena huella, encola remisión) y serialización de
  `FacturasSustituidas` (ya existentes).
- Validación de NIF con dígito de control existente (confirmar reuso — ver preguntas abiertas).

## Success Criteria

- [ ] Admin lista simplificadas elegibles vía endpoint nuevo.
- [ ] Convertir 1..N T en UNA F3: alta serie F / tipo F3, correlativo propio, huella
      encadenada al último registro global.
- [ ] F3 incluye `FacturasSustituidas` + `Destinatarios/IDDestinatario` y valida contra los XSD oficiales.
- [ ] Las T origen pasan a `sustituida` (nunca borradas), importes congelados; enlaces N→1 persistidos.
- [ ] Entrada de auditoría `conversion_f3` por cada conversión (invariante 4).
- [ ] Emisión y huella de simplificadas T INTACTAS (test de regresión); huella F3 independiente de `Destinatarios`.
- [ ] Pre-check amigable ante T ya sustituida / estado o serie inválidos.
- [ ] Cubierto por tests (TDD estricto): N→1 e2e, elegibilidad, `Destinatarios` en XML, huella estable.

## Proposal question round

Preguntas para afinar el PRD antes de spec/design (con default recomendado):
1. Validación de NIF del destinatario (dígito de control): ¿reusar la validación de NIF
   existente del proyecto? Default: SÍ, reusar; rechazar NIF inválido antes de emitir.
2. Reglas multi-simplificada en una F3: ¿se permite mezclar fechas/días y tipos de IVA
   distintos en una misma F3? Default: mismo emisor (obvio), cualquier rango de fechas,
   tipos de IVA mezclados permitidos (el `Desglose` los separa por tipo).
3. Contenido impreso de la F3: ¿qué muestra el listado de simplificadas sustituidas en el
   ticket/factura? Default: enumerar `NumSerieFactura` + fecha de cada T sustituida.
4. Reversibilidad: ¿se puede deshacer una F3 (vía rectificativa)? Default: FUERA de alcance
   en v1 (nota explícita); una F3 emitida es inmutable.
