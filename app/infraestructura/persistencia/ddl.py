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
#
# NOTA (renombrado FIX Judgment Day round 3 -- disambiguacion, sin cambio de
# comportamiento): esta constante era historicamente `_VENTA_CAMPOS_CONGELADOS`
# (nombre sin sufijo). Se renombra a `_VENTA_CAMPOS_CONGELADOS_0001` porque, a
# HEAD, es la version MUERTA/inerte -- la autoritativa es `_VENTA_CAMPOS_CONGELADOS_V2`
# (mas abajo), aplicada por la migracion 0011. El nombre sin sufijo era un footgun:
# un futuro desarrollador podia editarlo pensando que endurece el trigger vigente,
# sin efecto real a HEAD, y arriesgando romper la cadena de migraciones desde cero
# (ver nota siguiente).
#
# Esta lista alimenta `TRIGGERS` (mas abajo), que la migracion 0001 ejecuta TAL
# CUAL para CREAR el trigger por primera vez en una BD desde cero. Por eso esta
# lista NUNCA debe incluir una columna que no exista todavia en el esquema de la
# migracion 0001 (p. ej. `cualificada`/`destinatario_nombre`/`destinatario_nif`,
# anadidas 8-9 migraciones despues, en 0009/0010): si lo hiciera, migrar una BD desde
# cero fallaria en cuanto CUALQUIER migracion posterior tocara CUALQUIER tabla con
# `batch_alter_table` (SQLite revalida los triggers existentes contra el esquema
# ACTUAL al reescribir una tabla, y `NEW.cualificada` no existiria aun) -- probado
# empiricamente al intentar este mismo cambio (ver git history / apply-progress).
# El endurecimiento POSTERIOR de esta lista (D2 override cerrado, migracion 0011)
# vive en `_VENTA_CAMPOS_CONGELADOS_V2` / `TRIGGER_VENTA_NO_UPDATE_V2`, aplicado por
# esa migracion via DROP+CREATE DESPUES de que esas columnas ya existan.
_VENTA_CAMPOS_CONGELADOS_0001 = " AND ".join(
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
    # (creacion HISTORICA, migracion 0001 -- ver nota sobre
    # `_VENTA_CAMPOS_CONGELADOS_0001` arriba: NO tocar este cuerpo para endurecer
    # campos; usar `TRIGGER_VENTA_NO_UPDATE_V2` + una migracion DROP+CREATE nueva,
    # como 0011).
    f"""
    CREATE TRIGGER trg_venta_no_update
    BEFORE UPDATE ON venta
    FOR EACH ROW
    WHEN OLD.estado <> 'aparcada'
     AND NOT (
        OLD.estado = 'cobrada'
        AND NEW.estado IN ('anulada_con_rastro', 'sustituida')
        AND {_VENTA_CAMPOS_CONGELADOS_0001}
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

# --- Endurecimiento de `trg_venta_no_update` (migracion 0011) ---------------------
# Revision Judgment Day, round 2 (hueco empiricamente probado): el override D2 de
# las migraciones 0009/0010 asumia que una venta `cobrada` ya estaba "totalmente"
# bloqueada salvo el campo `estado` durante la transicion permitida
# `cobrada -> {anulada_con_rastro, sustituida}`. ESO ERA FALSO: el trigger de arriba
# SOLO re-verifica `_VENTA_CAMPOS_CONGELADOS_0001` durante esa transicion -- un UPDATE que
# combinara la transicion PERMITIDA con un cambio de `cualificada`/
# `destinatario_nombre`/`destinatario_nif` en la MISMA sentencia se colaba sin ser
# detectado (violando el invariante 1 de CLAUDE.md). Se confirmo que ningun camino de
# codigo legitimo escribe estas columnas durante esa transicion
# (`ConvertirEnFacturaF3.ejecutar()` las fija UNA SOLA VEZ mientras la F3 aun esta
# `aparcada`, ANTES de `motor.emit`; `NullEngine.cancel` solo escribe `estado`), asi
# que anadirlas aqui no rompe ningun flujo real.
#
# `_VENTA_CAMPOS_CONGELADOS_V2`/`TRIGGER_VENTA_NO_UPDATE_V2` (separados de la version
# HISTORICA de arriba, ver la nota junto a `_VENTA_CAMPOS_CONGELADOS_0001`) son la fuente
# unica de verdad que importa la migracion 0011 para el DROP+CREATE dirigido de
# `trg_venta_no_update` -- se aplican DESPUES de que las migraciones 0009/0010 ya
# hayan anadido esas columnas, por eso es seguro referenciarlas aqui.
_VENTA_CAMPOS_CONGELADOS_V2 = " AND ".join(
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
        "cualificada",
        "destinatario_nombre",
        "destinatario_nif",
    )
)

TRIGGER_VENTA_NO_UPDATE_V2 = f"""
CREATE TRIGGER trg_venta_no_update
BEFORE UPDATE ON venta
FOR EACH ROW
WHEN OLD.estado <> 'aparcada'
 AND NOT (
    OLD.estado = 'cobrada'
    AND NEW.estado IN ('anulada_con_rastro', 'sustituida')
    AND {_VENTA_CAMPOS_CONGELADOS_V2}
 )
BEGIN
    SELECT RAISE(ABORT, 'Venta emitida inmutable (RRSIF art. 8): solo transicion de estado permitida');
END;
"""

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
