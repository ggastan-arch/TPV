"""articulo: modo_precio (fijo|libre|al_peso) sustituye a precio_libre

Revision ID: 0007_modo_precio_articulo
Revises: 0006_articulo_imagen
Create Date: 2026-07-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_modo_precio_articulo"
down_revision = "0006_articulo_imagen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) columna nueva, nullable de entrada (se rellena antes de exigir NOT NULL).
    with op.batch_alter_table("articulo") as batch_op:
        batch_op.add_column(sa.Column("modo_precio", sa.String, nullable=True))

    # 2) mapear el dato existente: precio_libre=True -> 'libre', resto -> 'fijo'.
    op.execute(
        "UPDATE articulo SET modo_precio = CASE precio_libre WHEN 1 THEN 'libre' ELSE 'fijo' END"
    )

    # 3) NOT NULL + CheckConstraint (valor unico excluyente, evita estados ilegales
    # como "libre" + "al_peso" a la vez) + eliminar la columna vieja.
    with op.batch_alter_table("articulo") as batch_op:
        batch_op.alter_column("modo_precio", nullable=False)
        batch_op.create_check_constraint(
            "ck_articulo_modo_precio", "modo_precio IN ('fijo','libre','al_peso')"
        )
        batch_op.drop_column("precio_libre")


def downgrade() -> None:
    # Inverso: recrear precio_libre, mapear 'libre' -> True, resto -> False.
    # Caveat (ver design.md): "al_peso" degrada a precio_libre=False (se pierde el
    # matiz "al peso"); no afecta a datos fiscales.
    with op.batch_alter_table("articulo") as batch_op:
        batch_op.add_column(sa.Column("precio_libre", sa.Boolean, nullable=True))

    op.execute(
        "UPDATE articulo SET precio_libre = CASE WHEN modo_precio = 'libre' THEN 1 ELSE 0 END"
    )

    with op.batch_alter_table("articulo") as batch_op:
        batch_op.alter_column("precio_libre", nullable=False)
        batch_op.drop_constraint("ck_articulo_modo_precio", type_="check")
        batch_op.drop_column("modo_precio")
