"""Seed demo idempotente (`sembrar_demo`): sobre BD vacia crea catalogo base +
cliente de prueba; ejecutarlo dos veces no duplica filas.

BD en memoria con `create_all` (test de la LOGICA de seed en aislamiento); el
bootstrap real de tpv_demo.db usa Alembic (`make demo`, Fase 6), nunca
`create_all` en produccion/demo.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.seed as seed_module
from app.infraestructura.persistencia.modelos import Articulo, Base, Cliente, TipoIVA


def _sesion_en_memoria(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "SessionLocal", Sesion)
    return Sesion


def test_sembrar_demo_sobre_bd_vacia_crea_catalogo_y_cliente(monkeypatch):
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        assert s.execute(select(TipoIVA)).scalars().all()
        assert s.execute(select(Articulo)).scalars().all()
        clientes = s.execute(select(Cliente)).scalars().all()
        assert len(clientes) == 1
        assert clientes[0].nombre


def test_sembrar_demo_incluye_articulos_de_precio_libre(monkeypatch):
    """El catalogo demo ejercita el modo de precio libre: articulos a granel o
    negociables (discos, maderas, rocas...) se dan de alta con modo_precio='libre',
    de modo que la demo muestre esa funcionalidad del TPV."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        articulos = s.execute(select(Articulo)).scalars().all()

    libres = [a for a in articulos if a.modo_precio == "libre"]
    assert len(libres) >= 3
    assert all(a.pvp >= Decimal("0.00") for a in libres)


def test_sembrar_demo_dos_veces_no_duplica(monkeypatch):
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()
    with Sesion() as s:
        conteo_1 = (
            len(s.execute(select(TipoIVA)).scalars().all()),
            len(s.execute(select(Articulo)).scalars().all()),
            len(s.execute(select(Cliente)).scalars().all()),
        )

    seed_module.sembrar_demo()
    with Sesion() as s:
        conteo_2 = (
            len(s.execute(select(TipoIVA)).scalars().all()),
            len(s.execute(select(Articulo)).scalars().all()),
            len(s.execute(select(Cliente)).scalars().all()),
        )

    assert conteo_1 == conteo_2
