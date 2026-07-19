# Delta for consola-administracion

## ADDED Requirements

### Requirement: Listado de simplificadas elegibles para conversión

La consola MUST exponer un endpoint bajo `/admin/api/*` protegido por
sesión de administración que lista ventas serie T, `estado='cobrada'` y no
sustituidas (ver `conversion-factura-f3`), para su selección en el panel
"Convertir en factura".

#### Scenario: Listado solo con sesión activa
- GIVEN sesión de administración activa
- WHEN GET al endpoint de simplificadas elegibles
- THEN responde 200 con las T cobradas no sustituidas, excluyendo las ya
  sustituidas

#### Scenario: Endpoint protegido sin sesión
- GIVEN perfil `producción` y sin sesión
- WHEN GET al endpoint de simplificadas elegibles
- THEN responde 401

### Requirement: Endpoint de conversión a F3

La consola MUST exponer un endpoint `POST` bajo `/admin/api/*` protegido
por sesión de administración que recibe 1..N ids de venta elegibles más
NIF, nombre y domicilio del destinatario, invoca la conversión
(`conversion-factura-f3`) y devuelve la F3 resultante, o rechaza con un
mensaje claro si alguna venta no es elegible o el NIF es inválido, sin
persistir cambios parciales.

#### Scenario: Conversión válida de 2 ventas
- GIVEN sesión de administración activa y 2 T elegibles
- WHEN POST con ambos ids y un destinatario con NIF válido
- THEN responde 200 con la referencia de la F3 emitida

#### Scenario: Rechazo por venta no elegible
- GIVEN sesión de administración activa y una de las T ya sustituida
- WHEN POST incluyendo esa T
- THEN responde con error controlado (no 500 crudo) y no persiste ninguna
  F3 ni enlace

#### Scenario: Rechazo por NIF inválido
- GIVEN sesión de administración activa y T elegibles
- WHEN POST con un NIF de destinatario inválido
- THEN responde con error controlado y no persiste ninguna F3 ni enlace

### Requirement: Panel "Convertir en factura" en la consola

La consola MUST exponer un panel que permita multiseleccionar 1..N
simplificadas elegibles, completar un formulario inline de destinatario
(NIF + nombre + domicilio) y confirmar antes de convertir. Tras una
conversión exitosa, el panel MUST refrescar el listado de elegibles (las T
convertidas ya no aparecen) y MUST mostrar la referencia de la F3
generada.

#### Scenario: Selección múltiple y conversión desde el panel
- GIVEN el panel abierto con varias T elegibles listadas
- WHEN el administrador selecciona 2, completa el destinatario y confirma
- THEN se invoca el endpoint de conversión y se muestra la F3 resultante

#### Scenario: Listado se actualiza tras convertir
- GIVEN una conversión exitosa desde el panel
- WHEN el listado de elegibles se refresca
- THEN las T convertidas ya no aparecen entre las elegibles

**Tests**: `tests/test_admin_api.py` (listado, conversión válida, rechazo
por no elegible, rechazo por NIF inválido); `tests/test_admin_ui.py` (o
equivalente) para el panel.
