"""Validaciones de negocio previas a la remision."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from _helpers import construir_venta
from app.infraestructura.config import settings
from app.dominio.servicios import validaciones_negocio as vn
from app.infraestructura.fiscal.xml import sistema_desde_settings
from app.infraestructura.persistencia.modelos import RegistroFiscal

AHORA = datetime.fromisoformat("2026-07-10T23:59:00+02:00")
SISTEMA_OK = SimpleNamespace(id_sistema="BZ", nombre_sistema="TPV", solo_verifactu="S", multi_ot="N")


def _det(tipo, base, cuota):
    return SimpleNamespace(tipo_impositivo=str(tipo), base_imponible=str(base),
                           cuota_repercutida=str(cuota), impuesto="01",
                           clave_regimen="01", calificacion="S1")


def _reg(**kw):
    base = dict(
        tipo_registro="alta", tipo_factura="F2", id_emisor="00000000T",
        num_serie_factura="T2026-000001", fecha_expedicion="10-07-2026",
        cuota_total="1.50", importe_total="11.90", huella="A" * 64,
        huella_anterior=None, primer_registro=True, orden=1,
        fecha_hora_huso_gen_registro="2026-07-10T10:00:00+02:00",
        facturas_sustituidas=[], desglose=[_det("21", "4.13", "0.87"), _det("10", "6.27", "0.63")],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _codigos(incs):
    return {i.codigo for i in incs}


def test_alta_bien_formada_sin_incidencias():
    inc = vn.validar_alta(_reg(), nif_obligado="00000000T", sistema=SISTEMA_OK, ahora=AHORA)
    assert inc == []
    assert vn.hay_rechazos(inc) is False


def test_f2_supera_limite_3000():
    reg = _reg(desglose=[_det("21", "3000", "630")], cuota_total="630", importe_total="3630")
    inc = vn.validar_alta(reg, nif_obligado="00000000T", sistema=SISTEMA_OK, ahora=AHORA)
    assert "F2_LIMITE_3000" in _codigos(inc)
    assert vn.hay_rechazos(inc)


def test_tipo_impositivo_no_permitido():
    reg = _reg(desglose=[_det("13", "100", "13")], cuota_total="13", importe_total="113")
    inc = vn.validar_alta(reg, nif_obligado="00000000T", sistema=SISTEMA_OK, ahora=AHORA)
    assert "TIPO_IMPOSITIVO_NO_PERMITIDO" in _codigos(inc)


def test_nif_emisor_distinto_del_obligado():
    reg = _reg(id_emisor="12345678Z")  # NIF valido pero != obligado
    inc = vn.validar_alta(reg, nif_obligado="00000000T", sistema=SISTEMA_OK, ahora=AHORA)
    assert "NIF_EMISOR_DISTINTO" in _codigos(inc)


def test_numserie_con_caracteres_prohibidos():
    reg = _reg(num_serie_factura="T=2026")
    inc = vn.validar_alta(reg, nif_obligado="00000000T", sistema=SISTEMA_OK, ahora=AHORA)
    assert "NUMSERIE_CARACTERES" in _codigos(inc)


def test_fecha_expedicion_futura():
    reg = _reg(fecha_expedicion="31-12-2027")
    inc = vn.validar_alta(reg, nif_obligado="00000000T", sistema=SISTEMA_OK, ahora=AHORA)
    assert "FECHA_FUTURA" in _codigos(inc)


def test_id_sistema_mal_formado_es_rechazo():
    sistema = SimpleNamespace(id_sistema="BZX", nombre_sistema="TPV", solo_verifactu="S", multi_ot="N")
    inc = vn.validar_alta(_reg(), nif_obligado="00000000T", sistema=sistema, ahora=AHORA)
    assert "IDSISTEMA_FORMATO" in _codigos(inc)
    assert vn.hay_rechazos(inc)


def test_f2_con_destinatario_rechaza():
    inc = vn.validar_alta(_reg(), nif_obligado="00000000T", sistema=SISTEMA_OK,
                          ahora=AHORA, tiene_destinatario=True)
    assert "DESTINATARIO_NO_PERMITIDO" in _codigos(inc)


def test_f3_sin_destinatario_rechaza():
    reg = _reg(tipo_factura="F3")
    inc = vn.validar_alta(reg, nif_obligado="00000000T", sistema=SISTEMA_OK,
                          ahora=AHORA, tiene_destinatario=False)
    assert "FALTA_DESTINATARIO" in _codigos(inc)


def test_registro_real_emitido_pasa_las_validaciones(crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"],
                                [("Neon", "2.50", "2", "21"), ("Anubias", "6.90", "1", "10")])
        s.add(venta)
        reg = motor.emit(s, venta)
        reg_id = reg.id
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        inc = vn.validar_registro(
            reg, nif_obligado=settings.nif_emisor, sistema=sistema_desde_settings(),
        )
        assert not vn.hay_rechazos(inc), inc
        assert inc == []
