# Delta for tpv-venta

## ADDED Requirements

### Requirement: El DTO de botón/familia/artículo expone la imagen efectiva del destino

El sistema MUST incluir un campo `imagen` (ruta relativa bajo `media/`, o `null` si no
tiene) en:
- el objeto `articulo` de cada botón de tipo `articulo` en `GET /api/botonera`,
- el objeto `familia` de cada botón de tipo `familia` en `GET /api/botonera`,
- cada elemento de `subfamilias` y de `articulos` en `GET /tpv/api/familia/{familia_id}`.

El valor MUST ser el campo `imagen` del artículo o familia de destino (no existe un
campo `imagen` propio del botón); si el destino no tiene imagen asignada, el campo
MUST ser `null` y el sistema MUST NOT fallar al construir la respuesta para ese botón.

#### Scenario: Botón de artículo con imagen
- GIVEN un artículo con `imagen` asignada, referenciado por un botón de la botonera activa
- WHEN GET `/api/botonera`
- THEN el botón correspondiente incluye `articulo.imagen` con la ruta persistida

#### Scenario: Botón de familia con imagen
- GIVEN una familia con `imagen` asignada, referenciada por un botón de la botonera activa
- WHEN GET `/api/botonera`
- THEN el botón correspondiente incluye `familia.imagen` con la ruta persistida

#### Scenario: Destino sin imagen expone null
- GIVEN un artículo o una familia sin `imagen` asignada, referenciado por un botón
- WHEN GET `/api/botonera`
- THEN el campo `imagen` del destino es `null` y la respuesta no falla

#### Scenario: Drill-down de familia expone imagen de subfamilias y artículos
- GIVEN una familia con subfamilias y artículos, algunos con `imagen` asignada y otros sin ella
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN cada elemento de `subfamilias` y de `articulos` incluye su `imagen`
  (la persistida o `null`)

**Tests**: (a definir en diseño/tareas) — deben cubrir botón de artículo con imagen,
botón de familia con imagen, destino sin imagen (`null`) y el drill-down de familia
exponiendo `imagen` en subfamilias y artículos.
