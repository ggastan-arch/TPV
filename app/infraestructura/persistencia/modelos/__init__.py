"""Modelos SQLAlchemy del TPV. Importar `Base` desde aqui garantiza que todo el
metadata este registrado (para Alembic y para create_all en tests)."""
from __future__ import annotations

from app.infraestructura.persistencia.modelos.base import Base
from app.infraestructura.persistencia.modelos.botonera import Boton, FUNCIONES, PaginaBotonera, PerfilBotonera
from app.infraestructura.persistencia.modelos.cierre_z import CierreZ, CierreZDesgloseIva, CierreZDesglosePago
from app.infraestructura.persistencia.modelos.fiscal import (
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
from app.infraestructura.persistencia.modelos.maestros import Articulo, Cliente, CodigoBarras, Familia, TipoIVA
from app.infraestructura.persistencia.modelos.operacion import LogAuditoria, MovimientoStock, Usuario
from app.infraestructura.persistencia.modelos.venta import ESTADOS, Pago, Venta, VentaLinea, VentaSustitucion

__all__ = [
    "Base",
    "TipoIVA",
    "Familia",
    "Articulo",
    "CodigoBarras",
    "Cliente",
    "Serie",
    "ContadorSerie",
    "CierreZ",
    "CierreZDesgloseIva",
    "CierreZDesglosePago",
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
