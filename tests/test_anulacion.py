"""Anulacion: NullEngine.cancel genera el RegistroAnulacion encadenado."""
from __future__ import annotations

import pytest

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import RegistroFiscal, Venta


def _emitir(crear_sesion, motor, usuario_id):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, [("Neon", "2.50", "2", "21")])
        s.add(venta)
        registro = motor.emit(s, venta)
        return venta.id, registro.id


def test_cancel_genera_anulacion_encadenada(crear_sesion, motor, datos_base):
    venta_id, alta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])

    with crear_sesion() as s, s.begin():
        alta = s.get(RegistroFiscal, alta_id)
        anulacion = motor.cancel(s, alta)
        anulacion_id = anulacion.id

    with crear_sesion() as s:
        anulacion = s.get(RegistroFiscal, anulacion_id)
        alta = s.get(RegistroFiscal, alta_id)
        venta = s.get(Venta, venta_id)

        assert anulacion.tipo_registro == "anulacion"
        assert anulacion.orden == alta.orden + 1
        assert anulacion.registro_alta_anulado_id == alta.id
        assert anulacion.huella_anterior == alta.huella  # encadena con el alta
        assert len(anulacion.huella) == 64
        assert venta.estado == "anulada_con_rastro"

        # La cadena completa (alta + anulacion) sigue verificando.
        informe = motor.verify_chain(s)
        assert informe.ok, informe.errores
        assert informe.registros == 2


def test_no_se_puede_anular_una_venta_no_cobrada(crear_sesion, motor, datos_base):
    venta_id, alta_id = _emitir(crear_sesion, motor, datos_base["usuario_id"])
    # Anular una vez: ok. Anular de nuevo la misma (ya anulada): rechazado.
    with crear_sesion() as s, s.begin():
        motor.cancel(s, s.get(RegistroFiscal, alta_id))
    with crear_sesion() as s, s.begin():
        with pytest.raises(ValueError):
            motor.cancel(s, s.get(RegistroFiscal, alta_id))
