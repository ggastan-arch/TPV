"""Punto de entrada FastAPI. Los routers TPV/admin/fiscal se anaden en fases siguientes."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app.presentacion.admin import require_admin, require_admin_demo
from app.presentacion.admin import router as admin_router
from app.presentacion.health import router as health_router
from app.presentacion.landing import router as landing_router
from app.presentacion.tpv import router as tpv_router
from app.infraestructura import imagenes
from app.infraestructura.config import DB_PATH_PRODUCCION, Settings, settings
from app.infraestructura.db import crear_engine
from app.seed import sembrar_demo

# Raiz del proyecto (para localizar alembic.ini/migrations/ desde el reset de
# arranque demo), mismo patron que tests/conftest.py.
_RAIZ = Path(__file__).resolve().parent.parent


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


def _resetear_demo(s: Settings) -> None:
    """Reset de arranque en modo demo: recrea `tpv_demo.db` desde cero en CADA
    arranque (esquema real via Alembic `upgrade head` + `sembrar_demo`), nunca
    `create_all`/`DELETE` (invariante 1: `create_all` no crea los triggers de
    inmutabilidad; `DELETE` sobre ventas emitidas lo rechazan esos triggers).

    Guardarraiz propio (defensa en profundidad ademas de
    `_verificar_aislamiento_demo`): aborta con `RuntimeError` si `s.db_path`
    resuelve la misma ruta que produccion, ANTES de borrar ningun fichero.

    Usa un engine local construido desde `s.database_url` (nunca el singleton
    `SessionLocal`/`engine` de `app/infraestructura/db.py`, que se liga a otra
    BD en tiempo de importacion): la funcion queda autocontenida y testeable
    contra un `tpv_demo.db` en `tmp_path` sin tocar globals ni `tpv.db`."""
    if Path(s.db_path).resolve() == Path(DB_PATH_PRODUCCION).resolve():
        raise RuntimeError(
            "Reset de demo abortado: la ruta de BD coincide con la de "
            f"produccion ({DB_PATH_PRODUCCION})."
        )

    db_file = Path(s.db_path)
    for sufijo in ("", "-wal", "-shm", "-journal"):
        (db_file.parent / f"{db_file.name}{sufijo}").unlink(missing_ok=True)

    cfg = Config(str(_RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(_RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", s.database_url)
    command.upgrade(cfg, "head")

    engine_demo = crear_engine(s.database_url, poolclass=NullPool)
    try:
        factory = sessionmaker(bind=engine_demo, class_=Session, expire_on_commit=False)
        sembrar_demo(factory)
    finally:
        engine_demo.dispose()


def crear_app() -> FastAPI:
    _verificar_aislamiento_demo(settings)
    if settings.perfil == "demo":
        _resetear_demo(settings)
    app = FastAPI(title=settings.nombre_sistema, version=settings.version_sistema)
    if settings.perfil == "demo":
        # Acceso libre SOLO en demo: voltea de una vez las ~40 rutas que declaran
        # Depends(require_admin). Produccion NUNCA registra este override y su
        # login por sesion queda byte a byte identico (invariante 5).
        app.dependency_overrides[require_admin] = require_admin_demo
    # Sesion de la consola de administracion (cookie firmada).
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       same_site="lax", https_only=False)
    app.include_router(landing_router)
    app.include_router(health_router)
    app.include_router(tpv_router)
    app.include_router(admin_router)
    # Imagenes de catalogo: archivo en disco, ruta publica en BD (nunca binario
    # ni base64). `imagenes.MEDIA_DIR` se lee en tiempo de llamada (permite
    # monkeypatch a tmp_path en tests). Se crea si no existe para que el
    # arranque nunca falle por un `media/` ausente en una instalacion nueva.
    imagenes.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(imagenes.MEDIA_DIR)), name="media")
    # Fotos de la demo: catalogo real de la tienda, COMMITEADO en el repo (a
    # diferencia de /media, efimero) para que persista en el despliegue. Solo lo
    # referencia el seed demo (articulo.imagen == /media-demo/...); en produccion
    # el mount queda inerte porque el catalogo real no apunta ahi.
    img_demo = Path(__file__).resolve().parent / "img_demo"
    if img_demo.is_dir():
        app.mount("/media-demo", StaticFiles(directory=str(img_demo)), name="media-demo")
    return app


app = crear_app()
