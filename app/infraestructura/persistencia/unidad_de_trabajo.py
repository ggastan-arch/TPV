"""Unidad de Trabajo SQLAlchemy: agrupa repositorios y controla la transaccion."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.infraestructura.persistencia.repositorios import (
    RepositorioArticulosSQL,
    RepositorioRegistrosSQL,
    RepositorioUsuariosSQL,
    RepositorioVentasSQL,
)


class UnidadDeTrabajoSQL:
    def __init__(self, session: Session):
        self.session = session
        self.articulos = RepositorioArticulosSQL(session)
        self.ventas = RepositorioVentasSQL(session)
        self.usuarios = RepositorioUsuariosSQL(session)
        self.registros = RepositorioRegistrosSQL(session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
