# Delta for consola-administracion

## ADDED Requirements

### Requirement: Panel de Cierre Z en la consola (generar, listar, detalle)

La consola MUST exponer un panel de Cierre Z cableado a los endpoints
existentes (`POST`/`GET /admin/api/maestros/cierres-z`,
`GET /admin/api/maestros/cierres-z/{numero}`) que permita generar un nuevo
cierre con confirmación previa, listar el histórico (número, fecha, totales)
y ver el detalle de un cierre. El sistema MUST impedir el disparo de una
segunda generación cuando ya exista un Cierre Z cuya fecha
(`fecha_hora_huso`) sea la del día en curso, deshabilitando la acción
"Generar" y mostrando un aviso — guardarraíl de UI adicional al ya existente
en el backend (numeración correlativa; el backend no impone "uno por día").

#### Scenario: Confirmación antes de generar
- GIVEN el panel de Cierre Z abierto y sin cierre generado hoy
- WHEN el administrador pulsa "Generar"
- THEN se muestra una confirmación antes de invocar el `POST` de generación

#### Scenario: Histórico y detalle tras generar
- GIVEN la generación confirmada y exitosa
- WHEN el panel se actualiza
- THEN el nuevo cierre aparece en el listado histórico y su detalle es
  consultable

#### Scenario: Bloqueo de un segundo cierre el mismo día
- GIVEN que ya existe un Cierre Z con fecha de hoy en el listado
- WHEN se abre o refresca el panel
- THEN la acción "Generar" queda deshabilitada con un aviso explicando que
  ya existe un cierre para el día en curso

#### Scenario: Generación habilitada si no hay cierre hoy
- GIVEN que el último Cierre Z (si existe) es de una fecha distinta a hoy
- WHEN se abre el panel
- THEN la acción "Generar" está habilitada

**Tests**: `tests/test_admin_ui.py` (o equivalente) — cubrir las cuatro
escenas anteriores contra el HTML/JS servido.

### Requirement: Gestión de clientes (CRUD) en la consola

La consola MUST exponer un panel de clientes cableado a los endpoints
existentes (`GET`/`POST`/`PUT /admin/api/maestros/clientes`,
`POST .../activar`, `POST .../desactivar`) que permita listar, crear,
editar, desactivar y reactivar clientes. Desactivar/activar MUST limitarse a
alternar el `activo` ya existente en el backend, sin bloqueo ni confirmación
adicional más allá del comportamiento actual.

#### Scenario: Alta de cliente válido
- GIVEN el panel de clientes abierto
- WHEN el administrador crea un cliente con NIF válido
- THEN el `POST` se envía y el cliente aparece en el listado

#### Scenario: Alta rechazada por NIF inválido
- GIVEN el formulario de alta de cliente
- WHEN se envía un NIF/NIE/CIF inválido
- THEN se muestra el mensaje de error devuelto por el backend y no se crea
  el cliente

#### Scenario: Desactivar y reactivar sin bloqueo nuevo
- GIVEN un cliente activo listado
- WHEN el administrador pulsa "Desactivar" y luego "Activar"
- THEN el campo `activo` cambia a `false` y luego a `true`, igual que hace
  hoy el backend, sin condiciones adicionales

**Tests**: `tests/test_admin_ui.py` (o equivalente) — cubrir alta válida,
rechazo por NIF inválido y el ciclo desactivar/activar.

## Out of Scope

- Buscar y asignar cliente durante la venta (entrada de UI visible pero
  deshabilitada; ver `interfaz-nocturne`).
- Cualquier cambio al motor fiscal, cobro/emisión, huella/cadena o
  numeración.
- No regresión: la autenticación por perfil (login en producción, acceso
  libre en demo) y la ocultación de "Salir" en demo, ya definidas en este
  spec, no cambian con estos paneles.
