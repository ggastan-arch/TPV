"""Composicion de la huella SHA-256 encadenada (Orden HAC/1177/2024 art. 13).

Implementado y VERIFICADO contra el documento oficial de sede
"Detalle de las especificaciones tecnicas para generacion de la huella o hash de
los registros de facturacion" (AEAT, v0.1.2, 27/08/2024), incluidos sus tres
vectores de prueba (ver tests/test_huella_vectores.py). Ese doc esta en
docs/Verifactu/Veri-Factu_especificaciones_huella_hash_registros.pdf.

Formato (doc 3 y 6): los campos se concatenan, en el orden fijado, como
    nombreCampo1=valor1&nombreCampo2=valor2&...&nombreCampoN=valorN
- nombre del campo: constante segun el diseno de registro (OJO: el de anulacion
  usa los nombres con sufijo "Anulada").
- valor: el mismo del XML, con espacios de inicio/fin eliminados. Si falta o esta
  vacio (p. ej. la huella anterior en el primer registro): solo "nombre=".
- numericos: 2 decimales (los ceros a la derecha son irrelevantes para la AEAT).
- fechas de factura: dd-mm-aaaa. Fecha-hora de generacion: ISO 8601 con huso.
Salida: SHA-256, hexadecimal MAYUSCULAS, 64 caracteres. Entrada UTF-8.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP


def _s(valor: str | None) -> str:
    """Valor de campo: recorta espacios de inicio/fin; vacio si None."""
    return valor.strip() if valor else ""


def formato_importe(valor: Decimal) -> str:
    """Importe con 2 decimales, punto decimal. Misma representacion en XML y huella."""
    return format(Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


_imp = formato_importe


def _hash(cadena: str) -> str:
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def huella_alta(
    *,
    id_emisor: str,
    num_serie_factura: str,
    fecha_expedicion: str,
    tipo_factura: str,
    cuota_total: Decimal,
    importe_total: Decimal,
    huella_anterior: str | None,
    fecha_hora_huso_gen: str,
) -> str:
    cadena = (
        f"IDEmisorFactura={_s(id_emisor)}"
        f"&NumSerieFactura={_s(num_serie_factura)}"
        f"&FechaExpedicionFactura={_s(fecha_expedicion)}"
        f"&TipoFactura={_s(tipo_factura)}"
        f"&CuotaTotal={_imp(cuota_total)}"
        f"&ImporteTotal={_imp(importe_total)}"
        f"&Huella={_s(huella_anterior)}"
        f"&FechaHoraHusoGenRegistro={_s(fecha_hora_huso_gen)}"
    )
    return _hash(cadena)


def huella_anulacion(
    *,
    id_emisor: str,
    num_serie_factura: str,
    fecha_expedicion: str,
    huella_anterior: str | None,
    fecha_hora_huso_gen: str,
) -> str:
    # Nombres de campo especificos del registro de anulacion (sufijo "Anulada").
    cadena = (
        f"IDEmisorFacturaAnulada={_s(id_emisor)}"
        f"&NumSerieFacturaAnulada={_s(num_serie_factura)}"
        f"&FechaExpedicionFacturaAnulada={_s(fecha_expedicion)}"
        f"&Huella={_s(huella_anterior)}"
        f"&FechaHoraHusoGenRegistro={_s(fecha_hora_huso_gen)}"
    )
    return _hash(cadena)
