"""El sobre RegFactuSistemaFacturacion valida contra el XSD SuministroLR."""
from __future__ import annotations

import pytest

from _helpers import construir_venta
from app.fiscal import validacion
from app.fiscal.xml import (
    Cabecera,
    envelope_remision,
    registro_alta_xml,
    registro_anulacion_xml,
    sistema_desde_settings,
)
from app.models import RegistroFiscal

SISTEMA = sistema_desde_settings()
EMISOR = "Bizkaitropik"
CABECERA = Cabecera(nombre_obligado=EMISOR, nif_obligado="00000000T")


def test_sobre_con_alta_y_anulacion_valida_xsd(crear_sesion, motor, datos_base):
    # Emitir un alta y anularla -> 2 registros encadenados.
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "2", "21")])
        s.add(venta)
        alta = motor.emit(s, venta)
        alta_id = alta.id
    with crear_sesion() as s, s.begin():
        motor.cancel(s, s.get(RegistroFiscal, alta_id))

    with crear_sesion() as s:
        alta = s.get(RegistroFiscal, alta_id)
        anulacion = s.query(RegistroFiscal).filter_by(tipo_registro="anulacion").one()
        anterior_anulacion = s.get(RegistroFiscal, anulacion.registro_anterior_id)

        alta_xml = registro_alta_xml(alta, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None)
        anulacion_xml = registro_anulacion_xml(
            anulacion, sistema=SISTEMA, anterior=anterior_anulacion
        )
        sobre = envelope_remision([alta_xml, anulacion_xml], cabecera=CABECERA)

        assert validacion.errores_remision(sobre) == []


def test_sobre_con_incidencia_valida_xsd(crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(venta)
        alta = motor.emit(s, venta)
        alta_id = alta.id
    with crear_sesion() as s:
        alta = s.get(RegistroFiscal, alta_id)
        alta_xml = registro_alta_xml(alta, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None)
        cabecera = Cabecera(nombre_obligado=EMISOR, nif_obligado="00000000T", incidencia=True)
        sobre = envelope_remision([alta_xml], cabecera=cabecera)
        assert validacion.errores_remision(sobre) == []


def test_sobre_rechaza_mas_de_1000_registros():
    with pytest.raises(ValueError):
        envelope_remision([], cabecera=CABECERA)
