"""Puertos del dominio (interfaces que implementan los adaptadores de infraestructura).

Se definen como Protocol (tipado estructural) para que la capa de dominio/aplicacion no
importe las implementaciones concretas (inversion de dependencias). Nota (ADR-0001):
en la variante pragmatica las firmas usan las entidades ORM como tipos.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.infraestructura.persistencia.modelos.maestros import Articulo, Familia, TipoIVA
    from app.infraestructura.persistencia.modelos.fiscal import RegistroFiscal
    from app.infraestructura.persistencia.modelos.operacion import Usuario
    from app.infraestructura.persistencia.modelos.venta import Venta


class MotorFiscal(Protocol):
    """Emite el registro fiscal de una venta y lo encadena (ver ADR-0006)."""

    def emit(self, session: "Session", venta: "Venta", **kwargs) -> "RegistroFiscal":
        ...


class RepositorioArticulos(Protocol):
    def buscar(self, articulo_id: int) -> "Articulo | None": ...
    def buscar_por_codigo(self, codigo: str) -> "Articulo | None": ...
    def agregar(self, articulo: "Articulo") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["Articulo"]: ...


class RepositorioTiposIva(Protocol):
    def buscar(self, tipo_iva_id: int) -> "TipoIVA | None": ...
    def agregar(self, tipo_iva: "TipoIVA") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["TipoIVA"]: ...


class RepositorioFamilias(Protocol):
    def buscar(self, familia_id: int) -> "Familia | None": ...


class RepositorioVentas(Protocol):
    def agregar(self, venta: "Venta") -> None: ...
    def buscar(self, venta_id: int) -> "Venta | None": ...


class RepositorioUsuarios(Protocol):
    def buscar(self, usuario_id: int) -> "Usuario | None": ...


class RepositorioAuditoria(Protocol):
    def registrar(
        self, *, accion: str, entidad: str | None = None, entidad_id: str | None = None,
        detalle: str | None = None, usuario_id: int | None = None, origen: str = "local",
    ) -> None: ...


class RepositorioRegistros(Protocol):
    """Acceso a los registros fiscales para la cola de remision."""

    def buscar(self, registro_id: int) -> "RegistroFiscal | None": ...
    def pendientes(self, maximo: int = 1000) -> list["RegistroFiscal"]: ...
    def contar_pendientes(self) -> int: ...
    def hay_incidencia_pendiente(self) -> bool: ...
    def registros_a_reintentar(
        self, ahora=None, intervalo_horas: int = 1
    ) -> list["RegistroFiscal"]: ...
    def ultimos(self, limite: int = 10) -> list["RegistroFiscal"]: ...
    def registrar_resultado(
        self, registro: "RegistroFiscal", resultado: str, *,
        codigo_error: str | None = None, descripcion: str | None = None,
        csv: str | None = None,
    ) -> None: ...


class UnidadDeTrabajo(Protocol):
    """Agrupa los repositorios y controla la transaccion.

    `session` se expone para los colaboradores de infraestructura que operan sobre ella
    (p. ej. el motor fiscal); los casos de uso trabajan a traves de los repositorios.
    """

    articulos: RepositorioArticulos
    tipos_iva: RepositorioTiposIva
    familias: RepositorioFamilias
    ventas: RepositorioVentas
    usuarios: RepositorioUsuarios
    registros: RepositorioRegistros
    auditoria: RepositorioAuditoria
    session: "Session"

    def flush(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
