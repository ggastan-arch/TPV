"""El XML de RegistroAlta/RegistroAnulacion valida contra el XSD oficial de la AEAT."""
from __future__ import annotations

from _helpers import construir_venta
from app.fiscal import validacion
from app.fiscal.xml import (
    registro_alta_xml,
    registro_anulacion_xml,
    sistema_desde_settings,
)
from app.models import RegistroFacturaSustituida, RegistroFiscal

SISTEMA = sistema_desde_settings()
EMISOR = "Bizkaitropik"


def _emitir(crear_sesion, motor, usuario_id, lineas, **kw) -> int:
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, lineas)
        s.add(venta)
        reg = motor.emit(s, venta, **kw)
        return reg.id


def test_registro_alta_valida_contra_xsd(crear_sesion, motor, datos_base):
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"],
        [("Neon cardenal", "2.50", "2", "21"), ("Anubias", "6.90", "1", "10")],
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        xml = registro_alta_xml(reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None)
        assert reg.primer_registro is True
        assert validacion.errores(xml) == []


def test_segunda_alta_encadenada_valida_contra_xsd(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
    reg2_id = _emitir(crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
    with crear_sesion() as s:
        reg2 = s.get(RegistroFiscal, reg2_id)
        anterior = s.get(RegistroFiscal, reg2.registro_anterior_id)
        xml = registro_alta_xml(reg2, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=anterior)
        assert reg2.primer_registro is False
        assert validacion.errores(xml) == []


def test_registro_anulacion_valida_contra_xsd(crear_sesion, motor, datos_base):
    reg_id = _emitir(crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
    with crear_sesion() as s, s.begin():
        anulacion = motor.cancel(s, s.get(RegistroFiscal, reg_id))
        anulacion_id = anulacion.id
    with crear_sesion() as s:
        anulacion = s.get(RegistroFiscal, anulacion_id)
        anterior = s.get(RegistroFiscal, anulacion.registro_anterior_id)
        xml = registro_anulacion_xml(anulacion, sistema=SISTEMA, anterior=anterior)
        assert validacion.errores(xml) == []


def test_alta_f3_con_facturas_sustituidas_valida_contra_xsd(crear_sesion, motor, datos_base):
    ejercicio = datos_base["ejercicio"]
    # F2 simplificada a sustituir.
    f2_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "2", "21")],
        serie="T", ejercicio=ejercicio, tipo_factura="F2",
    )
    # F3 en sustitucion, con su bloque FacturasSustituidas.
    with crear_sesion() as s, s.begin():
        f2reg = s.query(RegistroFiscal).filter_by(venta_id=f2_id).one()
        f3 = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "2", "21")])
        s.add(f3)
        reg_f3 = motor.emit(s, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
        s.add(RegistroFacturaSustituida(
            registro_fiscal_id=reg_f3.id,
            id_emisor=f2reg.id_emisor,
            num_serie_factura=f2reg.num_serie_factura,
            fecha_expedicion=f2reg.fecha_expedicion,
        ))
        reg_f3_id = reg_f3.id

    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_f3_id)
        anterior = s.get(RegistroFiscal, reg.registro_anterior_id)
        xml = registro_alta_xml(reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=anterior)
        assert reg.tipo_factura == "F3"
        assert len(reg.facturas_sustituidas) == 1
        assert validacion.errores(xml) == []
