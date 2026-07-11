"""Salvaguarda de arranque: `crear_app()` rechaza una configuracion demo que
resolviera (por error o regresion futura) la misma BD que produccion.

Defensa en profundidad: `Settings._resolver_perfil` ya fuerza `db_path` en modo
demo (tests/test_config.py), pero este chequeo es independiente y compara rutas
ABSOLUTAS para blindar contra una regresion futura del validator.
"""
from __future__ import annotations

import pytest

from app.infraestructura.config import DB_PATH_PRODUCCION, DEMO_DB_PATH, Settings
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
