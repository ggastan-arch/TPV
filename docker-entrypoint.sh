#!/bin/sh
# Arranque del contenedor del modo demo. En un filesystem efimero (free tier) la BD
# tpv_demo.db se recrea en cada arranque en frio: reset automatico del demo.
set -e

# Perfil demo: BD aislada, sin certificado, motor NullEngine (invariante 7). Se fija
# tambien aqui por si la imagen se ejecuta sin la variable de entorno del build.
export TPV_PROFILE=demo

# Migracion Alembic REAL (triggers de inmutabilidad + cadena de huella heredados del
# esquema de produccion), nunca create_all. La URL se fija explicita para no depender
# de la resolucion del perfil en el proceso que lanza alembic.
python -c "from alembic import command; from alembic.config import Config; cfg = Config('alembic.ini'); cfg.set_main_option('sqlalchemy.url', 'sqlite:///tpv_demo.db'); command.upgrade(cfg, 'head')"

# Seed idempotente del catalogo demo (se salta si la BD ya tiene datos).
python -m app.seed --demo

# uvicorn en el puerto que inyecta la plataforma ($PORT), escuchando en todas las
# interfaces y SIN --reload (proceso de servidor de larga duracion).
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
