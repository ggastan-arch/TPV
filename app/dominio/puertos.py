"""Puertos del dominio (interfaces que implementan los adaptadores de infraestructura).

Se definen como Protocol (tipado estructural) para que la capa de dominio/aplicacion no
importe las implementaciones concretas (inversion de dependencias). Nota (ADR-0001):
en la variante pragmatica las firmas usan las entidades ORM como tipos.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.maestros import Articulo
    from app.models.fiscal import RegistroFiscal
    from app.models.operacion import Usuario
    from app.models.venta import Venta


class MotorFiscal(Protocol):
    """Emite el registro fiscal de una venta y lo encadena (ver ADR-0006)."""

    def emit(self, session: "Session", venta: "Venta", **kwargs) -> "RegistroFiscal":
        ...


class RepositorioArticulos(Protocol):
    def buscar(self, articulo_id: int) -> "Articulo | None": ...
    def buscar_por_codigo(self, codigo: str) -> "Articulo | None": ...


class RepositorioVentas(Protocol):
    def agregar(self, venta: "Venta") -> None: ...
    def buscar(self, venta_id: int) -> "Venta | None": ...


class RepositorioUsuarios(Protocol):
    def buscar(self, usuario_id: int) -> "Usuario | None": ...


class UnidadDeTrabajo(Protocol):
    """Agrupa los repositorios y controla la transaccion.

    `session` se expone para los colaboradores de infraestructura que operan sobre ella
    (p. ej. el motor fiscal); los casos de uso trabajan a traves de los repositorios.
    """

    articulos: RepositorioArticulos
    ventas: RepositorioVentas
    usuarios: RepositorioUsuarios
    session: "Session"

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
