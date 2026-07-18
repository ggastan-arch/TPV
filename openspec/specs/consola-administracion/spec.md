# consola-administracion Specification

## Purpose

Consola web de administración accesible en remoto (Tailscale), protegida con
sesión + rol `administracion`, bajo `/admin`. Expone panel fiscal (cola de
remisión, verificación de cadena, declaración responsable) e informe del día.
Cada acceso/acción queda auditada distinguiendo origen local/remoto.

## Requirements

### Requirement: Autenticación con sesión y rol de administración según perfil

Cuando el perfil sea `produccion`, el sistema MUST exigir sesión autenticada con
`rol="administracion"` para todo endpoint bajo `/admin/api/*` salvo login; MUST
rechazar usuarios sin ese rol o con password incorrecta; MUST permitir cerrar
sesión — sin cambios respecto al comportamiento actual.

Cuando el perfil sea `demo`, el sistema MUST resolver una identidad de
administración sin exigir login ni PIN, cableada exclusivamente en el
composition-root (nunca en el guard compartido), de modo que `/admin/api/me`
responda autenticado y el dashboard se muestre directamente. El sistema MUST NOT
permitir que este acceso libre sea alcanzable bajo perfil `produccion`.

#### Scenario: Endpoint protegido sin sesión (producción)
- GIVEN perfil `produccion`
- WHEN GET `/admin/api/me` o `/admin/api/fiscal/estado` sin sesión
- THEN responde 401

#### Scenario: Login solo para rol administración (producción)
- GIVEN perfil `produccion`
- WHEN un usuario con rol `venta` o con password incorrecta intenta login
- THEN responde 401
- WHEN el administrador usa credenciales correctas
- THEN responde 200 y la sesión queda activa

#### Scenario: Flujo completo de sesión (producción)
- GIVEN perfil `produccion` y sesión iniciada
- WHEN GET `/admin/api/me`
- THEN devuelve el nombre del administrador
- WHEN POST `/admin/api/logout` y luego GET `/admin/api/me`
- THEN la segunda petición responde 401

#### Scenario: Acceso libre sin login en demo
- GIVEN perfil `demo`
- WHEN GET `/admin/api/me` sin haber iniciado sesión alguna
- THEN responde 200 con una identidad de administración demo

#### Scenario: Dashboard directo en demo
- GIVEN perfil `demo`
- WHEN se abre `/admin/`
- THEN se muestra el dashboard directamente, sin pantalla de login ni PIN

#### Scenario: Producción no hereda el acceso libre de demo
- GIVEN perfil `produccion`
- WHEN GET `/admin/api/me` sin sesión
- THEN responde 401, igual que antes de esta capacidad

**Tests**: `tests/test_admin_api.py::test_endpoint_protegido_exige_sesion`,
`::test_login_solo_admin`, `::test_flujo_completo`,
`tests/test_navegacion.py::test_demo_acceso_libre_sin_login`,
`::test_produccion_sigue_exigiendo_login`

### Requirement: Panel fiscal — cola, cadena y declaración responsable

El sistema MUST exponer en `/admin/api/fiscal/estado` la declaración responsable
(software, id_sistema, versión, productor, obligado, entorno AEAT), el estado de
la cola de remisión (pendientes, incidencia, si hay certificado configurado —
solo un booleano, nunca la ruta o el contenido del certificado) y el resultado de
`verify_chain` (ok/registros/errores).

#### Scenario: Estado fiscal disponible para el administrador autenticado
- GIVEN sesión de administración activa
- WHEN GET `/admin/api/fiscal/estado`
- THEN el cuerpo incluye `declaracion_responsable`, `cola.certificado_configurado`
  (booleano) y `cadena.ok == true`

**Tests**: `tests/test_admin_api.py::test_flujo_completo` (bloque `estado`)

### Requirement: Reintento de remisión respeta la custodia del certificado

El sistema MUST informar de forma explícita cuando la remisión no está disponible
por falta de certificado, sin transmitir ni loguear el certificado en ningún caso
(invariante: el certificado nunca sale del servidor).

#### Scenario: Reintentar sin certificado configurado
- GIVEN sesión de administración activa y sin certificado configurado
- WHEN POST `/admin/api/fiscal/reintentar`
- THEN responde 200 con `ok: false` y un mensaje que menciona "Certificado"

**Tests**: `tests/test_admin_api.py::test_reintentar_sin_certificado`

### Requirement: Informe del día

El sistema MUST ofrecer un informe de ventas del día en curso (recuento y total)
al administrador autenticado.

#### Scenario: Informe accesible con sesión
- GIVEN sesión de administración activa
- WHEN GET `/admin/api/informes/dia`
- THEN responde 200

