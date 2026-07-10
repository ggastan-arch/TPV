"""Dependencias FastAPI: sesion de BD y motor fiscal."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.fiscal.engine import FiscalEngine, NullEngine


def get_session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def get_motor() -> FiscalEngine:
    return NullEngine(id_emisor=settings.nif_emisor, nombre_emisor=settings.nombre_emisor)
