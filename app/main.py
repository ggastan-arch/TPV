"""Punto de entrada FastAPI. Los routers TPV/admin/fiscal se anaden en fases siguientes."""
from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.tpv import router as tpv_router
from app.core.config import settings


def crear_app() -> FastAPI:
    app = FastAPI(title=settings.nombre_sistema, version=settings.version_sistema)
    # Sesion de la consola de administracion (cookie firmada).
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       same_site="lax", https_only=False)
    app.include_router(health_router)
    app.include_router(tpv_router)
    app.include_router(admin_router)
    return app


app = crear_app()
