"""Puertos del dominio (interfaces que implementan los adaptadores de infraestructura).

Se definen como Protocol (tipado estructural) para que la capa de dominio/aplicacion no
importe las implementaciones concretas (inversion de dependencias). Nota (ADR-0001):
en la variante pragmatica las firmas usan las entidades ORM como tipos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.infraestructura.persistencia.modelos.botonera import Boton, PaginaBotonera, PerfilBotonera
    from app.infraestructura.persistencia.modelos.cierre_z import CierreZ
    from app.infraestructura.persistencia.modelos.maestros import Articulo, Cliente, Familia, TipoIVA
    from app.infraestructura.persistencia.modelos.fiscal import RegistroFiscal
    from app.infraestructura.persistencia.modelos.operacion import MovimientoStock, Usuario
    from app.infraestructura.persistencia.modelos.venta import Venta


@dataclass
class UltimoErrorRemision:
    """Ultimo intento de remision rechazado (para el panel fiscal, visible de forma
    persistente entre refrescos sin necesidad de una nueva remision: se deriva del
    historico append-only `remision_intento`, no de un estado efimero en memoria)."""

    registro_id: int
    codigo: str | None
    descripcion: str | None
    num_serie: str | None
    fecha: str


@dataclass
class TotalesRangoZ:
    """Agregado de las ventas cobradas de un rango de `registro_fiscal.orden`
    (registros de alta). Usado por `GenerarCierreZ` para congelar el snapshot."""

    num_tickets: int
    base_total: Decimal
    cuota_total: Decimal
    total_con_iva: Decimal
    desglose_iva: list[tuple[Decimal, Decimal, Decimal]]  # (tipo_impositivo, base, cuota)
    desglose_pago: list[tuple[str, Decimal]]  # (medio, importe)


class MotorFiscal(Protocol):
    """Emite el registro fiscal de una venta y lo encadena (ver ADR-0006)."""

    def emit(self, session: "Session", venta: "Venta", **kwargs) -> "RegistroFiscal":
        ...


class RepositorioArticulos(Protocol):
    def buscar(self, articulo_id: int) -> "Articulo | None": ...
    def buscar_por_codigo(self, codigo: str) -> "Articulo | None": ...
    def buscar_por_nombre(self, q: str, limite: int = 20) -> list["Articulo"]: ...
    def agregar(self, articulo: "Articulo") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["Articulo"]: ...


class RepositorioTiposIva(Protocol):
    def buscar(self, tipo_iva_id: int) -> "TipoIVA | None": ...
    def agregar(self, tipo_iva: "TipoIVA") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["TipoIVA"]: ...


class RepositorioFamilias(Protocol):
    def buscar(self, familia_id: int) -> "Familia | None": ...
    def agregar(self, familia: "Familia") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["Familia"]: ...
    def hijos(self, familia_id: int, solo_activos: bool = False) -> list["Familia"]: ...


class RepositorioClientes(Protocol):
    def buscar(self, cliente_id: int) -> "Cliente | None": ...
    def agregar(self, cliente: "Cliente") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["Cliente"]: ...


class RepositorioVentas(Protocol):
    def agregar(self, venta: "Venta") -> None: ...
    def buscar(self, venta_id: int) -> "Venta | None": ...
    def listar_por_estado(self, estado: str) -> list["Venta"]: ...
    def eliminar(self, venta: "Venta") -> None: ...


class RepositorioUsuarios(Protocol):
    def buscar(self, usuario_id: int) -> "Usuario | None": ...
    def buscar_por_nombre(self, nombre: str) -> "Usuario | None": ...
    def agregar(self, usuario: "Usuario") -> None: ...
    def listar(self, incluir_inactivos: bool = True) -> list["Usuario"]: ...
    def contar_administradores_activos(self, excluir_id: int | None = None) -> int: ...


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
    def contar_requiere_intervencion(self) -> int: ...
    def registros_a_reintentar(
        self, ahora=None, intervalo_horas: int = 1
    ) -> list["RegistroFiscal"]: ...
    def ultimos(self, limite: int = 10) -> list["RegistroFiscal"]: ...
    def registrar_resultado(
        self, registro: "RegistroFiscal", resultado: str, *,
        codigo_error: str | None = None, descripcion: str | None = None,
        csv: str | None = None, estado_remision_final: str | None = None,
    ) -> None: ...
    def max_orden_alta(self) -> int: ...
    def reencolar(
        self, registro: "RegistroFiscal", *, usuario_id: int | None = None, origen: str = "local"
    ) -> None: ...
    def ultimo_error(self) -> "UltimoErrorRemision | None": ...


class RepositorioCierresZ(Protocol):
    """Acceso al Cierre Z: snapshot inmutable (invariante 1) derivado por rango de
    `registro_fiscal.orden`. Nunca se actualiza ni se borra un Cierre Z persistido."""

    def ultimo(self) -> "CierreZ | None": ...
    def agregar(self, cierre: "CierreZ") -> None: ...
    def buscar(self, numero: int) -> "CierreZ | None": ...
    def listar(self, limite: int = 100) -> list["CierreZ"]: ...
    def cobradas_por_rango_orden(self, desde_orden: int, hasta_orden: int) -> TotalesRangoZ: ...


class RepositorioConfiguracion(Protocol):
    """Ajuste de empresa global (fila singleton), editable desde consola admin."""

    def control_stock_activo(self) -> bool: ...
    def fijar_control_stock(self, activo: bool) -> None: ...


class RepositorioBotonera(Protocol):
    """Acceso al arbol perfil -> pagina -> boton (configuracion de la botonera del
    TPV: tabla mutable, sin triggers de inmutabilidad, no es dato fiscal)."""

    def arbol(self) -> list["PerfilBotonera"]: ...
    def buscar_perfil(self, perfil_id: int) -> "PerfilBotonera | None": ...
    def agregar_perfil(self, perfil: "PerfilBotonera") -> None: ...
    def perfiles(self) -> list["PerfilBotonera"]: ...
    def buscar_pagina(self, pagina_id: int) -> "PaginaBotonera | None": ...
    def agregar_pagina(self, pagina: "PaginaBotonera") -> None: ...
    def reemplazar_botones(self, pagina: "PaginaBotonera", botones: list["Boton"]) -> None: ...


class RepositorioStock(Protocol):
    """Stock informativo (entrada/venta/merma). Agregacion on-the-fly en
    Python/Decimal (nunca `SUM` SQL, ver design.md): los importes se guardan como
    TEXT y `SUM` degradaria a coma flotante."""

    def agregar(self, movimiento: "MovimientoStock") -> None: ...
    def stock_actual(self, articulo_id: int) -> Decimal: ...
    def movimientos(self, articulo_id: int) -> list["MovimientoStock"]: ...
    def rastreados_en_negativo(self) -> list[tuple[int, Decimal]]: ...


class UnidadDeTrabajo(Protocol):
    """Agrupa los repositorios y controla la transaccion.

    `session` se expone para los colaboradores de infraestructura que operan sobre ella
    (p. ej. el motor fiscal); los casos de uso trabajan a traves de los repositorios.
    """

    articulos: RepositorioArticulos
    tipos_iva: RepositorioTiposIva
    familias: RepositorioFamilias
    clientes: RepositorioClientes
    ventas: RepositorioVentas
    usuarios: RepositorioUsuarios
    registros: RepositorioRegistros
    auditoria: RepositorioAuditoria
    cierres_z: RepositorioCierresZ
    configuracion: RepositorioConfiguracion
    stock: RepositorioStock
    botoneras: RepositorioBotonera
    session: "Session"

    def flush(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
