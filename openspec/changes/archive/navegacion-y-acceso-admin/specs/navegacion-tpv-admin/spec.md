# navegacion-tpv-admin Specification

## Purpose

Navegación bidireccional entre el TPV (`/tpv/`) y la consola de Administración
(`/admin/`) desde la propia interfaz, sin depender de la landing (`/`). Ambas rutas
viven bajo el mismo dominio; el acceso a cada una (login, PIN o acceso libre en
demo) lo resuelve exclusivamente la capacidad correspondiente, no esta.

## Requirements

### Requirement: Botón de navegación TPV → Administración

El sistema MUST mostrar en la cabecera del TPV (`tpv.html`) un botón visible que
navega a `/admin/`. El botón MUST estar disponible con independencia del rol del
operador que tenga la sesión de TPV abierta.

#### Scenario: Operador navega del TPV a Administración
- GIVEN un operador con el TPV abierto, en cualquier rol
- WHEN pulsa el botón "Administración" de la cabecera
- THEN el navegador se dirige a `/admin/`

**Tests**: `tests/test_navegacion.py::test_boton_tpv_a_admin`

### Requirement: Botón de navegación Administración → TPV

El sistema MUST mostrar en la cabecera de la consola (`admin.html`) un botón
visible que navega a `/tpv/`. El botón MUST estar disponible con independencia
del rol del usuario que tenga abierta la consola.

#### Scenario: Usuario navega de Administración al TPV
- GIVEN un usuario con la consola de Administración abierta
- WHEN pulsa el botón "Ir al TPV" de la cabecera
- THEN el navegador se dirige a `/tpv/`

**Tests**: `tests/test_navegacion.py::test_boton_admin_a_tpv`

## Constraints (no debilitar)

- Los botones de navegación MUST NOT alterar ni eludir el guard de acceso
  (sesión, PIN o acceso libre demo) de la capacidad de destino: solo cambian de
  ruta, nunca de identidad ni de permisos.
