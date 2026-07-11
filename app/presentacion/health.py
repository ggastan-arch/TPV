"""Endpoint de salud."""
from __future__ import annotations

from fastapi import APIRouter

from app.infraestructura.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    # Fuente unica de verdad del perfil activo: la consola (admin.html) lo
    # consulta para pintar el banner "MODO DEMO" sin duplicar el estado.
    return {"status": "ok", "perfil": settings.perfil}
