# Delta for consola-administracion

## MODIFIED Requirements

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

(Previously: exigía sesión con rol `administracion` para todo endpoint bajo
`/admin/api/*`, sin distinción de perfil — un único comportamiento para todos
los entornos)

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

## ADDED Requirements

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
