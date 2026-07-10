"""Adaptadores SQLAlchemy de los puertos de repositorio.

Envuelven una `Session`. Las entidades son los modelos ORM (ADR-0001)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.reloj import ahora_huso
from app.infraestructura.persistencia.modelos import Articulo, CodigoBarras, RegistroFiscal, RemisionIntento, Usuario, Venta

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
