"""Triggers de INMUTABILIDAD a nivel de base de datos (invariantes 1 y 4 de CLAUDE.md).

Estos invariantes existen por obligacion legal (art. 29.2.j LGT + RRSIF) y se aplican
en la BD, no solo en la aplicacion. Fuente unica: la migracion Alembic y los tests
ejecutan exactamente estas sentencias.

Politica:
- venta emitida (estado != 'aparcada'): no UPDATE ni DELETE, salvo la transicion de
  estado controlada cobrada -> {anulada_con_rastro, sustituida} sin tocar ningun campo
  monetario ni de identidad.
- venta_linea / pago: inmutables si su venta ya esta emitida.
- registro_fiscal: inmutable salvo `estado_remision` (metadato de envio); nunca DELETE.
- desglose / facturas sustituidas: inmutables (contenido del registro).
- log_auditoria / movimiento_stock: append-only (ni UPDATE ni DELETE).
"""
from __future__ import annotations

# Igualdad null-safe de los campos que NO pueden cambiar en una venta emitida.
# NOTA (D2 override, migraciones 0009/0010): `cualificada` y
# `destinatario_nombre`/`destinatario_nif` se anadieron DESPUES via `op.add_column`
# y deliberadamente NO estan en esta lista -- una venta `cobrada` ya esta
# bloqueada para CUALQUIER UPDATE que no sea la transicion de estado controlada
# (ver `trg_venta_no_update` mas abajo), y ningun codigo actual escribe esas
# columnas durante esa transicion. Ver el docstring de cada migracion para el
# analisis completo antes de asumir que serian seguras de anadir sin mas.
_VENTA_CAMPOS_CONGELADOS = " AND ".join(
    f"NEW.{c} IS OLD.{c}"
    for c in (
        "serie",
        "ejercicio",
        "numero",
        "num_serie_factura",
        "fecha_hora_huso",
        "usuario_id",
        "cliente_id",
        "base_total",
        "cuota_total",
        "total_con_iva",
    )
)

# Igualdad null-safe del contenido fiscal de un registro (todo salvo estado_remision).
_REGISTRO_CAMPOS_CONGELADOS = " AND ".join(
    f"NEW.{c} IS OLD.{c}"
    for c in (
        "orden",
        "tipo_registro",
        "venta_id",
        "id_emisor",
        "num_serie_factura",
        "fecha_expedicion",
        "tipo_factura",
        "descripcion_operacion",
        "cuota_total",
        "importe_total",
        "primer_registro",
        "registro_anterior_id",
        "huella_anterior",
        "huella",
        "tipo_huella",
        "fecha_hora_huso_gen_registro",
        "registro_alta_anulado_id",
    )
)

