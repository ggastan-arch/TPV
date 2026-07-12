"""articulo: columna imagen (ruta publica bajo /media, ver catalogo de imagenes)

Revision ID: 0006_articulo_imagen
Revises: 0005_familia_visible_tactil
Create Date: 2026-07-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_articulo_imagen"
down_revision = "0005_familia_visible_tactil"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: nullable, sin server_default. Los articulos existentes quedan
    # sin imagen (NULL) hasta que se suba una desde la consola.
    op.add_column("articulo", sa.Column("imagen", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("articulo", "imagen")
