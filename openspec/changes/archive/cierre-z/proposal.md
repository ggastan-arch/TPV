# Proposal: Cierre Z (informe Z inmutable)

## Intent

Hoy la consola solo ofrece `informe_dia` (`app/presentacion/admin.py`): un agregado
efímero, no persistido, sin numeración ni inmutabilidad. Falta el documento de cierre
contable-operativo del período: un informe Z persistido, numerado sin huecos e inmutable
de las ventas emitidas, generado bajo demanda desde `/admin`. El Z NO es una factura ni se
remite a la AEAT; es un documento interno de control.

## Scope

### In Scope
- Entidad `CierreZ` inmutable (append-only; triggers BEFORE UPDATE/DELETE, patrón ADR-0003).
- Numeración correlativa propia (Z-1, Z-2…) asignada en la misma transacción (patrón
  ContadorSerie + BEGIN IMMEDIATE, ADR-0004).
- Generación desde `/admin` como acción auditada (log append-only, invariante 4).
- Totales derivados por RANGO de ventas emitidas: nº de tickets, base total, cuota total,
  total, desglose por tipo de IVA y por medio de pago; fecha/hora con huso
  (`FechaHoraHusoGenRegistro`, ISO 8601) y usuario generador.
- Rango cubierto SIN mutar ventas: `desde_venta_id`/`hasta_venta_id`; el Z siguiente
  continúa desde `hasta_venta_id` anterior + 1 (sin hueco ni solape).
- Listado y consulta de cierres Z.

### Out of Scope
- Arqueo de efectivo, apertura de caja y fondo inicial, conteo por denominaciones, descuadre.
- Cualquier reapertura o edición de un Z.
- **Non-goals:** que el Z sea una factura o que se remita a la AEAT.

## Capabilities

### New Capabilities
- `cierre-z`: documento Z inmutable, numerado sin huecos, derivado por rango de ventas emitidas.

### Modified Capabilities
- None (`/admin` es solo la superficie de entrega; el comportamiento a nivel de requisito
  es todo nuevo).

## Approach

Capability hexagonal (ADR-0001): modelo ORM `CierreZ` + contador propio; caso de uso fino
que abre transacción inmediata, lee el último Z para fijar `desde_venta_id`, calcula
`hasta_venta_id` = máximo id de venta emitida al cierre, agrega totales por rango
(reutilizando la lógica de `informe_dia`), asigna el correlativo y persiste — todo atómico.
Inmutabilidad por triggers de BD (migración Alembic, nunca `create_all`). Importes en
`Decimal`, redondeo half-up (ADR-0005). Endpoint `/admin` auditado. Desarrollo FORWARD con
TDD estricto.

**A resolver en design (no aquí):** (a) rango por id de venta (recomendado, determinista)
vs por fecha; (b) tratamiento de anulaciones/sustituciones respecto a la ventana del Z
(ventas que cambian de estado tras un cierre).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/dominio/`, `app/aplicacion/` | New | Entidad Z + caso de uso generar/consultar |
| `app/infraestructura/persistencia/modelos/` | New | Modelo `CierreZ` + contador propio |
| `app/infraestructura/persistencia/ddl.py`, `migrations/` | Modified/New | Triggers de inmutabilidad del Z + migración |
| `app/presentacion/admin.py` | Modified | Endpoint generar/listar Z (auditado) |
| `tests/` | New | Invariantes (inmutabilidad, sin huecos/solapes) + cuadre de totales |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Un Z muta ventas para marcarlas "cerradas" (viola invariante 1) | Med | Derivar por rango; solo lectura sobre `venta`, jamás UPDATE |
| Huecos o solapes entre Z consecutivos | Med | Rango por id + numeración en la misma transacción (BEGIN IMMEDIATE) |
| Concurrencia en la asignación del correlativo | Low | Transacción inmediata, patrón ADR-0004 |

## Rollback Plan

`alembic downgrade -1`: elimina tabla(s) y triggers del Z; no toca ventas ni registros
fiscales (el Z solo lee). Revertir el endpoint en `admin.py`. Sin datos que migrar.

## Dependencies

- Ventas en estado `cobrada` con `pagos` por medio (ya existentes).
- Patrón ContadorSerie y triggers de inmutabilidad existentes.

## Success Criteria

- [ ] Generar un Z produce un documento persistido e inmutable (UPDATE/DELETE rechazados por trigger).
- [ ] Numeración Z correlativa sin huecos ni reutilización.
- [ ] Rango sin huecos ni solape con el Z anterior; ventas nunca mutadas.
- [ ] Totales y desgloses (IVA, medio de pago) cuadran con las ventas del rango.
- [ ] Acción de generación registrada en el log de auditoría.
- [ ] Cubierto por tests nuevos (TDD estricto): invariantes + cuadre.
