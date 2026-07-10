"""Cola de remision: FIFO, contador de pendientes, resultados, reintento e incidencia."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from _helpers import construir_venta
from app.fiscal.cola import ColaRemision, ResultadoRemision
from app.models import RegistroFiscal, RemisionIntento


def _emitir(crear_sesion, motor, usuario_id, n):
    ids = []
    for _ in range(n):
        with crear_sesion() as s, s.begin():
            venta = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
            s.add(venta)
            reg = motor.emit(s, venta)
            ids.append(reg.id)
    return ids


def test_pendientes_fifo_y_contador(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 3)
    with crear_sesion() as s:
        cola = ColaRemision(s)
        assert cola.contar_pendientes() == 3
        ordenes = [r.orden for r in cola.pendientes()]
        assert ordenes == [1, 2, 3]  # FIFO por orden de generacion


def test_lote_maximo_1000(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 3)
    with crear_sesion() as s:
        assert len(ColaRemision(s).pendientes(maximo=2)) == 2


def test_aceptado_deja_de_estar_pendiente(crear_sesion, motor, datos_base):
    ids = _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)
    with crear_sesion() as s, s.begin():
        cola = ColaRemision(s)
        cola.registrar_resultado(
            s.get(RegistroFiscal, ids[0]),
            ResultadoRemision(resultado="aceptado", csv="CSV-123"),
        )
    with crear_sesion() as s:
        cola = ColaRemision(s)
        assert cola.contar_pendientes() == 1
        reg = s.get(RegistroFiscal, ids[0])
        assert reg.estado_remision == "aceptado"
        intento = s.query(RemisionIntento).filter_by(registro_fiscal_id=ids[0]).one()
        assert intento.resultado == "aceptado"
        assert intento.csv == "CSV-123"


def test_incidencia_marca_pendiente_y_flag(crear_sesion, motor, datos_base):
    ids = _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        ColaRemision(s).registrar_resultado(
            s.get(RegistroFiscal, ids[0]),
            ResultadoRemision(resultado="incidencia", descripcion="sin conexion"),
        )
    with crear_sesion() as s:
        cola = ColaRemision(s)
        assert s.get(RegistroFiscal, ids[0]).estado_remision == "pendiente"
        assert cola.contar_pendientes() == 1
        assert cola.hay_incidencia_pendiente() is True


def test_reintento_respeta_intervalo_horario(crear_sesion, motor, datos_base):
    ids = _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        ColaRemision(s).registrar_resultado(
            s.get(RegistroFiscal, ids[0]),
            ResultadoRemision(resultado="incidencia"),
        )
    with crear_sesion() as s:
        cola = ColaRemision(s)
        ahora = datetime.now().astimezone()
        # Recien intentado: no toca reintentar todavia.
        assert cola.registros_a_reintentar(ahora=ahora) == []
        # Pasada mas de una hora: entra al reintento.
        dentro_de_2h = ahora + timedelta(hours=2)
        a_reintentar = cola.registros_a_reintentar(ahora=dentro_de_2h)
        assert [r.id for r in a_reintentar] == ids


def test_registro_sin_intentos_siempre_se_reintenta(crear_sesion, motor, datos_base):
    ids = _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s:
        cola = ColaRemision(s)
        assert [r.id for r in cola.registros_a_reintentar()] == ids


def test_intento_de_remision_es_append_only(crear_sesion, motor, datos_base):
    ids = _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        ColaRemision(s).registrar_resultado(
            s.get(RegistroFiscal, ids[0]), ResultadoRemision(resultado="rechazado", codigo_error="4102")
        )
    with crear_sesion() as s:
        intento = s.query(RemisionIntento).one()
        intento.resultado = "aceptado"
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()
