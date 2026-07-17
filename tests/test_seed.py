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
from app.datos_demo import CLIENTES as CLIENTES_DEMO
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Base,
    Cliente,
    Familia,
    TipoIVA,
)


def _sesion_en_memoria(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "SessionLocal", Sesion)
    return Sesion


def test_sembrar_demo_sobre_bd_vacia_crea_catalogo_y_clientes(monkeypatch):
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        assert s.execute(select(TipoIVA)).scalars().all()
        assert s.execute(select(Articulo)).scalars().all()
        clientes = s.execute(select(Cliente)).scalars().all()
        assert len(clientes) == len(CLIENTES_DEMO)
        assert all(c.nombre for c in clientes)


def test_sembrar_demo_clientes_con_y_sin_nif(monkeypatch):
    """La demo incluye variedad para lucir los casos fiscales: al menos un
    cliente sin NIF (factura simplificada normal, art. 7 ROF) y varios con NIF +
    domicilio (simplificada cualificada del art. 7.2 / factura completa)."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        clientes = s.execute(select(Cliente)).scalars().all()

    sin_nif = [c for c in clientes if not c.nif]
    cualificables = [c for c in clientes if c.nif and c.domicilio]
    assert len(sin_nif) >= 1
    assert len(cualificables) >= 2


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


def test_sembrar_demo_pone_imagenes_a_peces_estrella(monkeypatch):
    """La demo luce fotos reales en los botones: los peces/plantas destacados
    llevan `imagen` bajo /media-demo (servido como estatico, commiteado en el
    repo para que persista en el despliegue)."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        articulos = {a.nombre_corto: a for a in s.execute(select(Articulo)).scalars()}

    con_foto = ["Guppy macho", "Neón cardenal", "Betta macho", "Ancistrus",
                "Anubias", "Disco turquesa", "Cometa"]
    for corto in con_foto:
        assert corto in articulos, f"falta el articulo demo {corto!r}"
        imagen = articulos[corto].imagen
        assert imagen and imagen.startswith("/media-demo/"), \
            f"{corto} deberia tener imagen /media-demo, tiene {imagen!r}"


def test_sembrar_demo_oculta_familias_de_material(monkeypatch):
    """Las familias de material con codigo de barras (filtracion, alimento,
    iluminacion, decoracion...) NO aparecen en la navegacion tactil por defecto
    (se venden por escaner/buscador); los peces y plantas si son visibles."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        familias = {f.nombre: f for f in s.execute(select(Familia)).scalars()}

    for oculta in ["Alimento", "Filtración", "Iluminación", "Decoración",
                   "Medicamentos", "Accesorios"]:
        assert familias[oculta].visible_en_tactil is False, \
            f"{oculta} deberia estar oculta en tactil"
    for visible in ["Peces por familias", "Plantas"]:
        assert familias[visible].visible_en_tactil is True, \
            f"{visible} deberia ser visible en tactil"


def test_sembrar_demo_pone_imagenes_a_familias_visibles(monkeypatch):
    """Las familias visibles en tactil llevan foto representativa (la de un pez
    tipico) para que el boton de familia tambien luzca imagen."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        familias = {f.nombre: f for f in s.execute(select(Familia)).scalars()}

    for nombre in ["Peces por familias", "Plantas", "Vivíparos", "Discos"]:
        imagen = familias[nombre].imagen
        assert imagen and imagen.startswith("/media-demo/"), \
            f"la familia {nombre} deberia tener foto, tiene {imagen!r}"


def test_sembrar_demo_articulos_navegables_heredan_foto_de_familia(monkeypatch):
    """Ningun boton navegable queda sin foto: un articulo sin imagen propia en
    una familia visible hereda la foto representativa de su familia."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        articulos = {a.nombre_corto: a for a in s.execute(select(Articulo)).scalars()}

    # Estos no tienen foto propia, pero su familia (Viviparos/Ciclidos/Plantas) si.
    for corto in ["Platy rojo", "Molly negro", "Escalar velo", "Vallisneria"]:
        imagen = articulos[corto].imagen
        assert imagen and imagen.startswith("/media-demo/"), \
            f"{corto} deberia heredar la foto de su familia, tiene {imagen!r}"


def test_sembrar_demo_incluye_articulo_bolsa(monkeypatch):
    """La demo tiene un articulo 'Bolsa' de bajo importe (0,10 EUR) como boton
    fijo de cobro rapido en la pagina de inicio."""
    Sesion = _sesion_en_memoria(monkeypatch)

    seed_module.sembrar_demo()

    with Sesion() as s:
        bolsa = s.execute(
            select(Articulo).where(Articulo.nombre_corto == "Bolsa")
        ).scalars().first()

    assert bolsa is not None, "deberia existir un articulo 'Bolsa'"
    assert bolsa.pvp == Decimal("0.10")


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
