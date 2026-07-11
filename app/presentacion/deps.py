"""Dependencias FastAPI: sesion de BD y motor fiscal."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.infraestructura.config import settings
from app.infraestructura.db import SessionLocal
from app.infraestructura.fiscal.engine import FiscalEngine, NullEngine
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def get_session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def get_uow() -> Iterator[UnidadDeTrabajoSQL]:
    s = SessionLocal()
    try:
        yield UnidadDeTrabajoSQL(s)
    finally:
        s.close()


def get_motor() -> FiscalEngine:
    # Primera rama, explicita: el perfil (no el cableado) es lo que garantiza
    # "no remite" en demo. Blinda contra un futuro VerifactuEngine de produccion
    # (fuera de alcance de este cambio) — en demo, el certificado NUNCA se lee.
    if settings.perfil == "demo":
        return NullEngine(id_emisor=settings.nif_emisor, nombre_emisor=settings.nombre_emisor)
    return NullEngine(id_emisor=settings.nif_emisor, nombre_emisor=settings.nombre_emisor)
