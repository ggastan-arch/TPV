"""Adaptadores SQLAlchemy de los puertos de repositorio.

Envuelven una `Session`. Las entidades son los modelos ORM (ADR-0001)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Articulo, CodigoBarras, Usuario, Venta


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
