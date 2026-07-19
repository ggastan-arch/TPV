"""venta: endurece `trg_venta_no_update` (anade `cualificada`/`destinatario_nombre`/
`destinatario_nif` a `_VENTA_CAMPOS_CONGELADOS_V2`)

Revision ID: 0011_venta_trigger_campos_congelados
Revises: 0010_venta_destinatario_f3
Create Date: 2026-07-19

Riesgo fiscal corregido (Judgment Day, round 2): el override D2 documentado en las
migraciones 0009/0010 asumia que una venta `cobrada` ya estaba "totalmente" bloqueada
salvo el campo `estado` durante la transicion permitida
`cobrada -> {anulada_con_rastro, sustituida}`. ESO ERA FALSO (probado empiricamente):
`trg_venta_no_update` SOLO re-verifica los campos listados en `_VENTA_CAMPOS_CONGELADOS_0001`
durante esa transicion -- cualquier columna AUSENTE de esa lista podia colarse GRATIS en
el MISMO UPDATE que hace la transicion de estado, por ejemplo:

    UPDATE venta SET estado = 'anulada_con_rastro',
                      destinatario_nif = 'B00000000',
                      destinatario_nombre = 'HACK'
    WHERE id = ...;

Ese UPDATE SUCEDIA sin ser rechazado, violando el invariante 1 de CLAUDE.md
(ninguna venta emitida se edita, ni siquiera a nivel de BD) para el snapshot congelado
del destinatario de una F1/F3 ya expedida (migracion 0010) y para el flag `cualificada`
(migracion 0009).

Se cierra anadiendo esas tres columnas a `_VENTA_CAMPOS_CONGELADOS_V2`
(`app/infraestructura/persistencia/ddl.py`) y recreando `trg_venta_no_update` con la
lista endurecida. Se confirmo que ningun camino de codigo legitimo escribe estas
columnas durante la transicion permitida:
- `ConvertirEnFacturaF3.ejecutar()` fija `destinatario_nombre`/`destinatario_nif` UNA
  SOLA VEZ mientras la F3 aun esta `aparcada`, ANTES de `motor.emit` (fuera del alcance
  del trigger, que solo actua sobre ventas ya emitidas).
- `NullEngine.cancel` (`cobrada -> anulada_con_rastro`) solo escribe `estado`.
- Las ventas T origen sustituidas (`cobrada -> sustituida`) nunca reciben destinatario:
  permanecen `NULL` toda su vida.
Por tanto, endurecer la lista NO rompe ningun flujo real (confirmado con tests que
ejercitan ambas transiciones tras el cambio).

DROP + CREATE de UN SOLO trigger (`trg_venta_no_update`), NUNCA `batch_alter_table` ni
recreacion de la tabla `venta`: en SQLite, `batch` recrea la tabla entera y DESTRUIRIA
los otros 15 triggers de inmutabilidad (`trg_venta_no_delete`, los de
`venta_linea`/`pago`, `registro_fiscal`, `registro_fiscal_desglose`,
`registro_factura_sustituida`, `log_auditoria`, `movimiento_stock`).

IMPORTANTE (probado empiricamente): `_VENTA_CAMPOS_CONGELADOS_0001` (la lista que usa la
migracion 0001 para CREAR el trigger por primera vez) NO se modifico in-place -- eso
rompe CUALQUIER migracion desde cero, porque migracion 0001 crearia un trigger que
referencia `NEW.cualificada`/`NEW.destinatario_nombre`/`NEW.destinatario_nif` antes de
que esas columnas existan (0009/0010, muchas migraciones despues); SQLite revalida el
texto de los triggers existentes contra el esquema actual en cuanto CUALQUIER otra
migracion usa `batch_alter_table` sobre CUALQUIER tabla (rename+recreate), y falla con
"no such column" si la columna referenciada aun no existe. Por eso el cuerpo NUEVO se
importa de una constante SEPARADA, `ddl.TRIGGER_VENTA_NO_UPDATE_V2` (basada en
`_VENTA_CAMPOS_CONGELADOS_V2`, fuente unica de verdad para el endurecimiento), que esta
migracion aplica DESPUES de que 0009/0010 ya anadieron esas columnas -- momento en el
que SI es seguro referenciarlas. El cuerpo ANTERIOR (para `downgrade`) queda fijado
como literal historico en este fichero -- una migracion es un hecho historico y no
debe depender de que `ddl.py` conserve versiones antiguas del trigger.
"""
from __future__ import annotations

from alembic import op

from app.infraestructura.persistencia.ddl import TRIGGER_VENTA_NO_UPDATE_V2

revision = "0011_venta_trigger_campos_congelados"
down_revision = "0010_venta_destinatario_f3"
branch_labels = None
depends_on = None

# Version ANTERIOR del trigger (0001-0010): `_VENTA_CAMPOS_CONGELADOS_0001` SIN
# `cualificada`/`destinatario_nombre`/`destinatario_nif`. Literal historico fijo (no se
# reimporta de ddl.py, que ya solo conoce la version endurecida) para que `downgrade`
# restaure EXACTAMENTE el trigger que existia antes de esta migracion.
_TRIGGER_VENTA_NO_UPDATE_ANTERIOR = """
CREATE TRIGGER trg_venta_no_update
BEFORE UPDATE ON venta
FOR EACH ROW
WHEN OLD.estado <> 'aparcada'
 AND NOT (
    OLD.estado = 'cobrada'
    AND NEW.estado IN ('anulada_con_rastro', 'sustituida')
    AND NEW.serie IS OLD.serie
    AND NEW.ejercicio IS OLD.ejercicio
    AND NEW.numero IS OLD.numero
    AND NEW.num_serie_factura IS OLD.num_serie_factura
    AND NEW.fecha_hora_huso IS OLD.fecha_hora_huso
    AND NEW.usuario_id IS OLD.usuario_id
    AND NEW.cliente_id IS OLD.cliente_id
    AND NEW.base_total IS OLD.base_total
    AND NEW.cuota_total IS OLD.cuota_total
    AND NEW.total_con_iva IS OLD.total_con_iva
 )
BEGIN
    SELECT RAISE(ABORT, 'Venta emitida inmutable (RRSIF art. 8): solo transicion de estado permitida');
END;
"""


def upgrade() -> None:
    op.execute("DROP TRIGGER trg_venta_no_update;")
    op.execute(TRIGGER_VENTA_NO_UPDATE_V2)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_venta_no_update;")
    op.execute(_TRIGGER_VENTA_NO_UPDATE_ANTERIOR)
