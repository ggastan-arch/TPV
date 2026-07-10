# ADR-0003: Inmutabilidad de ventas y registros con triggers de BD

- Estado: Aceptado
- Fecha: 2026-07-09

## Contexto

Invariante innegociable (art. 29.2.j LGT + RRSIF): ninguna venta emitida ni registro de
facturación puede editarse o borrarse. `CLAUDE.md` exige implementarlo **a nivel de BD**,
no solo en la capa de aplicación (una app puede tener bugs o rutas alternativas; la BD es
la última línea).

## Decisión

Triggers SQLite `BEFORE UPDATE/DELETE` que `RAISE(ABORT)`:

- `venta`: rechaza si `estado <> 'aparcada'`, salvo la transición controlada
  `cobrada → {anulada_con_rastro, sustituida}` sin tocar campos monetarios ni de identidad.
- `venta_linea` / `pago`: inmutables si la venta padre ya está emitida.
- `registro_fiscal`: inmutable salvo `estado_remision` (metadato de envío, no entra en la
  huella); nunca DELETE.
- `registro_fiscal_desglose`, `registro_factura_sustituida`: inmutables.
- `log_auditoria`, `movimiento_stock`, `remision_intento`: append-only.

Fuente única de los triggers: `app/models/ddl.py`, aplicada por la migración y por los tests.

## Consecuencias

- (+) La inalterabilidad no depende de la disciplina de la capa de aplicación.
- (+) Verificado por tests (rechazo de UPDATE/DELETE).
- (−) La lógica de negocio vive parcialmente en SQL (los triggers); documentado aquí.
- Anular/corregir = registro de anulación o factura rectificativa, nunca edición.
