"""Validacion de NIF/NIE/CIF (dato del cliente)."""
from __future__ import annotations

import pytest

from app.dominio.servicios.validadores import normalizar_documento, validar_documento


@pytest.mark.parametrize(
    "valor",
    [
        "12345678Z",   # DNI valido
        "00000000T",   # DNI valido
        "X1234567L",   # NIE valido
        "Z1234567R",   # NIE valido
        "A58818501",   # CIF valido (control numerico)
        "P1234567D",   # CIF valido (control alfabetico)
    ],
)
def test_documentos_validos(valor):
    assert validar_documento(valor) is True


@pytest.mark.parametrize(
    "valor",
    [
        "12345678A",   # letra de control incorrecta
        "X1234567Z",   # NIE con control incorrecto
        "A58818500",   # CIF con control incorrecto
        "1234567",     # formato invalido
        "",            # vacio
        None,          # None
        "AAAAAAAAA",   # basura
    ],
)
def test_documentos_invalidos(valor):
    assert validar_documento(valor) is False


def test_normaliza_espacios_y_guiones():
    assert validar_documento(" 12345678-z ") is True


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (" 12345678-z ", "12345678Z"),
        ("x1234567l", "X1234567L"),
        ("A58818501", "A58818501"),
    ],
)
def test_normalizar_documento(entrada, esperado):
    assert normalizar_documento(entrada) == esperado
