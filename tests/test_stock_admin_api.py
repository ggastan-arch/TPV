"""API de stock bajo /admin: ajuste global, entrada/merma manuales, listado,
movimientos y estado/alarma. Patron identico a `test_admin_api.py` (sesion +
rol administracion, auditoria). El stock es informativo: nunca bloquea el
cobro (CLAUDE.md); ver `tests/test_emitir_venta.py` para el efecto no
bloqueante dentro de `EmitirVenta`."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.presentacion.deps import get_session, get_uow
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.infraestructura.persistencia.modelos import LogAuditoria, Usuario


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


def _crear_articulo_rastreado(cliente, admin, datos_base, *, nombre: str = "Neon cardenal") -> int:
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos", json={
        "nombre": nombre, "nombre_corto": nombre[:8],
        "tipo_iva_id": datos_base["iva21_id"], "pvp": "2.50", "control_stock": True,
    })
    assert r.status_code == 201
    return r.json()["id"]


def test_endpoints_stock_exigen_sesion(cliente, admin, datos_base):
    assert cliente.post("/admin/api/stock/ajuste", json={"activo": True}).status_code == 401
    assert cliente.post("/admin/api/stock/entrada",
                        json={"articulo_id": 1, "cantidad": "1"}).status_code == 401
    assert cliente.post("/admin/api/stock/merma",
                        json={"articulo_id": 1, "cantidad": "1", "motivo": "x"}).status_code == 401
    assert cliente.get("/admin/api/stock").status_code == 401
    assert cliente.get("/admin/api/stock/1/movimientos").status_code == 401
    assert cliente.get("/admin/api/stock/estado").status_code == 401


def test_ajuste_activa_y_desactiva_control_stock(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/stock/ajuste", json={"activo": True})
    assert r.status_code == 200
    assert r.json()["control_activo"] is True

    r = cliente.post("/admin/api/stock/ajuste", json={"activo": False})
    assert r.status_code == 200
    assert r.json()["control_activo"] is False


def test_ajuste_queda_auditado(cliente, admin, datos_base, crear_sesion):
    _login(cliente, admin)
    cliente.post("/admin/api/stock/ajuste", json={"activo": True})
    with crear_sesion() as s:
        logs = s.query(LogAuditoria).filter_by(accion="ajustar_control_stock").all()
        assert len(logs) == 1
        assert logs[0].usuario_id == admin["usuario_id"]


def test_entrada_registra_movimiento_y_aparece_en_listado(cliente, admin, datos_base):
    articulo_id = _crear_articulo_rastreado(cliente, admin, datos_base)

    r = cliente.post("/admin/api/stock/entrada", json={"articulo_id": articulo_id, "cantidad": "10"})
    assert r.status_code == 201

    listado = cliente.get("/admin/api/stock").json()
    fila = next(a for a in listado if a["id"] == articulo_id)
    assert fila["stock_actual"] == "10.000"

    movimientos = cliente.get(f"/admin/api/stock/{articulo_id}/movimientos").json()
    assert len(movimientos) == 1
    assert movimientos[0]["tipo"] == "entrada"


def test_entrada_articulo_no_rastreado_devuelve_422(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos", json={
        "nombre": "Planta", "nombre_corto": "Planta",
        "tipo_iva_id": datos_base["iva10_id"], "pvp": "3.00", "control_stock": False,
    })
    articulo_id = r.json()["id"]

    r = cliente.post("/admin/api/stock/entrada", json={"articulo_id": articulo_id, "cantidad": "5"})
    assert r.status_code == 422


def test_entrada_cantidad_invalida_devuelve_422(cliente, admin, datos_base):
    articulo_id = _crear_articulo_rastreado(cliente, admin, datos_base)
    r = cliente.post("/admin/api/stock/entrada", json={"articulo_id": articulo_id, "cantidad": "0"})
    assert r.status_code == 422


def test_merma_con_motivo_registra_movimiento(cliente, admin, datos_base):
    articulo_id = _crear_articulo_rastreado(cliente, admin, datos_base)
    cliente.post("/admin/api/stock/entrada", json={"articulo_id": articulo_id, "cantidad": "10"})

    r = cliente.post("/admin/api/stock/merma",
                     json={"articulo_id": articulo_id, "cantidad": "3", "motivo": "rotura de bolsa"})
    assert r.status_code == 201

    listado = cliente.get("/admin/api/stock").json()
    fila = next(a for a in listado if a["id"] == articulo_id)
    assert fila["stock_actual"] == "7.000"


def test_merma_sin_motivo_devuelve_422(cliente, admin, datos_base):
    articulo_id = _crear_articulo_rastreado(cliente, admin, datos_base)
    r = cliente.post("/admin/api/stock/merma",
                     json={"articulo_id": articulo_id, "cantidad": "3", "motivo": "   "})
    assert r.status_code == 422


def test_movimientos_articulo_inexistente_devuelve_404(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.get("/admin/api/stock/999999/movimientos")
    assert r.status_code == 404


def test_estado_refleja_sobreventa(cliente, admin, datos_base):
    articulo_id = _crear_articulo_rastreado(cliente, admin, datos_base)
    cliente.post("/admin/api/stock/entrada", json={"articulo_id": articulo_id, "cantidad": "1"})
    cliente.post("/admin/api/stock/merma",
                 json={"articulo_id": articulo_id, "cantidad": "5", "motivo": "mortandad"})

    r = cliente.get("/admin/api/stock/estado")
    assert r.status_code == 200
    estado = r.json()
    assert estado["articulos_en_negativo"] == 1
    assert estado["detalle"] == [{"articulo_id": articulo_id, "stock_actual": "-4.000"}]
