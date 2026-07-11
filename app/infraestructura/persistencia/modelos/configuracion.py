"""Configuracion de empresa: ajuste global editable desde consola admin (Tailscale),
persistido en una fila singleton (id=1).

A diferencia de `venta`/`registro_fiscal`/`movimiento_stock`, esta tabla es MUTABLE
y NO lleva triggers de inmutabilidad: es un parametro de operacion, no un dato
fiscal (ver design.md, control-stock)."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.infraestructura.persistencia.modelos.base import Base


class ConfiguracionEmpresa(Base):
    """Fila singleton (id=1) con los ajustes globales de la empresa."""

    __tablename__ = "configuracion_empresa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    control_stock_activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
