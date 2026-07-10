"""Usuarios, log de auditoria (append-only) y movimientos de stock (append-only)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tipos import Cantidad
from app.infraestructura.persistencia.modelos.base import Base


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    pin_hash: Mapped[str] = mapped_column(String, nullable=False)  # PBKDF2, nunca en claro
    rol: Mapped[str] = mapped_column(String, nullable=False)  # 'venta' | 'administracion'
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("rol IN ('venta','administracion')", name="ck_usuario_rol"),
    )


class LogAuditoria(Base):
    """Log append-only: descuentos, anulaciones, aperturas de cajon, cambios de
    precio, importaciones, accesos de administracion (locales y remotos).
    La inmutabilidad se aplica con triggers (ver models/ddl.py)."""

    __tablename__ = "log_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha_hora_huso: Mapped[str] = mapped_column(String, nullable=False)  # ISO 8601 + offset
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True
    )
    accion: Mapped[str] = mapped_column(String, nullable=False)
    entidad: Mapped[str | None] = mapped_column(String, nullable=True)
    entidad_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detalle: Mapped[str | None] = mapped_column(String, nullable=True)  # texto/JSON
    origen: Mapped[str] = mapped_column(String, nullable=False, default="local")  # local|remoto

    __table_args__ = (
        CheckConstraint("origen IN ('local','remoto')", name="ck_log_origen"),
    )


class MovimientoStock(Base):
    """Movimientos de stock: entrada / venta / merma (con motivo). Append-only."""

    __tablename__ = "movimiento_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    articulo_id: Mapped[int] = mapped_column(
        ForeignKey("articulo.id", ondelete="RESTRICT"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String, nullable=False)  # entrada|venta|merma
    cantidad: Mapped[Decimal] = mapped_column(Cantidad(), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)  # obligatorio si merma
    venta_id: Mapped[int | None] = mapped_column(
        ForeignKey("venta.id", ondelete="RESTRICT"), nullable=True
    )
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True
    )
    fecha_hora_huso: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('entrada','venta','merma')", name="ck_movimiento_tipo"
        ),
        # La merma exige motivo (justificacion fiscal de la perdida de existencias).
        CheckConstraint(
            "tipo <> 'merma' OR (motivo IS NOT NULL AND length(trim(motivo)) > 0)",
            name="ck_movimiento_merma_motivo",
        ),
    )
