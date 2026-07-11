"""Perfil de arranque (produccion/demo): resolucion desde TPV_PROFILE.

En modo demo, `Settings` fuerza la BD y el emisor a valores aislados y anula el
certificado electronico (invariante 7: el certificado nunca se carga en demo).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.infraestructura.config import (
    DB_PATH_PRODUCCION,
    DEMO_DB_PATH,
    DEMO_NIF,
    DEMO_NOMBRE,
    Settings,
)


def test_perfil_demo_explicito_resuelve_db_y_emisor_demo(monkeypatch):
    monkeypatch.setenv("TPV_PROFILE", "demo")
    monkeypatch.setenv("TPV_CERTIFICADO_CERT_PATH", "/ruta/certificado.pem")
    monkeypatch.setenv("TPV_CERTIFICADO_KEY_PATH", "/ruta/clave.pem")

    s = Settings(_env_file=None)

    assert s.perfil == "demo"
    assert s.db_path == DEMO_DB_PATH
    assert s.nif_emisor == DEMO_NIF
    assert s.nombre_emisor == DEMO_NOMBRE
    # Invariante 7: el certificado nunca se carga en modo demo, aunque este configurado.
    assert s.certificado_cert_path is None
    assert s.certificado_key_path is None


def test_sin_tpv_profile_resuelve_produccion(monkeypatch):
    monkeypatch.delenv("TPV_PROFILE", raising=False)
    monkeypatch.setenv("TPV_NOMBRE_EMISOR", "Bizkaitropik Real")

    s = Settings(_env_file=None)

    assert s.perfil == "produccion"
    assert s.db_path == DB_PATH_PRODUCCION
    assert s.nombre_emisor == "Bizkaitropik Real"


def test_perfil_invalido_rechaza_arranque(monkeypatch):
    monkeypatch.setenv("TPV_PROFILE", "staging")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
