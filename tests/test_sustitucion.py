"""Convertir simplificada en factura completa (F3): estructura lista desde fase 1.

No implementa el FLUJO de conversion (fase 2), pero verifica que el modelo lo
soporta: transicion controlada a 'sustituida', enlace de sustitucion, tipo F3 y
bloque FacturasSustituidas, todo inmutable.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import (
    RegistroFacturaSustituida,
    RegistroFiscal,
    Venta,
    VentaSustitucion,
)


def test_convertir_simplificada_en_factura_completa(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    # 1) Simplificada (F2, serie T).
    with crear_sesion() as s, s.begin():
        f2 = construir_venta(usuario_id, [("Neon", "2.50", "2", "21")])
        s.add(f2)
        motor.emit(s, f2, serie="T", ejercicio=ejercicio, tipo_factura="F2")
        f2_id = f2.id
        f2_num = f2.num_serie_factura
        reg_f2 = s.query(RegistroFiscal).filter_by(venta_id=f2_id).one()
        reg_f2_emisor = reg_f2.id_emisor
        reg_f2_fecha = reg_f2.fecha_expedicion

    # 2) Factura completa F3 en sustitucion (serie F), con el bloque FacturasSustituidas
    #    y el enlace de sustitucion; la simplificada pasa a 'sustituida'.
    with crear_sesion() as s, s.begin():
        f3 = construir_venta(usuario_id, [("Neon", "2.50", "2", "21")])
        s.add(f3)
        registro_f3 = motor.emit(s, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
        f3_id = f3.id

        s.add(RegistroFacturaSustituida(
            registro_fiscal_id=registro_f3.id,
            id_emisor=reg_f2_emisor,
            num_serie_factura=f2_num,
            fecha_expedicion=reg_f2_fecha,
        ))
        s.add(VentaSustitucion(venta_sustituta_id=f3_id, venta_sustituida_id=f2_id))

        # Transicion controlada de la simplificada (permitida por el trigger).
        s.get(Venta, f2_id).estado = "sustituida"

    with crear_sesion() as s:
        f2 = s.get(Venta, f2_id)
        f3 = s.get(Venta, f3_id)
        assert f2.estado == "sustituida"
        assert f3.serie == "F"
        registro_f3 = s.query(RegistroFiscal).filter_by(venta_id=f3_id).one()
        assert registro_f3.tipo_factura == "F3"
        sustituidas = registro_f3.facturas_sustituidas
        assert len(sustituidas) == 1
        assert sustituidas[0].num_serie_factura == f2_num
        enlace = s.query(VentaSustitucion).filter_by(venta_sustituida_id=f2_id).one()
        assert enlace.venta_sustituta_id == f3_id


def test_bloque_facturas_sustituidas_es_inmutable(crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        f3 = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(f3)
        registro = motor.emit(s, f3, serie="F", ejercicio=datos_base["ejercicio"],
                              tipo_factura="F3")
        s.add(RegistroFacturaSustituida(
            registro_fiscal_id=registro.id, id_emisor="00000000T",
            num_serie_factura="T2027-000001", fecha_expedicion="2027-07-09",
        ))

    with crear_sesion() as s:
        fila = s.query(RegistroFacturaSustituida).one()
        fila.num_serie_factura = "T2027-999999"
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_modificar_importe_tras_sustituir(crear_sesion, motor, datos_base):
    # Una vez emitida, ni siquiera al pasar a 'sustituida' se tocan los importes.
    with crear_sesion() as s, s.begin():
        f2 = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(f2)
        motor.emit(s, f2, serie="T", ejercicio=datos_base["ejercicio"])
        f2_id = f2.id
    with crear_sesion() as s:
        f2 = s.get(Venta, f2_id)
        f2.estado = "sustituida"
        f2.total_con_iva = Decimal("0.01")  # intento de manipular importe: prohibido
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()