**Tests**: `tests/test_admin_api.py::test_flujo_completo` (bloque `informes/dia`)

### Requirement: Auditoría de accesos con distinción de origen local/remoto

El sistema MUST registrar cada acceso de administración en el log de auditoría
(`accion="acceso_admin"`), calculando el origen (`local` si el host es
loopback, `remoto` en otro caso) sin intervención manual.

#### Scenario: Acceso queda auditado
- WHEN un administrador hace login
- THEN existe al menos un `LogAuditoria` con `accion="acceso_admin"`

**Tests**: `tests/test_admin_api.py::test_acceso_queda_en_auditoria`

### Requirement: El hash del PIN nunca se expone

El sistema MUST NOT incluir el hash del PIN en ninguna respuesta de la API,
incluido el listado de usuarios de los maestros.

#### Scenario: Listado de usuarios sin hash
- GIVEN sesión de administración activa
- WHEN GET `/admin/api/maestros/usuarios`
- THEN ningún elemento contiene la clave `pin_hash`

**Tests**: `tests/test_admin_api.py::test_maestros_usuarios_no_exponen_hash`

### Requirement: Ajuste de "Salir" según perfil

El sistema MUST ocultar o repurponer el botón "Salir" de la consola cuando el
perfil sea `demo`, dado que no existe sesión que cerrar. El sistema MUST
mantener "Salir" funcional, sin cambios, cuando el perfil sea `produccion`.

#### Scenario: Consola en demo sin botón de cerrar sesión
- GIVEN perfil `demo`
- WHEN se abre la consola de administración
- THEN el botón "Salir" no se muestra, o se repurpone, porque no hay sesión que
  cerrar

#### Scenario: Consola en producción conserva "Salir"
- GIVEN perfil `produccion`
- WHEN se abre la consola de administración
- THEN el botón "Salir" se muestra y cierra la sesión como antes

**Tests**: `tests/test_navegacion.py::test_salir_oculto_en_demo`,
`::test_salir_presente_en_produccion`

### Requirement: Panel de Cierre Z en la consola (generar, listar, detalle)

La consola MUST exponer un panel de Cierre Z cableado a los endpoints
existentes (`POST`/`GET /admin/api/maestros/cierres-z`,
`GET /admin/api/maestros/cierres-z/{numero}`) que permita generar un nuevo
cierre con confirmación previa, listar el histórico (número, fecha, totales)
y ver el detalle de un cierre. Cuando ya exista un Cierre Z cuya fecha
(`fecha_hora_huso`) sea la del día en curso, el sistema MUST mostrar un aviso
advisory junto a "Generar" y exigir una segunda confirmación explícita antes
de invocar el `POST`, pero sin deshabilitar la acción — guardarraíl de UI
NO bloqueante, coherente con el backend (`GenerarCierreZ` no impone "uno por
día"; permite legalmente varios Z el mismo día).

#### Scenario: Confirmación antes de generar
- GIVEN el panel de Cierre Z abierto y sin cierre generado hoy
- WHEN el administrador pulsa "Generar"
- THEN se muestra una confirmación antes de invocar el `POST` de generación

#### Scenario: Histórico y detalle tras generar
- GIVEN la generación confirmada y exitosa
- WHEN el panel se actualiza
- THEN el nuevo cierre aparece en el listado histórico y su detalle es
  consultable

#### Scenario: Aviso advisory de un segundo cierre el mismo día
- GIVEN que ya existe un Cierre Z con fecha de hoy en el listado
- WHEN se abre o refresca el panel
- THEN se muestra un aviso junto a "Generar" explicando que ya existe un
  cierre para el día en curso, y pulsar "Generar" exige una segunda
  confirmación además de la habitual, PERO la acción sigue habilitada

#### Scenario: Sin aviso si no hay cierre hoy
- GIVEN que el último Cierre Z (si existe) es de una fecha distinta a hoy
- WHEN se abre el panel
- THEN la acción "Generar" está habilitada y no se muestra el aviso de
  duplicado

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

## Constraints (no debilitar)

- El certificado electrónico nunca sale del servidor ni se registra en logs.
- Todo acceso/acción de administración (local o remoto) queda en el log de
  auditoría append-only.

## Out of Scope

CRUD de usuarios (alta/edición de operadores desde la consola): trabajo futuro,
no entregado. Editor visual de botoneras y arqueo de caja: fuera de esta
capacidad. Buscar y asignar cliente durante la venta (entrada de UI visible
pero deshabilitada; ver `interfaz-nocturne`). Cualquier cambio al motor
fiscal, cobro/emisión, huella/cadena o numeración queda fuera de esta
capacidad.
