"""cola de remision: tabla remision_intento (append-only)

Revision ID: 0002_remision
Revises: 0001_inicial
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.infraestructura.persistencia.ddl import DROP_TRIGGERS_REMISION, TRIGGERS_REMISION

revision = "0002_remision"
down_revision = "0001_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remision_intento",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registro_fiscal_id", sa.Integer, sa.ForeignKey("registro_fiscal.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fecha_hora_huso", sa.String, nullable=False),
        sa.Column("resultado", sa.String, nullable=False),
        sa.Column("incidencia", sa.Boolean, nullable=False),
        sa.Column("codigo_error", sa.String, nullable=True),
        sa.Column("descripcion", sa.String, nullable=True),
        sa.Column("csv", sa.String, nullable=True),
        sa.CheckConstraint(
            "resultado IN ('enviado','aceptado','aceptado_con_errores','rechazado','incidencia')",
            name="ck_remision_resultado",
        ),
    )
    op.create_index("ix_remision_intento_registro", "remision_intento", ["registro_fiscal_id"])

    for sentencia in TRIGGERS_REMISION:
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS_REMISION:
        op.execute(sentencia)
    op.drop_index("ix_remision_intento_registro", table_name="remision_intento")
    op.drop_table("remision_intento")
