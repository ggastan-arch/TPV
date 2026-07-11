"""Endpoints `/admin/api/maestros/cierres-z` (Fase 6, RED primero: no existen aun).

Cubre: exige sesion de administrador (401), generacion autenticada (201 + fila de
auditoria), listado y detalle con desgloses (IVA y medio de pago), 404 en numero
inexistente. La generacion delega en `GenerarCierreZ`, que ya audita internamente
(no se duplica la auditoria en el endpoint)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _helpers import construir_venta
from app.presentacion.deps import get_session, get_uow
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.modelos import LogAuditoria, Pago, Usuario
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app


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


def _emitir(crear_sesion, motor, usuario_id, lineas, medio="efectivo"):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, lineas)
        s.add(venta)
        venta.pagos.append(Pago(medio=medio, importe=venta.total_con_iva))
        motor.emit(s, venta)


# --- Exige sesion de administrador ---------------------------------------------
def test_generar_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/cierres-z").status_code == 401


def test_listar_exige_sesion(cliente, datos_base):
    assert cliente.get("/admin/api/maestros/cierres-z").status_code == 401


def test_detalle_exige_sesion(cliente, datos_base):
    assert cliente.get("/admin/api/maestros/cierres-z/1").status_code == 401


# --- Generacion autenticada: crea el Cierre Z y audita -------------------------
def test_generar_cierre_z_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/cierres-z")
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["numero"] == 1
    assert cuerpo["desde_orden"] == 1
    assert cuerpo["num_tickets"] == 0
    assert cuerpo["base_total"] == "0.00"
    assert cuerpo["cuota_total"] == "0.00"
    assert cuerpo["total_con_iva"] == "0.00"


def test_generar_cierre_z_deja_fila_de_auditoria(cliente, admin, datos_base, crear_sesion):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/cierres-z")
    numero = r.json()["numero"]
    with crear_sesion() as s:
        fila = (
            s.query(LogAuditoria)
            .filter_by(accion="generar_cierre_z", entidad="cierre_z")
            .order_by(LogAuditoria.id.desc())
            .first()
        )
        assert fila is not None
        assert fila.usuario_id == admin["usuario_id"]
    assert numero == 1


# --- Listado ---------------------------------------------------------------
def test_listar_cierres_z(cliente, admin, datos_base):
    _login(cliente, admin)
    cliente.post("/admin/api/maestros/cierres-z")
    cliente.post("/admin/api/maestros/cierres-z")
    listado = cliente.get("/admin/api/maestros/cierres-z").json()
    numeros = [c["numero"] for c in listado]
    assert numeros == [2, 1]  # mas reciente primero


# --- Detalle con desgloses ---------------------------------------------------
def test_detalle_cierre_z_con_desgloses(cliente, admin, datos_base, crear_sesion, motor):
    _login(cliente, admin)
    _emitir(crear_sesion, motor, datos_base["usuario_id"],
           [("Neon cardenal", "2.50", "2", "21")], medio="efectivo")
    _emitir(crear_sesion, motor, datos_base["usuario_id"],
           [("Anubias", "6.90", "1", "10")], medio="tarjeta")

    numero = cliente.post("/admin/api/maestros/cierres-z").json()["numero"]
    detalle = cliente.get(f"/admin/api/maestros/cierres-z/{numero}").json()

    assert detalle["num_tickets"] == 2
    por_medio = {d["medio"]: d["importe"] for d in detalle["desglose_pago"]}
    assert set(por_medio) == {"efectivo", "tarjeta"}
    tipos_iva = {d["tipo_impositivo"] for d in detalle["desglose_iva"]}
    assert tipos_iva == {"21.00", "10.00"}


def test_detalle_cierre_z_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    assert cliente.get("/admin/api/maestros/cierres-z/999999").status_code == 404
