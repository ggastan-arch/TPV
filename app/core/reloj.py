"""Manejo del tiempo con huso horario (invariante 6 de CLAUDE.md).

Las fechas-hora de generacion del registro se almacenan en ISO 8601 con offset,
p. ej. `2027-07-01T10:15:30+02:00` (Orden HAC/1177/2024, FechaHoraHusoGenRegistro).
"""
from __future__ import annotations

from datetime import datetime


def ahora_huso() -> str:
    """Fecha-hora actual en ISO 8601 con offset de huso, precision de segundos."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fecha_expedicion_hoy() -> str:
    """Fecha de expedicion de la factura en formato fiscal `dd-mm-aaaa`.

    Es el formato exigido por la Orden (FechaExpedicionFactura) y el que entra en
    la huella. Se almacena asi para que XML y huella usen la misma representacion;
    la cadena de registros se ordena por el campo `orden`, no por esta fecha.
    """
    return datetime.now().astimezone().strftime("%d-%m-%Y")
