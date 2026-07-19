"""venta: snapshot congelado del destinatario (F1/F3), columnas
`destinatario_nombre`/`destinatario_nif`

Revision ID: 0010_venta_destinatario_f3
Revises: 0009_venta_cualificada
Create Date: 2026-07-19

Riesgo fiscal corregido (Judgment Day): `ConvertirEnFacturaF3` solo congelaba
`venta.cliente_id` (la FK). La remision (`RemitirLote`, cola FIFO asincrona)
resolvia el destinatario EN VIVO desde `venta.cliente.nombre/nif` en el momento
del envio -- si el cliente se editaba entre la emision y la remision, la AEAT
recibia un destinatario DISTINTO del emitido/impreso en la F3 (documento fiscal
que debe ser inmutable). Peor aun: si el NIF del cliente quedaba vacio, se
remitia un `<NIF/>` vacio (invalido contra el XSD), lo que bloquearia TODA la
cola FIFO de remision. Estas dos columnas nuevas guardan el destinatario
RESUELTO Y NORMALIZADO que se uso REALMENTE en la emision de la F1/F3 --
escritas UNA SOLA VEZ en `ConvertirEnFacturaF3.ejecutar()`, mientras la venta
aun esta `aparcada` (antes de `motor.emit`), y nunca mas actualizadas.

`ADD COLUMN` NATIVO (no `batch_alter_table`): en SQLite, `batch` RECREA la tabla
entera y PERDERIA los triggers de inmutabilidad (`trg_venta_no_update/no_delete`,
ver ddl.py) -- mismo patron que la migracion `0009_venta_cualificada`. Columnas
nullable, sin default ni backfill: las filas ya emitidas (F1/F3 previas a este
cambio, si las hubiera) quedan `NULL`, sin efecto retroactivo -- ninguna F1/F3
emitida antes de este cambio se re-remite ni se corrige automaticamente.

D2 override (mismo patron que 0009, ver tasks.md "Nota de override sobre D2" y
el ADR en `app/infraestructura/persistencia/ddl.py`): NO se recrea
`trg_venta_no_update` ni se anaden estas columnas a `_VENTA_CAMPOS_CONGELADOS_0001`.
Una venta `cobrada` YA esta totalmente congelada por el trigger vigente para
CUALQUIER UPDATE que no sea la transicion de estado controlada
`cobrada -> {anulada_con_rastro, sustituida}`; y ningun codigo de este cambio
escribe `destinatario_nombre`/`destinatario_nif` durante esa transicion (la F3
en si no transiciona de estado en el alcance actual, y las T origen sustituidas
nunca reciben destinatario -- permanecen `NULL` toda su vida). Se prefiere esta
opcion (B) por el mismo motivo que 0009: no requiere DROP+CREATE de un trigger
fiscal-critico para cerrar un hueco que ningun camino de codigo actual ejercita.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_venta_destinatario_f3"
down_revision = "0009_venta_cualificada"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("venta", sa.Column("destinatario_nombre", sa.String(), nullable=True))
    op.add_column("venta", sa.Column("destinatario_nif", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("venta", "destinatario_nif")
    op.drop_column("venta", "destinatario_nombre")
