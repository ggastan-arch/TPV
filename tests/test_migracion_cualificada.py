"""Migracion 0009: `cualificada` en `venta`, columna NATIVA (`op.add_column`).

Guarda de regresion (D2, override de design.md — ver tasks.md "Nota de override"):
NO se toca `trg_venta_no_update` ni `_VENTA_CAMPOS_CONGELADOS`. Una venta `cobrada`
ya esta totalmente congelada por el trigger vigente (ningun UPDATE plano pasa);
ningun codigo cambia el flag durante las transiciones de estado permitidas. `ADD
COLUMN` nativo (no `batch_alter_table`) nunca recrea la tabla: triggers e
invariantes quedan intactos, y la huella de una venta YA EMITIDA bajo el esquema
anterior (revision 0008) no cambia (la columna nueva es ajena a la huella).

Sin ORM: la fila "ya emitida" se inserta con SQL crudo (mismo patron que
test_migracion_aparcar.py) para no depender de que los modelos Python (que YA
declaran `cualificada` una vez implementada la Fase 1) coincidan con el esquema
fisico de la revision 0008, que aun no tiene esa columna."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, inspect, text

from app.dominio.servicios.huella import huella_alta
from app.dominio.servicios.redondeo import calcular_linea

_TRIGGERS_ESPERADOS = {
    "trg_venta_no_update",
    "trg_venta_no_delete",
    "trg_venta_linea_no_update",
    "trg_venta_linea_no_delete",
    "trg_pago_no_update",
    "trg_pago_no_delete",
}


def _emitir_venta_pre_0009(conn) -> dict:
    """Inserta (SQL crudo) una venta ya "emitida" bajo el esquema de la revision
    0008 -- sin `cualificada`, que todavia no existe -- replicando lo que produce
    `NullEngine.emit` (numeracion + registro encadenado + huella real, calculada
    con la funcion de dominio `huella_alta`)."""
    linea = calcular_linea(Decimal("2.50"), Decimal("2"), Decimal("21.00"))

    conn.execute(text(
        "INSERT INTO venta (id, estado, serie, ejercicio, numero, num_serie_factura, "
        "fecha_hora_huso, usuario_id, base_total, cuota_total, total_con_iva) "
        "VALUES (1, 'cobrada', 'T', 2026, 1, 'T2026-000001', "
        "'2026-07-18T10:00:00+02:00', 1, :base, :cuota, :total)"
    ), {"base": str(linea.base), "cuota": str(linea.cuota), "total": str(linea.total)})

    conn.execute(text(
        "INSERT INTO venta_linea (venta_id, descripcion, cantidad, pvp_unitario, "
        "tipo_iva_porcentaje, descuento, base_linea, cuota_linea, total_linea) "
        "VALUES (1, 'Neon cardenal', '2', '2.50', '21.00', '0.00', :base, :cuota, :total)"
    ), {"base": str(linea.base), "cuota": str(linea.cuota), "total": str(linea.total)})

    campos_huella = dict(
        id_emisor="00000000T", num_serie_factura="T2026-000001",
        fecha_expedicion="18-07-2026", tipo_factura="F2",
        cuota_total=linea.cuota, importe_total=linea.total,
        huella_anterior=None, fecha_hora_huso_gen="2026-07-18T10:00:00+02:00",
    )
    huella = huella_alta(**campos_huella)

    conn.execute(text(
        "INSERT INTO registro_fiscal (id, orden, tipo_registro, venta_id, id_emisor, "
        "num_serie_factura, fecha_expedicion, tipo_factura, cuota_total, importe_total, "
        "primer_registro, huella_anterior, huella, tipo_huella, "
        "fecha_hora_huso_gen_registro, estado_remision) "
        "VALUES (1, 1, 'alta', 1, :id_emisor, :num_serie_factura, :fecha_expedicion, "
        ":tipo_factura, :cuota, :importe, 1, NULL, :huella, '01', :fhh, 'no_remitido')"
    ), {
        "id_emisor": campos_huella["id_emisor"],
        "num_serie_factura": campos_huella["num_serie_factura"],
        "fecha_expedicion": campos_huella["fecha_expedicion"],
        "tipo_factura": campos_huella["tipo_factura"],
        "cuota": str(campos_huella["cuota_total"]),
        "importe": str(campos_huella["importe_total"]),
        "huella": huella,
        "fhh": campos_huella["fecha_hora_huso_gen"],
    })
    return {**campos_huella, "huella_original": huella}


def test_migracion_0009_no_rompe_triggers_ni_huella(tmp_path, aplicar_migraciones):
    db = tmp_path / "migracion_cualificada.db"
    url = f"sqlite:///{db}"

    aplicar_migraciones(url, "0008_venta_etiqueta_aparcada")

    engine = create_engine(url)
    with engine.begin() as conn:
        campos = _emitir_venta_pre_0009(conn)
    engine.dispose()

    aplicar_migraciones(url, "head")  # 0009_venta_cualificada

    engine = create_engine(url)

    # 1) columna nueva: existe, NULL-able, y NULL en la fila ya emitida (sin backfill).
    columnas = inspect(engine).get_columns("venta")
    columna = next((c for c in columnas if c["name"] == "cualificada"), None)
    assert columna is not None, "falta la columna cualificada en venta"
    assert columna["nullable"] is True
    with engine.connect() as conn:
        valor = conn.execute(
            text("SELECT cualificada FROM venta WHERE id = 1")
        ).scalar_one()
    assert valor is None

    # 2) los triggers de inmutabilidad SIGUEN presentes: `add_column` nativo no
    #    recrea la tabla (a diferencia de `batch_alter_table`); D2 override: NO se
    #    recrea `trg_venta_no_update` (Opcion B, ver tasks.md).
    with engine.connect() as conn:
        nombres = {
            fila[0] for fila in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            ).all()
        }
    assert _TRIGGERS_ESPERADOS <= nombres, f"faltan triggers: {_TRIGGERS_ESPERADOS - nombres}"

    # 3) un UPDATE ilegal sigue rechazado por el trigger vigente (sin tocar).
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(text("UPDATE venta SET total_con_iva = '999.99' WHERE id = 1"))
            raise AssertionError("el UPDATE ilegal debio ser rechazado por el trigger")
        except Exception as exc:  # noqa: BLE001 - sqlite lanza OperationalError con RAISE(ABORT)
            assert "inmutable" in str(exc).lower()

    # 4) la huella recomputada con los MISMOS campos es identica: la columna
    #    nueva es ajena al hash y no afecta filas ya emitidas.
    huella_recomputada = huella_alta(
        id_emisor=campos["id_emisor"], num_serie_factura=campos["num_serie_factura"],
        fecha_expedicion=campos["fecha_expedicion"], tipo_factura=campos["tipo_factura"],
        cuota_total=campos["cuota_total"], importe_total=campos["importe_total"],
        huella_anterior=campos["huella_anterior"],
        fecha_hora_huso_gen=campos["fecha_hora_huso_gen"],
    )
    assert huella_recomputada == campos["huella_original"]

    with engine.connect() as conn:
        huella_en_bd = conn.execute(
            text("SELECT huella FROM registro_fiscal WHERE id = 1")
        ).scalar_one()
    assert huella_en_bd == campos["huella_original"]
    engine.dispose()
