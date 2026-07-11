"""La resolucion de URL de las migraciones respeta el override -x del runner.

Regresion del incidente: `alembic ... -x sqlalchemy.url=<scratch>` era IGNORADO porque
env.py leia siempre la URL fija del alembic.ini (tpv.db). El override debe tener prioridad
para poder migrar contra una BD de scratch sin tocar la base real."""
from __future__ import annotations

from app.infraestructura.db import resolver_url_migracion

_INI = "sqlite:///tpv.db"
_DEF = "sqlite:///defecto.db"


def test_override_x_tiene_prioridad():
    assert resolver_url_migracion(
        {"sqlalchemy.url": "sqlite:///scratch.db"}, _INI, _DEF
    ) == "sqlite:///scratch.db"


def test_sin_override_usa_url_del_ini():
    assert resolver_url_migracion({}, _INI, _DEF) == _INI
    assert resolver_url_migracion(None, _INI, _DEF) == _INI


def test_sin_ini_cae_al_defecto():
    assert resolver_url_migracion({}, None, _DEF) == _DEF


def test_override_vacio_se_ignora():
    # `-x sqlalchemy.url=` (cadena vacia) NO debe ganar sobre la URL del ini.
    assert resolver_url_migracion({"sqlalchemy.url": ""}, _INI, _DEF) == _INI
