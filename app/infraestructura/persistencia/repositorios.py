"""Adaptadores SQLAlchemy de los puertos de repositorio.

Envuelven una `Session`. Las entidades son los modelos ORM (ADR-0001)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infraestructura.reloj import ahora_huso
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Cliente,
    CodigoBarras,
    Familia,
    LogAuditoria,
    RegistroFiscal,
    RemisionIntento,
    TipoIVA,
    Usuario,
    Venta,
)

# Estados terminales de aceptacion: ya no hace falta reintentar la remision.
ESTADOS_ACEPTADOS = ("aceptado", "aceptado_con_errores")


class RepositorioArticulosSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, articulo_id: int) -> Articulo | None:
        return self._s.get(Articulo, articulo_id)

    def buscar_por_codigo(self, codigo: str) -> Articulo | None:
        cb = self._s.execute(
            select(CodigoBarras).where(CodigoBarras.codigo == codigo)
        ).scalars().first()
        return self._s.get(Articulo, cb.articulo_id) if cb else None

    def agregar(self, articulo: Articulo) -> None:
        self._s.add(articulo)

    def listar(self, incluir_inactivos: bool = True) -> list[Articulo]:
        stmt = select(Articulo).order_by(Articulo.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Articulo.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioTiposIvaSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, tipo_iva_id: int) -> TipoIVA | None:
        return self._s.get(TipoIVA, tipo_iva_id)

    def agregar(self, tipo_iva: TipoIVA) -> None:
        self._s.add(tipo_iva)

    def listar(self, incluir_inactivos: bool = True) -> list[TipoIVA]:
        stmt = select(TipoIVA).order_by(TipoIVA.id)
        if not incluir_inactivos:
            stmt = stmt.where(TipoIVA.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioFamiliasSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, familia_id: int) -> Familia | None:
        return self._s.get(Familia, familia_id)

    def agregar(self, familia: Familia) -> None:
        self._s.add(familia)

    def listar(self, incluir_inactivos: bool = True) -> list[Familia]:
        stmt = select(Familia).order_by(Familia.orden, Familia.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Familia.activo.is_(True))
        return list(self._s.execute(stmt).scalars())

    def hijos(self, familia_id: int, solo_activos: bool = False) -> list[Familia]:
        stmt = select(Familia).where(Familia.parent_id == familia_id)
        if solo_activos:
            stmt = stmt.where(Familia.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioAuditoriaSQL:
    def __init__(self, session: Session):
        self._s = session

    def registrar(
        self, *, accion: str, entidad: str | None = None, entidad_id: str | None = None,
        detalle: str | None = None, usuario_id: int | None = None, origen: str = "local",
    ) -> None:
        self._s.add(LogAuditoria(
            fecha_hora_huso=ahora_huso(), usuario_id=usuario_id, accion=accion,
            entidad=entidad, entidad_id=entidad_id, detalle=detalle, origen=origen))


class RepositorioClientesSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, cliente_id: int) -> Cliente | None:
        return self._s.get(Cliente, cliente_id)

    def agregar(self, cliente: Cliente) -> None:
        self._s.add(cliente)

    def listar(self, incluir_inactivos: bool = True) -> list[Cliente]:
        stmt = select(Cliente).order_by(Cliente.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Cliente.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioVentasSQL:
    def __init__(self, session: Session):
        self._s = session

    def agregar(self, venta: Venta) -> None:
        self._s.add(venta)

    def buscar(self, venta_id: int) -> Venta | None:
        return self._s.get(Venta, venta_id)


class RepositorioUsuariosSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, usuario_id: int) -> Usuario | None:
        return self._s.get(Usuario, usuario_id)

    def buscar_por_nombre(self, nombre: str) -> Usuario | None:
        return self._s.execute(
            select(Usuario).where(Usuario.nombre == nombre)
        ).scalars().first()

    def agregar(self, usuario: Usuario) -> None:
        self._s.add(usuario)

    def listar(self, incluir_inactivos: bool = True) -> list[Usuario]:
        stmt = select(Usuario).order_by(Usuario.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Usuario.activo.is_(True))
        return list(self._s.execute(stmt).scalars())

    def contar_administradores_activos(self, excluir_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(Usuario).where(
            Usuario.rol == "administracion", Usuario.activo.is_(True))
        if excluir_id is not None:
            stmt = stmt.where(Usuario.id != excluir_id)
        return self._s.execute(stmt).scalar_one()


class RepositorioRegistrosSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, registro_id: int) -> RegistroFiscal | None:
        return self._s.get(RegistroFiscal, registro_id)

    def pendientes(self, maximo: int = 1000) -> list[RegistroFiscal]:
        stmt = (
            select(RegistroFiscal)
            .where(RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS))
            .order_by(RegistroFiscal.orden)
            .limit(min(maximo, 1000))
        )
        return list(self._s.execute(stmt).scalars())

    def contar_pendientes(self) -> int:
        stmt = (
            select(func.count())
            .select_from(RegistroFiscal)
            .where(RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS))
        )
        return self._s.execute(stmt).scalar_one()

    def hay_incidencia_pendiente(self) -> bool:
        stmt = (
            select(RemisionIntento.id)
            .join(RegistroFiscal, RemisionIntento.registro_fiscal_id == RegistroFiscal.id)
            .where(
                RemisionIntento.incidencia.is_(True),
                RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS),
            )
            .limit(1)
        )
        return self._s.execute(stmt).first() is not None

    def registros_a_reintentar(
        self, ahora: datetime | None = None, intervalo_horas: int = 1
    ) -> list[RegistroFiscal]:
        ahora = ahora or datetime.now().astimezone()
        limite = timedelta(hours=intervalo_horas)
        a_reintentar = []
        for reg in self.pendientes():
            ultimo = self._ultimo_intento(reg.id)
            if ultimo is None or ahora - datetime.fromisoformat(ultimo.fecha_hora_huso) >= limite:
                a_reintentar.append(reg)
        return a_reintentar

    def ultimos(self, limite: int = 10) -> list[RegistroFiscal]:
        stmt = select(RegistroFiscal).order_by(RegistroFiscal.orden.desc()).limit(limite)
        return list(self._s.execute(stmt).scalars())

    def registrar_resultado(
        self, registro: RegistroFiscal, resultado: str, *,
        codigo_error: str | None = None, descripcion: str | None = None,
        csv: str | None = None,
    ) -> None:
        """Anota el intento (append-only) y actualiza el estado canonico del registro.
        Una incidencia (no se pudo remitir) deja el registro 'pendiente' para reintento."""
        incidencia = resultado == "incidencia"
        self._s.add(RemisionIntento(
            registro_fiscal_id=registro.id, fecha_hora_huso=ahora_huso(),
            resultado=resultado, incidencia=incidencia,
            codigo_error=codigo_error, descripcion=descripcion, csv=csv))
        registro.estado_remision = "pendiente" if incidencia else resultado

    def _ultimo_intento(self, registro_id: int) -> RemisionIntento | None:
        stmt = (
            select(RemisionIntento)
            .where(RemisionIntento.registro_fiscal_id == registro_id)
            .order_by(RemisionIntento.id.desc())
            .limit(1)
        )
        return self._s.execute(stmt).scalars().first()
