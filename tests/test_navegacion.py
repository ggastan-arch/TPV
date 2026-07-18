"""Navegacion TPV<->Administracion y demo sin friccion: reset de arranque
idempotente, acceso libre solo en perfil demo, enlaces cruzados y ajuste del
boton "Salir" segun perfil. Produccion queda intacta en todos los casos."""
from __future__ import annotations

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


def _cliente_demo(tmp_path, monkeypatch) -> TestClient:
    """`crear_app()` con perfil demo: el reset de arranque siembra
    `tmp_path/tpv_demo.db`. Las dependencias `get_session`/`get_uow` se
    redirigen a ESE mismo fichero (el singleton global de `app/infraestructura/db.py`
    se liga a otra BD en tiempo de import y no sirve para las peticiones de test)."""
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
    return TestClient(app)


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
    el arranque, no por peticion."""
    s = _settings_demo(tmp_path)
    monkeypatch.setattr(main_module, "settings", s)
    llamadas = {"n": 0}
    original = main_module._resetear_demo

    def _spy(settings_arg):
        llamadas["n"] += 1
        original(settings_arg)

    monkeypatch.setattr(main_module, "_resetear_demo", _spy)

    app = crear_app()
    cliente = TestClient(app)
    cliente.get("/health")
    cliente.get("/health")
    cliente.get("/health")

    assert llamadas["n"] == 1


def test_produccion_no_resetea_en_reinicio(tmp_path, monkeypatch, aplicar_migraciones):
    """Dos `crear_app()` sucesivos con perfil produccion (datos ya presentes en
    `tmp_path`) conservan los datos sin wipe ni reseed: `_resetear_demo` nunca
    se invoca (invariante 1)."""
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

    crear_app()
    crear_app()

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
    cliente = _cliente_demo(tmp_path, monkeypatch)

    assert cliente.get("/admin/api/me").status_code == 200
    assert cliente.get("/admin/api/informes/dia").status_code == 200


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
