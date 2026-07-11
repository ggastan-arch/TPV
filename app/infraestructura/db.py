"""Motor de base de datos SQLite en modo WAL.

Configuracion por conexion:
- journal_mode=WAL: concurrencia lector/escritor trivial para el escenario
  "un puesto de venta + un administrador remoto".
- foreign_keys=ON: SQLite no aplica FKs por defecto.
- busy_timeout: los escritores en contienda esperan en vez de fallar.
- BEGIN IMMEDIATE (opcional): adquiere el lock de escritura al inicio de la
  transaccion. Es la pieza que garantiza numeracion correlativa SIN HUECOS bajo
  concurrencia (invariante 2): la emision (contador + venta + registro) ocurre
  en una unica transaccion serializada.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.infraestructura.config import settings


def resolver_url_migracion(
    x_args: dict[str, str] | None, url_ini: str | None, url_defecto: str
) -> str:
    """URL para las migraciones Alembic, por prioridad:
    override `-x sqlalchemy.url` del runner > `sqlalchemy.url` del alembic.ini/config >
    `settings.database_url`. El override tiene prioridad para poder migrar contra una BD de
    scratch sin tocar la base real (un `-x` vacio se ignora)."""
    x_args = x_args or {}
    return x_args.get("sqlalchemy.url") or url_ini or url_defecto


def crear_engine(url: str | None = None, *, inmediato: bool = True, **kwargs) -> Engine:
    engine = create_engine(
        url or settings.database_url,
        connect_args={"check_same_thread": False},
        **kwargs,
    )
    _configurar_pragmas(engine)
    if inmediato:
        _configurar_begin_immediate(engine)
    return engine


def _configurar_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _rec):  # noqa: ANN001
        # Delegar el control transaccional en SQLAlchemy (pysqlite no auto-begin).
        dbapi_conn.isolation_level = None
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute(f"PRAGMA busy_timeout={settings.busy_timeout_ms}")
        cur.close()


def _configurar_begin_immediate(engine: Engine) -> None:
    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # noqa: ANN001
        conn.exec_driver_sql("BEGIN IMMEDIATE")


engine = crear_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
