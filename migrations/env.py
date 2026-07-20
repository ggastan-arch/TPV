"""Entorno de Alembic. Resuelve la URL desde app.infraestructura.config (o el override
del runner) y usa el engine configurado (WAL, foreign_keys)."""
from __future__ import annotations

from alembic import context
from sqlalchemy import event

from app.infraestructura.config import settings
from app.infraestructura.db import crear_engine, resolver_url_migracion
from app.infraestructura.persistencia.modelos import Base  # registra todo el metadata

config = context.config

# URL con prioridad: override `-x sqlalchemy.url=...` > alembic.ini/config > settings.
# El `-x` debe ganar para poder migrar contra una BD de scratch sin tocar la base real.
url = resolver_url_migracion(
    context.get_x_argument(as_dictionary=True),
    config.get_main_option("sqlalchemy.url"),
    settings.database_url,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # inmediato=False: durante las migraciones no interesa forzar BEGIN IMMEDIATE.
    engine = crear_engine(url, inmediato=False)

    # foreign_keys=OFF durante TODA migracion online (no solo 0007/articulo). El
    # patron "move and copy" de `batch_alter_table` en SQLite recrea la tabla con
    # un DROP TABLE; con las FKs activas ese DROP ejecuta un DELETE implicito que
    # falla ("FOREIGN KEY constraint failed") si otra tabla (venta_linea,
    # movimiento_stock, boton...) tiene filas apuntando a ella. Se registra como
    # listener `connect` para aplicarlo sobre la conexion cruda ANTES de cualquier
    # transaccion (el PRAGMA es no-op dentro de una) y DESPUES del listener de
    # `_configurar_pragmas` que las activa. En produccion la integridad referencial
    # sigue vigente: cada conexion de la aplicacion reactiva foreign_keys=ON.
    # (El modo offline `--sql` no desactiva FKs: el script generado debe
    # prependerse manualmente con `PRAGMA foreign_keys=OFF;`.)
    @event.listens_for(engine, "connect")
    def _foreign_keys_off_en_migracion(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.close()

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
