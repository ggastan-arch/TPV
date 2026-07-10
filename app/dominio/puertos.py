"""Puertos del dominio (interfaces que implementan los adaptadores de infraestructura).

Se definen como Protocol (tipado estructural) para que la capa de dominio/aplicacion no
importe las implementaciones concretas (inversion de dependencias). Nota (ADR-0001):
en la variante pragmatica las firmas usan las entidades ORM como tipos.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.fiscal import RegistroFiscal
    from app.models.venta import Venta


class MotorFiscal(Protocol):
    """Emite el registro fiscal de una venta y lo encadena (ver ADR-0006)."""

    def emit(self, session: "Session", venta: "Venta", **kwargs) -> "RegistroFiscal":
        ...
