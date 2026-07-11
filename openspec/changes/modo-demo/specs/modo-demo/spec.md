# modo-demo Specification

## Purpose

Perfil de arranque aislado para exhibir el TPV sin exponer datos reales de la titular ni
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

#### Scenario: Producción resuelve VerifactuEngine
- GIVEN que el perfil es `produccion` y existe un certificado válido
- WHEN se resuelve el motor fiscal
- THEN el motor resuelto es `VerifactuEngine`

### Requirement: Empresa emisora ficticia en modo demo

El sistema MUST usar, bajo perfil `demo`, un emisor ficticio con NIF `00000000T` y MUST
NOT exponer los datos fiscales de la titular real bajo ese perfil.

#### Scenario: Emisión de ticket en modo demo
- GIVEN que el perfil resuelto es `demo`
- WHEN se consulta el emisor para expedir un ticket
- THEN el NIF del emisor es `00000000T` y no aparece la razón social real de la titular

### Requirement: Seed demo idempotente

El sistema MUST poblar `tpv_demo.db` con empresa demo, clientes y artículos de
acuariofilia de ejemplo, y MUST garantizar que ejecutar el seed varias veces no duplica
filas.

#### Scenario: Primer arranque en modo demo
- GIVEN una `tpv_demo.db` vacía
- WHEN el sistema arranca en modo demo
- THEN la BD contiene la empresa, los clientes y los artículos demo sembrados

#### Scenario: Reinicio no duplica datos
- GIVEN que el seed demo ya se ejecutó sobre `tpv_demo.db`
- WHEN el sistema se reinicia en modo demo
- THEN el número de filas de empresa, clientes y artículos demo no cambia

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

El sistema MUST comportarse, bajo perfil `produccion` (valor por defecto), de forma
idéntica al comportamiento previo a esta funcionalidad: `tpv.db`, emisor real, motor
según certificado disponible, sin marca de documento de prueba.

#### Scenario: Arranque sin variables de perfil configuradas
- GIVEN un entorno sin `TPV_PROFILE` definida
- WHEN el sistema arranca
- THEN el perfil resuelto es `produccion` y BD, emisor, motor y ticket se comportan
  exactamente igual que antes de introducir el perfil demo
