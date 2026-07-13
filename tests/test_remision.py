"""Repositorio de registros (cola) y caso de uso RemitirLote."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from lxml import etree

from _helpers import construir_venta, respuesta_remision_xml
from app.aplicacion.remitir_lote import RemitirLote
from app.infraestructura.fiscal.remitente import RemisionIncidencia, RemitenteVerifactu, endpoint_verifactu
from app.infraestructura.fiscal.xml import NS, sistema_desde_settings
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import LogAuditoria, RemisionIntento

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
            nombre_emisor="AcuaTPV", nif_obligado="00000000T",
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


# --- Rechazo de cabecera y exclusion de la cola (requiere_intervencion) ---------
def test_rechazo_cabecera_4109_marca_todo_el_lote(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 2)

    def poster(url, headers, body):
        return 200, respuesta_remision_xml([], estado="Incorrecto")

    _remitir(crear_sesion, poster)
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        for reg in repo.ultimos(2):
            assert reg.estado_remision == "requiere_intervencion"
        intentos = s.query(RemisionIntento).all()
        assert len(intentos) == 2
        for intento in intentos:
            assert intento.resultado == "rechazado"
            assert intento.incidencia is False
            assert intento.descripcion is not None and "Incorrecto" in intento.descripcion
        assert repo.contar_pendientes() == 0


def test_requiere_intervencion_no_esta_en_pendientes(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(
            repo.pendientes()[0], "rechazado", codigo_error="4109",
            descripcion="Cabecera incorrecta", estado_remision_final="requiere_intervencion")
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.pendientes() == []
        assert repo.contar_pendientes() == 0
        assert repo.hay_incidencia_pendiente() is False


def test_remitir_duplicado_sale_de_la_cola(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)

    def poster(url, headers, body):
        root = etree.fromstring(body)
        num = root.find(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura").text
        return 200, respuesta_remision_xml(
            [(num, "Incorrecto", 3000, "Registro duplicado", {"estado": "Correcta"})],
            estado="ParcialmenteCorrecto")

    respuesta = _remitir(crear_sesion, poster)
    assert respuesta is not None
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 0
        assert repo.pendientes() == []

    # Segundo intento: no debe reenviarse (ya no esta en pendientes -> lote vacio).
    llamadas = []

    def poster_no_debe_llamarse(url, headers, body):
        llamadas.append(1)
        return 200, respuesta_remision_xml([], estado="Correcto")

    assert _remitir(crear_sesion, poster_no_debe_llamarse) is None
    assert llamadas == []


# --- Reencolar (recuperacion manual + auditoria) --------------------------------
def test_reencolar_devuelve_a_pendiente_y_audita(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        reg = repo.pendientes()[0]
        reg_id = reg.id
        repo.registrar_resultado(
            reg, "rechazado", codigo_error="4109", descripcion="Cabecera incorrecta",
            estado_remision_final="requiere_intervencion")

    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        reg = repo.buscar(reg_id)
        assert reg.estado_remision == "requiere_intervencion"
        repo.reencolar(reg, usuario_id=datos_base["usuario_id"], origen="local")

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.buscar(reg_id).estado_remision == "pendiente"
        assert reg_id in [r.id for r in repo.pendientes()]
        assert s.query(LogAuditoria).filter_by(
            accion="reencolar_remision", entidad_id=str(reg_id)).count() == 1


def test_reencolar_rechaza_si_no_requiere_intervencion(crear_sesion, motor, datos_base):
    """Guarda de precondicion (fix de WARNING de verify): `reencolar()` solo vale
    sobre un registro en 'requiere_intervencion'. Sin esta guarda se podria forzar
    a 'pendiente' CUALQUIER registro (p.ej. uno ya 'aceptado', estado terminal),
    provocando un reenvio no querido a la AEAT."""
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        reg = repo.pendientes()[0]
        reg_id = reg.id
        repo.registrar_resultado(reg, "aceptado", csv="CSV-1")

    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        reg = repo.buscar(reg_id)
        assert reg.estado_remision == "aceptado"
        with pytest.raises(ValueError):
            repo.reencolar(reg, usuario_id=datos_base["usuario_id"], origen="local")

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        # Ni el estado ni la auditoria deben mutar: el rechazo no tiene efectos.
        assert repo.buscar(reg_id).estado_remision == "aceptado"
        assert s.query(LogAuditoria).filter_by(
            accion="reencolar_remision", entidad_id=str(reg_id)).count() == 0


# --- No regresion: comportamiento existente intacto -----------------------------
def test_noregresion_aceptado_incidencia_rechazo_linea(crear_sesion, motor, datos_base):
    """Fuera de alcance de este cambio: el rechazo de linea normal (codigo != 3000,
    sin RegistroDuplicado) sigue clasificado como 'rechazado' y sigue reintentable
    (no pasa a requiere_intervencion); aceptado/aceptado_con_errores e incidencia
    de red se comportan exactamente igual que antes."""
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 3)

    def poster(url, headers, body):
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml(
            [(nums[0], "Correcto", None, None),
             (nums[1], "AceptadoConErrores", None, None),
             (nums[2], "Incorrecto", 4102, "Error de ejemplo, cod != 3000")],
            estado="ParcialmenteCorrecto")

    respuesta = _remitir(crear_sesion, poster)
    assert respuesta is not None
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        regs = {r.num_serie_factura: r for r in repo.ultimos(3)}
        assert regs[respuesta.lineas[0].num_serie_factura].estado_remision == "aceptado"
        assert regs[respuesta.lineas[1].num_serie_factura].estado_remision == "aceptado_con_errores"
        # rechazo de linea normal (cod != 3000): sigue "rechazado", NO requiere_intervencion,
        # y por tanto sigue en pendientes() -> sigue reintentable (fuera de alcance).
        reg_rechazado = regs[respuesta.lineas[2].num_serie_factura]
        assert reg_rechazado.estado_remision == "rechazado"
        assert repo.contar_pendientes() == 1
        assert reg_rechazado.id in [r.id for r in repo.pendientes()]

    # Incidencia de red: sigue dejando el lote pendiente (comportamiento previo intacto).
    def poster_incidencia(url, headers, body):
        raise RemisionIncidencia("sin red")

    assert _remitir(crear_sesion, poster_incidencia) is None
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.contar_pendientes() == 1
        assert repo.hay_incidencia_pendiente() is True