TRIGGERS: list[str] = [
    # --- venta: inmutable tras emitir, salvo transicion de estado controlada ---
    f"""
    CREATE TRIGGER trg_venta_no_update
    BEFORE UPDATE ON venta
    FOR EACH ROW
    WHEN OLD.estado <> 'aparcada'
     AND NOT (
        OLD.estado = 'cobrada'
        AND NEW.estado IN ('anulada_con_rastro', 'sustituida')
        AND {_VENTA_CAMPOS_CONGELADOS}
     )
    BEGIN
        SELECT RAISE(ABORT, 'Venta emitida inmutable (RRSIF art. 8): solo transicion de estado permitida');
    END;
    """,
    """
    CREATE TRIGGER trg_venta_no_delete
    BEFORE DELETE ON venta
    FOR EACH ROW
    WHEN OLD.estado <> 'aparcada'
    BEGIN
        SELECT RAISE(ABORT, 'Venta emitida no se puede borrar (RRSIF art. 8)');
    END;
    """,
    # --- venta_linea: inmutable si la venta padre ya esta emitida ---
    """
    CREATE TRIGGER trg_venta_linea_no_update
    BEFORE UPDATE ON venta_linea
    FOR EACH ROW
    WHEN (SELECT estado FROM venta WHERE id = OLD.venta_id) <> 'aparcada'
    BEGIN
        SELECT RAISE(ABORT, 'Linea de venta emitida inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_venta_linea_no_delete
    BEFORE DELETE ON venta_linea
    FOR EACH ROW
    WHEN (SELECT estado FROM venta WHERE id = OLD.venta_id) <> 'aparcada'
    BEGIN
        SELECT RAISE(ABORT, 'Linea de venta emitida no se puede borrar');
    END;
    """,
    # --- pago: inmutable si la venta padre ya esta emitida ---
    """
    CREATE TRIGGER trg_pago_no_update
    BEFORE UPDATE ON pago
    FOR EACH ROW
    WHEN (SELECT estado FROM venta WHERE id = OLD.venta_id) <> 'aparcada'
    BEGIN
        SELECT RAISE(ABORT, 'Pago de venta emitida inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_pago_no_delete
    BEFORE DELETE ON pago
    FOR EACH ROW
    WHEN (SELECT estado FROM venta WHERE id = OLD.venta_id) <> 'aparcada'
    BEGIN
        SELECT RAISE(ABORT, 'Pago de venta emitida no se puede borrar');
    END;
    """,
    # --- registro_fiscal: inmutable salvo estado_remision; nunca DELETE ---
    f"""
    CREATE TRIGGER trg_registro_fiscal_no_update
    BEFORE UPDATE ON registro_fiscal
    FOR EACH ROW
    WHEN NOT ({_REGISTRO_CAMPOS_CONGELADOS})
    BEGIN
        SELECT RAISE(ABORT, 'Registro fiscal inmutable (RRSIF): solo estado_remision es editable');
    END;
    """,
    """
    CREATE TRIGGER trg_registro_fiscal_no_delete
    BEFORE DELETE ON registro_fiscal
    BEGIN
        SELECT RAISE(ABORT, 'Registro fiscal inmutable (RRSIF): no se puede borrar');
    END;
    """,
    # --- desglose del registro: inmutable ---
    """
    CREATE TRIGGER trg_desglose_no_update
    BEFORE UPDATE ON registro_fiscal_desglose
    BEGIN
        SELECT RAISE(ABORT, 'Desglose del registro fiscal inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_desglose_no_delete
    BEFORE DELETE ON registro_fiscal_desglose
    BEGIN
        SELECT RAISE(ABORT, 'Desglose del registro fiscal inmutable');
    END;
    """,
    # --- facturas sustituidas del registro: inmutable ---
    """
    CREATE TRIGGER trg_fact_sustituida_no_update
    BEFORE UPDATE ON registro_factura_sustituida
    BEGIN
        SELECT RAISE(ABORT, 'Facturas sustituidas del registro inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_fact_sustituida_no_delete
    BEFORE DELETE ON registro_factura_sustituida
    BEGIN
        SELECT RAISE(ABORT, 'Facturas sustituidas del registro inmutable');
    END;
    """,
    # --- log de auditoria: append-only ---
    """
    CREATE TRIGGER trg_log_auditoria_no_update
    BEFORE UPDATE ON log_auditoria
    BEGIN
        SELECT RAISE(ABORT, 'Log de auditoria append-only: no se puede modificar');
    END;
    """,
    """
    CREATE TRIGGER trg_log_auditoria_no_delete
    BEFORE DELETE ON log_auditoria
    BEGIN
        SELECT RAISE(ABORT, 'Log de auditoria append-only: no se puede borrar');
    END;
    """,
    # --- movimiento de stock: append-only ---
    """
    CREATE TRIGGER trg_movimiento_stock_no_update
    BEFORE UPDATE ON movimiento_stock
    BEGIN
        SELECT RAISE(ABORT, 'Movimiento de stock append-only: no se puede modificar');
    END;
    """,
    """
    CREATE TRIGGER trg_movimiento_stock_no_delete
    BEFORE DELETE ON movimiento_stock
    BEGIN
        SELECT RAISE(ABORT, 'Movimiento de stock append-only: no se puede borrar');
    END;
    """,
]

