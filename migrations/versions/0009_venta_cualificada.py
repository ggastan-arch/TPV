"""venta: cualificada (flag FacturaSimplificadaArt7273, art. 7.2/7.3 ROF)

Revision ID: 0009_venta_cualificada
Revises: 0008_venta_etiqueta_aparcada
Create Date: 2026-07-19

`ADD COLUMN` NATIVO (no `batch_alter_table`): en SQLite, `batch` RECREA la tabla
entera y PERDERIA los triggers de inmutabilidad (`trg_venta_no_update/no_delete`,
ver ddl.py). `ADD COLUMN` nativo nunca recrea la tabla: triggers e invariantes
quedan intactos. Columna nullable, sin default ni backfill: las filas ya emitidas
quedan `NULL`, sin efecto.

D2 override (ver tasks.md "Nota de override sobre D2"): NO se recrea
`trg_venta_no_update` ni se anade `cualificada` a `_VENTA_CAMPOS_CONGELADOS`. Una
venta `cobrada` ya esta totalmente congelada por el trigger vigente (un UPDATE
plano sobre CUALQUIER columna, incluida `cualificada`, ya es rechazado); ningun
codigo de este cambio cambia el flag durante las transiciones de estado
permitidas (`cobrada -> anulada_con_rastro/sustituida`). Se prefiere esta opcion
(B) porque no requiere DROP+CREATE de trigger para cerrar un hueco que no existe
en la practica.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_venta_cualificada"
down_revision = "0008_venta_etiqueta_aparcada"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("venta", sa.Column("cualificada", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("venta", "cualificada")
