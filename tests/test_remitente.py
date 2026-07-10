"""Cliente SOAP VERI*FACTU: envoltura, parseo de respuesta y flujo con la cola.

Todo con `poster` inyectado: ni red ni certificado. El dia que haya certificado solo
se configura (certificado_cert_path / entorno_aeat)."""
from __future__ import annotations

import pytest
from lxml import etree

from _helpers import construir_venta
from app.fiscal.cola import ColaRemision
from app.fiscal.remitente import (
    RemisionError,
    RemisionIncidencia,
    RemitenteVerifactu,
    endpoint_verifactu,
    remitente_desde_settings,
)
from app.fiscal.xml import NS, NS_LR
from app.models import RegistroFiscal, RemisionIntento

_E_RESP = "{%s}" % (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd"
)
_E_SF = "{%s}" % NS
_E_SOAP = "{%s}" % "http://schemas.xmlsoap.org/soap/envelope/"

_ENVELOPE_MIN = ('<?xml version="1.0"?>'
                 f'<sfLR:RegFactuSistemaFacturacion xmlns:sfLR="{NS_LR}"/>').encode()


def _respuesta_xml(lineas, *, csv="CSV-OK", tiempo=60, estado="Correcto") -> bytes:
    env = etree.Element(_E_SOAP + "Envelope")
    body = etree.SubElement(env, _E_SOAP + "Body")
    resp = etree.SubElement(body, _E_RESP + "RespuestaRegFactuSistemaFacturacion")
    if csv is not None:
        etree.SubElement(resp, _E_RESP + "CSV").text = csv
    etree.SubElement(resp, _E_RESP + "TiempoEsperaEnvio").text = str(tiempo)
    etree.SubElement(resp, _E_RESP + "EstadoEnvio").text = estado
    for num, estado_reg, codigo, desc in lineas:
        ln = etree.SubElement(resp, _E_RESP + "RespuestaLinea")
        idf = etree.SubElement(ln, _E_SF + "IDFactura")
        etree.SubElement(idf, _E_SF + "IDEmisorFactura").text = "00000000T"
        etree.SubElement(idf, _E_SF + "NumSerieFactura").text = num
        etree.SubElement(idf, _E_SF + "FechaExpedicionFactura").text = "10-07-2026"
        etree.SubElement(ln, _E_RESP + "EstadoRegistro").text = estado_reg
        if codigo is not None:
            etree.SubElement(ln, _E_RESP + "CodigoErrorRegistro").text = str(codigo)
        if desc is not None:
            etree.SubElement(ln, _E_RESP + "DescripcionErrorRegistro").text = desc
    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def _emitir(crear_sesion, motor, usuario_id, n):
    ids = []
    for _ in range(n):
        with crear_sesion() as s, s.begin():
            venta = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
            s.add(venta)
            ids.append(motor.emit(s, venta).id)
    return ids


def test_enviar_construye_soap_y_parsea_respuesta():
    captura = {}

    def poster(url, headers, body):
        captura.update(url=url, headers=headers, body=body)
        return 200, _respuesta_xml([("T2026-000001", "Correcto", None, None)],
                                   csv="ABC123", tiempo=63, estado="Correcto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)

    # Peticion: SOAP 1.1 con el sobre dentro del Body.
    assert captura["url"].endswith("/VerifactuSOAP")
    assert captura["headers"]["Content-Type"].startswith("text/xml")
    enviado = etree.fromstring(captura["body"])
    assert enviado.tag == _E_SOAP + "Envelope"
    assert enviado.find(f"{_E_SOAP}Body/{{{NS_LR}}}RegFactuSistemaFacturacion") is not None

    # Respuesta parseada.
    assert resp.csv == "ABC123"
    assert resp.tiempo_espera_segundos == 63
    assert resp.estado_envio == "Correcto"
    assert len(resp.lineas) == 1
    assert resp.lineas[0].num_serie_factura == "T2026-000001"
    assert resp.lineas[0].resultado == "aceptado"


def test_parsea_resultados_mixtos():
    def poster(url, headers, body):
        return 200, _respuesta_xml(
            [("T2026-000001", "Correcto", None, None),
             ("T2026-000002", "Incorrecto", 4102, "Error de ejemplo")],
            estado="ParcialmenteCorrecto",
        )

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)
    por_num = {ln.num_serie_factura: ln for ln in resp.lineas}
    assert por_num["T2026-000001"].resultado == "aceptado"
    assert por_num["T2026-000002"].resultado == "rechazado"
    assert por_num["T2026-000002"].codigo_error == "4102"


def test_soap_fault_lanza_remision_error():
    fault = (f'<?xml version="1.0"?><soapenv:Envelope xmlns:soapenv="{_E_SOAP[1:-1]}">'
             "<soapenv:Body><soapenv:Fault><faultstring>Cabecera invalida</faultstring>"
             "</soapenv:Fault></soapenv:Body></soapenv:Envelope>").encode()

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"),
                             poster=lambda u, h, b: (500, fault))
    with pytest.raises(RemisionError):
        rem.enviar(_ENVELOPE_MIN)


def test_incidencia_de_red_se_propaga():
    def poster(url, headers, body):
        raise RemisionIncidencia("sin conexion")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    with pytest.raises(RemisionIncidencia):
        rem.enviar(_ENVELOPE_MIN)


def test_remitente_desde_settings_usa_endpoint_pruebas():
    rem = remitente_desde_settings(poster=lambda u, h, b: (200, b""))
    assert rem.endpoint == "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"


def test_remitir_actualiza_estados_y_guarda_csv(crear_sesion, motor, datos_base):
    ids = _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)

    def poster(url, headers, body):
        # Responder "Correcto" para cada factura del sobre. El path IDFactura/NumSerieFactura
        # es preciso: excluye RegistroAnterior y FacturasSustituidas.
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, _respuesta_xml([(n, "Correcto", None, None) for n in nums], csv="CSV-LOTE")

    with crear_sesion() as s, s.begin():
        rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
        respuesta = ColaRemision(s).remitir(rem)
    assert respuesta is not None
    assert respuesta.csv == "CSV-LOTE"

    with crear_sesion() as s:
        cola = ColaRemision(s)
        assert cola.contar_pendientes() == 0
        for i in ids:
            assert s.get(RegistroFiscal, i).estado_remision == "aceptado"
        assert s.query(RemisionIntento).filter_by(csv="CSV-LOTE").count() == 2


def test_remitir_incidencia_deja_pendientes(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)

    def poster(url, headers, body):
        raise RemisionIncidencia("sin red")

    with crear_sesion() as s, s.begin():
        rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
        assert ColaRemision(s).remitir(rem) is None

    with crear_sesion() as s:
        cola = ColaRemision(s)
        assert cola.contar_pendientes() == 2
        assert cola.hay_incidencia_pendiente() is True
