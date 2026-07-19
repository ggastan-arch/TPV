"""Migracion 0010: `destinatario_nombre`/`destinatario_nif` en `venta`, columnas
NATIVAS (`op.add_column`).

Guarda de regresion (mismo patron que test_migracion_cualificada.py / migracion
0009): la migracion 0010 en si NO toca `trg_venta_no_update` ni
`_VENTA_CAMPOS_CONGELADOS` (ver ADR en `app/infraestructura/persistencia/ddl.py` y el
comentario de la propia migracion). `ADD COLUMN` nativo (no `batch_alter_table`)
nunca recrea la tabla: triggers e invariantes quedan intactos, y la huella de una
venta YA EMITIDA bajo el esquema anterior (revision 0009) no cambia (las columnas
nuevas son ajenas a la huella).

ACTUALIZACION (Judgment Day, round 2): el analisis original de "una venta `cobrada`
ya esta totalmente congelada" resulto INCOMPLETO -- el trigger solo revisaba
`_VENTA_CAMPOS_CONGELADOS` durante la transicion de estado PERMITIDA, y estas dos
columnas no estaban en esa lista (hueco cerrado en la migracion 0011, ver 3c) mas
abajo). `head` en este fichero ya incluye 0011: este test verifica el estado FINAL
(con el hueco cerrado), no solo el efecto aislado de 0010.

Sin ORM: la fila "ya emitida" se inserta con SQL crudo (mismo patron que
test_migracion_cualificada.py) para no depender de que los modelos Python (que YA
declaran `destinatario_nombre`/`destinatario_nif` una vez implementada la Fase 3.8)
coincidan con el esquema fisico de la revision 0009, que aun no tiene esas
columnas."""
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


def _emitir_venta_pre_0010(conn) -> dict:
    """Inserta (SQL crudo) una venta F3 ya "emitida" bajo el esquema de la revision
    0009 -- sin `destinatario_nombre`/`destinatario_nif`, que todavia no existen --
    replicando lo que produce `NullEngine.emit` (numeracion + registro encadenado +
    huella real, calculada con la funcion de dominio `huella_alta`)."""
    linea = calcular_linea(Decimal("2.50"), Decimal("2"), Decimal("21.00"))

    conn.execute(text(
        "INSERT INTO venta (id, estado, serie, ejercicio, numero, num_serie_factura, "
        "fecha_hora_huso, usuario_id, base_total, cuota_total, total_con_iva) "
        "VALUES (1, 'cobrada', 'F', 2026, 1, 'F2026-000001', "
        "'2026-07-18T10:00:00+02:00', 1, :base, :cuota, :total)"
    ), {"base": str(linea.base), "cuota": str(linea.cuota), "total": str(linea.total)})

    conn.execute(text(
        "INSERT INTO venta_linea (venta_id, descripcion, cantidad, pvp_unitario, "
        "tipo_iva_porcentaje, descuento, base_linea, cuota_linea, total_linea) "
        "VALUES (1, 'Neon cardenal', '2', '2.50', '21.00', '0.00', :base, :cuota, :total)"
    ), {"base": str(linea.base), "cuota": str(linea.cuota), "total": str(linea.total)})

    campos_huella = dict(
        id_emisor="00000000T", num_serie_factura="F2026-000001",
        fecha_expedicion="18-07-2026", tipo_factura="F3",
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


def test_migracion_0010_no_rompe_triggers_ni_huella(tmp_path, aplicar_migraciones):
    db = tmp_path / "migracion_destinatario_f3.db"
    url = f"sqlite:///{db}"

    aplicar_migraciones(url, "0009_venta_cualificada")

    engine = create_engine(url)
    with engine.begin() as conn:
        campos = _emitir_venta_pre_0010(conn)
    engine.dispose()

    aplicar_migraciones(url, "head")  # 0010_venta_destinatario_f3

    engine = create_engine(url)

    # 1) columnas nuevas: existen, NULL-ables, y NULL en la fila ya emitida (sin backfill).
    columnas = {c["name"]: c for c in inspect(engine).get_columns("venta")}
    for nombre in ("destinatario_nombre", "destinatario_nif"):
        assert nombre in columnas, f"falta la columna {nombre} en venta"
        assert columnas[nombre]["nullable"] is True
    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT destinatario_nombre, destinatario_nif FROM venta WHERE id = 1")
        ).one()
    assert fila.destinatario_nombre is None
    assert fila.destinatario_nif is None

    # 2) los triggers de inmutabilidad SIGUEN presentes: `add_column` nativo no
    #    recrea la tabla (a diferencia de `batch_alter_table`); D2 override (mismo
    #    patron que 0009): NO se recrea `trg_venta_no_update`.
    with engine.connect() as conn:
        nombres_triggers = {
            fila[0] for fila in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            ).all()
        }
    assert _TRIGGERS_ESPERADOS <= nombres_triggers, (
        f"faltan triggers: {_TRIGGERS_ESPERADOS - nombres_triggers}"
    )

    # 3) un UPDATE ilegal sigue rechazado por el trigger vigente (sin tocar).
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(text("UPDATE venta SET total_con_iva = '999.99' WHERE id = 1"))
            raise AssertionError("el UPDATE ilegal debio ser rechazado por el trigger")
        except Exception as exc:  # noqa: BLE001 - sqlite lanza OperationalError con RAISE(ABORT)
            assert "inmutable" in str(exc).lower()

    # 3b) tambien se rechaza un intento de "colar" un destinatario en un UPDATE
    #    directo de una venta ya emitida (el trigger bloquea CUALQUIER UPDATE
    #    plano sobre una fila `cobrada`, no solo los campos historicos). OJO: esto
    #    NO cambia estado, asi que ya rechazaba ANTES de la migracion 0011 (el
    #    trigger bloquea CUALQUIER UPDATE fuera de la transicion permitida,
    #    independientemente de que columnas toque) -- da falsa confianza sobre el
    #    vector realmente peligroso, ver 3c).
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(text(
                    "UPDATE venta SET destinatario_nombre = 'Otro', "
                    "destinatario_nif = 'B00000000' WHERE id = 1"
                ))
            raise AssertionError("el UPDATE ilegal debio ser rechazado por el trigger")
        except Exception as exc:  # noqa: BLE001
            assert "inmutable" in str(exc).lower()

    # 3c) el vector COMBINADO (Judgment Day, round 2, empiricamente probado): un
    #    UPDATE que hace la transicion de estado PERMITIDA (cobrada ->
    #    anulada_con_rastro) Y, en la MISMA sentencia, cambia
    #    destinatario_nombre/destinatario_nif, tambien se rechaza -- ANTES de la
    #    migracion 0011 este UPDATE SUCEDIA sin ser detectado (el trigger solo
    #    revisaba `_VENTA_CAMPOS_CONGELADOS` durante la transicion permitida, y esas
    #    dos columnas no estaban en la lista). "head" en este test ya incluye la
    #    migracion 0011 (endurece `trg_venta_no_update`), asi que este bloque
    #    prueba el hueco CERRADO.
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(text(
                    "UPDATE venta SET estado = 'anulada_con_rastro', "
                    "destinatario_nombre = 'HACK', destinatario_nif = 'B00000000' "
                    "WHERE id = 1"
                ))
            raise AssertionError("el UPDATE combinado debio ser rechazado por el trigger")
        except Exception as exc:  # noqa: BLE001
            assert "inmutable" in str(exc).lower()

    # 4) la huella recomputada con los MISMOS campos es identica: las columnas
    #    nuevas son ajenas al hash y no afectan filas ya emitidas.
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


