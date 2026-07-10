"""Maestros: tipos de IVA, familias (arbol), articulos, codigos de barras, clientes."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infraestructura.tipos import Dinero, Porcentaje
from app.infraestructura.persistencia.modelos.base import Base


class TipoIVA(Base):
    """Tipos impositivos configurables (nunca hardcodeados)."""

    __tablename__ = "tipo_iva"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    porcentaje: Mapped[Decimal] = mapped_column(Porcentaje(), nullable=False)
    # Calificacion de la operacion en el desglose fiscal (S1 = sujeta y no exenta).
    calificacion: Mapped[str] = mapped_column(String, nullable=False, default="S1")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Familia(Base):
    """Arbol de familias de niveles ilimitados (parent_id)."""

    __tablename__ = "familia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("familia.id", ondelete="RESTRICT"), nullable=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    imagen: Mapped[str | None] = mapped_column(String, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    padre: Mapped["Familia | None"] = relationship(
        remote_side="Familia.id", back_populates="hijos"
    )
    hijos: Mapped[list["Familia"]] = relationship(back_populates="padre")


class Articulo(Base):
    __tablename__ = "articulo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    nombre_corto: Mapped[str] = mapped_column(String, nullable=False)
    familia_id: Mapped[int | None] = mapped_column(
        ForeignKey("familia.id", ondelete="RESTRICT"), nullable=True
    )
    tipo_iva_id: Mapped[int] = mapped_column(
        ForeignKey("tipo_iva.id", ondelete="RESTRICT"), nullable=False
    )
    pvp: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)  # PVP con IVA incluido
    coste: Mapped[Decimal | None] = mapped_column(Dinero(), nullable=True)
    control_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    precio_libre: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requiere_cites: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color_boton: Mapped[str | None] = mapped_column(String, nullable=True)
    icono: Mapped[str | None] = mapped_column(String, nullable=True)
    # Los articulos con ventas NUNCA se borran; solo activo=false.
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tipo_iva: Mapped[TipoIVA] = relationship()
    familia: Mapped[Familia | None] = relationship()
    codigos: Mapped[list["CodigoBarras"]] = relationship(
        back_populates="articulo", cascade="all, delete-orphan"
    )


class CodigoBarras(Base):
    """N codigos de barras por articulo (EAN siempre como texto)."""

    __tablename__ = "codigo_barras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    articulo_id: Mapped[int] = mapped_column(
        ForeignKey("articulo.id", ondelete="CASCADE"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    articulo: Mapped[Articulo] = relationship(back_populates="codigos")


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nif: Mapped[str | None] = mapped_column(String, nullable=True)  # validado en capa app
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    domicilio: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String, nullable=True)
    rgpd_consentimiento: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
