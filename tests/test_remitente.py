"""Cliente SOAP VERI*FACTU: envoltura del sobre y parseo de la respuesta.

Todo con `poster` inyectado: ni red ni certificado. El flujo cola->envio esta en
test_remision.py (caso de uso RemitirLote)."""
from __future__ import annotations

import pytest
from lxml import etree

from _helpers import respuesta_remision_xml
from app.fiscal.remitente import (
    RemisionError,
    RemisionIncidencia,
    RemitenteVerifactu,
    endpoint_verifactu,
    remitente_desde_settings,
)
from app.fiscal.xml import NS, NS_LR

_E_SOAP = "{http://schemas.xmlsoap.org/soap/envelope/}"
_ENVELOPE_MIN = ('<?xml version="1.0"?>'
                 f'<sfLR:RegFactuSistemaFacturacion xmlns:sfLR="{NS_LR}"/>').encode()


def test_enviar_construye_soap_y_parsea_respuesta():
    captura = {}

    def poster(url, headers, body):
        captura.update(url=url, headers=headers, body=body)
        return 200, respuesta_remision_xml([("T2026-000001", "Correcto", None, None)],
                                           csv="ABC123", tiempo=63, estado="Correcto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)

    assert captura["url"].endswith("/VerifactuSOAP")
    assert captura["headers"]["Content-Type"].startswith("text/xml")
    enviado = etree.fromstring(captura["body"])
    assert enviado.tag == _E_SOAP + "Envelope"
    assert enviado.find(f"{_E_SOAP}Body/{{{NS_LR}}}RegFactuSistemaFacturacion") is not None

    assert resp.csv == "ABC123"
    assert resp.tiempo_espera_segundos == 63
    assert resp.estado_envio == "Correcto"
    assert len(resp.lineas) == 1
    assert resp.lineas[0].num_serie_factura == "T2026-000001"
    assert resp.lineas[0].resultado == "aceptado"


def test_parsea_resultados_mixtos():
    def poster(url, headers, body):
        return 200, respuesta_remision_xml(
            [("T2026-000001", "Correcto", None, None),
             ("T2026-000002", "Incorrecto", 4102, "Error de ejemplo")],
            estado="ParcialmenteCorrecto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)
    por_num = {ln.num_serie_factura: ln for ln in resp.lineas}
    assert por_num["T2026-000001"].resultado == "aceptado"
    assert por_num["T2026-000002"].resultado == "rechazado"
    assert por_num["T2026-000002"].codigo_error == "4102"


def test_soap_fault_lanza_remision_error():
    fault = ('<?xml version="1.0"?><soapenv:Envelope '
             'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
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
