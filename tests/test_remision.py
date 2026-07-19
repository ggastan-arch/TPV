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
from app.infraestructura.persistencia.modelos import Cliente, LogAuditoria, RemisionIntento

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


# --- Fase 3 (B): flag FacturaSimplificadaArt7273 resuelto por venta al remitir ---
def test_remitir_lote_incluye_flag_cualificada_en_el_xml(crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        venta.cualificada = True
        s.add(venta)
        motor.emit(s, venta)

    capturado: dict = {}

    def poster(url, headers, body):
        capturado["body"] = body
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums])

    _remitir(crear_sesion, poster)
    assert b"FacturaSimplificadaArt7273" in capturado["body"]


def test_remitir_lote_no_cualificada_no_incluye_flag_no_regresion(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], 1)

    capturado: dict = {}

    def poster(url, headers, body):
        capturado["body"] = body
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums])

    _remitir(crear_sesion, poster)
    assert b"FacturaSimplificadaArt7273" not in capturado["body"]


# --- Fase 3: bloque Destinatarios resuelto al remitir (F1/F3) -------------------
# NOTA (fix Judgment Day, riesgo fiscal real -- ver PRIMARY CHANGE): la resolucion
# ya NO lee `venta.cliente` EN VIVO -- lee el SNAPSHOT congelado en
# `venta.destinatario_nombre`/`venta.destinatario_nif`, escrito UNA SOLA VEZ por
# `ConvertirEnFacturaF3` al emitir (migracion 0010). Los tests de abajo simulan
# ese snapshot con asignacion directa (sin pasar por el caso de uso real, igual
# que el resto de este fichero construye ventas "a mano" con `construir_venta`).
def test_remitir_lote_resuelve_destinatario_para_f1_f3(crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        cliente = Cliente(nif="A58818501", nombre="Acuario S.L.")
        s.add(cliente)
        s.flush()
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        venta.cliente_id = cliente.id
        venta.destinatario_nombre = cliente.nombre
        venta.destinatario_nif = cliente.nif
        s.add(venta)
        motor.emit(s, venta, serie="F", ejercicio=datos_base["ejercicio"], tipo_factura="F3")

    capturado: dict = {}

    def poster(url, headers, body):
        capturado["body"] = body
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums])

    _remitir(crear_sesion, poster)
    body = capturado["body"]
    assert b"<sum1:Destinatarios>" in body
    assert b"<sum1:NombreRazon>Acuario S.L.</sum1:NombreRazon>" in body
    assert b"<sum1:NIF>A58818501</sum1:NIF>" in body


def test_remitir_lote_usa_snapshot_congelado_no_cliente_editado_despues(
    crear_sesion, motor, datos_base
):
    """FIX Judgment Day (riesgo fiscal real): el destinatario remitido es el
    SNAPSHOT congelado en la venta al emitir, NUNCA una relectura en vivo de
    `venta.cliente` -- si el cliente se edita DESPUES de emitir (p.ej. antes de
    que la remision FIFO asincrona procese el registro), la AEAT debe recibir el
    MISMO destinatario que se emitio/imprimio en la factura, no el editado."""
    with crear_sesion() as s, s.begin():
        cliente = Cliente(nif="A58818501", nombre="Acuario S.L.")
        s.add(cliente)
        s.flush()
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        venta.cliente_id = cliente.id
        venta.destinatario_nombre = cliente.nombre
        venta.destinatario_nif = cliente.nif
        s.add(venta)
        motor.emit(s, venta, serie="F", ejercicio=datos_base["ejercicio"], tipo_factura="F3")

    # El cliente se edita DESPUES de la emision, ANTES de que RemitirLote actue
    # (cola FIFO asincrona -- exactamente el escenario del hallazgo fiscal).
    with crear_sesion() as s, s.begin():
        cliente_editado = s.query(Cliente).filter_by(nif="A58818501").one()
        cliente_editado.nombre = "Otro Nombre Editado S.L."
        cliente_editado.nif = "B12345674"

    capturado: dict = {}

    def poster(url, headers, body):
        capturado["body"] = body
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums])

    _remitir(crear_sesion, poster)
    body = capturado["body"]
    assert b"<sum1:NombreRazon>Acuario S.L.</sum1:NombreRazon>" in body
    assert b"<sum1:NIF>A58818501</sum1:NIF>" in body
    assert b"Otro Nombre Editado" not in body
    assert b"B12345674" not in body


