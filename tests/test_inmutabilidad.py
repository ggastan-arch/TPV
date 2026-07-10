"""(a) Los triggers rechazan modificar/borrar una venta emitida y su registro fiscal."""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import RegistroFiscal, Venta


def _emitir(crear_sesion, motor, usuario_id) -> int:
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, [("Neon cardenal", "2.50", "2", "21")])
        s.add(venta)
        motor.emit(s, venta)
        venta_id = venta.id
    return venta_id


def test_no_se_puede_modificar_importe_de_venta_emitida(crear_sesion, motor, datos_base):
    venta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        assert venta.estado == "cobrada"
        venta.total_con_iva = Decimal("999.99")
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_venta_emitida(crear_sesion, motor, datos_base):
    venta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        s.delete(venta)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_modificar_huella_del_registro(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        registro = s.query(RegistroFiscal).one()
        registro.huella = "0" * 64
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_registro_fiscal(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        registro = s.query(RegistroFiscal).one()
        s.delete(registro)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_estado_remision_si_es_editable(crear_sesion, motor, datos_base):
    # El metadato de envio NO forma parte de la huella: debe poder actualizarse.
    _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s, s.begin():
        registro = s.query(RegistroFiscal).one()
        registro.estado_remision = "aceptado"
    with crear_sesion() as s:
        assert s.query(RegistroFiscal).one().estado_remision == "aceptado"


def test_venta_aparcada_si_es_editable(crear_sesion, datos_base):
    # Una venta aun no emitida (aparcada) SI puede modificarse y borrarse.
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Anubias", "6.90", "1", "10")])
        s.add(venta)
        s.flush()
        venta_id = venta.id
    with crear_sesion() as s, s.begin():
        venta = s.get(Venta, venta_id)
        venta.total_con_iva = Decimal("7.00")  # permitido: sigue aparcada
    with crear_sesion() as s, s.begin():
        venta = s.get(Venta, venta_id)
        s.delete(venta)  # permitido
