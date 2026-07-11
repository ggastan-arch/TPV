"""`get_motor()` en modo demo: NullEngine siempre, certificado NUNCA leido.

`VerifactuEngine` real todavia no existe (fuera de alcance de este cambio); estos
tests fijan la garantia de que el PERFIL (no el cableado actual) es lo que
decide el motor, para blindar el dia que exista un motor de produccion real.
"""
from __future__ import annotations

import app.presentacion.deps as deps_module
from app.infraestructura.config import DEMO_NIF, DEMO_NOMBRE, Settings
from app.infraestructura.fiscal.engine import NullEngine


def test_get_motor_en_demo_es_nullengine_y_certificado_nunca_se_lee(monkeypatch):
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    # Forzar un certificado "configurado" saltandose la resolucion normal
    # (bypass identico al usado en test_main.py): simula una regresion futura.
    # La ruta NO existe en disco: si algun codigo intentara abrirla, fallaria
    # con FileNotFoundError -> su ausencia demuestra que nunca se lee.
    s.certificado_cert_path = "no/existe/certificado.pem"
    monkeypatch.setattr(deps_module, "settings", s)

    motor = deps_module.get_motor()

    assert isinstance(motor, NullEngine)
    assert motor.id_emisor == DEMO_NIF
    assert motor.nombre_emisor == DEMO_NOMBRE


def test_get_motor_en_produccion_sin_cambios(monkeypatch):
    s = Settings(_env_file=None)
    monkeypatch.setattr(deps_module, "settings", s)

    motor = deps_module.get_motor()

    assert isinstance(motor, NullEngine)
    assert motor.id_emisor == s.nif_emisor
    assert motor.nombre_emisor == s.nombre_emisor
