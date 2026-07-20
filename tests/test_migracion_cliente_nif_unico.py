"""Migracion 0012: indice unico parcial `uq_cliente_nif_activo` sobre `cliente(nif)`.

Ver el docstring de la migracion
(migrations/versions/0012_cliente_nif_unico_activo.py) para la regla de negocio
(NIF unico solo entre clientes ACTIVOS) y el caveat de duplicados preexistentes
en una base de datos real."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_migracion_0012_indice_unico_parcial_activo_tras_upgrade(tmp_path, aplicar_migraciones):
    db = tmp_path / "migracion_nif_unico.db"
    url = f"sqlite:///{db}"
    aplicar_migraciones(url, "head")

    engine = create_engine(url)

    indices = inspect(engine).get_indexes("cliente")
    indice = next((i for i in indices if i["name"] == "uq_cliente_nif_activo"), None)
    assert indice is not None, "falta el indice uq_cliente_nif_activo"
    assert indice["unique"]

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cliente (nif, nombre, rgpd_consentimiento, activo) "
            "VALUES ('A58818501', 'Uno', 0, 1)"
        ))

    # Segundo cliente ACTIVO con el MISMO nif: rechazado a nivel de BD.
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(text(
                    "INSERT INTO cliente (nif, nombre, rgpd_consentimiento, activo) "
                    "VALUES ('A58818501', 'Dos', 0, 1)"
                ))
            raise AssertionError("debio rechazar el NIF duplicado entre clientes activos")
        except IntegrityError as exc:
            assert "unique" in str(exc).lower()

    # Un cliente INACTIVO con el mismo nif: permitido (indice parcial, activo=0
    # queda fuera de la condicion del indice).
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cliente (nif, nombre, rgpd_consentimiento, activo) "
            "VALUES ('A58818501', 'Tres inactivo', 0, 0)"
        ))

    # Varios clientes SIN nif: permitido (NULL no colisiona en el indice).
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cliente (nombre, rgpd_consentimiento, activo) "
            "VALUES ('Sin nif 1', 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO cliente (nombre, rgpd_consentimiento, activo) "
            "VALUES ('Sin nif 2', 0, 1)"
        ))

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM cliente")).scalar_one()
    assert total == 4
    engine.dispose()


def test_migracion_0012_downgrade_elimina_el_indice(tmp_path, aplicar_migraciones, bajar_migraciones):
    db = tmp_path / "migracion_nif_unico_downgrade.db"
    url = f"sqlite:///{db}"
    aplicar_migraciones(url, "head")
    bajar_migraciones(url, "0011_venta_trigger_campos_congelados")

    engine = create_engine(url)
    indices = inspect(engine).get_indexes("cliente")
    assert all(i["name"] != "uq_cliente_nif_activo" for i in indices)

    # Sin el indice, dos clientes ACTIVOS con el mismo nif ya no se rechazan.
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cliente (nif, nombre, rgpd_consentimiento, activo) "
            "VALUES ('A58818501', 'Uno', 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO cliente (nif, nombre, rgpd_consentimiento, activo) "
            "VALUES ('A58818501', 'Dos', 0, 1)"
        ))
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM cliente")).scalar_one()
    assert total == 2
    engine.dispose()
