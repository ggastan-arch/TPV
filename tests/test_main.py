"""Salvaguarda de arranque: `crear_app()` rechaza una configuracion demo que
resolviera (por error o regresion futura) la misma BD que produccion.

Defensa en profundidad: `Settings._resolver_perfil` ya fuerza `db_path` en modo
demo (tests/test_config.py), pero este chequeo es independiente y compara rutas
ABSOLUTAS para blindar contra una regresion futura del validator.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.infraestructura.config import DB_PATH_PRODUCCION, DEMO_DB_PATH, Settings
import app.infraestructura.imagenes as imagenes_mod
import app.main as main_module


def test_crear_app_rechaza_demo_apuntando_a_produccion(monkeypatch):
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    # Forzar la colision saltandose la resolucion normal (asignacion directa:
    # no hay validate_assignment, no vuelve a correr el model_validator).
    s.db_path = DB_PATH_PRODUCCION
    monkeypatch.setattr(main_module, "settings", s)

    with pytest.raises(RuntimeError):
        main_module.crear_app()


def test_crear_app_demo_con_tpv_demo_db_no_lanza(tmp_path, monkeypatch):
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    assert s.db_path == DEMO_DB_PATH  # resolucion normal, sin forzar nada
    # Aislar del repo: el lifespan de arranque ejecuta _resetear_demo (borra +
    # migra + siembra) al entrar en el TestClient como gestor de contexto, que
    # sobre DEMO_DB_PATH tocaria el tpv_demo.db real de la raiz del repo.
    s.db_path = str(tmp_path / "tpv_demo.db")
    monkeypatch.setattr(main_module, "settings", s)

    with TestClient(main_module.crear_app()):
        pass  # el arranque del lifespan (reset de demo) no debe lanzar


# --- pagina de inicio (portada del despliegue) ---------------------------------
def test_pagina_inicio_enruta_a_tpv_y_admin():
    cliente = TestClient(main_module.crear_app())
    r = cliente.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    cuerpo = r.text
    assert "/tpv" in cuerpo and "/admin" in cuerpo


# --- /media servido como estatico (StaticFiles) --------------------------------
def test_crear_app_no_falla_si_media_dir_no_existe_todavia(tmp_path, monkeypatch):
    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", tmp_path / "media_inexistente")

    main_module.crear_app()  # no debe lanzar aunque el directorio no exista

    assert (tmp_path / "media_inexistente").is_dir()  # se crea en el arranque


def test_media_sirve_los_archivos_de_media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", tmp_path)
    (tmp_path / "articulo-1-abcd1234.jpg").write_bytes(b"\xff\xd8\xff\xe0contenido")

    app = main_module.crear_app()
    cliente = TestClient(app)

    r = cliente.get("/media/articulo-1-abcd1234.jpg")
    assert r.status_code == 200
    assert r.content == b"\xff\xd8\xff\xe0contenido"


# --- /static sirve el sistema de diseno Nocturne (StaticFiles), sin CDN --------
def test_crear_app_sirve_nocturne_css_desde_static():
    cliente = TestClient(main_module.crear_app())

    r = cliente.get("/static/nocturne.css")

    assert r.status_code == 200


# --- reskin Nocturne de tpv.html: assets propios, wiring/IDs/handlers intactos -
def test_tpv_enlaza_assets_nocturne_sin_cdn():
    html = TestClient(main_module.crear_app()).get("/tpv/").text

    assert '<link rel="stylesheet" href="/static/nocturne.css">' in html
    assert '<script src="/static/nocturne-icons.js"></script>' in html
    assert "unpkg.com" not in html
    assert "fonts.googleapis.com" not in html


def test_tpv_conserva_ids_y_handlers_del_camino_de_cobro():
    html = TestClient(main_module.crear_app()).get("/tpv/").text

    for marcador in (
        'id="grid"', 'id="carrito"', 'id="total"', 'id="buscarInput"',
        'id="demoBanner"', 'id="usuario"', "/tpv/api/",
        "irInicio()", "abrirCobro()", "vaciar()",
    ):
        assert marcador in html, f"marcador ausente tras el reskin: {marcador}"


def test_tpv_hoja_puente_declara_min_height_tactil():
    html = TestClient(main_module.crear_app()).get("/tpv/").text

    assert "min-height:48px" in html


def _bloque_boton_que_contiene(html: str, etiqueta: str) -> str:
    """Extrae el `<button ...>...</button>` MAS CERCANO que envuelve `etiqueta`
    (el ultimo `<button` que abre antes de la etiqueta y el primer `</button>`
    que cierra despues), para no confundirlo con otros botones de la pagina."""
    idx = html.index(etiqueta)
    inicio = html.rindex("<button", 0, idx)
    fin = html.index("</button>", idx) + len("</button>")
    return html[inicio:fin]


def test_tpv_boton_convertir_en_factura_deshabilitado_sin_comportamiento_simulado():
    html = TestClient(main_module.crear_app()).get("/tpv/").text

    bloque = _bloque_boton_que_contiene(html, "Convertir en factura")
    assert "disabled" in bloque
    assert "fetch" not in bloque
    assert "onclick" not in bloque


def test_tpv_barra_funciones_futuras_presentes_deshabilitadas():
    html = TestClient(main_module.crear_app()).get("/tpv/").text

    for etiqueta in ("Convertir en factura", "Aparcar ticket", "Desaparcar", "Cliente en venta"):
        bloque = _bloque_boton_que_contiene(html, etiqueta)
        assert "disabled" in bloque, f"boton '{etiqueta}' no esta deshabilitado"
        assert "fetch" not in bloque, f"boton '{etiqueta}' no debe llamar a fetch"
        assert "onclick" not in bloque, f"boton '{etiqueta}' no debe tener handler"


# --- reskin Nocturne de landing.html: clases Nocturne, wiring/CDN intactos ----
def test_landing_enlaza_nocturne_sin_cdn():
    html = TestClient(main_module.crear_app()).get("/").text

    assert '<link rel="stylesheet" href="/static/nocturne.css">' in html
    assert "unpkg.com" not in html
    assert "fonts.googleapis.com" not in html


def test_landing_conserva_enlaces_bloques_y_script_demo():
    html = TestClient(main_module.crear_app()).get("/").text

    for marcador in (
        'href="/tpv/"', 'href="/admin/"', 'id="demoBadge"', 'id="demoBlocks"',
        'fetch("/health")',
    ):
        assert marcador in html, f"marcador ausente tras el reskin: {marcador}"


def test_landing_usa_clases_nocturne():
    html = TestClient(main_module.crear_app()).get("/").text

    assert 'class="card' in html
    assert 'class="tag' in html
    assert 'class="table' in html


# --- pulido visual: marca compacta cuadrada (logo-mark.png), no el wordmark
# ancho con espacio en blanco (logo-acuatpv.png), que se veia diminuto dentro
# de la caja pequena con object-fit:contain --
def test_landing_referencia_logo_real_de_marca():
    html = TestClient(main_module.crear_app()).get("/").text

    assert '/static/img/logo-mark.png' in html


def test_tpv_referencia_logo_real_de_marca():
    html = TestClient(main_module.crear_app()).get("/tpv/").text

    assert '/static/img/logo-mark.png' in html
