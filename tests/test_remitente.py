"""Cliente SOAP VERI*FACTU: envoltura del sobre y parseo de la respuesta.

Todo con `poster` inyectado: ni red ni certificado. El flujo cola->envio esta en
test_remision.py (caso de uso RemitirLote)."""
from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from _helpers import respuesta_remision_xml
from app.infraestructura.fiscal.remitente import (
    RemisionError,
    RemisionIncidencia,
    RemitenteVerifactu,
    endpoint_verifactu,
    remitente_desde_settings,
)
from app.infraestructura.fiscal.xml import NS, NS_LR

_GOLDEN = Path(__file__).parent / "golden"
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


# --- Duplicado (codigo 3000 + RegistroDuplicado) --------------------------------
def test_parsea_duplicado_correcta_es_aceptado():
    def poster(url, headers, body):
        return 200, respuesta_remision_xml(
            [("T2026-000001", "Incorrecto", 3000, "Registro duplicado",
              {"estado": "Correcta"})],
            estado="ParcialmenteCorrecto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)
    assert len(resp.lineas) == 1
    linea = resp.lineas[0]
    assert linea.resultado == "aceptado"
    assert linea.duplicado is True
    assert linea.estado_final is None


def test_parsea_duplicado_aceptada_con_errores():
    def poster(url, headers, body):
        return 200, respuesta_remision_xml(
            [("T2026-000001", "Incorrecto", 3000, "Registro duplicado",
              {"estado": "AceptadaConErrores"})],
            estado="ParcialmenteCorrecto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)
    linea = resp.lineas[0]
    assert linea.resultado == "aceptado_con_errores"
    assert linea.duplicado is True


def test_parsea_duplicado_anulada_requiere_intervencion():
    def poster(url, headers, body):
        return 200, respuesta_remision_xml(
            [("T2026-000001", "Incorrecto", 3000, "Registro duplicado",
              {"estado": "Anulada"})],
            estado="ParcialmenteCorrecto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)
    linea = resp.lineas[0]
    assert linea.resultado == "rechazado"
    assert linea.duplicado is True
    assert linea.estado_final == "requiere_intervencion"


# --- Captura de la respuesta cruda de la AEAT (depuracion / golden tests) --------
def test_captura_peticion_y_respuesta_crudas(tmp_path):
    resp_bytes = respuesta_remision_xml([("T2026-000001", "Correcto", None, None)],
                                        csv="ABC123")

    def poster(url, headers, body):
        return 200, resp_bytes

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster,
                             captura_dir=str(tmp_path))
    rem.enviar(_ENVELOPE_MIN)

    ficheros = list(tmp_path.iterdir())
    respuestas = [f for f in ficheros if "respuesta" in f.name]
    peticiones = [f for f in ficheros if "peticion" in f.name]
    assert len(respuestas) == 1
    assert len(peticiones) == 1
    # Los bytes se guardan crudos, sin reparsear: es lo que hace fiable el golden test.
    assert respuestas[0].read_bytes() == resp_bytes


def test_captura_fallida_no_rompe_remision(tmp_path):
    # captura_dir imposible de crear (su padre es un fichero): la captura es best-effort
    # y JAMAS puede tumbar la remision fiscal.
    ocupado = tmp_path / "ocupado"
    ocupado.write_text("no soy un directorio")
    resp_bytes = respuesta_remision_xml([("T2026-000001", "Correcto", None, None)], csv="OK")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"),
                             poster=lambda u, h, b: (200, resp_bytes),
                             captura_dir=str(ocupado / "sub"))
    resp = rem.enviar(_ENVELOPE_MIN)
    assert resp.csv == "OK"


# --- Golden test: respuesta REAL de la AEAT (sanitizada) -------------------------
# Reproduce el layout real (prefijos tikR/tik, IDFactura en NS_RESP con hijos en NS_SF,
# RegistroDuplicado en NS_RESP con hijos en NS_SF) que los fixtures sinteticos NO
# reproducian y que dejo escapar el bug de namespaces cruzados. Es el candado de regresion.
def test_golden_respuesta_real_aeat_duplicados_mixta():
    crudo = (_GOLDEN / "respuesta_aeat_duplicados_mixta.xml").read_bytes()

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"),
                             poster=lambda u, h, b: (200, crudo))
    resp = rem.enviar(_ENVELOPE_MIN)

    assert resp.csv == "CSV-GOLDEN-PRUEBA"
    assert resp.estado_envio == "ParcialmenteCorrecto"
    assert resp.tiempo_espera_segundos == 60

    por_num = {ln.num_serie_factura: ln for ln in resp.lineas}
    # Las 4 series se leyeron (num_serie None era el sintoma del bug: no casaba en RemitirLote).
    assert set(por_num) == {"T2026-000001", "T2026-000002", "T2026-000003", "T2026-000004"}

    # Duplicado AceptadaConErrores -> aceptado_con_errores; el codigo de linea (3000) es el
    # que se persiste, no el interno del bloque duplicado (2004).
    assert por_num["T2026-000001"].resultado == "aceptado_con_errores"
    assert por_num["T2026-000001"].duplicado is True
    assert por_num["T2026-000001"].codigo_error == "3000"

    # Duplicado Correcta -> aceptado.
    assert por_num["T2026-000002"].resultado == "aceptado"
    assert por_num["T2026-000002"].duplicado is True
    assert por_num["T2026-000003"].resultado == "aceptado"
    assert por_num["T2026-000003"].duplicado is True

    # Alta nueva EstadoRegistro=Correcto -> aceptado, sin bloque duplicado.
    assert por_num["T2026-000004"].resultado == "aceptado"
    assert por_num["T2026-000004"].duplicado is False


# --- Rechazo de cabecera (sin lineas) --------------------------------------------
def test_parsea_rechazo_de_cabecera_sin_lineas():
    def poster(url, headers, body):
        return 200, respuesta_remision_xml([], estado="Incorrecto")

    rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
    resp = rem.enviar(_ENVELOPE_MIN)
    assert resp.lineas == []
    assert resp.estado_envio == "Incorrecto"
    assert resp.descripcion_cabecera is not None
    assert "Incorrecto" in resp.descripcion_cabecera
