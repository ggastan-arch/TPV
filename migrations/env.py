"""Entorno de Alembic. Resuelve la URL desde app.infraestructura.config (o el override
del runner) y usa el engine configurado (WAL, foreign_keys)."""
from __future__ import annotations

from alembic import context

from app.infraestructura.config import settings
from app.infraestructura.db import crear_engine
from app.infraestructura.persistencia.modelos import Base  # registra todo el metadata

config = context.config

# URL: la del propio comando alembic (o el override de tests) tiene prioridad.
url = config.get_main_option("sqlalchemy.url") or settings.database_url

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
