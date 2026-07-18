# Delta for modo-demo

## MODIFIED Requirements

### Requirement: Reset de arranque en modo demo (wipe + reseed)

El sistema MUST, en cada (re)arranque del proceso con perfil `demo`, descartar el
estado acumulado de `tpv_demo.db` (wipe) y volver a poblarla (reseed) con la
empresa demo, clientes y artículos de acuariofilia de ejemplo, de modo que el
estado resultante sea siempre el estado sembrado limpio, sin importar los
cambios acumulados en ejecuciones previas. El sistema MUST NOT ejecutar este
reset mientras el proceso está en marcha — solo ocurre en el (re)arranque. El
sistema MUST NOT aplicar este reset cuando el perfil sea `produccion`.

(Previously: "Seed demo idempotente" — garantizaba que ejecutar el seed varias
veces no duplicara filas, preservando entre reinicios los cambios acumulados;
ahora el reinicio descarta esos cambios y re-siembra limpio)

#### Scenario: Primer arranque en modo demo
- GIVEN una `tpv_demo.db` vacía
- WHEN el sistema arranca en modo demo
- THEN la BD contiene la empresa, los clientes y los artículos demo sembrados

#### Scenario: Rearranque descarta cambios acumulados
- GIVEN que `tpv_demo.db` tiene cambios acumulados de una sesión anterior (p. ej.
  ventas o artículos añadidos durante una demo)
- WHEN el sistema (re)arranca en modo demo
- THEN esos cambios desaparecen y la BD vuelve exactamente al estado sembrado
  limpio

#### Scenario: El reset no ocurre a mitad de una demo en curso
- GIVEN que el sistema está corriendo en modo demo con cambios acumulados
- WHEN transcurre el tiempo sin reiniciar el proceso
- THEN los cambios permanecen intactos — no hay reset fuera de un (re)arranque

**Tests**: `tests/test_modo_demo.py::test_primer_arranque_siembra`,
`tests/test_navegacion.py::test_rearranque_demo_descarta_cambios`,
`::test_reset_no_ocurre_sin_reiniciar`

### Requirement: No regresión del comportamiento de producción

El sistema MUST comportarse, bajo perfil `produccion` (valor por defecto), de
forma idéntica al comportamiento previo a esta funcionalidad: `tpv.db`, emisor
real, motor según certificado disponible, sin marca de documento de prueba. El
sistema MUST NOT aplicar el reset de arranque (wipe + reseed) bajo perfil
`produccion`: los datos productivos persisten intactos entre reinicios, en
cumplimiento del invariante de que ninguna venta emitida se borra (ADR-0003).

(Previously: no mencionaba el reset de arranque, introducido en esta capacidad
solo para el perfil `demo`)

#### Scenario: Arranque sin variables de perfil configuradas
- GIVEN un entorno sin `TPV_PROFILE` definida
- WHEN el sistema arranca
- THEN el perfil resuelto es `produccion` y BD, emisor, motor y ticket se
  comportan exactamente igual que antes de introducir el perfil demo

#### Scenario: Producción no resetea datos entre reinicios
- GIVEN perfil `produccion` con ventas y artículos ya registrados
- WHEN el sistema se reinicia
- THEN todos los datos previos persisten sin cambios, sin wipe ni reseed

**Tests**: `tests/test_modo_demo.py::test_produccion_sin_cambios`,
`tests/test_navegacion.py::test_produccion_no_resetea_en_reinicio`
