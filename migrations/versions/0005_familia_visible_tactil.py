"""familia: flag visible_en_tactil para el drill-down del TPV

Revision ID: 0005_familia_visible_tactil
Revises: 0004_configuracion_empresa
Create Date: 2026-07-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_familia_visible_tactil"
down_revision = "0004_configuracion_empresa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: server_default=true() evita dejar NULL en filas existentes
    # (todas las familias ya creadas quedan visibles tras migrar).
    op.add_column(
        "familia",
        sa.Column("visible_en_tactil", sa.Boolean, nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("familia", "visible_en_tactil")