def test_migracion_0011_downgrade_restaura_trigger_anterior(
    tmp_path, aplicar_migraciones, bajar_migraciones
):
    """`downgrade()` de la migracion 0011 restaura EXACTAMENTE el trigger anterior
    (lista SIN `cualificada`/`destinatario_nombre`/`destinatario_nif`): el vector
    combinado, rechazado en `head`, vuelve a "colarse" bajo el trigger de la
    revision 0010 -- prueba que el downgrade hace lo que dice (no solo que no
    rompe nada al bajar)."""
    db = tmp_path / "migracion_0011_downgrade.db"
    url = f"sqlite:///{db}"

    aplicar_migraciones(url, "head")
    engine = create_engine(url)
    with engine.begin() as conn:
        _emitir_venta_pre_0010(conn)  # F3 "emitida" (columnas ya existen en head)
    engine.dispose()

    bajar_migraciones(url, "0010_venta_destinatario_f3")

    engine = create_engine(url)
    with engine.connect() as conn:
        with conn.begin():
            # Bajo el trigger de la revision 0010 (SIN el endurecimiento de 0011)
            # este UPDATE combinado NO debe ser rechazado.
            conn.execute(text(
                "UPDATE venta SET estado = 'anulada_con_rastro', "
                "destinatario_nombre = 'HACK', destinatario_nif = 'B00000000' "
                "WHERE id = 1"
            ))
        fila = conn.execute(
            text("SELECT estado, destinatario_nombre, destinatario_nif FROM venta WHERE id = 1")
        ).one()
    assert fila.estado == "anulada_con_rastro"
    assert fila.destinatario_nombre == "HACK"
    assert fila.destinatario_nif == "B00000000"
    engine.dispose()
