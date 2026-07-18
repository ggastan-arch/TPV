"""Assets estaticos del sistema de diseno Nocturne: servidos desde /static sin
ninguna dependencia de red (invariante de cobro offline). `nocturne.css` es la
copia vendorizada de `design/nocturne/styles.css` con el `@import` de Google
Fonts eliminado; `nocturne-icons.js` expone el mapa de iconos Phosphor inline."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import crear_app


def test_nocturne_css_servido_y_sin_dependencia_de_red():
    cliente = TestClient(crear_app())

    r = cliente.get("/static/nocturne.css")

    assert r.status_code == 200
    cuerpo = r.text
    assert "--color-accent" in cuerpo
    assert "@import" not in cuerpo
    assert "fonts.googleapis.com" not in cuerpo


def test_nocturne_icons_js_servido_con_mapa_y_helper():
    cliente = TestClient(crear_app())

    r = cliente.get("/static/nocturne-icons.js")

    assert r.status_code == 200
    cuerpo = r.text
    assert "window.ICONOS" in cuerpo
    assert "function icono(" in cuerpo


def test_fuente_inter_autohospedada_y_servida():
    """La fuente Inter se auto-hospeda (invariante offline): `nocturne.css` la
    declara con @font-face apuntando a /static/fonts/ (nunca a un CDN) y el
    binario woff2 se sirve. Sin esto, la fuente degradaria a system-ui en
    silencio y ningun test lo detectaria."""
    cliente = TestClient(crear_app())

    css = cliente.get("/static/nocturne.css").text
    assert "@font-face" in css
    assert "/static/fonts/InterVariable.woff2" in css

    r = cliente.get("/static/fonts/InterVariable.woff2")
    assert r.status_code == 200
    assert int(r.headers["content-length"]) > 0
