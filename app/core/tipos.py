"""Tipos de columna para importes exactos.

SQLite NO tiene tipo Decimal nativo y degrada NUMERIC/REAL a coma flotante
binaria, lo que introduce descuadres de centimos. Regla innegociable de CLAUDE.md:
`Decimal`, jamas `float`, para importes. Por eso los importes se almacenan como
TEXT (cadena canonica, p. ej. "12.34") y se devuelven siempre como `Decimal`.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class DecimalTexto(TypeDecorator):
    """Almacena un `Decimal` como TEXT preservando exactitud."""

    impl = String
    cache_ok = True

    def __init__(self, decimales: int = 2, **kw):
        self._exp = Decimal(1).scaleb(-decimales)  # 2 -> Decimal("0.01")
        self.decimales = decimales
        super().__init__(**kw)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return format(value.quantize(self._exp, rounding=ROUND_HALF_UP), "f")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value)


def Dinero() -> DecimalTexto:
    """Importe monetario: 2 decimales."""
    return DecimalTexto(2)


def Porcentaje() -> DecimalTexto:
    """Tipo impositivo: 2 decimales (21.00 / 10.00)."""
    return DecimalTexto(2)


def Cantidad() -> DecimalTexto:
    """Cantidad vendida: 3 decimales (permite pesos/tallas)."""
    return DecimalTexto(3)
