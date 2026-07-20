"""Logica de escritura de TPV_SESSION_SECRET en el .env (scripts/preparar_produccion.py).

Se prueba la parte riesgosa del script de go-live: NO pisar otras variables del
.env, reemplazar solo el valor por defecto y no tocar un secreto fuerte ya puesto.
El reset del PIN admin (getpass + BD) es interactivo y queda fuera de estos tests.
"""
from __future__ import annotations

from app.infraestructura.config import SESSION_SECRET_DEFAULT
from scripts.preparar_produccion import _CLAVE, _plan_secret

_NUEVO = "valor-nuevo-generado-xyz"


def test_agrega_secret_si_falta():
    lineas = ["TPV_PROFILE=produccion", "TPV_DB_PATH=tpv_pruebas.db"]
    res, accion = _plan_secret(lineas, _NUEVO, rotar=False)
    assert accion == "agregado"
    assert f"{_CLAVE}={_NUEVO}" in res
    # las demas variables quedan intactas
    assert "TPV_PROFILE=produccion" in res
    assert "TPV_DB_PATH=tpv_pruebas.db" in res


def test_reemplaza_el_valor_por_defecto():
    lineas = ["TPV_NIF_EMISOR=12345678Z", f"{_CLAVE}={SESSION_SECRET_DEFAULT}"]
    res, accion = _plan_secret(lineas, _NUEVO, rotar=False)
    assert accion == "reemplazado"
    assert f"{_CLAVE}={_NUEVO}" in res
    assert f"{_CLAVE}={SESSION_SECRET_DEFAULT}" not in res
    assert "TPV_NIF_EMISOR=12345678Z" in res  # intacto


def test_no_pisa_un_secreto_fuerte_existente():
    lineas = [f"{_CLAVE}=un-secreto-fuerte-ya-configurado"]
    res, accion = _plan_secret(lineas, _NUEVO, rotar=False)
    assert accion == "sin-cambios"
    assert res == lineas


def test_rotar_reemplaza_aunque_sea_fuerte():
    lineas = [f"{_CLAVE}=un-secreto-fuerte-ya-configurado"]
    res, accion = _plan_secret(lineas, _NUEVO, rotar=True)
    assert accion == "rotado"
    assert f"{_CLAVE}={_NUEVO}" in res
    assert "un-secreto-fuerte-ya-configurado" not in "\n".join(res)
