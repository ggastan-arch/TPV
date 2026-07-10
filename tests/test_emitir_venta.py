"""Caso de uso EmitirVenta (capa de aplicacion), probado sin HTTP."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.emitir_venta import (
    EmitirVenta,
    PagoVenta,
    TicketVacio,
    UsuarioNoValido,
)
from app.aplicacion.lineas import ArticuloNoExiste, ItemVenta
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import Articulo, RegistroFiscal, Venta


def _uc(session, motor):
    return EmitirVenta(UnidadDeTrabajoSQL(session), motor)


@pytest.fixture
def articulo_neon(session, datos_base):
    a = Articulo(nombre="Neon cardenal", nombre_corto="Neon",
                 tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
    session.add(a)
    session.commit()
    return a.id


def test_emitir_venta_emite_y_encadena(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("2"))],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )
    assert resultado.num_serie.startswith("T")
    assert resultado.total == "5.00"
    assert resultado.cambio == "5.00"

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.estado == "cobrada"
        assert s.query(RegistroFiscal).filter_by(venta_id=venta.id).count() == 1


def test_ticket_vacio(crear_sesion, motor, datos_base):
    with crear_sesion() as s, pytest.raises(TicketVacio):
        _uc(s, motor).ejecutar(usuario_id=datos_base["usuario_id"], items=[], pagos=[])


def test_usuario_no_valido(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s, pytest.raises(UsuarioNoValido):
        _uc(s, motor).ejecutar(
            usuario_id=999999, items=[ItemVenta(articulo_id=articulo_neon)], pagos=[])


def test_articulo_inexistente(crear_sesion, motor, datos_base):
    with crear_sesion() as s, pytest.raises(ArticuloNoExiste):
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"], items=[ItemVenta(articulo_id=999999)], pagos=[])
