"""Venta: cabecera + lineas (precios congelados) + pagos + sustitucion.

Estados: aparcada (aun no emitida, editable/borrable) / cobrada (emitida, inmutable) /
anulada_con_rastro / sustituida (reemplazada por una factura completa F3).

La serie y el numero se asignan en la MISMA transaccion de emision
(ver app.infraestructura.fiscal.engine). La inmutabilidad tras emitir se aplica con triggers
(ver models/ddl.py): ninguna venta emitida se borra ni se edita, salvo la
transicion controlada de estado hacia anulada_con_rastro / sustituida.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infraestructura.tipos import Cantidad, Dinero, Porcentaje
from app.infraestructura.persistencia.modelos.base import Base

ESTADOS = ("aparcada", "cobrada", "anulada_con_rastro", "sustituida")


class Venta(Base):
    __tablename__ = "venta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="aparcada")

    # Asignados en la transaccion de emision (nulos mientras esta aparcada).
    serie: Mapped[str | None] = mapped_column(
        ForeignKey("serie.codigo", ondelete="RESTRICT"), nullable=True
    )
    ejercicio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_serie_factura: Mapped[str | None] = mapped_column(String, nullable=True)

    fecha_hora_huso: Mapped[str | None] = mapped_column(String, nullable=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    cliente_id: Mapped[int | None] = mapped_column(
        ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=True
    )

    base_total: Mapped[Decimal] = mapped_column(Dinero(), nullable=False, default=Decimal("0.00"))
    cuota_total: Mapped[Decimal] = mapped_column(Dinero(), nullable=False, default=Decimal("0.00"))
    total_con_iva: Mapped[Decimal] = mapped_column(
        Dinero(), nullable=False, default=Decimal("0.00")
    )

    # Etiqueta de texto libre, opcional, para borradores aparcados (no fiscal:
    # ajena a la huella y a `_VENTA_CAMPOS_CONGELADOS`, ver ddl.py).
    etiqueta_aparcada: Mapped[str | None] = mapped_column(String, nullable=True)

    lineas: Mapped[list["VentaLinea"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )
    pagos: Mapped[list["Pago"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Sin duplicados de numeracion a nivel de BD.
        UniqueConstraint("serie", "ejercicio", "numero", name="uq_venta_numeracion"),
        CheckConstraint(f"estado IN {ESTADOS}", name="ck_venta_estado"),
    )


class VentaLinea(Base):
    """Linea de venta con descripcion y precios CONGELADOS en el momento de la venta."""

    __tablename__ = "venta_linea"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venta_id: Mapped[int] = mapped_column(
        ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False
    )
    articulo_id: Mapped[int | None] = mapped_column(
        ForeignKey("articulo.id", ondelete="RESTRICT"), nullable=True
    )
    descripcion: Mapped[str] = mapped_column(String, nullable=False)  # congelada
    cantidad: Mapped[Decimal] = mapped_column(Cantidad(), nullable=False, default=Decimal("1"))
    pvp_unitario: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)  # congelado
    tipo_iva_porcentaje: Mapped[Decimal] = mapped_column(Porcentaje(), nullable=False)  # congelado
    descuento: Mapped[Decimal] = mapped_column(Dinero(), nullable=False, default=Decimal("0.00"))
    base_linea: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)
    cuota_linea: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)
    total_linea: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)

    venta: Mapped[Venta] = relationship(back_populates="lineas")


class Pago(Base):
    __tablename__ = "pago"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venta_id: Mapped[int] = mapped_column(
        ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False
    )
    medio: Mapped[str] = mapped_column(String, nullable=False)  # efectivo|tarjeta
    importe: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)

    venta: Mapped[Venta] = relationship(back_populates="pagos")

    __table_args__ = (
        CheckConstraint("medio IN ('efectivo','tarjeta')", name="ck_pago_medio"),
    )


class VentaSustitucion(Base):
    """Relacion "convertir en factura": una factura completa (F3) sustituye a una o
    varias simplificadas. N simplificadas -> 1 completa (por eso el sustituido es unico)."""

    __tablename__ = "venta_sustitucion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venta_sustituta_id: Mapped[int] = mapped_column(
        ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False
    )  # la factura completa F3
    venta_sustituida_id: Mapped[int] = mapped_column(
        ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False, unique=True
    )  # la simplificada reemplazada (solo puede sustituirse una vez)
