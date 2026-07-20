"""La resolucion de URL de las migraciones respeta el override -x del runner.

Regresion del incidente: `alembic ... -x sqlalchemy.url=<scratch>` era IGNORADO porque
env.py leia siempre la URL fija del alembic.ini (tpv.db). El override debe tener prioridad
para poder migrar contra una BD de scratch sin tocar la base real."""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from app.infraestructura.db import resolver_url_migracion

_INI = "sqlite:///tpv.db"
_DEF = "sqlite:///defecto.db"

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


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


def test_alembic_ini_no_fija_url_que_pise_settings():
    """El `alembic.ini` NO debe fijar una `sqlalchemy.url` concreta.

    Incidente: con `sqlalchemy.url = sqlite:///tpv.db` en el ini,
    `resolver_url_migracion` la prioriza sobre `settings.database_url`, asi que
    `alembic upgrade head` (make migrate) migraba `tpv.db` en vez de la BD real
    de produccion (`tpv_pruebas.db`, fijada por `TPV_DB_PATH` en el .env). El
    valor debe quedar vacio para caer a settings (env.py resuelve la URL)."""
    url_ini = Config(str(_ALEMBIC_INI)).get_main_option("sqlalchemy.url")
    assert not url_ini, (
        f"alembic.ini fija sqlalchemy.url={url_ini!r}; debe quedar vacio para "
        "que `make migrate` use settings.database_url (la BD real)"
    )
