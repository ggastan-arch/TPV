# modo-demo Specification

## Purpose

Perfil de arranque aislado para exhibir el TPV sin exponer datos reales de la persona titular ni
remitir registros a la AEAT. Aditivo, gated por `TPV_PROFILE`; no modifica el
comportamiento de producción (perfil por defecto).

## Requirements

### Requirement: Selección de perfil de arranque

El sistema MUST resolver el perfil de ejecución desde `TPV_PROFILE`, aceptando solo
`produccion` o `demo`, y MUST usar `produccion` por defecto si la variable no está
definida. El sistema MUST rechazar el arranque ante cualquier otro valor.

#### Scenario: Sin TPV_PROFILE definida
- GIVEN que `TPV_PROFILE` no está definida
- WHEN el sistema arranca
- THEN el perfil resuelto es `produccion`

#### Scenario: Perfil demo explícito
- GIVEN que `TPV_PROFILE=demo`
- WHEN el sistema arranca
- THEN el perfil resuelto es `demo`

#### Scenario: Valor de perfil inválido
- GIVEN que `TPV_PROFILE=staging`
- WHEN el sistema arranca
- THEN el arranque se rechaza con un error indicando los valores válidos

### Requirement: Aislamiento de base de datos en modo demo

El sistema MUST usar exclusivamente `tpv_demo.db` cuando el perfil sea `demo`, y MUST NOT
abrir ni escribir `tpv.db` bajo ese perfil.

#### Scenario: Demo usa tpv_demo.db
- GIVEN que el perfil resuelto es `demo`
- WHEN el sistema abre la conexión a base de datos
- THEN la ruta resuelta es `tpv_demo.db` y `tpv.db` no se abre

#### Scenario: Producción usa tpv.db
- GIVEN que el perfil resuelto es `produccion`
- WHEN el sistema abre la conexión a base de datos
- THEN la ruta resuelta es `tpv.db`

### Requirement: Motor fiscal forzado a NullEngine en demo

El sistema MUST resolver siempre `NullEngine` como motor fiscal cuando el perfil sea
`demo`, exista o no un certificado electrónico configurado. En modo demo el sistema MUST
NOT cargar ni leer el certificado electrónico.

#### Scenario: Certificado presente pero perfil demo
- GIVEN que el perfil es `demo` y existe un certificado configurado
- WHEN se resuelve el motor fiscal
- THEN el motor resuelto es `NullEngine` y el certificado no se carga ni se lee

#### Scenario: Producción resuelve el motor de remisión productivo — DEFERRED
> **DEFERRED**: `VerifactuEngine` aún no está implementado (solo existe `NullEngine`);
> ver trabajo futuro "remisión real a la AEAT" (out of scope). Hoy producción también
> resuelve `NullEngine` (no-regresión); este escenario aplicará cuando exista el motor
> de remisión productivo.
- GIVEN que el perfil es `produccion`, existe un certificado válido y `VerifactuEngine` está disponible
- WHEN se resuelve el motor fiscal
- THEN el motor resuelto es `VerifactuEngine`

### Requirement: Empresa emisora ficticia en modo demo

El sistema MUST usar, bajo perfil `demo`, un emisor ficticio con NIF `00000000T` y MUST
NOT exponer los datos fiscales de la persona titular real bajo ese perfil.

#### Scenario: Emisión de ticket en modo demo
- GIVEN que el perfil resuelto es `demo`
- WHEN se consulta el emisor para expedir un ticket
- THEN el NIF del emisor es `00000000T` y no aparece la razón social real de la persona titular

### Requirement: Reset de arranque en modo demo (wipe + reseed)

El sistema MUST, en cada (re)arranque del proceso con perfil `demo`, descartar el
estado acumulado de `tpv_demo.db` (wipe) y volver a poblarla (reseed) con la
empresa demo, clientes y artículos de acuariofilia de ejemplo, de modo que el
estado resultante sea siempre el estado sembrado limpio, sin importar los
cambios acumulados en ejecuciones previas. El sistema MUST NOT ejecutar este
reset mientras el proceso está en marcha — solo ocurre en el (re)arranque. El
sistema MUST NOT aplicar este reset cuando el perfil sea `produccion`.

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

### Requirement: Marcado inequívoco de ticket y consola demo

El sistema MUST imprimir en cada ticket emitido bajo perfil `demo` la leyenda "DOCUMENTO
DE PRUEBA — SIN VALIDEZ FISCAL", MUST suprimir el QR de cotejo real de la AEAT en esos
tickets, y MUST mostrar la misma marca de forma visible en la consola de administración
mientras el perfil activo sea `demo`.

#### Scenario: Ticket impreso en modo demo
- GIVEN que el perfil resuelto es `demo`
- WHEN se imprime el ticket de una venta
- THEN incluye la leyenda de documento de prueba y no incluye el QR de cotejo real

#### Scenario: Consola en modo demo
- GIVEN que el perfil resuelto es `demo`
- WHEN un usuario abre la consola de administración
- THEN la consola muestra visiblemente la marca de modo demo

#### Scenario: Ticket de producción sin marca demo
- GIVEN que el perfil resuelto es `produccion`
- WHEN se imprime el ticket de una venta
- THEN no incluye la leyenda de documento de prueba y sí incluye el QR de cotejo real

### Requirement: Salvaguarda de arranque contra colisión de rutas

El sistema MUST rechazar el arranque con un error explícito cuando el perfil sea `demo` y
la ruta absoluta de base de datos resuelta coincida con la de `tpv.db`.

#### Scenario: Configuración demo apunta a producción
- GIVEN que el perfil es `demo` y la ruta absoluta resuelta coincide con `tpv.db`
- WHEN el sistema intenta arrancar
- THEN el arranque se rechaza y no se abre ninguna conexión de base de datos

### Requirement: No regresión del comportamiento de producción

El sistema MUST comportarse, bajo perfil `produccion` (valor por defecto), de
forma idéntica al comportamiento previo a esta funcionalidad: `tpv.db`, emisor
real, motor según certificado disponible, sin marca de documento de prueba. El
sistema MUST NOT aplicar el reset de arranque (wipe + reseed) bajo perfil
`produccion`: los datos productivos persisten intactos entre reinicios, en
cumplimiento del invariante de que ninguna venta emitida se borra (ADR-0003).

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
