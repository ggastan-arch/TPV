# aparcar-ticket Specification

## Purpose

Permite dejar un carrito activo como borrador no fiscal (`Venta` en estado
`aparcada`) y recuperarlo después. Aditivo: no modifica el cobro/emisión
existente (`tpv-venta`), que sigue siendo el único punto que asigna identidad
fiscal.

## Requirements

### Requirement: Aparcar un carrito como borrador no fiscal

El sistema MUST, al aparcar, persistir el carrito activo como
`Venta(estado='aparcada')` + `VentaLinea`, con una etiqueta de texto libre
opcional (columna nullable, no fiscal), y MUST vaciar el carrito. El sistema
MUST NOT asignar `serie`, `ejercicio`, `numero` ni `num_serie_factura`,
`fecha_hora_huso`, crear `RegistroFiscal`/huella, mutar `ContadorSerie`, ni
invocar al motor fiscal.

#### Scenario: Aparcar un carrito con etiqueta
- GIVEN un carrito con 3 líneas y etiqueta "Mostrador 2"
- WHEN se aparca
- THEN se persiste una `Venta` aparcada con 3 `VentaLinea` y esa etiqueta; el
  carrito queda vacío

#### Scenario: Aparcar sin etiqueta
- GIVEN un carrito con líneas y sin etiqueta
- WHEN se aparca
- THEN la etiqueta persistida es `null`

### Requirement: Rechazo de aparcar un carrito vacío

El sistema MUST rechazar aparcar un carrito sin líneas, sin persistir
ninguna fila.

#### Scenario: Carrito vacío
- GIVEN un carrito sin líneas
- WHEN se solicita aparcar
- THEN se rechaza con un error controlado; no se persiste `Venta` ni
  `VentaLinea`

### Requirement: Listado de borradores aparcados

El sistema MUST listar de solo lectura todas las `Venta` con
`estado='aparcada'` (kiosco: sin filtrar por `usuario_id` creador), con
etiqueta (o su ausencia), total y nº de líneas por borrador. El sistema MUST
NOT imponer límite al número de borradores simultáneos.

#### Scenario: Listado con borradores de distintos usuarios
- GIVEN 2 ventas aparcadas por usuarios distintos, una con etiqueta
- WHEN cualquier usuario autenticado solicita el listado
- THEN se devuelven ambas con su etiqueta (o `null`), total y nº de líneas

### Requirement: Recuperar (desaparcar) un borrador consumiéndolo

El sistema MUST, al desaparcar un borrador por id, cargar sus líneas en el
carrito activo, y MUST eliminar en la misma operación la `Venta` aparcada y
sus `VentaLinea`. Un id ya consumido o inexistente MUST rechazarse sin
efecto sobre el carrito.

#### Scenario: Desaparcar un borrador
- GIVEN una venta aparcada con 2 líneas
- WHEN se desaparca su id
- THEN el carrito recibe esas 2 líneas y la venta deja de existir y de
  aparecer en el listado

#### Scenario: Desaparcar dos veces el mismo id
- GIVEN un borrador ya desaparcado (consumido)
- WHEN se solicita desaparcar el mismo id de nuevo
- THEN se rechaza (borrador no encontrado); no se duplican líneas en el
  carrito

### Requirement: Frontera fiscal de aparcar, listar y desaparcar

El sistema MUST NOT, en ninguna operación de aparcar, listar o desaparcar,
asignar identidad fiscal (`serie`, `ejercicio`, `numero`,
`num_serie_factura`, `fecha_hora_huso`), crear `RegistroFiscal`, generar
huella, ni invocar `MotorFiscal.emit`. El único camino habilitado para
asignar identidad fiscal sigue siendo `EmitirVenta` / `POST
/tpv/api/cobrar`.

#### Scenario: Aparcar no crea identidad fiscal
- GIVEN un carrito con líneas
- WHEN se aparca
- THEN la `Venta` resultante no tiene `numero`, `num_serie_factura` ni
  `registro_fiscal` asociado, y `MotorFiscal.emit` no se invoca

### Requirement: No regresión del cobro existente

El sistema MUST mantener sin cambios `EmitirVenta` / `POST
/tpv/api/cobrar` para cualquier carrito, incluido uno cargado desde un
borrador desaparcado: sigue asignando serie, número, registro fiscal y
huella exactamente igual que antes de este cambio.

#### Scenario: Cobrar un carrito recuperado
- GIVEN un carrito cargado a partir de un borrador desaparcado
- WHEN se cobra ese carrito
- THEN se emite una `Venta` nueva con numeración, registro fiscal y huella,
  igual que cualquier venta emitida desde cero

## Constraints (no debilitar)

- Invariantes 1-7 (LGT art. 29.2.j / RRSIF) intactos; `EmitirVenta` sigue
  siendo el único punto que asigna identidad fiscal (ADR-0004).
- `estado='aparcada'` sigue exento de los triggers de inmutabilidad
  (ADR-0003, `fundaciones-datos`): mutable/borrable por diseño.
- La etiqueta es una columna nullable puramente descriptiva; MUST NOT
  aparecer en el contenido fiscal del ticket, registro o huella.

## Out of Scope

- Convertir en factura F3, asignación/búsqueda de `cliente_id`, descuentos
  de línea sobre el borrador.
- Restringir recuperar al mismo `usuario_id` que aparcó (kiosco: abierto).
- Cambios en `EmitirVenta`, numeración, registro fiscal o triggers.
