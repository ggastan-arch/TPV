"""Modelos SQLAlchemy del TPV. Importar `Base` desde aqui garantiza que todo el
metadata este registrado (para Alembic y para create_all en tests)."""
from __future__ import annotations

from app.models.base import Base
from app.models.botonera import Boton, FUNCIONES, PaginaBotonera, PerfilBotonera
from app.models.fiscal import (
    ContadorSerie,
    ESTADOS_REMISION,
    RESULTADOS_REMISION,
    RegistroFacturaSustituida,
    RegistroFiscal,
    RegistroFiscalDesglose,
    RemisionIntento,
    Serie,
    TIPOS_FACTURA,
)
from app.models.maestros import Articulo, Cliente, CodigoBarras, Familia, TipoIVA
from app.models.operacion import LogAuditoria, MovimientoStock, Usuario
from app.models.venta import ESTADOS, Pago, Venta, VentaLinea, VentaSustitucion

__all__ = [
    "Base",
    "TipoIVA",
    "Familia",
    "Articulo",
    "CodigoBarras",
    "Cliente",
    "Serie",
    "ContadorSerie",
    "Venta",
    "VentaLinea",
    "Pago",
    "VentaSustitucion",
    "RegistroFiscal",
    "RegistroFiscalDesglose",
    "RegistroFacturaSustituida",
    "RemisionIntento",
    "ESTADOS_REMISION",
    "RESULTADOS_REMISION",
    "Usuario",
    "LogAuditoria",
    "MovimientoStock",
    "PerfilBotonera",
    "PaginaBotonera",
    "Boton",
    "ESTADOS",
    "TIPOS_FACTURA",
    "FUNCIONES",
]
