"""Regresion (bloqueante pre-go-live): las migraciones que recrean una tabla via
`batch_alter_table` deben poder ejecutarse sobre una BD POBLADA con filas hijas
que la referencian.

Incidente: `0007_modo_precio_articulo` recrea `articulo` con el patron "move and
copy" de SQLite (crear tmp -> copiar -> DROP articulo -> renombrar). Con
`PRAGMA foreign_keys=ON` (lo activa `_configurar_pragmas`), el `DROP TABLE` ejecuta
un DELETE implicito que verifica las FKs. Eso produce DOS modos de fallo distintos
segun el tipo de hija, y cada test cubre uno:

- Hija RESTRICT (`movimiento_stock`): el DROP falla RUIDOSAMENTE con
  "FOREIGN KEY constraint failed". Migraba bien desde cero (demo/tests migran
  vacio) pero rompia en produccion con datos reales, dejando el sistema sin poder
  actualizarse nunca.
- Hija CASCADE (`codigo_barras`): el DROP NO falla, pero borra en cascada las
  filas hijas SIN error (perdida de datos silenciosa). Es el camino mas peligroso.

Fix: `run_migrations_online` (migrations/env.py) desactiva `foreign_keys` durante
la migracion (patron canonico Alembic+SQLite). La integridad referencial sigue
vigente en produccion porque cada conexion de la aplicacion la reactiva en
`_configurar_pragmas`.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

_PRE_0007 = "0006_articulo_imagen"


def _crear_articulo_pre_0007(conn) -> None:
    """tipo_iva + articulo bajo el esquema pre-0007 (aun con `precio_libre`)."""
    conn.execute(text(
        "INSERT INTO tipo_iva (id, nombre, porcentaje, calificacion, activo) "
        "VALUES (1, 'General 21%', '21.00', 'S1', 1)"
    ))
    conn.execute(text(
        "INSERT INTO articulo (id, nombre, nombre_corto, tipo_iva_id, pvp, "
        "control_stock, precio_libre, requiere_cites, activo) "
        "VALUES (1, 'Neon', 'Neon', 1, '2.50', 1, 0, 0, 1)"
    ))


def _assert_articulo_migrado_sin_huerfanos(engine) -> None:
    """El esquema nuevo de 0007 esta aplicado y la BD queda sin huerfanos."""
    columnas = {c["name"] for c in inspect(engine).get_columns("articulo")}
    assert "modo_precio" in columnas
    assert "precio_libre" not in columnas
    with engine.connect() as conn:
        # precio_libre=0 -> 'fijo' (mapeo de 0007).
        assert conn.execute(text("SELECT modo_precio FROM articulo WHERE id = 1")).scalar_one() == "fijo"
        # integridad referencial global tras el recreate (agnostico del esquema).
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_batch_recrea_articulo_con_hija_restrict_no_falla(tmp_path, aplicar_migraciones):
    """Camino RUIDOSO: con FK=ON el DROP del recreate falla por la hija RESTRICT.
    Si el fix de env.py se revierte, `aplicar_migraciones(..., head)` lanza
    "FOREIGN KEY constraint failed" -> este test falla (guard real)."""
    db = tmp_path / "restrict.db"
    url = f"sqlite:///{db}"
    aplicar_migraciones(url, _PRE_0007)

    engine = create_engine(url)
    with engine.begin() as conn:
        _crear_articulo_pre_0007(conn)
        conn.execute(text(
            "INSERT INTO movimiento_stock (articulo_id, tipo, cantidad, fecha_hora_huso) "
            "VALUES (1, 'entrada', '10', '2026-07-20T10:00:00+02:00')"
        ))
    engine.dispose()

    aplicar_migraciones(url, "head")  # recrea `articulo` (DROP + rename)

    engine = create_engine(url)
    _assert_articulo_migrado_sin_huerfanos(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM movimiento_stock")).scalar_one() == 1
    engine.dispose()


def test_batch_recrea_articulo_con_hija_cascade_no_pierde_datos(tmp_path, aplicar_migraciones):
    """Camino SILENCIOSO (el mas peligroso): SIN hija RESTRICT que enmascare, con
    FK=ON el DROP del recreate no falla pero borra en cascada `codigo_barras` sin
    error. Si el fix se revierte, la fila desaparece -> COUNT = 0 -> este test
    falla (guard real del camino de perdida de datos silenciosa)."""
    db = tmp_path / "cascade.db"
    url = f"sqlite:///{db}"
    aplicar_migraciones(url, _PRE_0007)

    engine = create_engine(url)
    with engine.begin() as conn:
        _crear_articulo_pre_0007(conn)
        conn.execute(text(
            "INSERT INTO codigo_barras (articulo_id, codigo, principal) "
            "VALUES (1, '8412345678905', 1)"
        ))
    engine.dispose()

    aplicar_migraciones(url, "head")  # recrea `articulo` (DROP + rename)

    engine = create_engine(url)
    _assert_articulo_migrado_sin_huerfanos(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM codigo_barras")).scalar_one() == 1
    engine.dispose()
