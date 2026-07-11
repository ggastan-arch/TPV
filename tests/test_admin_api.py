"""Consola de administracion: auth con sesion, panel fiscal, informe y maestros."""
from __future__ import annotations

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


def test_endpoint_protegido_exige_sesion(cliente, admin):
    assert cliente.get("/admin/api/me").status_code == 401
    assert cliente.get("/admin/api/fiscal/estado").status_code == 401


def test_login_solo_admin(cliente, admin, datos_base):
    # Usuario con rol 'venta' no entra a la consola.
    assert cliente.post("/admin/api/login",
                        json={"nombre": "dependiente", "password": "0000"}).status_code == 401
    # Password incorrecta.
    assert cliente.post("/admin/api/login",
                        json={"nombre": "jefa", "password": "mal"}).status_code == 401
    # Admin correcto.
    assert _login(cliente, admin).status_code == 200


def test_flujo_completo(cliente, admin):
    assert _login(cliente, admin).status_code == 200
    assert cliente.get("/admin/api/me").json()["nombre"] == "jefa"

    estado = cliente.get("/admin/api/fiscal/estado").json()
    assert "declaracion_responsable" in estado
    assert estado["cola"]["certificado_configurado"] is False
    assert estado["cadena"]["ok"] is True

    assert cliente.get("/admin/api/informes/dia").status_code == 200
    assert cliente.get("/admin/api/maestros/articulos").status_code == 200
    assert cliente.get("/admin/api/maestros/usuarios").status_code == 200

    assert cliente.post("/admin/api/logout").status_code == 200
    assert cliente.get("/admin/api/me").status_code == 401


def test_maestros_usuarios_no_exponen_hash(cliente, admin):
    _login(cliente, admin)
    usuarios = cliente.get("/admin/api/maestros/usuarios").json()
    assert all("pin_hash" not in u for u in usuarios)
    assert any(u["nombre"] == "jefa" for u in usuarios)


def test_acceso_queda_en_auditoria(cliente, admin, crear_sesion):
    _login(cliente, admin)
    with crear_sesion() as s:
        assert s.query(LogAuditoria).filter_by(accion="acceso_admin").count() >= 1


def test_reintentar_sin_certificado(cliente, admin):
    _login(cliente, admin)
    r = cliente.post("/admin/api/fiscal/reintentar")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ok"] is False
    assert "Certificado" in cuerpo["mensaje"]


# --- Maestros: alta/edicion/baja de articulos ----------------------------------
def _nuevo_articulo(datos_base, **extra):
    cuerpo = {"nombre": "Neon cardenal", "nombre_corto": "Neon",
              "tipo_iva_id": datos_base["iva21_id"], "pvp": "2.50"}
    cuerpo.update(extra)
    return cuerpo


def test_crear_articulo_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/articulos",
                        json=_nuevo_articulo(datos_base)).status_code == 401


def test_crear_articulo_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos", json=_nuevo_articulo(datos_base))
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    articulos = cliente.get("/admin/api/maestros/articulos").json()
    assert any(a["id"] == nuevo_id and a["nombre"] == "Neon cardenal" for a in articulos)


def test_crear_articulo_tipo_iva_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos",
                     json=_nuevo_articulo(datos_base, tipo_iva_id=999999))
    assert r.status_code == 422


def test_actualizar_articulo_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.put("/admin/api/maestros/articulos/999999", json=_nuevo_articulo(datos_base))
    assert r.status_code == 404


def test_desactivar_articulo(cliente, admin, datos_base):
    _login(cliente, admin)
    nuevo_id = cliente.post("/admin/api/maestros/articulos",
                            json=_nuevo_articulo(datos_base)).json()["id"]
    assert cliente.post(f"/admin/api/maestros/articulos/{nuevo_id}/desactivar").status_code == 200
    articulos = cliente.get("/admin/api/maestros/articulos").json()
    assert any(a["id"] == nuevo_id and a["activo"] is False for a in articulos)


