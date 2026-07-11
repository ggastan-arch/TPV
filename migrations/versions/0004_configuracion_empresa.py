"""configuracion de empresa: ajuste global singleton (control de stock) + indice
de movimiento_stock por articulo

Revision ID: 0004_configuracion_empresa
Revises: 0003_cierre_z
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_configuracion_empresa"
down_revision = "0003_cierre_z"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tabla de parametros, MUTABLE: no es dato fiscal, por lo que no lleva
    # triggers de inmutabilidad (ver design.md, control-stock).
    op.create_table(
        "configuracion_empresa",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("control_stock_activo", sa.Boolean, nullable=False),
    )
    op.execute(
        "INSERT INTO configuracion_empresa (id, control_stock_activo) VALUES (1, 0)"
    )

    # Agiliza la agregacion on-the-fly de `stock_actual`/`rastreados_en_negativo`.
    op.create_index("ix_movimiento_stock_articulo", "movimiento_stock", ["articulo_id"])


def downgrade() -> None:
    op.drop_index("ix_movimiento_stock_articulo", table_name="movimiento_stock")
    op.drop_table("configuracion_empresa")
