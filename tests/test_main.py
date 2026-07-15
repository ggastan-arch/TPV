"""Salvaguarda de arranque: `crear_app()` rechaza una configuracion demo que
resolviera (por error o regresion futura) la misma BD que produccion.

Defensa en profundidad: `Settings._resolver_perfil` ya fuerza `db_path` en modo
demo (tests/test_config.py), pero este chequeo es independiente y compara rutas
ABSOLUTAS para blindar contra una regresion futura del validator.
"""
from __future__ import annotations

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


def test_crear_app_demo_con_tpv_demo_db_no_lanza(monkeypatch):
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    assert s.db_path == DEMO_DB_PATH  # resolucion normal, sin forzar nada
    monkeypatch.setattr(main_module, "settings", s)

    main_module.crear_app()  # no debe lanzar


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