# --- Maestros: tipos de IVA ----------------------------------------------------
def test_crear_tipo_iva_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/tipos-iva",
                        json={"nombre": "Superreducido", "porcentaje": "4.00"}).status_code == 401


def test_crear_tipo_iva_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/tipos-iva",
                     json={"nombre": "Superreducido 4%", "porcentaje": "4.00"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    tipos = cliente.get("/admin/api/maestros/tipos-iva").json()
    assert any(t["id"] == nuevo_id and t["porcentaje"] == "4.00" for t in tipos)


def test_crear_tipo_iva_porcentaje_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/tipos-iva",
                     json={"nombre": "Malo", "porcentaje": "-1"})
    assert r.status_code == 422


def test_actualizar_tipo_iva_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.put("/admin/api/maestros/tipos-iva/999999",
                    json={"nombre": "X", "porcentaje": "21.00"})
    assert r.status_code == 404


# --- Maestros: familias --------------------------------------------------------
def test_crear_familia_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/familias",
                        json={"nombre": "Peces"}).status_code == 401


def test_crear_familia_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    familias = cliente.get("/admin/api/maestros/familias").json()
    assert any(f["id"] == nuevo_id and f["nombre"] == "Peces" for f in familias)


def test_crear_familia_padre_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/familias",
                     json={"nombre": "Huerfana", "parent_id": 999999})
    assert r.status_code == 422


def test_reasignar_padre_ciclo_devuelve_422(cliente, admin, datos_base):
    _login(cliente, admin)
    padre = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]
    hijo = cliente.post("/admin/api/maestros/familias",
                        json={"nombre": "Ciclidos", "parent_id": padre}).json()["id"]
    # Intentar que el padre cuelgue de su hijo -> ciclo.
    r = cliente.put(f"/admin/api/maestros/familias/{padre}",
                    json={"nombre": "Peces", "parent_id": hijo})
    assert r.status_code == 422


def test_desactivar_familia_con_hijos_devuelve_409(cliente, admin, datos_base):
    _login(cliente, admin)
    padre = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]
    cliente.post("/admin/api/maestros/familias", json={"nombre": "Ciclidos", "parent_id": padre})
    r = cliente.post(f"/admin/api/maestros/familias/{padre}/desactivar")
    assert r.status_code == 409


# --- Maestros: clientes --------------------------------------------------------
def test_crear_cliente_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/clientes",
                        json={"nombre": "Cliente"}).status_code == 401


def test_crear_cliente_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/clientes",
                     json={"nombre": "Acuario S.L.", "nif": "a58818501"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    clientes = cliente.get("/admin/api/maestros/clientes").json()
    assert any(c["id"] == nuevo_id and c["nif"] == "A58818501" for c in clientes)


def test_crear_cliente_nif_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/clientes",
                     json={"nombre": "Malo", "nif": "12345678A"})
    assert r.status_code == 422


def test_actualizar_cliente_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.put("/admin/api/maestros/clientes/999999", json={"nombre": "X"})
    assert r.status_code == 404


# --- Maestros: usuarios --------------------------------------------------------
def test_crear_usuario_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/usuarios",
                        json={"nombre": "cajera", "rol": "venta", "pin": "1234"}).status_code == 401


def test_crear_usuario_ok_sin_exponer_hash(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/usuarios",
                     json={"nombre": "cajera", "rol": "venta", "pin": "1234"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    usuarios = cliente.get("/admin/api/maestros/usuarios").json()
    fila = next(u for u in usuarios if u["id"] == nuevo_id)
    assert fila["rol"] == "venta"
    assert "pin_hash" not in fila and "pin" not in fila


def test_crear_usuario_rol_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/usuarios",
                     json={"nombre": "x", "rol": "jefe", "pin": "1234"})
    assert r.status_code == 422


def test_desactivar_ultimo_admin_devuelve_409(cliente, admin, datos_base):
    # 'admin' (jefa) es el unico administrador activo: no puede autodesactivarse.
    _login(cliente, admin)
    r = cliente.post(f"/admin/api/maestros/usuarios/{admin['usuario_id']}/desactivar")
    assert r.status_code == 409
