"""Guarda contra divergencia entre los modelos y la migracion Alembic.

Refleja el esquema realmente creado por la migracion y comprueba que cada tabla y
columna declarada en los modelos existe. (No compara tipos: en SQLite los importes
son TEXT a nivel fisico.)
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.infraestructura.persistencia.modelos import Articulo, Base


def test_todas_las_tablas_y_columnas_del_modelo_existen(engine):
    inspector = inspect(engine)
    tablas_reales = set(inspector.get_table_names())

    for tabla in Base.metadata.sorted_tables:
        assert tabla.name in tablas_reales, f"Falta la tabla {tabla.name} en la migracion"
        columnas_reales = {c["name"] for c in inspector.get_columns(tabla.name)}
        columnas_modelo = {c.name for c in tabla.columns}
        faltan = columnas_modelo - columnas_reales
        assert not faltan, f"Faltan columnas en {tabla.name}: {faltan}"


def test_triggers_de_inmutabilidad_instalados(engine):
    # Consulta directa a sqlite_master.
    from sqlalchemy import text

    with engine.connect() as conn:
        filas = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger'")
        ).all()
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
        "trg_cierre_z_no_update",
        "trg_cierre_z_no_delete",
        "trg_cierre_z_desglose_iva_no_update",
        "trg_cierre_z_desglose_iva_no_delete",
        "trg_cierre_z_desglose_pago_no_update",
        "trg_cierre_z_desglose_pago_no_delete",
    }
    assert esperados <= nombres, f"Faltan triggers: {esperados - nombres}"


# --- modo_precio: sustituye a precio_libre (fijo | libre | al_peso) -----------


def test_articulo_modo_precio_default_fijo(session, datos_base):
    articulo = Articulo(
        nombre="Articulo de prueba", nombre_corto="Prueba",
        tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00"),
    )
    session.add(articulo)
    session.commit()

    session.refresh(articulo)
    assert articulo.modo_precio == "fijo"


def test_articulo_modo_precio_admite_libre_y_al_peso(session, datos_base):
    libre = Articulo(
        nombre="Generico libre", nombre_corto="Libre",
        tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("0.00"), modo_precio="libre",
    )
    al_peso = Articulo(
        nombre="Madera flotante", nombre_corto="Madera",
        tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("12.00"), modo_precio="al_peso",
    )
    session.add_all([libre, al_peso])
    session.commit()

    session.refresh(libre)
    session.refresh(al_peso)
    assert libre.modo_precio == "libre"
    assert al_peso.modo_precio == "al_peso"


def test_articulo_modo_precio_rechaza_valor_fuera_del_enum(session, datos_base):
    articulo = Articulo(
        nombre="Articulo invalido", nombre_corto="Invalido",
        tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00"), modo_precio="otro",
    )
    session.add(articulo)
    with pytest.raises(IntegrityError):
        session.commit()
