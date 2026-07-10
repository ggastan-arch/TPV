"""Fixtures de test.

Cada test corre sobre una BD SQLite temporal a la que se le aplica la migracion
Alembic real (tablas + triggers), de modo que se prueba el esquema de produccion,
no un create_all paralelo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.db import crear_engine
from app.core.seguridad import hash_pin
from app.fiscal.engine import NullEngine
from app.infraestructura.persistencia.modelos import ContadorSerie, Serie, TipoIVA, Usuario

RAIZ = Path(__file__).resolve().parents[1]
ALEMBIC_INI = RAIZ / "alembic.ini"
# Debe coincidir con el ejercicio por defecto de NullEngine.emit (ano en curso).
EJERCICIO = datetime.now().astimezone().year


def _aplicar_migraciones(url: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture
def engine(tmp_path):
    db = tmp_path / "test.db"
    url = f"sqlite:///{db}"
    _aplicar_migraciones(url)
    # NullPool: cada conexion es independiente (necesario para el test de concurrencia).
    eng = crear_engine(url, inmediato=True, poolclass=NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def crear_sesion(engine):
    hacer = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return hacer


@pytest.fixture
def session(crear_sesion):
    s = crear_sesion()
    yield s
    s.close()


@pytest.fixture
def motor():
    return NullEngine(id_emisor="00000000T", nombre_emisor="Bizkaitropik")


@pytest.fixture
def datos_base(session):
    """Usuario, tipos de IVA (21/10), serie T y su contador para el ejercicio."""
    usuario = Usuario(nombre="dependiente", pin_hash=hash_pin("0000"), rol="venta")
    iva21 = TipoIVA(nombre="General 21%", porcentaje="21.00")
    iva10 = TipoIVA(nombre="Reducido 10%", porcentaje="10.00")
    serie_t = Serie(codigo="T", descripcion="Simplificadas", tipo_factura_default="F2")
    serie_f = Serie(codigo="F", descripcion="Completas", tipo_factura_default="F1")
    session.add_all([usuario, iva21, iva10, serie_t, serie_f])
    session.flush()
    session.add_all([
        ContadorSerie(serie="T", ejercicio=EJERCICIO, ultimo_numero=0),
        ContadorSerie(serie="F", ejercicio=EJERCICIO, ultimo_numero=0),
    ])
    session.commit()
    return {
        "usuario_id": usuario.id,
        "iva21_id": iva21.id,
        "iva10_id": iva10.id,
        "ejercicio": EJERCICIO,
    }
