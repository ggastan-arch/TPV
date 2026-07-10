"""Verifica la regla de dependencias hexagonal con import-linter.

Los contratos estan en pyproject.toml [tool.importlinter]. Si un import cruza una
capa indebida (p. ej. el dominio importando infraestructura en runtime, o alguien
importando presentacion), este test falla."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("importlinter")

RAIZ = Path(__file__).resolve().parents[1]
_SCRIPT = Path(sys.executable).parent / ("lint-imports.exe" if os.name == "nt" else "lint-imports")


def test_regla_de_dependencias_hexagonal():
    if not _SCRIPT.exists():
        pytest.skip("lint-imports no disponible")
    resultado = subprocess.run(
        [str(_SCRIPT)], cwd=str(RAIZ), capture_output=True, text=True
    )
    assert resultado.returncode == 0, resultado.stdout + "\n" + resultado.stderr
