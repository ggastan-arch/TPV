"""venta: etiqueta_aparcada (texto libre, no fiscal, para borradores aparcados)

Revision ID: 0008_venta_etiqueta_aparcada
Revises: 0007_modo_precio_articulo
Create Date: 2026-07-18

`ADD COLUMN` NATIVO (no `batch_alter_table`): en SQLite, `batch` RECREA la tabla
entera y PERDERIA los triggers de inmutabilidad (`trg_venta_no_update/no_delete`,
ver design.md). `ADD COLUMN` nativo nunca recrea la tabla: triggers e invariantes
quedan intactos. Columna nullable, sin default ni backfill: ajena a la huella y a
`_VENTA_CAMPOS_CONGELADOS`; las filas ya emitidas quedan `NULL`, sin efecto.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_venta_etiqueta_aparcada"
down_revision = "0007_modo_precio_articulo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("venta", sa.Column("etiqueta_aparcada", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("venta", "etiqueta_aparcada")
