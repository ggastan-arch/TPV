"""Reset de arranque en modo demo (`app.main._resetear_demo`): bootstrap real via
Alembic (nunca `create_all`/`DELETE`) + `sembrar_demo`, aislado de produccion."""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import app.main as main_module
from app.infraestructura.config import DB_PATH_PRODUCCION, Settings
from app.infraestructura.db import crear_engine
from app.infraestructura.persistencia.modelos import Cliente, TipoIVA, Usuario, Venta


def test_primer_arranque_siembra(tmp_path):
    """`_resetear_demo(s)` sobre un fichero inexistente: tras ejecutar, un
    engine local con Alembic `head` contiene el catalogo + clientes sembrados."""
    db_path = tmp_path / "tpv_demo.db"
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    s.db_path = str(db_path)

    main_module._resetear_demo(s)

    engine = crear_engine(s.database_url, poolclass=NullPool)
    Sesion = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with Sesion() as sesion:
        assert sesion.execute(select(TipoIVA)).scalars().first() is not None
        assert sesion.execute(select(Cliente)).scalars().first() is not None
    engine.dispose()


def test_resetear_demo_instala_triggers_de_inmutabilidad(tmp_path):
    """`_resetear_demo(s)` recrea el esquema via Alembic `upgrade head`, nunca
    `create_all` (invariante 1): la BD demo resultante debe llevar los MISMOS
    triggers de inmutabilidad que produccion, o `create_all` los estaria
    omitiendo en silencio (no crea triggers, solo tablas/columnas)."""
    db_path = tmp_path / "tpv_demo.db"
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    s.db_path = str(db_path)

    main_module._resetear_demo(s)

    engine = crear_engine(s.database_url, poolclass=NullPool)
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")).all()
    engine.dispose()

    nombres = {f[0] for f in filas}
    esperados = {
        "trg_venta_no_update",
        "trg_venta_no_delete",
        "trg_registro_fiscal_no_update",
        "trg_registro_fiscal_no_delete",
        "trg_log_auditoria_no_update",
        "trg_log_auditoria_no_delete",
        "trg_movimiento_stock_no_update",
        "trg_movimiento_stock_no_delete",
    }
    assert esperados <= nombres, f"Faltan triggers en la BD demo: {esperados - nombres}"


def test_resetear_demo_rechaza_borrar_venta_emitida(tmp_path):
    """No basta con que los triggers EXISTAN: deben estar ACTIVOS en la BD demo
    igual que en produccion. Una venta con estado distinto de 'aparcada'
    (emitida) no se puede borrar tampoco ahi (`trg_venta_no_delete`)."""
    db_path = tmp_path / "tpv_demo.db"
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    s.db_path = str(db_path)

    main_module._resetear_demo(s)

    engine = crear_engine(s.database_url, poolclass=NullPool)
    Sesion = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with Sesion() as sesion, sesion.begin():
        usuario = Usuario(nombre="demo-inmutable", pin_hash="x", rol="venta")
        sesion.add(usuario)
        sesion.flush()
        venta = Venta(estado="cobrada", usuario_id=usuario.id)
        sesion.add(venta)
        sesion.flush()
        venta_id = venta.id

    with Sesion() as sesion:
        venta = sesion.get(Venta, venta_id)
        sesion.delete(venta)
        with pytest.raises(sa.exc.DatabaseError):
            sesion.flush()
        sesion.rollback()
    engine.dispose()


def test_resetear_demo_rechaza_ruta_produccion():
    """Guardarraiz de `_resetear_demo`: si `s.db_path` resuelve la misma ruta
    que produccion, aborta con `RuntimeError` SIN borrar ni migrar nada
    (defensa en profundidad ademas de `_verificar_aislamiento_demo`)."""
    s = Settings(_env_file=None)
    assert s.db_path == DB_PATH_PRODUCCION

    with pytest.raises(RuntimeError):
        main_module._resetear_demo(s)


def test_produccion_sin_cambios(tmp_path, monkeypatch, aplicar_migraciones):
    """El ciclo de vida ASGI completo (lifespan de arranque, disparado al usar
    `TestClient` como gestor de contexto) con perfil produccion NO invoca
    `_resetear_demo` (invariante 1: ningun reset en el SIF real); los datos
    previos persisten."""
    db_path = tmp_path / "tpv.db"
    url = f"sqlite:///{db_path}"
    aplicar_migraciones(url)
    engine = crear_engine(url, poolclass=NullPool)
    Sesion = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with Sesion() as sesion, sesion.begin():
        sesion.add(TipoIVA(nombre="Marcador", porcentaje=Decimal("21.00")))
    engine.dispose()

    s = Settings(_env_file=None)
    s.db_path = str(db_path)
    monkeypatch.setattr(main_module, "settings", s)
    llamadas = {"n": 0}
    monkeypatch.setattr(
        main_module, "_resetear_demo",
        lambda _s: llamadas.__setitem__("n", llamadas["n"] + 1),
    )

    with TestClient(main_module.crear_app()):
        pass

    assert llamadas["n"] == 0
    engine2 = crear_engine(url, poolclass=NullPool)
    with sessionmaker(bind=engine2, class_=Session, expire_on_commit=False)() as sesion:
        assert sesion.execute(
            select(TipoIVA).where(TipoIVA.nombre == "Marcador")
        ).scalars().first() is not None
    engine2.dispose()


# --- Reset de arranque via lifespan ASGI (no en crear_app()/tiempo de import) --
def test_crear_app_no_resetea_al_construir(tmp_path, monkeypatch):
    """El bug corregido: `crear_app()` (y por tanto `import app.main`, que
    ejecuta `app = crear_app()` a nivel de modulo) NO debe ejecutar
    `_resetear_demo` en su cuerpo. Antes, lanzar con
    `python -m uvicorn app.main:app` importaba el modulo en el proceso
    lanzador Y en el proceso hijo que sirve, disparando el reset DOS veces en
    paralelo contra el mismo `tpv_demo.db` -> `sqlite3.OperationalError:
    database is locked` (panel fiscal en 500). El reset se difiere al
    lifespan ASGI, que arranca una unica vez en el proceso que realmente
    sirve peticiones."""
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    s.db_path = str(tmp_path / "tpv_demo.db")
    monkeypatch.setattr(main_module, "settings", s)
    llamadas = {"n": 0}
    original = main_module._resetear_demo

    def _spy(settings_arg):
        llamadas["n"] += 1
        original(settings_arg)

    monkeypatch.setattr(main_module, "_resetear_demo", _spy)

    main_module.crear_app()

    assert llamadas["n"] == 0  # construir la app no toca la BD


def test_lifespan_resetea_demo_una_vez_al_arrancar(tmp_path, monkeypatch):
    """El reset de demo vive en el lifespan de arranque: se dispara UNA vez
    al entrar en el ciclo de vida ASGI (`with TestClient(app) as c:`), no en
    cada import ni en cada peticion posterior."""
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    s.db_path = str(tmp_path / "tpv_demo.db")
    monkeypatch.setattr(main_module, "settings", s)
    llamadas = {"n": 0}
    original = main_module._resetear_demo

    def _spy(settings_arg):
        llamadas["n"] += 1
        original(settings_arg)

    monkeypatch.setattr(main_module, "_resetear_demo", _spy)

    app = main_module.crear_app()
    assert llamadas["n"] == 0

    with TestClient(app) as cliente:
        assert llamadas["n"] == 1
        cliente.get("/health")

    assert llamadas["n"] == 1
