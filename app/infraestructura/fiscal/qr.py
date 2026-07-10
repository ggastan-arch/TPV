"""Codigo QR tributario y URL de cotejo (Orden HAC/1177/2024 arts. 20-21).

Especificaciones tomadas del documento oficial de sede
docs/Verifactu/DetalleEspecificacTecnCodigoQRfactura.pdf (v0.5.0):
- URL de cotejo con 4 parametros obligatorios en orden: nif, numserie, fecha, importe.
- Valores codificados con URL-encoding (UTF-8): p. ej. '&' -> '%26'.
- QR ISO/IEC 18004 con nivel de correccion de errores M; 30x30 a 40x40 mm.
- Encima: "QR tributario:". Debajo (VERI*FACTU): la leyenda de verificabilidad.
"""
from __future__ import annotations

import io
from urllib.parse import quote_plus

import segno

from app.core.config import settings
from app.dominio.servicios.huella import formato_importe
from app.infraestructura.persistencia.modelos.fiscal import RegistroFiscal

# URL base del servicio de cotejo para sistemas que emiten facturas VERIFICABLES.
BASE_PRUEBAS = "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?"
BASE_PRODUCCION = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?"

TEXTO_QR = "QR tributario:"
LEYENDA_LARGA = "Factura verificable en la sede electronica de la AEAT"
LEYENDA_CORTA = "VERI*FACTU"

_NIVEL_CORRECCION = "m"  # art. 21: nivel M (medio)


def _base(entorno: str) -> str:
    return BASE_PRODUCCION if entorno == "produccion" else BASE_PRUEBAS


def url_cotejo(
    *,
    nif: str,
    num_serie_factura: str,
    fecha_expedicion: str,
    importe_total,
    entorno: str | None = None,
) -> str:
    """Construye la URL de cotejo con los 4 parametros obligatorios URL-encoded."""
    entorno = entorno or settings.entorno_aeat
    return (
        f"{_base(entorno)}nif={quote_plus(nif)}"
        f"&numserie={quote_plus(num_serie_factura)}"
        f"&fecha={quote_plus(fecha_expedicion)}"
        f"&importe={quote_plus(formato_importe(importe_total))}"
    )


def url_cotejo_registro(registro: RegistroFiscal, *, entorno: str | None = None) -> str:
    return url_cotejo(
        nif=registro.id_emisor,
        num_serie_factura=registro.num_serie_factura,
        fecha_expedicion=registro.fecha_expedicion,
        importe_total=registro.importe_total,
        entorno=entorno,
    )


def generar_qr(url: str) -> segno.QRCode:
    """QR con el nivel de correccion M exigido por el art. 21."""
    return segno.make(url, error=_NIVEL_CORRECCION)


def qr_png(url: str, *, scale: int = 4, border: int = 4) -> bytes:
    buf = io.BytesIO()
    generar_qr(url).save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()
