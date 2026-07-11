"""API `/admin/api/botonera/*`: arbol, CRUD de perfiles/paginas, activacion de
perfil y guardado de layout. Mismo patron que tests/test_admin_api.py (sesion +
rol administracion, TestClient)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.presentacion.deps import get_session, get_uow
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Familia,
    LogAuditoria,
    Usuario,
)


@pytest.fixture
def admin(session, datos_base):
    u = Usuario(nombre="jefa", pin_hash=hash_pin("secreta123"), rol="administracion")
    session.add(u)
    session.commit()
    return {"nombre": "jefa", "password": "secreta123", "usuario_id": u.id}


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
    return TestClient(app)


def _login(cliente, admin):
    return cliente.post("/admin/api/login",
                        json={"nombre": admin["nombre"], "password": admin["password"]})


@pytest.fixture
def articulo_id(session, datos_base) -> int:
    a = Articulo(nombre="Neon cardenal", nombre_corto="Neon",
                 tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
    session.add(a)
    session.commit()
    return a.id


@pytest.fixture
def familia_id(session) -> int:
    f = Familia(nombre="Peces")
    session.add(f)
    session.commit()
    return f.id


def _crear_perfil(cliente, admin, nombre="Principal") -> int:
    _login(cliente, admin)
    return cliente.post("/admin/api/botonera/perfiles", json={"nombre": nombre}).json()["id"]


def _crear_pagina(cliente, admin, perfil_id, **extra) -> int:
    _login(cliente, admin)
    cuerpo = {"nombre": "Inicio", "orden": 0, "columnas": 5, "filas": 4}
    cuerpo.update(extra)
    return cliente.post(f"/admin/api/botonera/perfiles/{perfil_id}/paginas", json=cuerpo).json()["id"]


# --- proteccion: 401 sin sesion -------------------------------------------------

def test_todos_los_endpoints_exigen_sesion(cliente):
    assert cliente.get("/admin/api/botonera").status_code == 401
    assert cliente.post("/admin/api/botonera/perfiles", json={"nombre": "X"}).status_code == 401
    assert cliente.put("/admin/api/botonera/perfiles/1", json={"nombre": "X"}).status_code == 401
    assert cliente.post("/admin/api/botonera/perfiles/1/activar").status_code == 401
    assert cliente.delete("/admin/api/botonera/perfiles/1").status_code == 401
    assert cliente.post("/admin/api/botonera/perfiles/1/paginas",
                        json={"nombre": "X", "filas": 4, "columnas": 5}).status_code == 401
    assert cliente.put("/admin/api/botonera/paginas/1",
                       json={"nombre": "X", "filas": 4, "columnas": 5}).status_code == 401
    assert cliente.delete("/admin/api/botonera/paginas/1").status_code == 401
    assert cliente.put("/admin/api/botonera/paginas/1/layout",
                       json={"filas": 4, "columnas": 5, "botones": []}).status_code == 401


# --- arbol -----------------------------------------------------------------------

def test_arbol_vacio_y_con_datos(cliente, admin):
    _login(cliente, admin)
    assert cliente.get("/admin/api/botonera").json() == []

    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)

    arbol = cliente.get("/admin/api/botonera").json()
    assert len(arbol) == 1
    assert arbol[0]["id"] == perfil_id
    assert arbol[0]["paginas"][0]["id"] == pagina_id


# --- perfiles: crear/renombrar/activar/borrar -----------------------------------

def test_crear_perfil_ok_y_queda_inactivo(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin, "Secundario")
    arbol = cliente.get("/admin/api/botonera").json()
    assert any(p["id"] == perfil_id and p["activo"] is False for p in arbol)


def test_renombrar_perfil_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    r = cliente.put("/admin/api/botonera/perfiles/999999", json={"nombre": "X"})
    assert r.status_code == 404


def test_renombrar_perfil_ok(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin, "Original")
    r = cliente.put(f"/admin/api/botonera/perfiles/{perfil_id}", json={"nombre": "Nuevo"})
    assert r.status_code == 200
    arbol = cliente.get("/admin/api/botonera").json()
    assert any(p["id"] == perfil_id and p["nombre"] == "Nuevo" for p in arbol)


def test_activar_perfil_desactiva_los_demas(cliente, admin):
    a = _crear_perfil(cliente, admin, "A")
    b = _crear_perfil(cliente, admin, "B")
    _login(cliente, admin)
    assert cliente.post(f"/admin/api/botonera/perfiles/{a}/activar").status_code == 200
    assert cliente.post(f"/admin/api/botonera/perfiles/{b}/activar").status_code == 200
    arbol = cliente.get("/admin/api/botonera").json()
    estados = {p["id"]: p["activo"] for p in arbol}
    assert estados[a] is False and estados[b] is True


def test_activar_perfil_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    assert cliente.post("/admin/api/botonera/perfiles/999999/activar").status_code == 404


def test_borrar_perfil_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    assert cliente.delete("/admin/api/botonera/perfiles/999999").status_code == 404


def test_borrar_perfil_ok_elimina_del_arbol(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    _login(cliente, admin)
    assert cliente.delete(f"/admin/api/botonera/perfiles/{perfil_id}").status_code == 200
    arbol = cliente.get("/admin/api/botonera").json()
    assert all(p["id"] != perfil_id for p in arbol)


# --- paginas: crear/actualizar/borrar --------------------------------------------

def test_crear_pagina_con_perfil_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    r = cliente.post("/admin/api/botonera/perfiles/999999/paginas",
                     json={"nombre": "X", "filas": 4, "columnas": 5})
    assert r.status_code == 404


def test_crear_pagina_con_rango_invalido_da_422(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    _login(cliente, admin)
    r = cliente.post(f"/admin/api/botonera/perfiles/{perfil_id}/paginas",
                     json={"nombre": "X", "filas": 13, "columnas": 5})
    assert r.status_code == 422


def test_crear_pagina_ok(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    arbol = cliente.get("/admin/api/botonera").json()
    paginas = next(p for p in arbol if p["id"] == perfil_id)["paginas"]
    assert any(p["id"] == pagina_id for p in paginas)


def test_actualizar_pagina_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    r = cliente.put("/admin/api/botonera/paginas/999999",
                    json={"nombre": "X", "filas": 4, "columnas": 5})
    assert r.status_code == 404


def test_actualizar_pagina_ok(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    _login(cliente, admin)
    r = cliente.put(f"/admin/api/botonera/paginas/{pagina_id}",
                    json={"nombre": "Renombrada", "orden": 1, "filas": 6, "columnas": 6})
    assert r.status_code == 200
    arbol = cliente.get("/admin/api/botonera").json()
    pagina = next(p for p in arbol if p["id"] == perfil_id)["paginas"][0]
    assert pagina["nombre"] == "Renombrada" and pagina["filas"] == 6 and pagina["columnas"] == 6


def test_borrar_pagina_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    assert cliente.delete("/admin/api/botonera/paginas/999999").status_code == 404


def test_borrar_pagina_ok(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    _login(cliente, admin)
    assert cliente.delete(f"/admin/api/botonera/paginas/{pagina_id}").status_code == 200
    arbol = cliente.get("/admin/api/botonera").json()
    assert next(p for p in arbol if p["id"] == perfil_id)["paginas"] == []


# --- layout: guardado -------------------------------------------------------------

def test_guardar_layout_pagina_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    r = cliente.put("/admin/api/botonera/paginas/999999/layout",
                    json={"filas": 4, "columnas": 5, "botones": []})
    assert r.status_code == 404


def test_guardar_layout_invalido_da_422_con_detalle(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    _login(cliente, admin)
    r = cliente.put(f"/admin/api/botonera/paginas/{pagina_id}/layout", json={
        "filas": 4, "columnas": 5,
        "botones": [{"ref": "sin_destino", "fila": 0, "columna": 0}],
    })
    assert r.status_code == 422
    cuerpo = r.json()
    assert "detail" in cuerpo
    assert any("sin_destino" in e for e in cuerpo["detail"])


def test_guardar_layout_con_destino_inexistente_da_422(cliente, admin):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    _login(cliente, admin)
    r = cliente.put(f"/admin/api/botonera/paginas/{pagina_id}/layout", json={
        "filas": 4, "columnas": 5,
        "botones": [{"ref": "x", "fila": 0, "columna": 0, "articulo_id": 999999}],
    })
    assert r.status_code == 422


def test_guardar_layout_valido_persiste(cliente, admin, articulo_id, familia_id):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    _login(cliente, admin)
    r = cliente.put(f"/admin/api/botonera/paginas/{pagina_id}/layout", json={
        "filas": 4, "columnas": 5,
        "botones": [
            {"ref": "a", "fila": 0, "columna": 0, "articulo_id": articulo_id, "texto": "Neon"},
            {"ref": "b", "fila": 1, "columna": 0, "familia_id": familia_id},
            {"ref": "c", "fila": 3, "columna": 4, "funcion": "cobrar"},
        ],
    })
    assert r.status_code == 200
    arbol = cliente.get("/admin/api/botonera").json()
    botones = next(p for p in arbol if p["id"] == perfil_id)["paginas"][0]["botones"]
    assert len(botones) == 3
    assert any(b["articulo_id"] == articulo_id and b["texto"] == "Neon" for b in botones)


# --- auditoria: cada endpoint mutante deja rastro con el origen correcto --------

def test_endpoints_mutantes_dejan_auditoria(cliente, admin, crear_sesion, articulo_id):
    perfil_id = _crear_perfil(cliente, admin)
    pagina_id = _crear_pagina(cliente, admin, perfil_id)
    _login(cliente, admin)
    cliente.post(f"/admin/api/botonera/perfiles/{perfil_id}/activar")
    cliente.put(f"/admin/api/botonera/paginas/{pagina_id}/layout", json={
        "filas": 4, "columnas": 5,
        "botones": [{"ref": "a", "fila": 0, "columna": 0, "articulo_id": articulo_id}],
    })
    with crear_sesion() as s:
        acciones = {log.accion for log in s.query(LogAuditoria).all()}
        assert {
            "crear_perfil_botonera", "crear_pagina_botonera",
            "activar_perfil_botonera", "guardar_layout_botonera",
        } <= acciones
        # El origen lo resuelve `_origen(request)` (local/remoto): debe quedar
        # informado (no nulo) en cada entrada, sea cual sea el valor resuelto.
        logs_botonera = s.query(LogAuditoria).filter(
            LogAuditoria.accion.like("%_botonera")).all()
        assert logs_botonera and all(log.origen in ("local", "remoto") for log in logs_botonera)
