# Control de Stock Specification

## Purpose

Control de existencias informativo: entradas, mermas justificadas y descuento en
venta para artículos con `control_stock = true`, gobernado por un ajuste de empresa
global. El stock NUNCA condiciona ni bloquea el cobro offline (CLAUDE.md); la
sobreventa es un estado válido y solo dispara alarma informativa.

**Fuera de alcance**: la anulación de una venta NO revierte sus movimientos de
stock en esta entrega (ver proposal, Out of Scope).

## Requirements

### Requirement: Ajuste de empresa para el control de stock

El sistema MUST exponer un ajuste de empresa global, persistido y editable desde
consola admin, que activa/desactiva el control de stock. Default MUST ser desactivado.

#### Scenario: Valor por defecto desactivado

- GIVEN una instalación nueva sin configuración previa
- WHEN se consulta el ajuste
- THEN su valor es "desactivado"

#### Scenario: Administración cambia el ajuste

- GIVEN el ajuste está desactivado
- WHEN administración lo activa desde consola
- THEN queda persistido "activado" y rige operaciones posteriores

### Requirement: Control desactivado ⇒ sin efectos de stock

Con el ajuste desactivado, el sistema MUST NOT generar movimientos ni alarma de
stock para ninguna venta, sin importar `Articulo.control_stock`.

#### Scenario: Venta con control desactivado no genera movimiento

- GIVEN el ajuste está desactivado
- WHEN se emite una venta con líneas de artículos con `control_stock = true`
- THEN no se crea ningún `MovimientoStock`
- AND la alarma de stock no cuenta artículos

### Requirement: Control activado ⇒ solo artículos rastreados descuentan

Con el ajuste activado, `EmitirVenta` MUST registrar un `MovimientoStock` tipo
`venta` (cantidad negativa) por cada línea con `control_stock = true`, en la misma
transacción de la venta. Líneas con `control_stock = false` MUST NOT generar
movimiento.

#### Scenario: Venta descuenta solo artículos rastreados

- GIVEN la venta incluye un artículo rastreado y otro no rastreado
- WHEN se emite la venta con el ajuste activado
- THEN se crea movimiento `venta` solo para el artículo rastreado

### Requirement: Registrar entrada de stock

El sistema MUST ofrecer `RegistrarEntrada`, que crea un `MovimientoStock`
append-only tipo `entrada` (cantidad positiva) y MUST auditar la operación
(invariante 4, `log_auditoria`).

#### Scenario: Entrada aumenta el stock y queda auditada

- GIVEN un artículo con `control_stock = true`
- WHEN se ejecuta `RegistrarEntrada` con cantidad positiva
- THEN se persiste el movimiento `entrada`
- AND se registra una entrada en `log_auditoria`

### Requirement: Registrar merma con motivo obligatorio

El sistema MUST ofrecer `RegistrarMerma`, que crea un `MovimientoStock`
append-only tipo `merma` (cantidad negativa) con `motivo` obligatorio, y MUST
auditar la operación. Si falta el motivo, MUST rechazar con excepción explícita
y MUST NOT persistir movimiento.

#### Scenario: Merma con motivo se registra y audita

- GIVEN un artículo con `control_stock = true`
- WHEN se ejecuta `RegistrarMerma` con cantidad y motivo no vacío
- THEN se persiste el movimiento `merma` y se audita

#### Scenario: Merma sin motivo se rechaza

- GIVEN un artículo con `control_stock = true`
- WHEN se ejecuta `RegistrarMerma` sin motivo
- THEN el sistema lanza una excepción explícita
- AND no se persiste ningún movimiento

### Requirement: Cálculo de stock actual

El stock actual de un artículo MUST calcularse como suma de movimientos: `entrada`
suma, `venta` y `merma` restan; on-the-fly, sin saldo materializado aparte.

#### Scenario: Stock resultante de movimientos mixtos

- GIVEN movimientos entrada(+10), venta(-3), merma(-2)
- WHEN se consulta el stock actual
- THEN el resultado es 5

### Requirement: Venta sin stock suficiente siempre se permite

Vender por encima del stock disponible MUST permitirse siempre; el stock MUST
poder quedar negativo sin abortar, retrasar ni bloquear la venta. El sistema MUST
activar alarma informativa para ese artículo.

#### Scenario: Sobreventa deja stock negativo y dispara alarma

- GIVEN un artículo rastreado con stock actual 1
- WHEN se venden 5 unidades
- THEN la venta se emite con normalidad y el stock queda en -4
- AND la alarma de stock incluye ese artículo

### Requirement: Un fallo al registrar el movimiento de stock nunca aborta la venta

Si el registro del `MovimientoStock` tipo `venta` falla, el sistema MUST NOT
abortar, revertir ni retrasar la venta ni el registro fiscal asociado. La venta
MUST quedar emitida igual.

#### Scenario: Fallo de stock no impide la emisión de la venta

- GIVEN el registro de movimientos de stock falla (p. ej. excepción del repositorio)
- WHEN se emite una venta con líneas rastreadas y control activado
- THEN la venta queda emitida con su registro fiscal encadenado con normalidad

### Requirement: Alarma de stock negativo

El sistema MUST exponer un estado consultable (patrón `/api/fiscal/estado`) con el
número de artículos rastreados con stock negativo. Es informativo y MUST NOT
bloquear ninguna operación.

#### Scenario: Alarma cuenta artículos rastreados en negativo

- GIVEN dos artículos rastreados, uno con stock -2 y otro con stock 3
- WHEN se consulta el estado de alarma
- THEN el contador de artículos en negativo es 1
