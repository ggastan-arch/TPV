"""Guarda contra divergencia entre los modelos y la migracion Alembic.

Refleja el esquema realmente creado por la migracion y comprueba que cada tabla y
columna declarada en los modelos existe. (No compara tipos: en SQLite los importes
son TEXT a nivel fisico.)
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.models import Base


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
    }
    assert esperados <= nombres, f"Faltan triggers: {esperados - nombres}"
