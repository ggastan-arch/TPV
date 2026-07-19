"""Caso de uso ConvertirEnFacturaF3 (capa de aplicacion), probado sin HTTP.

Formaliza el flujo "convertir en factura" (spec conversion-factura-f3):
elegibilidad, N->1 atomico, destinatario inline, auditoria e integridad de
cadena. Mirror de tests/test_emitir_venta.py (mismo patron `_uc`)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from _helpers import construir_venta
from app.aplicacion.convertir_en_factura_f3 import (
    ConvertirEnFacturaF3,
    DatosDestinatario,
    DestinatarioInvalido,
    SimplificadaNoElegible,
    YaSustituida,
)
from app.infraestructura.persistencia.modelos import (
    Cliente,
    LogAuditoria,
    RegistroFacturaSustituida,
    RegistroFiscal,
    Venta,
    VentaSustitucion,
)
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _uc(session, motor):
    return ConvertirEnFacturaF3(UnidadDeTrabajoSQL(session), motor)


_DESTINATARIO_OK = DatosDestinatario(
    nif="A58818501", nombre="Acuario S.L.", domicilio="Calle Mayor 1"
)


def _emitir_t(session, motor, usuario_id, ejercicio, lineas_spec) -> int:
    t = construir_venta(usuario_id, lineas_spec)
    session.add(t)
    motor.emit(session, t, serie="T", ejercicio=ejercicio, tipo_factura="F2")
    return t.id


def _emitir_t_aparcada(session, usuario_id) -> int:
    t = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
    session.add(t)
    session.flush()
    return t.id


# --- 2.1: elegibilidad rechaza no cobrada / no T / inexistente ----------------------


def test_elegibilidad_rechaza_no_cobrada_no_t_o_inexistente(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        aparcada_id = _emitir_t_aparcada(s, usuario_id)
        f = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
        s.add(f)
        motor.emit(s, f, serie="F", ejercicio=ejercicio, tipo_factura="F1")
        f_id = f.id

    for id_no_elegible in (999999, aparcada_id, f_id):
        with crear_sesion() as s, pytest.raises(SimplificadaNoElegible):
            _uc(s, motor).ejecutar(
                usuario_id=usuario_id, origen="local",
                simplificada_ids=[id_no_elegible], destinatario=_DESTINATARIO_OK,
            )


# --- 2.3: convertir dos veces la misma T falla con YaSustituida (no excepcion cruda) -


def _crear_t_ya_sustituida(session, motor, usuario_id, ejercicio) -> int:
    """T cobrada y luego marcada 'sustituida' a mano (mismo patron manual que
    tests/test_sustitucion.py), SIN pasar por el caso de uso -- a esta altura del
    desarrollo (fase 2.3) el caso de uso aun no implementa el camino feliz."""
    t = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
    session.add(t)
    motor.emit(session, t, serie="T", ejercicio=ejercicio, tipo_factura="F2")
    t_id = t.id

    f3 = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
    session.add(f3)
    motor.emit(session, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
    session.add(VentaSustitucion(venta_sustituta_id=f3.id, venta_sustituida_id=t_id))
    session.get(Venta, t_id).estado = "sustituida"
    return t_id


def test_convertir_dos_veces_una_t_falla(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _crear_t_ya_sustituida(s, motor, usuario_id, ejercicio)

    with crear_sesion() as s, pytest.raises(YaSustituida):
        _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_id], destinatario=_DESTINATARIO_OK,
        )


# --- ids duplicados en una misma llamada se deduplican (no IntegrityError cruda) ----


def test_ids_duplicados_se_deduplican(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "2", "21")])

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_id, t_id], destinatario=_DESTINATARIO_OK,
        )

    assert resultado.num_origenes == 1  # el id repetido cuenta una sola vez

    with crear_sesion() as s:
        t = s.get(Venta, t_id)
        assert t.estado == "sustituida"
        f3 = s.get(Venta, resultado.venta_id)
        assert len(f3.lineas) == 1  # las lineas NO se duplican
        assert f3.total_con_iva == t.total_con_iva  # los totales NO se doblan
        assert s.query(VentaSustitucion).filter_by(venta_sustituida_id=t_id).count() == 1


# --- elegibilidad se fia de VentaSustitucion, no solo del campo estado --------------


def _crear_t_con_sustitucion_pero_estado_inconsistente(session, motor, usuario_id, ejercicio) -> int:
    """T cobrada con un `VentaSustitucion` ya registrado pero SIN actualizar su
    estado a 'sustituida' (simula la inconsistencia "dos fuentes de verdad" que
    `_validar_elegible` debe cubrir fiandose de `VentaSustitucion`, no solo del
    campo `estado`)."""
    t = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
    session.add(t)
    motor.emit(session, t, serie="T", ejercicio=ejercicio, tipo_factura="F2")
    t_id = t.id

    f3 = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
    session.add(f3)
    motor.emit(session, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
    session.add(VentaSustitucion(venta_sustituta_id=f3.id, venta_sustituida_id=t_id))
    # A proposito NO se marca t.estado = "sustituida": el UNIQUE de BD ya
    # impediria una segunda sustitucion, pero la elegibilidad NO debe depender
    # solo de ese campo.
    return t_id


def test_elegibilidad_rechaza_id_en_venta_sustitucion_aunque_estado_no_lo_diga(
    crear_sesion, motor, datos_base
):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _crear_t_con_sustitucion_pero_estado_inconsistente(
            s, motor, usuario_id, ejercicio
        )

    with crear_sesion() as s, pytest.raises(YaSustituida):
        _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_id], destinatario=_DESTINATARIO_OK,
        )


# --- 2.5: NIF de destinatario invalido rechaza sin persistir nada -------------------


def test_nif_destinatario_invalido(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "1", "21")])

    destinatario_invalido = DatosDestinatario(
        nif="A58818500",  # digito de control incorrecto (correcto es 1)
        nombre="Acuario S.L.", domicilio="Calle Mayor 1",
    )

    with crear_sesion() as s, pytest.raises(DestinatarioInvalido):
        _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_id], destinatario=destinatario_invalido,
        )

    with crear_sesion() as s:
        t = s.get(Venta, t_id)
        assert t.estado == "cobrada"  # nada cambio: rechazo antes de tocar la sesion


# --- art. 6 ROF: nombre/domicilio del destinatario vacios rechaza sin persistir -----


def test_destinatario_con_nombre_o_domicilio_vacio_rechaza(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "1", "21")])

    destinatarios_invalidos = [
        DatosDestinatario(nif="A58818501", nombre="", domicilio="Calle Mayor 1"),
        DatosDestinatario(nif="A58818501", nombre="   ", domicilio="Calle Mayor 1"),
        DatosDestinatario(nif="A58818501", nombre="Acuario S.L.", domicilio=""),
        DatosDestinatario(nif="A58818501", nombre="Acuario S.L.", domicilio="   "),
    ]

    for destinatario in destinatarios_invalidos:
        with crear_sesion() as s, pytest.raises(DestinatarioInvalido):
            _uc(s, motor).ejecutar(
                usuario_id=usuario_id, origen="local",
                simplificada_ids=[t_id], destinatario=destinatario,
            )

    with crear_sesion() as s:
        t = s.get(Venta, t_id)
        assert t.estado == "cobrada"  # nada cambio: rechazo antes de tocar la sesion


# --- 2.7: convertir una sola simplificada (N=1) --------------------------------------


def test_convertir_una_sola_simplificada_n1(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "2", "21")])

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_id], destinatario=_DESTINATARIO_OK,
        )

    assert resultado.num_serie.startswith("F")
    assert resultado.num_origenes == 1

    with crear_sesion() as s:
        t = s.get(Venta, t_id)
        assert t.estado == "sustituida"
        f3 = s.get(Venta, resultado.venta_id)
        assert f3.serie == "F"
        assert f3.estado == "cobrada"
        assert f3.cliente_id is not None
        registro_f3 = s.query(RegistroFiscal).filter_by(venta_id=f3.id).one()
        assert registro_f3.tipo_factura == "F3"
        sustituidas = registro_f3.facturas_sustituidas
        assert len(sustituidas) == 1
        assert sustituidas[0].num_serie_factura == t.num_serie_factura
        enlace = s.query(VentaSustitucion).filter_by(venta_sustituida_id=t_id).one()
        assert enlace.venta_sustituta_id == f3.id


# --- 2.9 / 2.10: IVA mixto y reconciliacion de totales sin re-redondeo ---------------


def test_convertir_dos_simplificadas_iva_mixto_en_una_f3(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t1_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "2", "21")])
        t2_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Musgo de Java", "3.00", "1", "10")])

    with crear_sesion() as s:
        t1_total = s.get(Venta, t1_id).total_con_iva
        t2_total = s.get(Venta, t2_id).total_con_iva

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t1_id, t2_id], destinatario=_DESTINATARIO_OK,
        )

    with crear_sesion() as s:
        registro_f3 = s.query(RegistroFiscal).filter_by(venta_id=resultado.venta_id).one()
        assert registro_f3.importe_total == t1_total + t2_total
        porcentajes = {d.tipo_impositivo for d in registro_f3.desglose}
        assert porcentajes == {Decimal("21.00"), Decimal("10.00")}


def test_totales_f3_reconcilian_sin_deriva(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t1_id = _emitir_t(s, motor, usuario_id, ejercicio, [
            ("Neon", "0.33", "3", "21"), ("Guppy", "1.11", "7", "21"),
        ])
        t2_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Musgo", "2.99", "5", "10")])

    with crear_sesion() as s:
        t1 = s.get(Venta, t1_id)
        t2 = s.get(Venta, t2_id)
        suma_total = t1.total_con_iva + t2.total_con_iva
        suma_cuota = t1.cuota_total + t2.cuota_total

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t1_id, t2_id], destinatario=_DESTINATARIO_OK,
        )

    with crear_sesion() as s:
        registro_f3 = s.query(RegistroFiscal).filter_by(venta_id=resultado.venta_id).one()
        assert registro_f3.importe_total == suma_total
        assert registro_f3.cuota_total == suma_cuota


# --- 2.11: rechazo atomico si una de las T no es elegible ----------------------------


def test_rechazo_atomico_si_una_t_no_es_elegible(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_elegible_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "1", "21")])
        t_sustituida_id = _crear_t_ya_sustituida(s, motor, usuario_id, ejercicio)

    with crear_sesion() as s:
        ventas_antes = s.query(Venta).count()
        registros_antes = s.query(RegistroFiscal).count()
        clientes_antes = s.query(Cliente).count()
        facturas_sustituidas_antes = s.query(RegistroFacturaSustituida).count()
        sustituciones_antes = s.query(VentaSustitucion).count()

    with crear_sesion() as s, pytest.raises(YaSustituida):
        _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_elegible_id, t_sustituida_id], destinatario=_DESTINATARIO_OK,
        )

    with crear_sesion() as s:
        assert s.query(Venta).count() == ventas_antes
        assert s.query(RegistroFiscal).count() == registros_antes
        assert s.query(Cliente).count() == clientes_antes  # no partial persist (2.11)
        assert s.query(RegistroFacturaSustituida).count() == facturas_sustituidas_antes
        assert s.query(VentaSustitucion).count() == sustituciones_antes
        assert s.get(Venta, t_elegible_id).estado == "cobrada"


# --- 2.12: la conversion registra auditoria "conversion_f3" --------------------------


def test_conversion_registra_auditoria_conversion_f3(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t1_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "1", "21")])
        t2_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Guppy", "3.00", "1", "21")])

    with crear_sesion() as s:
        t1_num = s.get(Venta, t1_id).num_serie_factura
        t2_num = s.get(Venta, t2_id).num_serie_factura

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t1_id, t2_id], destinatario=_DESTINATARIO_OK,
        )

    with crear_sesion() as s:
        log = s.query(LogAuditoria).filter_by(accion="conversion_f3").one()
        assert log.entidad == "venta"
        assert log.entidad_id == str(resultado.venta_id)
        assert t1_num in log.detalle
        assert t2_num in log.detalle


# --- 2.14: verify_chain sigue OK tras la conversion ----------------------------------


def test_verify_chain_ok_tras_conversion_f3(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t1_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "1", "21")])
        t2_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Guppy", "3.00", "1", "21")])

    with crear_sesion() as s:
        informe_antes = motor.verify_chain(s)

    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t1_id, t2_id], destinatario=_DESTINATARIO_OK,
        )

    with crear_sesion() as s:
        informe_despues = motor.verify_chain(s)

    assert informe_despues.ok is True
    assert informe_despues.registros == informe_antes.registros + 1


# --- 2.15 (regresion): importes de la T congelados tras sustituir -------------------


def test_importes_t_congelados_tras_sustituir(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        t_id = _emitir_t(s, motor, usuario_id, ejercicio, [("Neon", "2.50", "1", "21")])

    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=[t_id], destinatario=_DESTINATARIO_OK,
        )

    with crear_sesion() as s:
        t = s.get(Venta, t_id)
        assert t.estado == "sustituida"
        t.total_con_iva = Decimal("0.01")  # intento de manipular importe: prohibido
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()
