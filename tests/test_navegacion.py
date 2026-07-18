"""Navegacion TPV<->Administracion y demo sin friccion: reset de arranque
idempotente, acceso libre solo en perfil demo, enlaces cruzados y ajuste del
boton "Salir" segun perfil. Produccion queda intacta en todos los casos."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import app.main as main_module
from app.infraestructura.config import Settings
from app.infraestructura.db import crear_engine
from app.infraestructura.persistencia.modelos import Cliente
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.presentacion.deps import get_session, get_uow


def _settings_demo(tmp_path) -> Settings:
    s = Settings(_env_file=None, TPV_PROFILE="demo")
    s.db_path = str(tmp_path / "tpv_demo.db")
    return s


@contextmanager
def _cliente_demo(tmp_path, monkeypatch, *, overrides: dict | None = None):
    """`crear_app()` con perfil demo: el reset de arranque (lifespan ASGI,
    disparado al entrar como gestor de contexto) siembra `tmp_path/tpv_demo.db`.
    Las dependencias `get_session`/`get_uow` se redirigen a ESE mismo fichero
    (el singleton global de `app/infraestructura/db.py` se liga a otra BD en
    tiempo de import y no sirve para las peticiones de test).

    `overrides` permite anadir/pisar `dependency_overrides` adicionales (p. ej.
    forzar `require_admin` para aislar un test de un problema no relacionado
    con `require_admin_demo`)."""
    s = _settings_demo(tmp_path)
    monkeypatch.setattr(main_module, "settings", s)

    app = crear_app()

    engine = crear_engine(s.database_url, poolclass=NullPool)
    Sesion = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def _get_session():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    def _get_uow():
        sesion = Sesion()
        try:
            yield UnidadDeTrabajoSQL(sesion)
        finally:
            sesion.close()

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_uow] = _get_uow
    if overrides:
        app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        engine.dispose()


# --- Fase 2: reset de arranque (continuacion de tests/test_modo_demo.py) -------
def test_rearranque_demo_descarta_cambios(tmp_path):
    """Un segundo `_resetear_demo` sobre el mismo `s` descarta cualquier cambio
    hecho tras el primero: vuelve al estado sembrado limpio."""
    s = _settings_demo(tmp_path)

    main_module._resetear_demo(s)

    engine = crear_engine(s.database_url, poolclass=NullPool)
    Sesion = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with Sesion() as sesion:
        conteo_inicial = len(sesion.execute(select(Cliente)).scalars().all())
    with Sesion() as sesion, sesion.begin():
        sesion.add(Cliente(nombre="Cliente basura (no sembrado)"))
    engine.dispose()

    main_module._resetear_demo(s)

    engine2 = crear_engine(s.database_url, poolclass=NullPool)
    with sessionmaker(bind=engine2, class_=Session, expire_on_commit=False)() as sesion:
        clientes = sesion.execute(select(Cliente)).scalars().all()
    engine2.dispose()

    assert len(clientes) == conteo_inicial
    assert all(c.nombre != "Cliente basura (no sembrado)" for c in clientes)


def test_reset_no_ocurre_sin_reiniciar(tmp_path, monkeypatch):
    """Dentro de una misma instancia de `crear_app()` (perfil demo), varias
    peticiones no disparan un segundo reset: `_resetear_demo` corre UNA vez, en
    el arranque del lifespan ASGI, no por peticion."""
    s = _settings_demo(tmp_path)
    monkeypatch.setattr(main_module, "settings", s)
    llamadas = {"n": 0}
    original = main_module._resetear_demo

    def _spy(settings_arg):
        llamadas["n"] += 1
        original(settings_arg)

    monkeypatch.setattr(main_module, "_resetear_demo", _spy)

    app = crear_app()
    with TestClient(app) as cliente:
        cliente.get("/health")
        cliente.get("/health")
        cliente.get("/health")

    assert llamadas["n"] == 1


def test_produccion_no_resetea_en_reinicio(tmp_path, monkeypatch, aplicar_migraciones):
    """Dos arranques sucesivos (lifespan ASGI) con perfil produccion (datos ya
    presentes en `tmp_path`) conservan los datos sin wipe ni reseed:
    `_resetear_demo` nunca se invoca (invariante 1)."""
    from decimal import Decimal

    from app.infraestructura.persistencia.modelos import TipoIVA

    db_path = tmp_path / "tpv.db"
    url = f"sqlite:///{db_path}"
    aplicar_migraciones(url)
    engine = crear_engine(url, poolclass=NullPool)
    Sesion = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with Sesion() as sesion, sesion.begin():
        sesion.add(TipoIVA(nombre="Marcador produccion", porcentaje=Decimal("21.00")))
    engine.dispose()

    s = Settings(_env_file=None)
    s.db_path = str(db_path)
    monkeypatch.setattr(main_module, "settings", s)
    llamadas = {"n": 0}
    monkeypatch.setattr(
        main_module, "_resetear_demo",
        lambda _s: llamadas.__setitem__("n", llamadas["n"] + 1),
    )

    with TestClient(crear_app()):
        pass
    with TestClient(crear_app()):
        pass

    assert llamadas["n"] == 0
    engine2 = crear_engine(url, poolclass=NullPool)
    with sessionmaker(bind=engine2, class_=Session, expire_on_commit=False)() as sesion:
        assert sesion.execute(
            select(TipoIVA).where(TipoIVA.nombre == "Marcador produccion")
        ).scalars().first() is not None
    engine2.dispose()


# --- Fase 3: override de acceso libre ------------------------------------------
def test_demo_acceso_libre_sin_login(tmp_path, monkeypatch):
    """En perfil demo, `/admin/api/me` y una ruta protegida devuelven 200 SIN
    sesion (acceso libre gateado en `crear_app`, nunca en produccion)."""
    with _cliente_demo(tmp_path, monkeypatch) as cliente:
        assert cliente.get("/admin/api/me").status_code == 200
        assert cliente.get("/admin/api/informes/dia").status_code == 200


# --- Regresion: reset de demo por lifespan (no import-time) -------------------
def test_demo_panel_fiscal_no_falla_por_reset_concurrente(tmp_path, monkeypatch):
    """Regresion del bug: antes, `_resetear_demo` corria en el CUERPO de
    `crear_app()`, que se ejecuta en tiempo de IMPORT (`app = crear_app()` a
    nivel de modulo en `app/main.py`). Con `python -m uvicorn app.main:app`
    (y el arranque en Render) el modulo se importa en el proceso lanzador Y en
    el proceso hijo que sirve, disparando el reset DOS VECES en paralelo sobre
    el mismo `tpv_demo.db` -> `sqlite3.OperationalError: database is locked`,
    y `/admin/api/fiscal/estado` (invoca `NullEngine.verify_chain`) devolvia
    500. Con el reset movido al lifespan ASGI (una unica vez, en el proceso
    que sirve), el panel fiscal responde 200 en un unico proceso sin lock.

    Usa el `require_admin_demo` REAL que registra `crear_app()` (sin override
    de aislamiento): ver `test_demo_get_uow_no_se_autobloquea_contra_require_admin_demo`
    para el bug distinto (y ya corregido) del auto-bloqueo `get_uow`/`get_session`."""
    with _cliente_demo(tmp_path, monkeypatch) as cliente:
        assert cliente.get("/admin/api/fiscal/estado").status_code == 200


def test_demo_get_uow_no_se_autobloquea_contra_require_admin_demo(tmp_path, monkeypatch):
    """Bug real (distinto del anterior): `require_admin_demo` abria su PROPIA
    sesion via `Depends(get_session)`, que FastAPI NO deduplica con la sesion
    de `Depends(get_uow)` que usan los endpoints admin de escritura/fiscal (son
    callables DISTINTOS, cada uno abre su propia conexion). Ambas sesiones
    fuerzan `BEGIN IMMEDIATE` (ver `app/infraestructura/db.py::
    _configurar_begin_immediate`) sobre el MISMO fichero SQLite dentro de la
    MISMA peticion -> auto-bloqueo real (`sqlite3.OperationalError: database
    is locked` -> 500 via el manejador de excepciones), independiente del
    orden de arranque. Afecta a TODO endpoint admin que dependa de `get_uow`
    (panel fiscal, cierres Z, stock, maestros de escritura...).

    Fix: `require_admin_demo` ya no abre conexion propia; resuelve el id del
    administrador demo cacheado en el lifespan de arranque
    (`admin.fijar_id_admin_demo`, ver `app/main.py`)."""
    with _cliente_demo(tmp_path, monkeypatch) as cliente:
        # Los dos endpoints confirmados en produccion con 500 (ambos get_uow).
        assert cliente.get("/admin/api/fiscal/estado").status_code == 200
        assert cliente.get("/admin/api/maestros/cierres-z").status_code == 200
        # No regresion: los endpoints get_session (mismo callable que
        # require_admin_demo, deduplicados por FastAPI) siguen en 200.
        assert cliente.get("/admin/api/me").status_code == 200
        assert cliente.get("/admin/api/informes/dia").status_code == 200
        assert cliente.get("/admin/api/maestros/clientes").status_code == 200


def test_demo_admin_cacheado_es_el_sembrado_y_se_limpia_al_apagar(tmp_path, monkeypatch):
    """El lifespan de arranque (demo) cachea el id del PRIMER `Usuario`
    `rol='administracion'` activo sembrado por `sembrar_demo` (nombre "admin",
    ver `app/seed.py::_sembrar_iva_series_usuarios`) y lo limpia al apagar
    (fin del `with TestClient(...)`), para no dejar estado global filtrado
    entre arranques/tests."""
    from app.presentacion import admin as admin_module

    with _cliente_demo(tmp_path, monkeypatch) as cliente:
        assert cliente.get("/admin/api/me").json()["nombre"] == "admin"

    with pytest.raises(HTTPException) as exc:
        admin_module.require_admin_demo()
    assert exc.value.status_code == 503


def test_produccion_sigue_exigiendo_login():
    """En perfil produccion, el override NO se registra: `/admin/api/me` sigue
    dando 401 sin sesion (no-regresion del login por sesion)."""
    cliente = TestClient(crear_app())

    assert cliente.get("/admin/api/me").status_code == 401


# --- Fase 4: navegacion TPV <-> administracion ---------------------------------
def test_boton_tpv_a_admin():
    cliente = TestClient(crear_app())
    r = cliente.get("/tpv/")

    assert r.status_code == 200
    assert 'href="/admin/"' in r.text


def test_boton_admin_a_tpv():
    cliente = TestClient(crear_app())
    r = cliente.get("/admin/")

    assert r.status_code == 200
    assert 'href="/tpv/"' in r.text
    assert "Ir al TPV" in r.text


# --- Fase 5: ajuste de "Salir" segun perfil ------------------------------------
# Comprobacion ESTRUCTURAL del HTML/JS servido (sin motor de plantillas ni
# navegador): el HTML de `/admin/` es estatico, la rama que activa cada perfil
# se resuelve en el navegador contra `window.esDemo` (mismo contrato que
# tpv.html / tests/test_health.py). Aqui se verifican las DOS mitades del
# condicional: la rama que oculta "Salir" en demo y la rama que lo sigue
# montando cuando no aplica, con su `.onclick` protegido por null-check.
def test_salir_oculto_en_demo():
    html = TestClient(crear_app()).get("/admin/").text

    assert 'window.esDemo ? "" :' in html


def test_salir_presente_en_produccion():
    html = TestClient(crear_app()).get("/admin/").text

    assert '<button class="accion" id="salir">Salir</button>' in html
    assert "if (btnSalir)" in html
