"""Pagina de inicio publica (portada del despliegue).

Presenta el proyecto y enruta a /tpv y /admin. Es la puerta de entrada del modo
demo desplegado (el corrector abre la raiz); en produccion tambien evita el 404
en la raiz. La pagina se adapta al perfil consultando /health (muestra las
credenciales de prueba solo en modo demo)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

_UI = Path(__file__).resolve().parents[1] / "ui" / "landing.html"

router = APIRouter()


@router.get("/", include_in_schema=False)
def pagina_inicio() -> FileResponse:
    return FileResponse(_UI)
