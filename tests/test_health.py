"""GET /health expone el perfil activo: fuente unica de verdad para la consola
(banner "MODO DEMO" en admin.html se apoya en este contrato)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import app.presentacion.health as health_module
from app.infraestructura.config import Settings
from app.main import crear_app


def test_health_expone_perfil_produccion_por_defecto():
    cliente = TestClient(crear_app())

    r = cliente.get("/health")

    assert r.status_code == 200
    assert r.json()["perfil"] == "produccion"


def test_health_expone_perfil_demo(monkeypatch):
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    monkeypatch.setattr(health_module, "settings", s)
    cliente = TestClient(crear_app())

    r = cliente.get("/health")

    assert r.json()["perfil"] == "demo"
