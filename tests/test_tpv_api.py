"""API del TPV tactil: login, botonera, calcular y cobrar (TestClient)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.presentacion.deps import get_motor, get_session, get_uow
from app.infraestructura.fiscal.engine import NullEngine
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.infraestructura.persistencia.modelos import (
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


def test_botonera_refleja_layout_editado_por_el_editor(cliente, crear_sesion, datos_tpv):
    """Requisito 'Compatibilidad del contrato de lectura del TPV' (spec): editar
    el layout del perfil activo vía `ServicioBotonera.guardar_layout` no cambia
    la FORMA de `GET /tpv/api/botonera` y refleja el nuevo layout guardado."""
    from app.aplicacion.botoneras import DatosBoton, DatosLayout, ServicioBotonera
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    # Layout original (fixture `datos_tpv`): 3 botones. Lo reemplazamos por uno
    # nuevo, distinto, vía el servicio de aplicación (no HTTP, ver tasks.md Tarea 5).
    with crear_sesion() as s:
        svc = ServicioBotonera(UnidadDeTrabajoSQL(s))
        arbol = svc.cargar_arbol()
        pagina_id = arbol[0]["paginas"][0]["id"]
        svc.guardar_layout(pagina_id, DatosLayout(
            filas=4, columnas=5,
            botones=[
                DatosBoton(ref="solo", fila=2, columna=3,
                           articulo_id=datos_tpv["neon_id"], texto="Neon nuevo"),
            ],
        ))

    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    cuerpo = r.json()

    # Forma SIN cambios: mismas claves de siempre (regresion de shape).
    assert set(cuerpo.keys()) == {"perfil", "pagina", "botones"}
    assert set(cuerpo["pagina"].keys()) == {"id", "nombre", "columnas", "filas"}
    assert cuerpo["botones"] and set(cuerpo["botones"][0].keys()) == {
        "fila", "columna", "ancho", "alto", "color", "icono", "texto", "tipo", "articulo",
    }

    # Refleja el layout recien guardado (un solo boton, el nuevo).
    assert len(cuerpo["botones"]) == 1
    boton = cuerpo["botones"][0]
    assert boton["fila"] == 2 and boton["columna"] == 3 and boton["texto"] == "Neon nuevo"
    assert boton["tipo"] == "articulo"
    assert boton["articulo"]["id"] == datos_tpv["neon_id"]


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


# --- Alarma de stock (informativa, nunca bloquea el cobro) ---------------------
def test_stock_alarma_exige_pin(cliente, datos_tpv):
    assert cliente.get("/tpv/api/stock/alarma").status_code == 401
    assert cliente.get("/tpv/api/stock/alarma?pin=9999").status_code == 401


def test_stock_alarma_sin_sobreventa(cliente, datos_tpv):
    r = cliente.get("/tpv/api/stock/alarma?pin=0000")
    assert r.status_code == 200
    assert r.json() == {"control_activo": False, "articulos_en_negativo": 0}


# --- Drill-down de familias: filtro de visibilidad tactil ---------------------
def test_familia_excluye_subfamilias_no_visibles_en_tactil(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        visible = Familia(nombre="Ciclidos", parent_id=raiz.id, visible_en_tactil=True)
        no_visible = Familia(nombre="Peces escaneo", parent_id=raiz.id, visible_en_tactil=False)
        s.add_all([visible, no_visible])
        s.commit()
        raiz_id, visible_id = raiz.id, visible.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    ids = {sub["id"] for sub in r.json()["subfamilias"]}
    assert ids == {visible_id}


def test_familia_incluye_subfamilias_visibles_y_activas(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        h1 = Familia(nombre="Ciclidos", parent_id=raiz.id)
        h2 = Familia(nombre="Tetras", parent_id=raiz.id)
        s.add_all([h1, h2])
        s.commit()
        raiz_id, h1_id, h2_id = raiz.id, h1.id, h2.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    ids = {sub["id"] for sub in r.json()["subfamilias"]}
    assert ids == {h1_id, h2_id}


def test_familia_excluye_subfamilia_inactiva_aunque_visible_en_tactil(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        activa = Familia(nombre="Ciclidos", parent_id=raiz.id)
        inactiva = Familia(nombre="Descontinuada", parent_id=raiz.id, activo=False)
        s.add_all([activa, inactiva])
        s.commit()
        raiz_id, activa_id = raiz.id, activa.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    ids = {sub["id"] for sub in r.json()["subfamilias"]}
    assert ids == {activa_id}


def test_botonera_respeta_boton_explicito_a_familia_no_visible(cliente, crear_sesion, datos_tpv):
    with crear_sesion() as s:
        pagina = s.query(PaginaBotonera).one()
        no_visible = Familia(nombre="Trastienda", visible_en_tactil=False)
        s.add(no_visible)
        s.flush()
        s.add(Boton(pagina_id=pagina.id, fila=2, columna=2, texto="Trastienda",
                    familia_id=no_visible.id))
        s.commit()
        no_visible_id = no_visible.id

    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    familias_en_botones = [b["familia"]["id"] for b in r.json()["botones"] if b["tipo"] == "familia"]
    assert no_visible_id in familias_en_botones


def test_stock_alarma_refleja_sobreventa(cliente, crear_sesion, datos_tpv):
    from app.infraestructura.persistencia.modelos import MovimientoStock
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        uow.configuracion.fijar_control_stock(True)
        uow.stock.agregar(MovimientoStock(
            articulo_id=datos_tpv["neon_id"], tipo="venta", cantidad=Decimal("4"),
            fecha_hora_huso="2026-07-11T00:00:00+02:00"))
        s.commit()

    r = cliente.get("/tpv/api/stock/alarma?pin=0000")
    assert r.status_code == 200
    assert r.json() == {"control_activo": True, "articulos_en_negativo": 1}
