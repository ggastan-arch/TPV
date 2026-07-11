"""Cierre Z: documento interno de control, inmutable y numerado.

No es una factura ni se remite a la AEAT (ver openspec/changes/cierre-z/design.md).
Es un SNAPSHOT congelado de un rango de ventas cobradas, delimitado por el orden de
emision de la cadena fiscal (`registro_fiscal.orden`), no por `venta.id`. Los totales
y desgloses se persisten ya calculados en la transaccion de cierre; nunca se
recomputan al leer.

Los desgloses (por tipo de IVA y por medio de pago) viven en tablas hija, replicando
el patron de `registro_fiscal_desglose` (fiscal.py): evita perder el tipado
`Decimal` (Dinero/Porcentaje) y evita recomputar en lectura. Inmutabilidad por
triggers de BD (ver ddl.py): ningun `CierreZ` persistido se actualiza ni se borra.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infraestructura.tipos import Dinero, Porcentaje
from app.infraestructura.persistencia.modelos.base import Base


class CierreZ(Base):
    """Cabecera del Cierre Z: numero correlativo global (Z-1, Z-2...), rango de
    orden de emision y totales congelados en el momento de la generacion."""

    __tablename__ = "cierre_z"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)  # Z-N, secuencia global
    fecha_hora_huso: Mapped[str] = mapped_column(String, nullable=False)  # ISO 8601 + offset
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )

    # Rango sobre registro_fiscal.orden (registros de tipo alta), no sobre venta.id:
    # el orden de emision es monotono en el momento de emitir (invariante 2).
    desde_orden: Mapped[int] = mapped_column(Integer, nullable=False)
    hasta_orden: Mapped[int] = mapped_column(Integer, nullable=False)

    num_tickets: Mapped[int] = mapped_column(Integer, nullable=False)
    base_total: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)
    cuota_total: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)
    total_con_iva: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)

    desglose_iva: Mapped[list["CierreZDesgloseIva"]] = relationship(
        back_populates="cierre_z", cascade="all, delete-orphan"
    )
    desglose_pago: Mapped[list["CierreZDesglosePago"]] = relationship(
        back_populates="cierre_z", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("numero", name="uq_cierre_z_numero"),
    )


class CierreZDesgloseIva(Base):
    """Desglose por tipo de IVA de un Cierre Z (patron `registro_fiscal_desglose`)."""

    __tablename__ = "cierre_z_desglose_iva"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cierre_z_id: Mapped[int] = mapped_column(
        ForeignKey("cierre_z.id", ondelete="CASCADE"), nullable=False
    )
    tipo_impositivo: Mapped[Decimal] = mapped_column(Porcentaje(), nullable=False)
    base_imponible: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)
    cuota_repercutida: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)

    cierre_z: Mapped[CierreZ] = relationship(back_populates="desglose_iva")


class CierreZDesglosePago(Base):
    """Desglose por medio de pago (efectivo|tarjeta) de un Cierre Z."""

    __tablename__ = "cierre_z_desglose_pago"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cierre_z_id: Mapped[int] = mapped_column(
        ForeignKey("cierre_z.id", ondelete="CASCADE"), nullable=False
    )
    medio: Mapped[str] = mapped_column(String, nullable=False)  # efectivo|tarjeta
    importe: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)

    cierre_z: Mapped[CierreZ] = relationship(back_populates="desglose_pago")

    __table_args__ = (
        CheckConstraint("medio IN ('efectivo','tarjeta')", name="ck_cierre_z_desglose_pago_medio"),
    )
