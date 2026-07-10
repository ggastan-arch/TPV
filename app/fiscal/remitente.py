"""Transporte SOAP hacia el servicio VERI*FACTU de la AEAT.

Operacion `RegFactuSistemaFacturacion` (SOAP 1.1 document/literal) del WSDL
SistemaFacturacion.wsdl. El cuerpo SOAP es directamente el sobre
RegFactuSistemaFacturacion (ya construido y validado por app.fiscal.xml). La respuesta
es RespuestaRegFactuSistemaFacturacion (RespuestaSuministro.xsd).

El certificado de la titular (mutual-TLS) y el envio HTTP son INYECTABLES:
- `cert`: lo que acepte requests (ruta a PEM, o (cert, key)). Nunca sale del servidor.
- `poster`: callable(url, headers, body) -> (status, body_bytes). Por defecto usa
  requests; en tests se inyecta uno simulado y NO hace falta ni red ni certificado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from app.core.config import settings
from app.fiscal.xml import NS as NS_SF

SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_RESP = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd"
)

# Endpoints del WSDL (sistemas que emiten facturas verificables).
_ENDPOINTS = {
    ("pruebas", False): "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    ("pruebas", True): "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    ("produccion", False): "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    ("produccion", True): "https://www10.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
}

# EstadoRegistro de la AEAT -> resultado interno de la cola.
_ESTADO_A_RESULTADO = {
    "Correcto": "aceptado",
    "AceptadoConErrores": "aceptado_con_errores",
    "Incorrecto": "rechazado",
}


def endpoint_verifactu(entorno: str, *, sello: bool = False) -> str:
    return _ENDPOINTS[(entorno, sello)]


class RemisionError(Exception):
    """Error de remision no recuperable (SOAP Fault, respuesta HTTP inesperada)."""


class RemisionIncidencia(Exception):
    """Incidencia de conectividad: reintentar respetando el orden temporal (art. 17)."""


@dataclass
class ResultadoLinea:
    num_serie_factura: str
    resultado: str  # aceptado | aceptado_con_errores | rechazado
    codigo_error: str | None = None
    descripcion: str | None = None


@dataclass
class RespuestaEnvio:
    csv: str | None
    tiempo_espera_segundos: int
    estado_envio: str  # Correcto | ParcialmenteCorrecto | Incorrecto
    lineas: list[ResultadoLinea] = field(default_factory=list)


class Remitente:
    """Contrato del transporte: envelope (bytes) -> RespuestaEnvio."""

    def enviar(self, envelope: bytes) -> RespuestaEnvio:  # pragma: no cover
        raise NotImplementedError


def _poster_requests(cert, verify, timeout):
    def poster(url: str, headers: dict, body: bytes):
        import requests

        try:
            resp = requests.post(
                url, data=body, headers=headers, cert=cert, verify=verify, timeout=timeout
            )
        except requests.exceptions.RequestException as exc:  # red/timeout/TLS
            raise RemisionIncidencia(str(exc)) from exc
        return resp.status_code, resp.content

    return poster


class RemitenteVerifactu(Remitente):
    def __init__(
        self,
        *,
        endpoint: str,
        cert=None,
        verify=True,
        timeout: int = 60,
        poster=None,
    ):
        self.endpoint = endpoint
        self._poster = poster or _poster_requests(cert, verify, timeout)

    def enviar(self, envelope: bytes) -> RespuestaEnvio:
        cuerpo = _envolver_soap(envelope)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}
        estado, contenido = self._poster(self.endpoint, headers, cuerpo)
        if estado != 200:
            # 200 con EstadoEnvio=Incorrecto sigue siendo respuesta valida a parsear;
            # un codigo != 200 es un fallo del servicio (o SOAP Fault).
            _lanzar_fault(contenido, estado)
        return _parsear_respuesta(contenido)


class RemitenteSimulado(Remitente):
    """Transporte de desarrollo: devuelve una RespuestaEnvio fija. No remite nada."""

    def __init__(self, respuesta: RespuestaEnvio):
        self._respuesta = respuesta

    def enviar(self, envelope: bytes) -> RespuestaEnvio:
        return self._respuesta


def remitente_desde_settings(*, poster=None) -> RemitenteVerifactu:
    """Construye el remitente segun la config. Sin certificado configurado el objeto
    queda listo, pero la AEAT rechazara el TLS hasta que se aporte el certificado."""
    cert = None
    if settings.certificado_cert_path and settings.certificado_key_path:
        cert = (settings.certificado_cert_path, settings.certificado_key_path)
    elif settings.certificado_cert_path:
        cert = settings.certificado_cert_path
    return RemitenteVerifactu(
        endpoint=endpoint_verifactu(settings.entorno_aeat, sello=settings.certificado_sello),
        cert=cert,
        poster=poster,
    )


# --- helpers de (de)serializacion SOAP -----------------------------------------
def _envolver_soap(cuerpo: bytes) -> bytes:
    contenido = etree.fromstring(cuerpo)
    env = etree.Element(etree.QName(SOAP, "Envelope"), nsmap={"soapenv": SOAP})
    body = etree.SubElement(env, etree.QName(SOAP, "Body"))
    body.append(contenido)
    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def _lanzar_fault(contenido: bytes, estado: int) -> None:
    try:
        root = etree.fromstring(contenido)
        fault = root.find(f".//{{{SOAP}}}Fault")
        if fault is not None:
            mensaje = fault.findtext("faultstring") or etree.tostring(fault, encoding="unicode")
            raise RemisionError(f"SOAP Fault: {mensaje}")
    except etree.XMLSyntaxError:
        pass
    raise RemisionError(f"Respuesta HTTP {estado} inesperada de la AEAT")


def _texto(elemento, tag_ns: str) -> str | None:
    hijo = elemento.find(tag_ns)
    return hijo.text if hijo is not None else None


def _parsear_respuesta(contenido: bytes) -> RespuestaEnvio:
    root = etree.fromstring(contenido)
    if root.find(f".//{{{SOAP}}}Fault") is not None:
        _lanzar_fault(contenido, 200)

    resp = root.find(f".//{{{NS_RESP}}}RespuestaRegFactuSistemaFacturacion")
    if resp is None:
        raise RemisionError("Respuesta sin RespuestaRegFactuSistemaFacturacion")

    csv = _texto(resp, f"{{{NS_RESP}}}CSV")
    tiempo = int(_texto(resp, f"{{{NS_RESP}}}TiempoEsperaEnvio") or 0)
    estado_envio = _texto(resp, f"{{{NS_RESP}}}EstadoEnvio") or ""

    lineas: list[ResultadoLinea] = []
    for ln in resp.findall(f"{{{NS_RESP}}}RespuestaLinea"):
        idf = ln.find(f"{{{NS_SF}}}IDFactura")
        num_serie = idf.find(f"{{{NS_SF}}}NumSerieFactura").text if idf is not None else None
        estado_reg = ln.find(f"{{{NS_RESP}}}EstadoRegistro").text
        lineas.append(
            ResultadoLinea(
                num_serie_factura=num_serie,
                resultado=_ESTADO_A_RESULTADO.get(estado_reg, "rechazado"),
                codigo_error=_texto(ln, f"{{{NS_RESP}}}CodigoErrorRegistro"),
                descripcion=_texto(ln, f"{{{NS_RESP}}}DescripcionErrorRegistro"),
            )
        )
    return RespuestaEnvio(
        csv=csv, tiempo_espera_segundos=tiempo, estado_envio=estado_envio, lineas=lineas
    )