_NOMBRES_TRIGGERS = [
    "trg_venta_no_update",
    "trg_venta_no_delete",
    "trg_venta_linea_no_update",
    "trg_venta_linea_no_delete",
    "trg_pago_no_update",
    "trg_pago_no_delete",
    "trg_registro_fiscal_no_update",
    "trg_registro_fiscal_no_delete",
    "trg_desglose_no_update",
    "trg_desglose_no_delete",
    "trg_fact_sustituida_no_update",
    "trg_fact_sustituida_no_delete",
    "trg_log_auditoria_no_update",
    "trg_log_auditoria_no_delete",
    "trg_movimiento_stock_no_update",
    "trg_movimiento_stock_no_delete",
]

DROP_TRIGGERS: list[str] = [f"DROP TRIGGER IF EXISTS {n};" for n in _NOMBRES_TRIGGERS]

# --- Triggers de la migracion 0002 (cola de remision, append-only) ---
TRIGGERS_REMISION: list[str] = [
    """
    CREATE TRIGGER trg_remision_intento_no_update
    BEFORE UPDATE ON remision_intento
    BEGIN
        SELECT RAISE(ABORT, 'Intento de remision append-only: no se puede modificar');
    END;
    """,
    """
    CREATE TRIGGER trg_remision_intento_no_delete
    BEFORE DELETE ON remision_intento
    BEGIN
        SELECT RAISE(ABORT, 'Intento de remision append-only: no se puede borrar');
    END;
    """,
]

DROP_TRIGGERS_REMISION: list[str] = [
    "DROP TRIGGER IF EXISTS trg_remision_intento_no_update;",
    "DROP TRIGGER IF EXISTS trg_remision_intento_no_delete;",
]

# --- Triggers de la migracion 0003 (Cierre Z: snapshot inmutable, sin excepciones) ---
TRIGGERS_CIERRE_Z: list[str] = [
    """
    CREATE TRIGGER trg_cierre_z_no_update
    BEFORE UPDATE ON cierre_z
    BEGIN
        SELECT RAISE(ABORT, 'Cierre Z inmutable: no se puede modificar');
    END;
    """,
    """
    CREATE TRIGGER trg_cierre_z_no_delete
    BEFORE DELETE ON cierre_z
    BEGIN
        SELECT RAISE(ABORT, 'Cierre Z inmutable: no se puede borrar');
    END;
    """,
    """
    CREATE TRIGGER trg_cierre_z_desglose_iva_no_update
    BEFORE UPDATE ON cierre_z_desglose_iva
    BEGIN
        SELECT RAISE(ABORT, 'Desglose de IVA del Cierre Z inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_cierre_z_desglose_iva_no_delete
    BEFORE DELETE ON cierre_z_desglose_iva
    BEGIN
        SELECT RAISE(ABORT, 'Desglose de IVA del Cierre Z inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_cierre_z_desglose_pago_no_update
    BEFORE UPDATE ON cierre_z_desglose_pago
    BEGIN
        SELECT RAISE(ABORT, 'Desglose de pago del Cierre Z inmutable');
    END;
    """,
    """
    CREATE TRIGGER trg_cierre_z_desglose_pago_no_delete
    BEFORE DELETE ON cierre_z_desglose_pago
    BEGIN
        SELECT RAISE(ABORT, 'Desglose de pago del Cierre Z inmutable');
    END;
    """,
]

DROP_TRIGGERS_CIERRE_Z: list[str] = [
    "DROP TRIGGER IF EXISTS trg_cierre_z_no_update;",
    "DROP TRIGGER IF EXISTS trg_cierre_z_no_delete;",
    "DROP TRIGGER IF EXISTS trg_cierre_z_desglose_iva_no_update;",
    "DROP TRIGGER IF EXISTS trg_cierre_z_desglose_iva_no_delete;",
    "DROP TRIGGER IF EXISTS trg_cierre_z_desglose_pago_no_update;",
    "DROP TRIGGER IF EXISTS trg_cierre_z_desglose_pago_no_delete;",
]
