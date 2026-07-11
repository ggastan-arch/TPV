"""Validacion de documentos de identidad espanoles: NIF, NIE y CIF.

Comprueba el digito/letra de control. No consulta ninguna base externa.
"""
from __future__ import annotations

import re

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_LETRAS_CIF = "JABCDEFGHI"

_RE_DNI = re.compile(r"^\d{8}[A-Z]$")
_RE_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")
_RE_CIF = re.compile(r"^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$")

_NIE_PREFIJO = {"X": "0", "Y": "1", "Z": "2"}


def _letra_dni(numero: int) -> str:
    return _LETRAS_DNI[numero % 23]


def _validar_dni(v: str) -> bool:
    return _letra_dni(int(v[:8])) == v[8]


def _validar_nie(v: str) -> bool:
    numero = _NIE_PREFIJO[v[0]] + v[1:8]
    return _letra_dni(int(numero)) == v[8]


def normalizar_documento(valor: str) -> str:
    """Forma canonica del documento: mayusculas, sin espacios ni guiones.

    Regla unica de normalizacion reutilizada por `validar_documento` y por la capa de
    aplicacion para almacenar el NIF siempre del mismo modo."""
    return valor.strip().upper().replace("-", "").replace(" ", "")


def _validar_cif(v: str) -> bool:
    digitos = v[1:8]
    suma_pares = sum(int(digitos[i]) for i in (1, 3, 5))
    suma_impares = 0
    for i in (0, 2, 4, 6):
        doble = int(digitos[i]) * 2
        suma_impares += doble if doble < 10 else doble - 9
    control = (10 - (suma_pares + suma_impares) % 10) % 10
    esperado_num = str(control)
    esperado_letra = _LETRAS_CIF[control]
    ctrl = v[8]
    if v[0] in "ABEH":        # organizaciones con control numerico
        return ctrl == esperado_num
    if v[0] in "KPQRSNW":     # organizaciones con control alfabetico
        return ctrl == esperado_letra
    return ctrl in (esperado_num, esperado_letra)


def validar_documento(valor: str | None) -> bool:
    """True si el valor es un NIF, NIE o CIF con control correcto."""
    if not valor:
        return False
    v = normalizar_documento(valor)
    if _RE_DNI.match(v):
        return _validar_dni(v)
    if _RE_NIE.match(v):
        return _validar_nie(v)
    if _RE_CIF.match(v):
        return _validar_cif(v)
    return False
