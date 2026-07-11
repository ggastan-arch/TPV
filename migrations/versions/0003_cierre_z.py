"""cierre Z: cabecera + desglose IVA + desglose pago (snapshot inmutable)

Revision ID: 0003_cierre_z
Revises: 0002_remision
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.infraestructura.persistencia.ddl import DROP_TRIGGERS_CIERRE_Z, TRIGGERS_CIERRE_Z

revision = "0003_cierre_z"
down_revision = "0002_remision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cierre_z",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("fecha_hora_huso", sa.String, nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("desde_orden", sa.Integer, nullable=False),
        sa.Column("hasta_orden", sa.Integer, nullable=False),
        sa.Column("num_tickets", sa.Integer, nullable=False),
        sa.Column("base_total", sa.String, nullable=False),
        sa.Column("cuota_total", sa.String, nullable=False),
        sa.Column("total_con_iva", sa.String, nullable=False),
        sa.UniqueConstraint("numero", name="uq_cierre_z_numero"),
    )

    op.create_table(
        "cierre_z_desglose_iva",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cierre_z_id", sa.Integer, sa.ForeignKey("cierre_z.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo_impositivo", sa.String, nullable=False),
        sa.Column("base_imponible", sa.String, nullable=False),
        sa.Column("cuota_repercutida", sa.String, nullable=False),
    )
    op.create_index("ix_cierre_z_desglose_iva_cierre_z", "cierre_z_desglose_iva", ["cierre_z_id"])

    op.create_table(
        "cierre_z_desglose_pago",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cierre_z_id", sa.Integer, sa.ForeignKey("cierre_z.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medio", sa.String, nullable=False),
        sa.Column("importe", sa.String, nullable=False),
        sa.CheckConstraint("medio IN ('efectivo','tarjeta')", name="ck_cierre_z_desglose_pago_medio"),
    )
    op.create_index("ix_cierre_z_desglose_pago_cierre_z", "cierre_z_desglose_pago", ["cierre_z_id"])

    for sentencia in TRIGGERS_CIERRE_Z:
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS_CIERRE_Z:
        op.execute(sentencia)

    op.drop_index("ix_cierre_z_desglose_pago_cierre_z", table_name="cierre_z_desglose_pago")
    op.drop_table("cierre_z_desglose_pago")
    op.drop_index("ix_cierre_z_desglose_iva_cierre_z", table_name="cierre_z_desglose_iva")
    op.drop_table("cierre_z_desglose_iva")
    op.drop_table("cierre_z")