def test_remitir_lote_f1_f3_sin_destinatario_congelado_marca_requiere_intervencion(
    crear_sesion, motor, datos_base
):
    """Guarda fiscal (fix Judgment Day): un F1/F3 SIN `destinatario_nif` congelado
    (dato inconsistente -- NO deberia ocurrir con el camino real de
    `ConvertirEnFacturaF3`, que siempre lo fija antes de emitir) ya NO se remite
    silenciosamente sin destinatario (comportamiento PREVIO, bug): un `<NIF/>`
    vacio o el bloque `Destinatarios` ausente en un F1/F3 es fiscalmente invalido
    (FALTA_DESTINATARIO, doc Validaciones_Errores_Veri-Factu.pdf 3.1.3.13) y
    bloquearia TODA la cola FIFO si la AEAT lo rechaza. Se marca
    'requiere_intervencion' y se EXCLUYE del sobre enviado."""
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(venta)
        motor.emit(s, venta, serie="F", ejercicio=datos_base["ejercicio"], tipo_factura="F3")

    def poster(url, headers, body):
        pytest.fail("no debe remitirse un F1/F3 sin destinatario congelado (dato invalido)")

    respuesta = _remitir(crear_sesion, poster)
    assert respuesta is None  # nada que enviar: unico registro del lote, invalido

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        reg = repo.ultimos(1)[0]
        assert reg.estado_remision == "requiere_intervencion"
        assert repo.contar_pendientes() == 0


def test_remitir_lote_excluye_solo_el_registro_invalido_resto_del_lote_sigue(
    crear_sesion, motor, datos_base
):
    """La guarda de destinatario faltante NO bloquea el resto del lote: un F3
    valido junto a un F3 sin destinatario congelado -- solo el invalido queda
    `requiere_intervencion`, el valido se remite con normalidad."""
    with crear_sesion() as s, s.begin():
        cliente = Cliente(nif="A58818501", nombre="Acuario S.L.")
        s.add(cliente)
        s.flush()
        f3_valida = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        f3_valida.cliente_id = cliente.id
        f3_valida.destinatario_nombre = cliente.nombre
        f3_valida.destinatario_nif = cliente.nif
        s.add(f3_valida)
        motor.emit(s, f3_valida, serie="F", ejercicio=datos_base["ejercicio"], tipo_factura="F3")
        f3_valida_num = f3_valida.num_serie_factura

        f3_invalida = construir_venta(datos_base["usuario_id"], [("Guppy", "3.00", "1", "21")])
        s.add(f3_invalida)
        motor.emit(s, f3_invalida, serie="F", ejercicio=datos_base["ejercicio"], tipo_factura="F3")
        f3_invalida_num = f3_invalida.num_serie_factura

    capturado: dict = {}

    def poster(url, headers, body):
        capturado["body"] = body
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums])

    respuesta = _remitir(crear_sesion, poster)
    assert respuesta is not None
    assert f3_invalida_num.encode() not in capturado["body"]
    assert f3_valida_num.encode() in capturado["body"]

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        regs = {r.num_serie_factura: r for r in repo.ultimos(2)}
        assert regs[f3_valida_num].estado_remision == "aceptado"
        assert regs[f3_invalida_num].estado_remision == "requiere_intervencion"


# --- Item 7: `_TIPOS_CON_DESTINATARIO` alineado con validaciones_negocio -------
def test_tipos_con_destinatario_alineado_con_validaciones_negocio():
    """`remitir_lote._TIPOS_CON_DESTINATARIO` NUNCA debe divergir silenciosamente
    de `validaciones_negocio.TIPOS_CON_DESTINATARIO` (fuente unica de verdad de
    "que tipos de factura llevan destinatario") -- si R1-R4 (rectificativas) se
    implementan sin tocar `remitir_lote.py`, la resolucion debe aplicarles
    exactamente la misma logica que F1/F3 (incluida la guarda de NIF faltante)."""
    from app.aplicacion import remitir_lote
    from app.dominio.servicios import validaciones_negocio

    assert remitir_lote._TIPOS_CON_DESTINATARIO == validaciones_negocio.TIPOS_CON_DESTINATARIO


# --- Fase 3 (3.7): no regresion -- F2 nunca recibe destinatario -----------------
def test_xml_f2_nunca_recibe_destinatario(crear_sesion, motor, datos_base):
    """Confirma que el camino real (RemitirLote) NUNCA pasa `destinatario` para
    F2, aunque `venta.cliente_id` este fijado (regla AEAT DESTINATARIO_NO_PERMITIDO,
    3.1.3.13; ver tambien test_f2_con_destinatario_rechaza en
    test_validaciones_negocio.py). Nota de ubicacion: tasks.md 3.7 referencia
    `tests/test_xml_validacion.py`, pero esta prueba necesita la infraestructura
    de `RemitirLote`/`Remitente` ya presente en este fichero (mismo patron que
    3.5/3.6): se mantiene aqui junto al resto de pruebas de remision real."""
    with crear_sesion() as s, s.begin():
        cliente = Cliente(nif="A58818501", nombre="Acuario S.L.")
        s.add(cliente)
        s.flush()
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        venta.cliente_id = cliente.id
        s.add(venta)
        motor.emit(s, venta, serie="T", ejercicio=datos_base["ejercicio"], tipo_factura="F2")

    capturado: dict = {}

    def poster(url, headers, body):
        capturado["body"] = body
        root = etree.fromstring(body)
        nums = [e.text for e in root.findall(f".//{_E_SF}IDFactura/{_E_SF}NumSerieFactura")]
        return 200, respuesta_remision_xml([(n, "Correcto", None, None) for n in nums])

    _remitir(crear_sesion, poster)
    assert b"Destinatarios" not in capturado["body"]
