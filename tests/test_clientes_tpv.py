"""API `/tpv/api/clientes`: busqueda (PIN-gated) y alta inline con RGPD.

Ver specs/cliente-en-venta/spec.md — "Busqueda de cliente por nombre o NIF desde
el TPV" y "Alta de cliente inline desde el TPV con consentimiento RGPD"."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.aplicacion.clientes import DatosCliente, ServicioClientes
from app.presentacion.deps import get_session, get_uow
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.infraestructura.persistencia.modelos import Cliente


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


def test_buscar_clientes_exige_pin(cliente, datos_base):
    assert cliente.get("/tpv/api/clientes", params={"q": "perez"}).status_code == 401
    assert cliente.get("/tpv/api/clientes", params={"q": "perez", "pin": "9999"}).status_code == 401


def test_buscar_clientes_coincide_por_nombre(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        ServicioClientes(UnidadDeTrabajoSQL(s)).crear(DatosCliente(nombre="Juan Perez"))

    r = cliente.get("/tpv/api/clientes", params={"q": "perez", "pin": "0000"})
    assert r.status_code == 200
    assert [c["nombre"] for c in r.json()] == ["Juan Perez"]


def test_buscar_clientes_coincide_por_nif(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501"))

    r = cliente.get("/tpv/api/clientes", params={"q": "A58818501", "pin": "0000"})
    assert r.status_code == 200
    assert [c["nombre"] for c in r.json()] == ["Acuario S.L."]


def test_buscar_clientes_no_expone_email_ni_telefono(cliente, crear_sesion, datos_base):
    """Judgment Day S-4: el picker del TPV solo necesita id/nombre/nif/domicilio;
    la busqueda no debe filtrar PII (email, telefono) que no usa la UI."""
    with crear_sesion() as s:
        ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Juan Perez", email="juan@example.com", telefono="600111222"))

    r = cliente.get("/tpv/api/clientes", params={"q": "perez", "pin": "0000"})
    assert r.status_code == 200
    resultado = r.json()[0]
    assert set(resultado.keys()) == {"id", "nombre", "nif", "domicilio"}


def test_alta_inline_con_rgpd_persiste_y_queda_disponible_para_buscar(
    cliente, crear_sesion, datos_base
):
    r = cliente.post("/tpv/api/clientes", params={"pin": "0000"}, json={
        "nombre": "Cliente nuevo", "rgpd_consentimiento": True,
    })
    assert r.status_code == 200
    cliente_id = r.json()["id"]

    with crear_sesion() as s:
        c = s.get(Cliente, cliente_id)
        assert c is not None and c.rgpd_consentimiento is True

    buscado = cliente.get("/tpv/api/clientes", params={"q": "nuevo", "pin": "0000"})
    assert [c["nombre"] for c in buscado.json()] == ["Cliente nuevo"]


def test_alta_inline_con_ficha_completa_persiste_email_telefono_y_rgpd(
    cliente, crear_sesion, datos_base
):
    """La ficha de alta inline del TPV admite email/telefono ademas de
    nombre/nif/domicilio/rgpd; todos opcionales salvo nombre."""
    r = cliente.post("/tpv/api/clientes", params={"pin": "0000"}, json={
        "nombre": "Cliente completo",
        "nif": "A58818501",
        "domicilio": "Calle Falsa 123",
        "email": "cliente@example.com",
        "telefono": "600111222",
        "rgpd_consentimiento": True,
    })
    assert r.status_code == 200
    cliente_id = r.json()["id"]

    with crear_sesion() as s:
        c = s.get(Cliente, cliente_id)
        assert c is not None
        assert c.email == "cliente@example.com"
        assert c.telefono == "600111222"
        assert c.rgpd_consentimiento is True
        assert c.nif == "A58818501"
        assert c.domicilio == "Calle Falsa 123"


def test_alta_inline_nif_invalido_rechaza_422_sin_persistir(cliente, crear_sesion, datos_base):
    r = cliente.post("/tpv/api/clientes", params={"pin": "0000"}, json={
        "nombre": "Malo", "nif": "12345678A", "rgpd_consentimiento": True,
    })
    assert r.status_code == 422

    with crear_sesion() as s:
        assert s.query(Cliente).count() == 0


def test_alta_inline_exige_pin(cliente, datos_base):
    r = cliente.post("/tpv/api/clientes", json={"nombre": "Sin PIN"})
    assert r.status_code == 401
