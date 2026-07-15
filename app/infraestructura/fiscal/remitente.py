"""Transporte SOAP hacia el servicio VERI*FACTU de la AEAT.

Operacion `RegFactuSistemaFacturacion` (SOAP 1.1 document/literal) del WSDL
SistemaFacturacion.wsdl. El cuerpo SOAP es directamente el sobre
RegFactuSistemaFacturacion (ya construido y validado por app.infraestructura.fiscal.xml). La respuesta
es RespuestaRegFactuSistemaFacturacion (RespuestaSuministro.xsd).

El certificado de la persona titular (mutual-TLS) y el envio HTTP son INYECTABLES:
- `cert`: lo que acepte requests (ruta a PEM, o (cert, key)). Nunca sale del servidor.
- `poster`: callable(url, headers, body) -> (status, body_bytes). Por defecto usa
  requests; en tests se inyecta uno simulado y NO hace falta ni red ni certificado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from app.infraestructura.config import settings
from app.infraestructura.fiscal.xml import NS as NS_SF

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

# EstadoRegistroDuplicado (vocabulario propio, FEMENINO: Correcta/AceptadaConErrores/
# Anulada, XSD EstadoRegistroSFType) -> resultado interno cuando la AEAT rechaza el
# registro por duplicado (codigo 3000) porque ya existe dado de alta en su sistema.
# Tabla DEDICADA: mezclar con _ESTADO_A_RESULTADO (formas masculinas de linea normal)
# volveria a clasificar el duplicado como rechazado y reactivaria el bucle de reenvio.
_DUPLICADO_A_RESULTADO = {
    "Correcta": "aceptado",
    "AceptadaConErrores": "aceptado_con_errores",
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
    resultado: str  # CHECK-valid en remision_intento: aceptado|aceptado_con_errores|rechazado
    codigo_error: str | None = None
    descripcion: str | None = None
    # Override de registro_fiscal.estado_remision (None = derivar de `resultado`).
    # Solo se usa para el duplicado "Anulada": terminal anomalo, no reintentable,
    # que no cabe en el vocabulario CHECK de `resultado` (ver design.md).
    estado_final: str | None = None
    duplicado: bool = False  # True si la linea vino con bloque RegistroDuplicado (cod 3000)


@dataclass
class RespuestaEnvio:
    csv: str | None
    tiempo_espera_segundos: int
    estado_envio: str  # Correcto | ParcialmenteCorrecto | Incorrecto
    lineas: list[ResultadoLinea] = field(default_factory=list)
    # Rechazo de cabecera (EstadoEnvio=Incorrecto sin ninguna RespuestaLinea): el XSD
    # RespuestaBaseType no define un codigo de error a nivel de envio, por eso
    # `codigo_error_cabecera` normalmente queda en None y solo se rellena la
    # descripcion (ver design.md, Open Questions).
    codigo_error_cabecera: str | None = None
    descripcion_cabecera: str | None = None


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
        captura_dir: str | None = None,
    ):
        self.endpoint = endpoint
        self._poster = poster or _poster_requests(cert, verify, timeout)
        # Directorio opcional para volcar peticion/respuesta crudas (depuracion y
        # golden tests). None = desactivado. Nunca se escribe el certificado.
        self._captura_dir = captura_dir

    def enviar(self, envelope: bytes) -> RespuestaEnvio:
        cuerpo = _envolver_soap(envelope)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}
        estado, contenido = self._poster(self.endpoint, headers, cuerpo)
        if self._captura_dir:
            _capturar(self._captura_dir, cuerpo, contenido, estado)
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
        captura_dir=settings.captura_respuesta_dir,
    )


def _capturar(directorio: str, peticion: bytes, respuesta: bytes, estado: int) -> None:
    """Vuelca a disco el sobre enviado y la respuesta cruda de la AEAT, con timestamp.

    Best-effort e INTENCIONADAMENTE a prueba de fallos: cualquier excepcion se traga
    (la captura es una ayuda de depuracion y jamas puede afectar a la remision fiscal).
    Solo escribe XML de peticion/respuesta: nunca el certificado (invariante 7)."""
    try:
        import os
        from datetime import datetime

        os.makedirs(directorio, exist_ok=True)
        sello = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        base = os.path.join(directorio, f"aeat-{sello}")
        with open(f"{base}-peticion.xml", "wb") as fh:
            fh.write(peticion)
        with open(f"{base}-respuesta-http{estado}.xml", "wb") as fh:
            fh.write(respuesta)
    except Exception:  # noqa: BLE001 - best-effort: la captura nunca rompe la remision
        pass


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
        # IDFactura es un elemento LOCAL de RespuestaSuministro.xsd (NS_RESP); solo sus
        # hijos (IDFacturaExpedidaType) viven en SuministroInformacion.xsd (NS_SF). Buscarlo
        # en NS_SF devolvia None -> num_serie None -> el registro no casaba en RemitirLote y
        # quedaba como "no remitido" aunque la AEAT lo hubiera aceptado.
        idf = ln.find(f"{{{NS_RESP}}}IDFactura")
        num_serie = idf.find(f"{{{NS_SF}}}NumSerieFactura").text if idf is not None else None
        estado_reg = ln.find(f"{{{NS_RESP}}}EstadoRegistro").text
        codigo_error = _texto(ln, f"{{{NS_RESP}}}CodigoErrorRegistro")
        descripcion = _texto(ln, f"{{{NS_RESP}}}DescripcionErrorRegistro")
        lineas.append(_clasificar_linea(ln, num_serie, estado_reg, codigo_error, descripcion))

    codigo_error_cabecera = None
    descripcion_cabecera = None
    if not lineas and estado_envio == "Incorrecto":
        # Rechazo de cabecera: el XSD RespuestaBaseType no define un codigo de error a
        # nivel de envio (ver design.md, Open Questions), asi que se deja constancia
        # del EstadoEnvio para que quede un motivo persistido por cada registro.
        descripcion_cabecera = f"Rechazo de cabecera de la AEAT (EstadoEnvio={estado_envio})"

    return RespuestaEnvio(
        csv=csv, tiempo_espera_segundos=tiempo, estado_envio=estado_envio, lineas=lineas,
        codigo_error_cabecera=codigo_error_cabecera, descripcion_cabecera=descripcion_cabecera,
    )


def _clasificar_linea(
    ln, num_serie: str | None, estado_reg: str, codigo_error: str | None, descripcion: str | None
) -> ResultadoLinea:
    """Clasifica una RespuestaLinea: normal (EstadoRegistro, formas masculinas) o
    duplicado (bloque RegistroDuplicado, EstadoRegistroDuplicado en formas femeninas).
    El nodo RegistroDuplicado solo llega cuando la AEAT rechazo por duplicado (cod 3000)."""
    duplicado_nodo = ln.find(f"{{{NS_RESP}}}RegistroDuplicado")
    if duplicado_nodo is not None:
        # RegistroDuplicado es local de RespuestaSuministro.xsd (NS_RESP), pero es de tipo
        # RegistroDuplicadoType (SuministroInformacion.xsd): sus hijos viven en NS_SF.
        estado_dup = _texto(duplicado_nodo, f"{{{NS_SF}}}EstadoRegistroDuplicado") or ""
        resultado_dup = _DUPLICADO_A_RESULTADO.get(estado_dup)
        if resultado_dup is not None:
            return ResultadoLinea(
                num_serie_factura=num_serie, resultado=resultado_dup,
                codigo_error=codigo_error, descripcion=descripcion, duplicado=True,
            )
        # "Anulada" u otro valor no contemplado: terminal anomalo, no reintentable;
        # no cabe en el vocabulario CHECK de `resultado`, se aisla via `estado_final`.
        return ResultadoLinea(
            num_serie_factura=num_serie, resultado="rechazado",
            codigo_error=codigo_error, descripcion=descripcion,
            estado_final="requiere_intervencion", duplicado=True,
        )
    return ResultadoLinea(
        num_serie_factura=num_serie,
        resultado=_ESTADO_A_RESULTADO.get(estado_reg, "rechazado"),
        codigo_error=codigo_error, descripcion=descripcion,
    )
