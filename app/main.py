"""Punto de entrada FastAPI. Los routers TPV/admin/fiscal se anaden en fases siguientes."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app.presentacion.admin import router as admin_router
from app.presentacion.health import router as health_router
from app.presentacion.tpv import router as tpv_router
from app.infraestructura import imagenes
from app.infraestructura.config import DB_PATH_PRODUCCION, Settings, settings


def _verificar_aislamiento_demo(s: Settings) -> None:
    """Salvaguarda de arranque (defensa en profundidad, invariante 5/7).

    Independiente de `Settings._resolver_perfil`: compara rutas ABSOLUTAS
    resueltas para blindar contra una regresion futura que dejara el perfil
    demo apuntando a la BD real. Aborta el arranque sin abrir ninguna conexion.
    """
    if s.perfil == "demo" and Path(s.db_path).resolve() == Path(DB_PATH_PRODUCCION).resolve():
        raise RuntimeError(
            "Configuracion invalida: el perfil 'demo' resuelve la misma BD que "
            f"produccion ({DB_PATH_PRODUCCION}). Arranque abortado."
        )


def crear_app() -> FastAPI:
    _verificar_aislamiento_demo(settings)
    app = FastAPI(title=settings.nombre_sistema, version=settings.version_sistema)
    # Sesion de la consola de administracion (cookie firmada).
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       same_site="lax", https_only=False)
    app.include_router(health_router)
    app.include_router(tpv_router)
    app.include_router(admin_router)
    # Imagenes de catalogo: archivo en disco, ruta publica en BD (nunca binario
    # ni base64). `imagenes.MEDIA_DIR` se lee en tiempo de llamada (permite
    # monkeypatch a tmp_path en tests). Se crea si no existe para que el
    # arranque nunca falle por un `media/` ausente en una instalacion nueva.
    imagenes.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(imagenes.MEDIA_DIR)), name="media")
    return app


app = crear_app()
