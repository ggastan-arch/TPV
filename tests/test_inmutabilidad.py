"""(a) Los triggers rechazan modificar/borrar una venta emitida y su registro fiscal."""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import RegistroFiscal, Venta


def _emitir(crear_sesion, motor, usuario_id) -> int:
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, [("Neon cardenal", "2.50", "2", "21")])
        s.add(venta)
        motor.emit(s, venta)
        venta_id = venta.id
    return venta_id


def test_no_se_puede_modificar_importe_de_venta_emitida(crear_sesion, motor, datos_base):
    venta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        assert venta.estado == "cobrada"
        venta.total_con_iva = Decimal("999.99")
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_venta_emitida(crear_sesion, motor, datos_base):
    venta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        s.delete(venta)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_modificar_huella_del_registro(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        registro = s.query(RegistroFiscal).one()
        registro.huella = "0" * 64
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_registro_fiscal(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        registro = s.query(RegistroFiscal).one()
        s.delete(registro)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_estado_remision_si_es_editable(crear_sesion, motor, datos_base):
    # El metadato de envio NO forma parte de la huella: debe poder actualizarse.
    _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s, s.begin():
        registro = s.query(RegistroFiscal).one()
        registro.estado_remision = "aceptado"
    with crear_sesion() as s:
        assert s.query(RegistroFiscal).one().estado_remision == "aceptado"


def test_no_se_puede_colar_destinatario_ni_cualificada_en_transicion_permitida(
    crear_sesion, motor, datos_base
):
    """Vector COMBINADO (Judgment Day, revision round 2, empiricamente probado): el
    trigger `trg_venta_no_update` exime la transicion de estado PERMITIDA
    (cobrada -> anulada_con_rastro/sustituida) y SOLO re-verifica los campos listados
    en `_VENTA_CAMPOS_CONGELADOS_0001` durante esa transicion. Antes de la migracion 0011,
    `destinatario_nombre`/`destinatario_nif`/`cualificada` NO estaban en esa lista: un
    UPDATE que combinara la transicion PERMITIDA con un cambio de estos campos, en la
    MISMA sentencia, se colaba sin ser detectado -- esto rompia el invariante 1 de
    CLAUDE.md (ninguna venta emitida se edita, ni a nivel de BD) para el snapshot
    congelado del destinatario de una F1/F3 ya expedida.

    Tambien confirma que los DOS caminos legitimos que SI hacen esa transicion
    (T origen `cobrada -> sustituida` sin destinatario, y `motor.cancel`
    `cobrada -> anulada_con_rastro` sin destinatario) siguen funcionando tras
    endurecer la lista."""
    venta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])

    # Vector combinado: la transicion PERMITIDA coleando, en el MISMO UPDATE, un
    # cambio de destinatario_nombre/destinatario_nif/cualificada.
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        venta.estado = "anulada_con_rastro"
        venta.destinatario_nombre = "HACK"
        venta.destinatario_nif = "B00000000"
        venta.cualificada = True
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        # El rollback deshizo TODO el UPDATE (estado incluido): no hay "exito parcial".
        assert venta.estado == "cobrada"
        assert venta.destinatario_nombre is None
        assert venta.destinatario_nif is None

    # (a) camino legitimo: T origen `cobrada -> sustituida` SIN tocar destinatario
    # (permanece NULL en ambos lados) sigue permitido.
    with crear_sesion() as s, s.begin():
        s.get(Venta, venta_id).estado = "sustituida"
    with crear_sesion() as s:
        assert s.get(Venta, venta_id).estado == "sustituida"

    # (b) camino legitimo: `motor.cancel()` (`cobrada -> anulada_con_rastro`) sin
    # tocar destinatario sigue permitido -- venta NUEVA porque la anterior ya paso
    # a 'sustituida' arriba.
    venta_id_2 = _emitir(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s, s.begin():
        registro = s.query(RegistroFiscal).filter_by(venta_id=venta_id_2).one()
        motor.cancel(s, registro)
    with crear_sesion() as s:
        assert s.get(Venta, venta_id_2).estado == "anulada_con_rastro"


def test_venta_aparcada_si_es_editable(crear_sesion, datos_base):
    # Una venta aun no emitida (aparcada) SI puede modificarse y borrarse.
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Anubias", "6.90", "1", "10")])
        s.add(venta)
        s.flush()
        venta_id = venta.id
    with crear_sesion() as s, s.begin():
        venta = s.get(Venta, venta_id)
        venta.total_con_iva = Decimal("7.00")  # permitido: sigue aparcada
    with crear_sesion() as s, s.begin():
        venta = s.get(Venta, venta_id)
        s.delete(venta)  # permitido


# --- Drift guard (FIX Judgment Day round 3): footgun de las DOS constantes ------
def test_trigger_venta_no_update_no_diverge_de_ddl_v2(engine):
    """`app/infraestructura/persistencia/ddl.py` tiene DOS constantes de campos
    congelados: `_VENTA_CAMPOS_CONGELADOS_0001` (historica, SOLO usada por la
    migracion 0001 para crear el trigger desde cero -- muerta a HEAD, nunca
    tocar) y `_VENTA_CAMPOS_CONGELADOS_V2`/`TRIGGER_VENTA_NO_UPDATE_V2`
    (autoritativa a HEAD, aplicada por la migracion 0011 via DROP+CREATE). Este
    test es la guarda DIRECTA contra el footgun: construye una BD desde cero
    hasta `head` (fixture `engine`, migraciones reales) y compara el cuerpo VIVO
    de `trg_venta_no_update` en `sqlite_master` contra `TRIGGER_VENTA_NO_UPDATE_V2`
    byte a byte. Si una migracion futura anade una columna congelada y olvida el
    DROP+CREATE (o lo hace con un cuerpo distinto de `ddl.py`), este test falla
    inmediatamente -- sin depender de un vector de ataque concreto como
    `test_no_se_puede_colar_destinatario_ni_cualificada_en_transicion_permitida`."""
    from sqlalchemy import text

    from app.infraestructura.persistencia import ddl

    with engine.connect() as conn:
        fila = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'trigger' AND name = 'trg_venta_no_update'"
            )
        ).first()

    assert fila is not None, "trg_venta_no_update no existe en la BD migrada a head"
    # SQLite guarda en `sqlite_master.sql` el texto EXACTO de la sentencia CREATE
    # que se ejecuto, sin el `;` final ni espacios en blanco de borde: se normaliza
    # `TRIGGER_VENTA_NO_UPDATE_V2` de la misma forma para una comparacion justa.
    esperado = ddl.TRIGGER_VENTA_NO_UPDATE_V2.strip().rstrip(";")
    assert fila[0] == esperado
