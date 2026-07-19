# Delta for Motor Fiscal VERI*FACTU

## MODIFIED Requirements

### Requirement: Validaciones de negocio previas a la remisión

El sistema MUST validar cada registro antes de remitir: límite 3.000 € (F2),
tipos permitidos, NIF emisor coherente, formato de serie, fecha no futura,
formato de sistema, destinatario según tipo, y que una venta cualificada (art.
7.2/7.3) tenga cliente asignado con NIF y domicilio no vacíos.
(Previously: no validaba la condición de simplificada cualificada.)

#### Scenario: F2 supera el límite de 3.000 €
- GIVEN un registro F2 con importe total de 3.630 €
- WHEN se valida antes de remitir
- THEN se reporta `F2_LIMITE_3000` como rechazo

#### Scenario: Cualificada sin NIF o domicilio del cliente (NUEVO)
- GIVEN un registro F2 cualificado cuyo cliente asignado carece de NIF o
  domicilio
- WHEN se valida antes de remitir
- THEN se reporta un rechazo de validación (`CUALIFICADA_SIN_NIF_DOMICILIO`)

## ADDED Requirements

### Requirement: Marcaje condicional de simplificada cualificada (FacturaSimplificadaArt7273)

El sistema MUST serializar el elemento `FacturaSimplificadaArt7273` (`S`/`N`,
`minOccurs=0`) en `RegistroAlta` únicamente cuando la venta es cualificada, con
valor `S`; una simplificada NO cualificada MUST omitir el elemento, produciendo
un XML byte-idéntico al emitido antes de este cambio. El elemento MUST NOT
coexistir con el bloque `Destinatarios` (exclusivo F1/F3) en el mismo registro;
una venta cualificada permanece `TipoFactura=F2`. El sistema MUST NOT incluir el
flag en el cálculo de la huella (`huella.py`).

#### Scenario: Cualificada emite el flag S
- GIVEN una venta F2 marcada como cualificada
- WHEN se serializa el `RegistroAlta`
- THEN el XML incluye `FacturaSimplificadaArt7273=S`, sin bloque
  `Destinatarios`, y valida contra el XSD oficial

#### Scenario: Simplificada normal omite el elemento (byte-idéntico)
- GIVEN una venta F2 NO cualificada
- WHEN se serializa el `RegistroAlta`
- THEN el XML es byte-idéntico al generado antes de este cambio (sin el
  elemento)

#### Scenario: El flag no altera la huella
- GIVEN dos ventas F2 con los mismos campos fiscales, una cualificada y otra no
- WHEN se calcula la huella de alta de cada una
- THEN ambas huellas son idénticas

#### Scenario: Cualificada nunca lleva Destinatarios
- GIVEN una venta F2 marcada como cualificada
- WHEN se valida antes de remitir
- THEN un intento de incluir `Destinatarios` se rechaza igual que hoy
  (`DESTINATARIO_NO_PERMITIDO`)

**Tests**: `tests/test_xml_validacion.py::test_cualificada_emite_flag_s_valida_xsd`
(NUEVO), `::test_simplificada_normal_xml_byte_identico` (NUEVO);
`tests/test_huella_vectores.py::test_flag_cualificada_no_altera_huella` (NUEVO);
`tests/test_validaciones_negocio.py::test_cualificada_sin_nif_domicilio_rechaza`
(NUEVO), `::test_cualificada_rechaza_destinatarios` (NUEVO)

## Constraints (no debilitar)

- El flag es aditivo y `minOccurs=0`; no toca numeración, cadena ni triggers de
  inmutabilidad.
- `Destinatarios` sigue siendo exclusivo F1/F3.
