"""Unidad de Trabajo SQLAlchemy: agrupa repositorios y controla la transaccion."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.infraestructura.persistencia.repositorios import (
    RepositorioArticulosSQL,
    RepositorioAuditoriaSQL,
    RepositorioCierresZSQL,
    RepositorioClientesSQL,
    RepositorioFamiliasSQL,
    RepositorioRegistrosSQL,
    RepositorioTiposIvaSQL,
    RepositorioUsuariosSQL,
    RepositorioVentasSQL,
)


class UnidadDeTrabajoSQL:
    def __init__(self, session: Session):
        self.session = session
        self.articulos = RepositorioArticulosSQL(session)
        self.tipos_iva = RepositorioTiposIvaSQL(session)
        self.familias = RepositorioFamiliasSQL(session)
        self.clientes = RepositorioClientesSQL(session)
        self.ventas = RepositorioVentasSQL(session)
        self.usuarios = RepositorioUsuariosSQL(session)
        self.registros = RepositorioRegistrosSQL(session)
        self.auditoria = RepositorioAuditoriaSQL(session)
        self.cierres_z = RepositorioCierresZSQL(session)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
