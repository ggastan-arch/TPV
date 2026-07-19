# conversion-factura-f3 Specification

## Purpose

Flujo de conversión, disparado desde la consola de administración, de 1..N
facturas simplificadas (serie T, ya cobradas) en una única factura completa
F3 en sustitución. Orquesta elegibilidad, captura de destinatario, emisión
vía `MotorFiscal.emit`, persistencia N:1 (`VentaSustitucion` +
`RegistroFacturaSustituida`) y auditoría. El modelo y el motor ya soportan
F3 estructuralmente (`motor-fiscal-verifactu`); esta capacidad añade el
caso de uso real que faltaba.

## Requirements

### Requirement: Elegibilidad de simplificadas convertibles

El sistema MUST considerar elegible una venta solo si `serie='T'`,
`estado='cobrada'` y no aparece ya como `venta_sustituida_id` en
`VentaSustitucion`. El listado de elegibles MUST excluir cualquier venta
que no cumpla las tres condiciones.

#### Scenario: Listado excluye ventas ya sustituidas o no cobradas
- GIVEN una T cobrada sin sustituir, una T ya sustituida y una T aparcada
- WHEN se solicita el listado de elegibles
- THEN solo aparece la T cobrada sin sustituir

### Requirement: Conversión atómica de 1..N simplificadas en una F3

El sistema MUST, dado un conjunto de 1..N ids de ventas elegibles, sumar
sus bases y cuotas agrupadas por tipo de IVA con la función única de
redondeo del proyecto (`Decimal`, half-up por línea), emitir una única F3
(`MotorFiscal.emit(serie="F", tipo_factura="F3")`) con correlativo propio
y huella encadenada al último registro global, y persistir un bloque
`FacturasSustituidas` con una entrada (`NumSerieFactura` + fecha) por cada
T referenciada. La operación MUST ser todo-o-nada: si cualquier
verificación de elegibilidad falla, MUST NOT persistir cambios parciales.

#### Scenario: Convertir dos simplificadas en una F3
- GIVEN dos T cobradas y elegibles, con tipos de IVA distintos
- WHEN se convierten juntas
- THEN se emite una única F3 cuyo `Desglose` separa ambos tipos y cuyo
  `ImporteTotal` es la suma exacta de ambas T

#### Scenario: Convertir una sola simplificada (N=1)
- GIVEN una única T cobrada y elegible
- WHEN se convierte
- THEN se emite una F3 con un único registro en `FacturasSustituidas`

#### Scenario: Rechazo atómico si una T no es elegible
- GIVEN dos T seleccionadas, una elegible y otra ya sustituida
- WHEN se solicita la conversión conjunta
- THEN se rechaza la operación completa con un mensaje claro (no una
  excepción cruda de integridad de BD) y no se persiste ninguna F3 ni
  enlace

### Requirement: Transición de origen a `sustituida` sin borrado

El sistema MUST, en la misma transacción que emite la F3, transicionar
cada T convertida de `cobrada` a `sustituida` (nunca `DELETE`), dejando sus
campos monetarios e identidad congelados por el trigger existente
(invariante 1 de CLAUDE.md).

#### Scenario: Importes de la T congelados tras la conversión
- GIVEN una T recién convertida (ahora `sustituida`)
- WHEN se intenta modificar su importe
- THEN la base de datos rechaza el cambio

### Requirement: Captura inline de destinatario con validación de NIF

El sistema MUST solicitar NIF, nombre y domicilio del destinatario en la
propia acción de conversión (sin exigir un `Cliente` guardado) y MUST
validar el NIF con la función de dígito de control existente antes de
persistir nada.

#### Scenario: NIF inválido rechaza la conversión sin persistir
- GIVEN un NIF de destinatario con dígito de control incorrecto
- WHEN se solicita la conversión
- THEN se rechaza antes de emitir la F3 o persistir cualquier enlace

### Requirement: Auditoría de la conversión

El sistema MUST registrar en el log de auditoría append-only (invariante
4) una entrada `conversion_f3` por cada conversión exitosa, referenciando
las T origen y la F3 resultante.

#### Scenario: Entrada de auditoría tras convertir
- WHEN se completa una conversión de 2 T en 1 F3
- THEN existe un `LogAuditoria` con `accion="conversion_f3"` referenciando
  ambas T y la F3

### Requirement: Integridad de la cadena de huellas tras la conversión

El sistema MUST mantener `verify_chain` reportando `ok=True` después de
emitir una F3, incluyendo el nuevo registro en el recorrido de la cadena.

#### Scenario: verify_chain OK tras una conversión
- GIVEN varias ventas emitidas y una conversión F3 reciente
- WHEN se invoca `verify_chain`
- THEN reporta `ok=True` incluyendo el registro F3

## Out of Scope

Deshacer/revertir una F3 ya emitida (inmutable, fuera de alcance v1).
Selección de `Cliente` guardado (ver `cliente-en-venta`, no entregado).
Disparo desde el TPV (botón footer sigue deshabilitado). Límite de 3.000 €
(no aplica a F3, ya es factura completa). Prevención del doble conteo
entre Cierres Z de distintos periodos cuando la T convertida ya estaba en
un Z pasado inmutable: se ACEPTA y se documenta como limitación conocida,
sin bloqueo ni mecanismo compensatorio en esta capacidad.
