# Cierre Z Specification

## Purpose

El Cierre Z es un documento interno de control, inmutable y numerado, que resume
por rango de **orden de emisión** (`registro_fiscal.orden`) los tickets, totales
y desgloses de un período. No es una factura ni se remite a la AEAT.

## Requirements

### Requirement: Generación atómica del Cierre Z

El sistema MUST generar el Cierre Z como una única operación atómica que asigna
número, `fecha_hora_huso` (ISO 8601 con offset) y `usuario_id` generador, todo en
la misma transacción de BD.

#### Scenario: Generación exitosa

- GIVEN un usuario administrador autenticado
- WHEN solicita generar un Cierre Z desde `/admin`
- THEN el sistema persiste un `CierreZ` con número, fecha/hora con huso, usuario,
  rango y totales, todo dentro de una única transacción

### Requirement: Rango por orden de emisión contiguo

El sistema MUST fijar `desde_orden` como `hasta_orden` del Cierre Z anterior + 1,
o `1` si es el primero; y `hasta_orden` como el máximo `registro_fiscal.orden`
entre los registros de tipo `alta` al momento del cierre (`0` si no existe
ninguno). Los rangos de Cierres Z consecutivos MUST NOT solaparse ni dejar
huecos. El eje del rango es el **orden de emisión real** (monótono), no el id de
la venta ni su fecha de creación, porque una venta puede crearse `aparcada` con
id bajo y emitirse (obtener su registro de alta y su `orden`) más tarde.

#### Scenario: El siguiente Z continúa desde el anterior

- GIVEN el último Cierre Z tiene `hasta_orden = 120`
- WHEN se genera un nuevo Cierre Z y el mayor `orden` entre registros de alta
  existentes es 145
- THEN el nuevo Cierre Z tiene `desde_orden = 121` y `hasta_orden = 145`

#### Scenario: Primer Cierre Z del sistema

- GIVEN no existe ningún Cierre Z previo
- WHEN se genera el primer Cierre Z
- THEN `desde_orden = 1`

#### Scenario: Un ticket aparcado emitido tras un cierre no se pierde

- GIVEN una venta se creó `aparcada` (id bajo) antes del último Cierre Z, pero
  se emite (pasa a `cobrada` y su registro de alta obtiene `orden`) después de
  que ese Cierre Z ya fue generado
- WHEN se genera el Cierre Z siguiente
- THEN el `orden` de esa venta cae dentro de `[desde_orden, hasta_orden]` del
  nuevo Cierre Z, y la venta queda incluida en sus totales sin dejar hueco

### Requirement: Cuadre de totales y desgloses

El sistema MUST calcular nº de tickets, base total, cuota total, total y
desglose por tipo de IVA y por medio de pago exclusivamente a partir de las
ventas en estado `cobrada` cuyo registro de alta tenga `orden` en
`[desde_orden, hasta_orden]`, en el momento de la generación. Base + cuota MUST
igualar el total (ADR-0005).

#### Scenario: Los totales cuadran con las ventas del rango

- GIVEN ventas cobradas cuyos registros de alta tienen orden dentro del rango,
  con pagos en efectivo y tarjeta y dos tipos de IVA distintos
- WHEN se genera el Cierre Z
- THEN `base_total + cuota_total == total_con_iva`, y la suma del desglose por
  IVA y por medio de pago coincide exactamente con esos totales

#### Scenario: Una anulación posterior no reabre un Z ya cerrado

- GIVEN una venta del rango de un Cierre Z ya cerrado pasa a estado
  `anulada_con_rastro` después del cierre
- WHEN se consulta ese Cierre Z
- THEN sus totales permanecen sin cambios; el efecto de la anulación se refleja
  únicamente en el Cierre Z del rango donde caiga el `orden` del documento
  generado por la anulación

### Requirement: Inmutabilidad del Cierre Z

El sistema MUST rechazar, mediante trigger de BD, cualquier UPDATE o DELETE
sobre un `CierreZ` ya persistido (patrón ADR-0003).

#### Scenario: Rechazo de modificación o borrado

- GIVEN un Cierre Z persistido
- WHEN se ejecuta un UPDATE o un DELETE sobre esa fila
- THEN la BD rechaza la operación mediante trigger y la fila permanece igual

### Requirement: No mutación de ventas al generar el Z

El sistema MUST NOT ejecutar ninguna escritura sobre `venta`, `venta_linea`,
`pago` ni `registro_fiscal` como parte de la generación de un Cierre Z; el
acceso MUST ser exclusivamente de lectura (invariante 1).

#### Scenario: Las ventas no cambian tras el cierre

- GIVEN un conjunto de ventas cobradas con sus registros de alta
- WHEN se genera un Cierre Z que las incluye en su rango
- THEN ninguna columna de esas ventas, líneas, pagos o registros fiscales
  cambia de valor

### Requirement: Numeración correlativa global sin huecos ni reutilización

El sistema MUST asignar el número de Cierre Z (Z-1, Z-2…) de forma correlativa,
**global y monótona** (una única serie para todo el sistema, que NO se reinicia
por ejercicio), sin huecos ni reutilización, mediante un contador propio
asignado en la misma transacción del documento (patrón ADR-0004).

#### Scenario: Numeración consecutiva

- GIVEN el último Cierre Z generado es Z-7
- WHEN se genera un nuevo Cierre Z, sea cual sea el ejercicio en curso
- THEN su número es Z-8

#### Scenario: La concurrencia no duplica ni salta números

- GIVEN dos solicitudes de generación llegan simultáneamente
- WHEN ambas intentan asignar el siguiente correlativo
- THEN una obtiene el número siguiente y la otra falla o espera; ningún número
  se asigna dos veces ni se salta, ni siquiera si una transacción hace rollback

### Requirement: Auditoría de la generación

El sistema MUST registrar en el log de auditoría append-only (invariante 4)
cada generación de Cierre Z, incluyendo usuario, fecha/hora y número asignado.

#### Scenario: Registro de auditoría

- GIVEN un usuario genera un Cierre Z
- WHEN la generación se completa con éxito
- THEN queda una entrada en el log de auditoría con usuario, fecha/hora con huso
  y número de Cierre Z generado

### Requirement: Generación sin ventas nuevas desde el último cierre

El sistema MUST permitir generar un Cierre Z con rango vacío y totales en cero
cuando no existen registros de alta nuevos desde el último cierre
(`hasta_orden < desde_orden`), en lugar de rechazar la operación. Este es el
comportamiento definitivo.

(Decisión: se prioriza la numeración correlativa y la práctica operativa de
cierres por turno sin actividad, sobre una excepción que complicaría la
generación bajo demanda y rompería la contigüidad determinista del rango.)

#### Scenario: Cierre sin actividad

- GIVEN el último Cierre Z tiene `hasta_orden = 200` y no existe ningún
  registro de alta con `orden > 200`
- WHEN se genera un nuevo Cierre Z
- THEN se persiste con `desde_orden = 201`, `hasta_orden = 200` (rango vacío),
  0 tickets y todos los totales en 0.00
