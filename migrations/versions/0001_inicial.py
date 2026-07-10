"""esquema inicial del TPV (maestros, ventas, registro fiscal, triggers de inmutabilidad)

Revision ID: 0001_inicial
Revises:
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.models.ddl import DROP_TRIGGERS, TRIGGERS

revision = "0001_inicial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tipo_iva",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String, nullable=False),
        sa.Column("porcentaje", sa.String, nullable=False),
        sa.Column("calificacion", sa.String, nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False),
    )

    op.create_table(
        "familia",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String, nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("familia.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("color", sa.String, nullable=True),
        sa.Column("imagen", sa.String, nullable=True),
        sa.Column("activo", sa.Boolean, nullable=False),
    )

    op.create_table(
        "serie",
        sa.Column("codigo", sa.String, primary_key=True),
        sa.Column("descripcion", sa.String, nullable=False),
        sa.Column("tipo_factura_default", sa.String, nullable=False),
    )

    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String, nullable=False, unique=True),
        sa.Column("pin_hash", sa.String, nullable=False),
        sa.Column("rol", sa.String, nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False),
        sa.CheckConstraint("rol IN ('venta','administracion')", name="ck_usuario_rol"),
    )

    op.create_table(
        "cliente",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nif", sa.String, nullable=True),
        sa.Column("nombre", sa.String, nullable=False),
        sa.Column("domicilio", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("telefono", sa.String, nullable=True),
        sa.Column("rgpd_consentimiento", sa.Boolean, nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False),
    )

    op.create_table(
        "articulo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String, nullable=False),
        sa.Column("nombre_corto", sa.String, nullable=False),
        sa.Column("familia_id", sa.Integer, sa.ForeignKey("familia.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("tipo_iva_id", sa.Integer, sa.ForeignKey("tipo_iva.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pvp", sa.String, nullable=False),
        sa.Column("coste", sa.String, nullable=True),
        sa.Column("control_stock", sa.Boolean, nullable=False),
        sa.Column("precio_libre", sa.Boolean, nullable=False),
        sa.Column("requiere_cites", sa.Boolean, nullable=False),
        sa.Column("color_boton", sa.String, nullable=True),
        sa.Column("icono", sa.String, nullable=True),
        sa.Column("activo", sa.Boolean, nullable=False),
    )

    op.create_table(
        "codigo_barras",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("articulo_id", sa.Integer, sa.ForeignKey("articulo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("codigo", sa.String, nullable=False, unique=True),
        sa.Column("principal", sa.Boolean, nullable=False),
    )

    op.create_table(
        "contador_serie",
        sa.Column("serie", sa.String, sa.ForeignKey("serie.codigo", ondelete="RESTRICT"), primary_key=True),
        sa.Column("ejercicio", sa.Integer, primary_key=True),
        sa.Column("ultimo_numero", sa.Integer, nullable=False),
    )

    op.create_table(
        "venta",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("estado", sa.String, nullable=False),
        sa.Column("serie", sa.String, sa.ForeignKey("serie.codigo", ondelete="RESTRICT"), nullable=True),
        sa.Column("ejercicio", sa.Integer, nullable=True),
        sa.Column("numero", sa.Integer, nullable=True),
        sa.Column("num_serie_factura", sa.String, nullable=True),
        sa.Column("fecha_hora_huso", sa.String, nullable=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cliente_id", sa.Integer, sa.ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("base_total", sa.String, nullable=False),
        sa.Column("cuota_total", sa.String, nullable=False),
        sa.Column("total_con_iva", sa.String, nullable=False),
        sa.UniqueConstraint("serie", "ejercicio", "numero", name="uq_venta_numeracion"),
        sa.CheckConstraint(
            "estado IN ('aparcada','cobrada','anulada_con_rastro','sustituida')",
            name="ck_venta_estado",
        ),
    )

    op.create_table(
        "venta_linea",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("articulo_id", sa.Integer, sa.ForeignKey("articulo.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("descripcion", sa.String, nullable=False),
        sa.Column("cantidad", sa.String, nullable=False),
        sa.Column("pvp_unitario", sa.String, nullable=False),
        sa.Column("tipo_iva_porcentaje", sa.String, nullable=False),
        sa.Column("descuento", sa.String, nullable=False),
        sa.Column("base_linea", sa.String, nullable=False),
        sa.Column("cuota_linea", sa.String, nullable=False),
        sa.Column("total_linea", sa.String, nullable=False),
    )

    op.create_table(
        "pago",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("medio", sa.String, nullable=False),
        sa.Column("importe", sa.String, nullable=False),
        sa.CheckConstraint("medio IN ('efectivo','tarjeta')", name="ck_pago_medio"),
    )

    op.create_table(
        "venta_sustitucion",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("venta_sustituta_id", sa.Integer, sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("venta_sustituida_id", sa.Integer, sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False, unique=True),
    )

    op.create_table(
        "registro_fiscal",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("orden", sa.Integer, nullable=False, unique=True),
        sa.Column("tipo_registro", sa.String, nullable=False),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("id_emisor", sa.String, nullable=False),
        sa.Column("num_serie_factura", sa.String, nullable=False),
        sa.Column("fecha_expedicion", sa.String, nullable=False),
        sa.Column("tipo_factura", sa.String, nullable=False),
        sa.Column("descripcion_operacion", sa.String, nullable=True),
        sa.Column("cuota_total", sa.String, nullable=False),
        sa.Column("importe_total", sa.String, nullable=False),
        sa.Column("primer_registro", sa.Boolean, nullable=False),
        sa.Column("registro_anterior_id", sa.Integer, sa.ForeignKey("registro_fiscal.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("huella_anterior", sa.String, nullable=True),
        sa.Column("huella", sa.String, nullable=False),
        sa.Column("tipo_huella", sa.String, nullable=False),
        sa.Column("fecha_hora_huso_gen_registro", sa.String, nullable=False),
        sa.Column("estado_remision", sa.String, nullable=False),
        sa.Column("registro_alta_anulado_id", sa.Integer, sa.ForeignKey("registro_fiscal.id", ondelete="RESTRICT"), nullable=True),
    )

    op.create_table(
        "registro_fiscal_desglose",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registro_fiscal_id", sa.Integer, sa.ForeignKey("registro_fiscal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("impuesto", sa.String, nullable=False),
        sa.Column("clave_regimen", sa.String, nullable=False),
        sa.Column("calificacion", sa.String, nullable=False),
        sa.Column("tipo_impositivo", sa.String, nullable=False),
        sa.Column("base_imponible", sa.String, nullable=False),
        sa.Column("cuota_repercutida", sa.String, nullable=False),
    )

    op.create_table(
        "registro_factura_sustituida",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registro_fiscal_id", sa.Integer, sa.ForeignKey("registro_fiscal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_emisor", sa.String, nullable=False),
        sa.Column("num_serie_factura", sa.String, nullable=False),
        sa.Column("fecha_expedicion", sa.String, nullable=False),
    )

    op.create_table(
        "log_auditoria",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fecha_hora_huso", sa.String, nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("accion", sa.String, nullable=False),
        sa.Column("entidad", sa.String, nullable=True),
        sa.Column("entidad_id", sa.String, nullable=True),
        sa.Column("detalle", sa.String, nullable=True),
        sa.Column("origen", sa.String, nullable=False),
        sa.CheckConstraint("origen IN ('local','remoto')", name="ck_log_origen"),
    )

    op.create_table(
        "movimiento_stock",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("articulo_id", sa.Integer, sa.ForeignKey("articulo.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo", sa.String, nullable=False),
        sa.Column("cantidad", sa.String, nullable=False),
        sa.Column("motivo", sa.String, nullable=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("fecha_hora_huso", sa.String, nullable=False),
        sa.CheckConstraint("tipo IN ('entrada','venta','merma')", name="ck_movimiento_tipo"),
        sa.CheckConstraint(
            "tipo <> 'merma' OR (motivo IS NOT NULL AND length(trim(motivo)) > 0)",
            name="ck_movimiento_merma_motivo",
        ),
    )

    op.create_table(
        "perfil_botonera",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String, nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False),
    )

    op.create_table(
        "pagina_botonera",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("perfil_id", sa.Integer, sa.ForeignKey("perfil_botonera.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nombre", sa.String, nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("columnas", sa.Integer, nullable=False),
        sa.Column("filas", sa.Integer, nullable=False),
    )

    op.create_table(
        "boton",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pagina_id", sa.Integer, sa.ForeignKey("pagina_botonera.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fila", sa.Integer, nullable=False),
        sa.Column("columna", sa.Integer, nullable=False),
        sa.Column("ancho", sa.Integer, nullable=False),
        sa.Column("alto", sa.Integer, nullable=False),
        sa.Column("color", sa.String, nullable=True),
        sa.Column("icono", sa.String, nullable=True),
        sa.Column("texto", sa.String, nullable=True),
        sa.Column("articulo_id", sa.Integer, sa.ForeignKey("articulo.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("familia_id", sa.Integer, sa.ForeignKey("familia.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("funcion", sa.String, nullable=True),
        sa.CheckConstraint(
            "((articulo_id IS NOT NULL) + (familia_id IS NOT NULL) + (funcion IS NOT NULL)) = 1",
            name="ck_boton_destino_unico",
        ),
    )

    # Invariantes de inmutabilidad a nivel de BD (fuente unica: app/models/ddl.py).
    for sentencia in TRIGGERS:
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)

    for tabla in (
        "boton",
        "pagina_botonera",
        "perfil_botonera",
        "movimiento_stock",
        "log_auditoria",
        "registro_factura_sustituida",
        "registro_fiscal_desglose",
        "registro_fiscal",
        "venta_sustitucion",
        "pago",
        "venta_linea",
        "venta",
        "contador_serie",
        "codigo_barras",
        "articulo",
        "cliente",
        "usuario",
        "serie",
        "familia",
        "tipo_iva",
    ):
        op.drop_table(tabla)
