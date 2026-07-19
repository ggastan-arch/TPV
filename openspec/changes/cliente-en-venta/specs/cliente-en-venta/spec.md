# Cliente en Venta — Especificación

## Purpose

Buscar, crear (inline) y asignar un cliente a la venta en curso del TPV, y marcar
la venta como factura simplificada cualificada (art. 7.2/7.3 ROF) cuando el
comprador pide NIF, domicilio y cuota separada en el ticket, sin forzar el flujo de
conversión a factura completa (F3).

## Requirements

### Requirement: Búsqueda de cliente por nombre o NIF desde el TPV

El sistema MUST exponer un endpoint `/tpv/api/*` protegido por PIN de operador
para buscar clientes activos por coincidencia de subcadena (case-insensitive) en
`nombre` o por `nif`, reutilizando el patrón de búsqueda de artículo
(`RepositorioArticulosSQL.buscar_por_nombre`). El sistema MUST NOT exponer este
endpoint bajo la autenticación de consola (`require_admin`).

#### Scenario: Coincidencia por nombre
- GIVEN un cliente activo `nombre="Juan Pérez"`
- WHEN se busca `q="perez"` en el endpoint PIN-gated del TPV
- THEN aparece en los resultados

#### Scenario: Coincidencia exacta por NIF
- GIVEN un cliente activo con NIF normalizado
- WHEN se busca por ese NIF
- THEN aparece en los resultados

### Requirement: Alta de cliente inline desde el TPV con consentimiento RGPD

El sistema MUST permitir crear un cliente (NIF opcional, nombre, domicilio) desde
el panel de venta sin salir del TPV, reutilizando `ServicioClientes.crear`
(validación y normalización de NIF ya vigentes en `maestros-crud`). El sistema
MUST capturar y persistir `rgpd_consentimiento` en el alta inline.

#### Scenario: Alta inline con consentimiento
- GIVEN un walk-in sin cliente registrado
- WHEN se crea un cliente inline con `rgpd_consentimiento=true`
- THEN el cliente persiste con ese consentimiento y queda disponible para asignar

#### Scenario: NIF inválido en alta inline se rechaza
- WHEN se crea un cliente inline con un NIF que no supera la validación existente
- THEN se rechaza (422); no se persiste el cliente ni se asigna a la venta

### Requirement: Asignación de cliente a la venta en curso

El sistema MUST permitir asignar (o desasignar) un cliente ya existente a la
venta en curso antes del cobro. La asignación MUST ser opcional: una venta sin
cliente asignado MUST comportarse igual que hoy.

#### Scenario: Asignar cliente a la venta en curso
- GIVEN una venta en curso sin cliente
- WHEN se asigna un cliente existente
- THEN la venta en curso queda referenciando ese cliente hasta el cobro

#### Scenario: Cobro sin cliente asignado no cambia
- GIVEN una venta en curso sin cliente asignado
- WHEN se cobra
- THEN se comporta igual que antes de este cambio (sin regresión)

### Requirement: Marcar la venta como simplificada cualificada exige NIF y domicilio

El sistema MUST exigir, para marcar la venta en curso como cualificada (art.
7.2/7.3 ROF), que el cliente asignado tenga `nif` y `domicilio` no vacíos. El
sistema MUST rechazar de forma controlada (sin marcar la venta) si falta alguno
de los dos. Una venta MUST NOT auto-marcarse como cualificada por el mero hecho
de asignar un cliente.

#### Scenario: Marcar cualificada con cliente completo
- GIVEN un cliente asignado con NIF y domicilio
- WHEN se marca la venta en curso como cualificada
- THEN la venta queda marcada como cualificada

#### Scenario: Rechazo por falta de NIF o domicilio
- GIVEN un cliente asignado sin NIF o sin domicilio
- WHEN se intenta marcar la venta como cualificada
- THEN se rechaza de forma controlada; la venta no queda marcada

#### Scenario: Asignar cliente no auto-marca cualificada
- GIVEN una venta en curso
- WHEN se asigna un cliente con NIF y domicilio completos
- THEN la venta permanece no cualificada hasta la acción explícita

**Tests**: nuevos, p.ej. `tests/test_clientes_tpv.py`: búsqueda por nombre/NIF,
alta inline + RGPD, NIF inválido rechaza, asignar/desasignar cliente, marcar
cualificada ok, marcar cualificada rechaza sin NIF/domicilio, no auto-marca.

## Constraints (no debilitar)

- Reutiliza `ServicioClientes` y su validación de NIF (`maestros-crud`); no
  duplica reglas de normalización.
- No construye ni referencia el bloque `Destinatarios` (exclusivo F1/F3).
- No afecta los invariantes 1-7 (CLAUDE.md).
