"""Impresion del ticket ESC/POS con QR (sin hardware, via Dummy)."""
from __future__ import annotations

from escpos.printer import Dummy

from _helpers import construir_venta
from app.infraestructura.fiscal import qr as qr_mod
from app.infraestructura.persistencia.modelos import RegistroFiscal, Venta
from app.infraestructura.impresion.ticket import abrir_cajon, imprimir_ticket


def _emitir_con_lineas(crear_sesion, motor, usuario_id):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(
            usuario_id, [("Neon cardenal", "2.50", "2", "21"), ("Anubias", "6.90", "1", "10")]
        )
        s.add(venta)
        reg = motor.emit(s, venta)
        return venta.id, reg.id


def test_ticket_contiene_datos_y_qr(crear_sesion, motor, datos_base):
    venta_id, reg_id = _emitir_con_lineas(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        registro = s.get(RegistroFiscal, reg_id)
        _ = venta.lineas  # cargar relacion dentro de la sesion
        _ = registro.desglose

        dummy = Dummy()
        imprimir_ticket(dummy, venta, registro)
        salida = dummy.output

        # Contenido de factura simplificada (art. 7 ROF).
        assert registro.num_serie_factura.encode() in salida
        assert registro.fecha_expedicion.encode() in salida
        assert b"NIF:" in salida
        assert b"11,90 EUR" in salida          # total con coma decimal
        assert b"Neon cardenal" in salida
        assert b"QR tributario:" in salida
        assert qr_mod.LEYENDA_CORTA.encode() in salida  # 'VERI*FACTU'

        # El QR nativo incrusta la URL de cotejo en el comando GS ( k.
        assert b"ValidarQR" in salida
        assert b"nif=00000000T" in salida
        # Corte de papel al final.
        assert b"\x1dV" in salida


def test_abrir_cajon_emite_pulso():
    dummy = Dummy()
    abrir_cajon(dummy)
    assert b"\x1bp" in dummy.output  # comando ESC p de apertura de cajon


def test_ticket_demo_marca_documento_de_prueba_sin_qr_real(crear_sesion, motor, datos_base):
    venta_id, reg_id = _emitir_con_lineas(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        registro = s.get(RegistroFiscal, reg_id)
        _ = venta.lineas
        _ = registro.desglose

        dummy = Dummy()
        imprimir_ticket(dummy, venta, registro, demo=True)
        salida = dummy.output

        # Invariante 5: cada documento demo queda marcado sin ambiguedad.
        assert "DOCUMENTO DE PRUEBA".encode() in salida
        assert "SIN VALIDEZ FISCAL".encode() in salida
        # Invariante 7 (indirecto): sin QR de cotejo real ni leyenda VERI*FACTU.
        assert b"ValidarQR" not in salida
        assert qr_mod.LEYENDA_CORTA.encode() not in salida


# --- Fase 3 (B): ticket cualificado (destinatario NIF+domicilio+cuota separada) --
def test_ticket_cualificada_incluye_nif_domicilio_cuota_separada(crear_sesion, motor, datos_base):
    from app.aplicacion.clientes import DatosCliente, ServicioClientes
    from app.infraestructura.persistencia.modelos import Cliente
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501", domicilio="Calle Mayor 1"))

    with crear_sesion() as s, s.begin():
        venta = construir_venta(
            datos_base["usuario_id"],
            [("Neon cardenal", "2.50", "2", "21"), ("Anubias", "6.90", "1", "10")],
        )
        venta.cliente_id = cliente_id
        venta.cualificada = True
        s.add(venta)
        reg = motor.emit(s, venta)
        venta_id, reg_id = venta.id, reg.id

    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        registro = s.get(RegistroFiscal, reg_id)
        cliente = s.get(Cliente, cliente_id)
        _ = venta.lineas
        _ = registro.desglose

        dummy = Dummy()
        imprimir_ticket(dummy, venta, registro, cliente=cliente)
        salida = dummy.output

        assert "Acuario S.L.".encode() in salida
        assert b"A58818501" in salida
        assert "Calle Mayor 1".encode() in salida
        # Cuota separada por tipo (el desglose ya la imprime, sin cambios, D6).
        assert b"IVA 21%" in salida
        assert b"IVA 10%" in salida


def test_ticket_no_cualificado_sin_cambios(crear_sesion, motor, datos_base):
    """Golden: una venta NO cualificada se imprime EXACTAMENTE igual que antes de
    este cambio, con o sin el kwarg `cliente` (ausente/None -> sin destinatario)."""
    venta_id, reg_id = _emitir_con_lineas(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        registro = s.get(RegistroFiscal, reg_id)
        _ = venta.lineas
        _ = registro.desglose

        dummy_llamada_previa = Dummy()
        imprimir_ticket(dummy_llamada_previa, venta, registro)

        dummy_cliente_explicito_none = Dummy()
        imprimir_ticket(dummy_cliente_explicito_none, venta, registro, cliente=None)

        assert dummy_llamada_previa.output == dummy_cliente_explicito_none.output


def test_ticket_produccion_explicito_mantiene_qr_y_leyenda(crear_sesion, motor, datos_base):
    venta_id, reg_id = _emitir_con_lineas(crear_sesion, motor, datos_base["usuario_id"])
    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        registro = s.get(RegistroFiscal, reg_id)
        _ = venta.lineas
        _ = registro.desglose

        dummy = Dummy()
        imprimir_ticket(dummy, venta, registro, demo=False)
        salida = dummy.output

        assert b"ValidarQR" in salida
        assert qr_mod.LEYENDA_CORTA.encode() in salida
        assert "DOCUMENTO DE PRUEBA".encode() not in salida
