"""Casos de uso de mantenimiento de clientes (maestro con datos personales).

Reglas: el NIF es opcional (la simplificada no lo exige), pero si se aporta debe ser un
documento valido y se almacena normalizado; nunca hard-delete (el derecho de supresion
RGPD cede ante la obligacion de conservacion fiscal de las ventas asociadas): solo
activo=false."""
from __future__ import annotations

import pytest

from app.aplicacion.clientes import (
    ClienteNoEncontrado,
    DatosCliente,
    NifInvalido,
    ServicioClientes,
)
from app.infraestructura.persistencia.modelos import Cliente, LogAuditoria
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _svc(session, datos_base):
    return ServicioClientes(
        UnidadDeTrabajoSQL(session), usuario_id=datos_base["usuario_id"], origen="local")


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def test_crear_cliente_sin_nif_ok(crear_sesion, datos_base):
    with crear_sesion() as s:
        cliente_id = _svc(s, datos_base).crear(DatosCliente(nombre="Cliente de paso"))
    with crear_sesion() as s:
        cliente = s.get(Cliente, cliente_id)
        assert cliente is not None and cliente.nif is None and cliente.activo is True
    assert len(_auditorias(crear_sesion, "crear_cliente")) == 1


def test_crear_cliente_con_nif_valido_se_normaliza(crear_sesion, datos_base):
    with crear_sesion() as s:
        cliente_id = _svc(s, datos_base).crear(
            DatosCliente(nombre="Acuario S.L.", nif=" a58818501 "))
    with crear_sesion() as s:
        assert s.get(Cliente, cliente_id).nif == "A58818501"  # normalizado


def test_crear_cliente_nif_invalido_falla_y_no_persiste(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(NifInvalido):
            _svc(s, datos_base).crear(DatosCliente(nombre="Malo", nif="12345678A"))
    with crear_sesion() as s:
        assert s.query(Cliente).count() == 0


def test_actualizar_cliente_ok_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        cliente_id = _svc(s, datos_base).crear(DatosCliente(nombre="Ana"))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(
            cliente_id, DatosCliente(nombre="Ana Garcia", nif="12345678Z",
                                     rgpd_consentimiento=True))
    with crear_sesion() as s:
        cliente = s.get(Cliente, cliente_id)
        assert cliente.nombre == "Ana Garcia"
        assert cliente.nif == "12345678Z"
        assert cliente.rgpd_consentimiento is True
    assert len(_auditorias(crear_sesion, "actualizar_cliente")) == 1


def test_actualizar_nif_invalido_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        cliente_id = _svc(s, datos_base).crear(DatosCliente(nombre="Ana"))
    with crear_sesion() as s:
        with pytest.raises(NifInvalido):
            _svc(s, datos_base).actualizar(cliente_id, DatosCliente(nombre="Ana", nif="X1234567Z"))


def test_actualizar_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(ClienteNoEncontrado):
            _svc(s, datos_base).actualizar(999999, DatosCliente(nombre="X"))


def test_desactivar_no_borra(crear_sesion, datos_base):
    with crear_sesion() as s:
        cliente_id = _svc(s, datos_base).crear(DatosCliente(nombre="Temporal"))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(cliente_id)
    with crear_sesion() as s:
        cliente = s.get(Cliente, cliente_id)
        assert cliente is not None and cliente.activo is False
    assert len(_auditorias(crear_sesion, "desactivar_cliente")) == 1


# --- Repositorio: busqueda por NIF / nombre (cliente-en-venta, mirror de
# RepositorioArticulosSQL.buscar_por_nombre, ver repositorios.py:70-90) -------


def test_repositorio_clientes_buscar_por_nif_exacto_normalizado(crear_sesion, datos_base):
    with crear_sesion() as s:
        _svc(s, datos_base).crear(DatosCliente(nombre="Acuario S.L.", nif=" a58818501 "))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).clientes
        encontrado = repo.buscar_por_nif("A58818501")
        assert encontrado is not None and encontrado.nombre == "Acuario S.L."
        # Tambien acepta el valor sin normalizar de entrada (normaliza antes de comparar).
        assert repo.buscar_por_nif(" a58818501 ") is not None
        assert repo.buscar_por_nif("00000000T") is None


def test_repositorio_clientes_buscar_por_nombre_subcadena_case_insensitive(crear_sesion, datos_base):
    with crear_sesion() as s:
        _svc(s, datos_base).crear(DatosCliente(nombre="Juan Perez"))
        _svc(s, datos_base).crear(DatosCliente(nombre="Maria Garcia"))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).clientes
        resultado = repo.buscar_por_nombre("perez")
        assert [c.nombre for c in resultado] == ["Juan Perez"]
        assert repo.buscar_por_nombre("PEREZ") != []


def test_repositorio_clientes_buscar_por_nombre_excluye_inactivos(crear_sesion, datos_base):
    with crear_sesion() as s:
        activo_id = _svc(s, datos_base).crear(DatosCliente(nombre="Cliente activo"))
        inactivo_id = _svc(s, datos_base).crear(DatosCliente(nombre="Cliente inactivo"))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(inactivo_id)

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).clientes
        resultado = repo.buscar_por_nombre("cliente")
        assert [c.id for c in resultado] == [activo_id]


def test_repositorio_clientes_buscar_por_nombre_query_corta_devuelve_vacio(crear_sesion, datos_base):
    with crear_sesion() as s:
        _svc(s, datos_base).crear(DatosCliente(nombre="Juan Perez"))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).clientes
        assert repo.buscar_por_nombre("") == []
        assert repo.buscar_por_nombre("a") == []
