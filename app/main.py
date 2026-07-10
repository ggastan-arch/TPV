"""Punto de entrada FastAPI. Los routers TPV/admin/fiscal se anaden en fases siguientes."""
from __future__ import annotations

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.tpv import router as tpv_router
from app.core.config import settings


def crear_app() -> FastAPI:
    app = FastAPI(title=settings.nombre_sistema, version=settings.version_sistema)
    app.include_router(health_router)
    app.include_router(tpv_router)
    return app


app = crear_app()
