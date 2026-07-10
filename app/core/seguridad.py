"""Hash de PIN de usuario (PBKDF2-HMAC-SHA256).

El PIN nunca se almacena en claro (CLAUDE.md 9). El formato es autodescriptivo:
    pbkdf2_sha256$<iteraciones>$<salt_hex>$<hash_hex>
"""
from __future__ import annotations

import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERACIONES = 200_000


def hash_pin(pin: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERACIONES)
    return f"{_ALGO}${_ITERACIONES}${salt.hex()}${dk.hex()}"


def verificar_pin(pin: str, almacenado: str) -> bool:
    try:
        algo, iteraciones, salt_hex, dk_hex = almacenado.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), int(iteraciones)
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False
