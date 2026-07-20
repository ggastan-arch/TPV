"""Comprobacion ESTRUCTURAL del HTML/JS servido en `/tpv/` (sin navegador, sin
motor de plantillas), mismo patron que tests/test_admin_ui.py y
tests/test_navegacion.py.

Cubre la ficha de alta inline de cliente del panel "Cliente en venta": debe
pedir la ficha COMPLETA del maestro (nombre obligatorio; nif, domicilio,
email, telefono y consentimiento RGPD opcionales), no solo nombre/nif/domicilio
via `prompt()` encadenados (ver specs/cliente-en-venta/spec.md)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import crear_app


def _html() -> str:
    return TestClient(crear_app()).get("/tpv/").text


def _bloque_cliente_en_venta(html: str) -> str:
    inicio = html.index("function abrirClienteEnVenta")
    return html[inicio:]


def test_alta_inline_cliente_pide_ficha_completa():
    bloque = _bloque_cliente_en_venta(_html())
    for campo_id in ("ceNombre", "ceNif", "ceDomicilio", "ceEmail", "ceTelefono", "ceRgpd"):
        assert f'id="{campo_id}"' in bloque, f"falta el campo {campo_id} en la ficha de alta inline"


def test_alta_inline_cliente_envia_email_y_telefono_en_el_post():
    bloque = _bloque_cliente_en_venta(_html())
    assert (
        "body: JSON.stringify({ nombre, nif, domicilio, email, telefono, rgpd_consentimiento: rgpd })"
        in bloque
    )


def test_alta_inline_cliente_exige_nombre_en_cliente_pero_el_resto_es_opcional():
    bloque = _bloque_cliente_en_venta(_html())
    assert "El nombre es obligatorio" in bloque


def test_alta_inline_cliente_ya_no_usa_prompt_encadenados():
    """No-regresion: la ficha completa reemplaza los prompt()/confirm() previos
    (que solo pedian nombre/nif/domicilio + confirmacion RGPD aislada)."""
    bloque = _bloque_cliente_en_venta(_html())
    assert 'prompt("Nombre del cliente:"' not in bloque
    assert "confirm(" not in bloque
