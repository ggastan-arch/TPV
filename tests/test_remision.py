"""Repositorio de registros (cola) y caso de uso RemitirLote."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from lxml import etree

from _helpers import construir_venta, respuesta_remision_xml
from app.aplicacion.remitir_lote import RemitirLote
from app.fiscal.remitente import RemisionIncidencia, RemitenteVerifactu, endpoint_verifactu
from app.fiscal.xml import NS, sistema_desde_settings
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import RemisionIntento

_E_SF = "{%s}" % NS


def _emitir(crear_sesion, motor, usuario_id, n):
    for _ in range(n):
        with crear_sesion() as s, s.begin():
            venta = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
            s.add(venta)
            motor.emit(s, venta)


# --- RepositorioRegistros ------------------------------------------------------
def test_pendientes_fifo_y_contador(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 3)
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 3
        assert [r.orden for r in repo.pendientes()] == [1, 2, 3]
        assert len(repo.pendientes(maximo=2)) == 2


def test_registrar_resultado_aceptado(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        reg = repo.pendientes()[0]
        reg_id = reg.id
        repo.registrar_resultado(reg, "aceptado", csv="CSV-1")
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 1
        assert repo.buscar(reg_id).estado_remision == "aceptado"
        assert s.query(RemisionIntento).filter_by(registro_fiscal_id=reg_id, csv="CSV-1").count() == 1


def test_incidencia_marca_pendiente(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(repo.pendientes()[0], "incidencia", descripcion="sin red")
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 1
        assert repo.hay_incidencia_pendiente() is True


def test_reintento_respeta_intervalo(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(repo.pendientes()[0], "incidencia")
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        ahora = datetime.now().astimezone()
        assert repo.registros_a_reintentar(ahora=ahora) == []
        assert len(repo.registros_a_reintentar(ahora=ahora + timedelta(hours=2))) == 1


def test_registro_sin_intentos_siempre_reintenta(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s:
        assert len(UnidadDeTrabajoSQL(s).registros.registros_a_reintentar()) == 1


def test_intento_remision_append_only(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(repo.pendientes()[0], "rechazado", codigo_error="4102")
    with crear_sesion() as s:
        intento = s.query(RemisionIntento).one()
        intento.resultado = "aceptado"
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


# --- RemitirLote ---------------------------------------------------------------
def _remitir(crear_sesion, poster):
    with crear_sesion() as s:
        rem = RemitenteVerifactu(endpoint=endpoint_verifactu("pruebas"), poster=poster)
        return RemitirLote(UnidadDeTrabajoSQL(s), rem).ejecutar(
            nombre_emisor="Bizkaitropik", nif_obligado="00000000T",
            sistema=sistema_desde_settings())


def test_remitir_actualiza_estados_y_csv(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)

    def poster(url, headers, body):
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums], csv="CSV-LOTE")

    respuesta = _remitir(crear_sesion, poster)
    assert respuesta is not None and respuesta.csv == "CSV-LOTE"
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 0
        assert s.query(RemisionIntento).filter_by(csv="CSV-LOTE").count() == 2


def test_remitir_incidencia_deja_pendientes(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)

    def poster(url, headers, body):
        raise RemisionIncidencia("sin red")

    assert _remitir(crear_sesion, poster) is None
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 2
        assert repo.hay_incidencia_pendiente() is True
