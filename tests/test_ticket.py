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
