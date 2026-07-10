"""URL de cotejo y QR tributario (Orden arts. 20-21)."""
from __future__ import annotations

from decimal import Decimal

from app.infraestructura.fiscal import qr


def test_url_cotejo_pruebas_formato_documentado():
    # Valores del ejemplo del documento de sede (importe a 2 decimales).
    url = qr.url_cotejo(
        nif="89890001K",
        num_serie_factura="12345678-G33",
        fecha_expedicion="01-09-2024",
        importe_total=Decimal("241.40"),
        entorno="pruebas",
    )
    assert url == (
        "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?"
        "nif=89890001K&numserie=12345678-G33&fecha=01-09-2024&importe=241.40"
    )


def test_url_cotejo_produccion():
    url = qr.url_cotejo(
        nif="89890001K", num_serie_factura="T2027-000001",
        fecha_expedicion="09-07-2027", importe_total=Decimal("11.90"),
        entorno="produccion",
    )
    assert url.startswith("https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?")


def test_numserie_con_caracteres_especiales_se_codifica():
    # El '&' en el numero de serie debe ir como %26 (ejemplo del documento).
    url = qr.url_cotejo(
        nif="89890001K", num_serie_factura="12345678&G33",
        fecha_expedicion="01-01-2024", importe_total=Decimal("241.40"),
        entorno="pruebas",
    )
    assert "numserie=12345678%26G33" in url


def test_importe_dos_decimales_punto_no_coma():
    url = qr.url_cotejo(
        nif="00000000T", num_serie_factura="T2027-000001",
        fecha_expedicion="01-01-2027", importe_total=Decimal("7.2"),
        entorno="pruebas",
    )
    assert "importe=7.20" in url
    assert "," not in url


def test_qr_nivel_correccion_m_y_png():
    url = qr.url_cotejo(
        nif="00000000T", num_serie_factura="T2027-000001",
        fecha_expedicion="01-01-2027", importe_total=Decimal("11.90"),
    )
    codigo = qr.generar_qr(url)
    assert codigo.error.upper() == "M"  # nivel M exigido por el art. 21
    png = qr.qr_png(url)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # cabecera PNG
