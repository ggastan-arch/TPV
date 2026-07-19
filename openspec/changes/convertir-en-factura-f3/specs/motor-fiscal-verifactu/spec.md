# Delta for Motor Fiscal VERI*FACTU

## MODIFIED Requirements

### Requirement: Sustitución de simplificada por factura completa (F3)

El sistema MUST soportar la conversión de 1..N facturas simplificadas (F2,
serie T) ya cobradas en una única F3 en sustitución: bloque
`FacturasSustituidas` (una entrada por T referenciada), enlace
`VentaSustitucion` (N:1) y transición atómica de cada T a `sustituida`,
inmutable tras su creación. La orquestación completa (elegibilidad,
captura de destinatario, persistencia N:1, auditoría) MUST vivir en la
capacidad `conversion-factura-f3`; este requisito cubre únicamente el
soporte estructural del motor y la serialización.

(Previously: solo cubría 1 F2 → 1 F3 a nivel estructural, orquestado a
mano en `tests/test_sustitucion.py`, sin caso de uso real ni endpoint.)

#### Scenario: F3 sustituye a una F2 previa
- GIVEN una venta F2 ya emitida
- WHEN se emite una F3 referenciando la F2
- THEN la F2 pasa a `sustituida` y el enlace queda registrado

#### Scenario: F3 sustituye a varias F2 (N:1)
- GIVEN N ventas F2 ya cobradas
- WHEN se emite una única F3 referenciando las N F2
- THEN las N F2 pasan a `sustituida` y quedan N registros
  `RegistroFacturaSustituida` bajo el mismo registro F3

**Trazabilidad**: `tests/test_sustitucion.py` (todas);
`tests/test_convertir_en_factura_f3.py` (N:1 end-to-end).

## ADDED Requirements

### Requirement: Bloque `Destinatarios/IDDestinatario` condicional (F1/F3)

El sistema MUST serializar el bloque `Destinatarios/IDDestinatario` (NIF +
nombre) en el XML del registro de alta cuando `TipoFactura` sea F1 o F3, y
MUST NOT emitirlo cuando sea F2. Este bloque MUST NOT participar en el
cómputo de la huella: la huella sigue calculándose exclusivamente sobre el
subconjunto fijo del art. 13 (NIF emisor + serie/número + fecha
expedición + tipo factura + cuota total + importe total + huella anterior
+ fecha-hora-huso de generación).

#### Scenario: F3 incluye Destinatarios
- GIVEN un registro de alta F3 con destinatario válido (NIF + nombre)
- WHEN se serializa a XML
- THEN el bloque `Destinatarios/IDDestinatario` está presente y valida
  contra el XSD oficial

#### Scenario: F2 no incluye Destinatarios (sin regresión)
- GIVEN un registro de alta F2 (simplificada)
- WHEN se serializa a XML
- THEN el bloque `Destinatarios` está ausente, igual que antes de este
  cambio

#### Scenario: La huella no cambia por añadir Destinatarios
- GIVEN dos registros F3 con los mismos importes y fecha, pero destinatario
  distinto
- WHEN se calcula la huella de cada uno
- THEN ambas huellas son idénticas — `Destinatarios` queda fuera del
  cómputo

**Trazabilidad**: `tests/test_xml_validacion.py` (F3 con Destinatarios; F2
sin Destinatarios, caso de no regresión); nuevo test de huella estable
F3 con/sin destinatario (`tests/test_huella_vectores.py` o equivalente).
