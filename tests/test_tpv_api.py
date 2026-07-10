"""API del TPV tactil: login, botonera, calcular y cobrar (TestClient)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_motor, get_session, get_uow
from app.fiscal.engine import NullEngine
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.models import (
    Articulo,
    Boton,
    CodigoBarras,
    Familia,
    PaginaBotonera,
    PerfilBotonera,
    RegistroFiscal,
    Venta,
)


@pytest.fixture
def datos_tpv(session, datos_base):
    fam = Familia(nombre="Peces", orden=1)
    session.add(fam)
    session.flush()
    neon = Articulo(nombre="Neon cardenal", nombre_corto="Neon", familia_id=fam.id,
                    tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"), control_stock=True)
    tridacna = Articulo(nombre="Tridacna maxima", nombre_corto="Tridacna", familia_id=fam.id,
                        tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("45.00"),
                        precio_libre=True, requiere_cites=True)
    session.add_all([neon, tridacna])
    session.flush()
    session.add(CodigoBarras(articulo_id=neon.id, codigo="8412345678905", principal=True))
    perfil = PerfilBotonera(nombre="Principal")
    session.add(perfil)
    session.flush()
    pagina = PaginaBotonera(perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4)
    session.add(pagina)
    session.flush()
    session.add_all([
        Boton(pagina_id=pagina.id, fila=0, columna=0, texto="Neon", articulo_id=neon.id),
        Boton(pagina_id=pagina.id, fila=1, columna=0, texto="Peces", familia_id=fam.id),
        Boton(pagina_id=pagina.id, fila=3, columna=4, texto="Cobrar", funcion="cobrar"),
    ])
    session.commit()
    return {"neon_id": neon.id, "tridacna_id": tridacna.id, "familia_id": fam.id, **datos_base}


@pytest.fixture
def cliente(crear_sesion):
    app = crear_app()

    def _get_session():
        s = crear_sesion()
        try:
            yield s
        finally:
            s.close()

    def _get_uow():
        s = crear_sesion()
        try:
            yield UnidadDeTrabajoSQL(s)
        finally:
            s.close()

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_uow] = _get_uow
    app.dependency_overrides[get_motor] = lambda: NullEngine("00000000T", "Bizkaitropik")
    return TestClient(app)


def test_pagina_tpv_sirve_html(cliente):
    r = cliente.get("/tpv/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "TPV Bizkaitropik" in r.text


def test_login_ok_y_ko(cliente, datos_tpv):
    r = cliente.post("/tpv/api/login", json={"pin": "0000"})
    assert r.status_code == 200
    assert r.json()["usuario_id"] == datos_tpv["usuario_id"]
    assert cliente.post("/tpv/api/login", json={"pin": "9999"}).status_code == 401


def test_botonera_incluye_articulo(cliente, datos_tpv):
    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    tipos = {b["tipo"] for b in r.json()["botones"]}
    assert {"articulo", "familia", "funcion"} <= tipos


def test_articulo_por_codigo(cliente, datos_tpv):
    r = cliente.get("/tpv/api/articulo/por-codigo/8412345678905")
    assert r.status_code == 200
    assert r.json()["nombre_corto"] == "Neon"
    assert cliente.get("/tpv/api/articulo/por-codigo/000").status_code == 404


def test_calcular_totales_en_servidor(cliente, datos_tpv):
    r = cliente.post("/tpv/api/calcular",
                     json={"items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}]})
    assert r.status_code == 200
    assert r.json()["total"] == "5.00"  # 2 x 2,50


def test_calcular_precio_libre(cliente, datos_tpv):
    r = cliente.post("/tpv/api/calcular", json={"items": [
        {"articulo_id": datos_tpv["tridacna_id"], "cantidad": "1", "pvp": "50.00"}]})
    assert r.json()["total"] == "50.00"
    assert r.json()["lineas"][0]["requiere_cites"] is True


def test_cobrar_emite_venta(cliente, crear_sesion, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}],
        "pagos": [{"medio": "efectivo", "importe": "10.00"}],
    })
    assert r.status_code == 200
    datos = r.json()
    assert datos["num_serie"].startswith("T")
    assert datos["total"] == "5.00"
    assert datos["cambio"] == "5.00"

    with crear_sesion() as s:
        venta = s.get(Venta, datos["venta_id"])
        assert venta.estado == "cobrada"
        assert s.query(RegistroFiscal).filter_by(venta_id=venta.id).count() == 1

    # El QR de la venta se sirve como PNG.
    qr = cliente.get(f"/tpv/api/venta/{datos['venta_id']}/qr.png")
    assert qr.status_code == 200 and qr.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_cobrar_ticket_vacio_rechaza(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar",
                     json={"usuario_id": login["usuario_id"], "items": [], "pagos": []})
    assert r.status_code == 400
