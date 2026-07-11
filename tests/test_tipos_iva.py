"""Casos de uso de mantenimiento de tipos de IVA (maestro), probados sin HTTP.

El tipo de IVA es un parametro fiscal: su alta/edicion/baja se audita, y el cambio de
porcentaje NO altera las ventas ya emitidas (el porcentaje viaja CONGELADO en la linea)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.emitir_venta import EmitirVenta, PagoVenta
from app.aplicacion.lineas import ItemVenta
from app.aplicacion.tipos_iva import (
    DatosTipoIva,
    PorcentajeInvalido,
    ServicioTiposIva,
    TipoIvaNoEncontrado,
)
from app.infraestructura.persistencia.modelos import Articulo, LogAuditoria, TipoIVA, VentaLinea
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _svc(session, datos_base):
    return ServicioTiposIva(
        UnidadDeTrabajoSQL(session), usuario_id=datos_base["usuario_id"], origen="local")


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def test_crear_tipo_iva_persiste_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(
            DatosTipoIva(nombre="Superreducido 4%", porcentaje=Decimal("4.00")))

    with crear_sesion() as s:
        tipo = s.get(TipoIVA, nuevo_id)
        assert tipo is not None
        assert tipo.porcentaje == Decimal("4.00")
        assert tipo.calificacion == "S1"
        assert tipo.activo is True

    logs = _auditorias(crear_sesion, "crear_tipo_iva")
    assert len(logs) == 1
    assert logs[0].entidad_id == str(nuevo_id)


def test_crear_porcentaje_negativo_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PorcentajeInvalido):
            _svc(s, datos_base).crear(DatosTipoIva(nombre="Malo", porcentaje=Decimal("-1")))
    with crear_sesion() as s:
        assert s.query(TipoIVA).filter_by(nombre="Malo").count() == 0


def test_actualizar_cambia_porcentaje_y_audita(crear_sesion, datos_base):
    tipo_id = datos_base["iva10_id"]
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(
            tipo_id, DatosTipoIva(nombre="Reducido 10%", porcentaje=Decimal("8.00")))

    with crear_sesion() as s:
        assert s.get(TipoIVA, tipo_id).porcentaje == Decimal("8.00")

    logs = _auditorias(crear_sesion, "cambio_porcentaje_iva")
    assert len(logs) == 1
    assert "10.00" in logs[0].detalle and "8.00" in logs[0].detalle


def test_actualizar_sin_cambio_de_porcentaje_no_audita_cambio(crear_sesion, datos_base):
    tipo_id = datos_base["iva21_id"]
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(
            tipo_id, DatosTipoIva(nombre="IVA general", porcentaje=Decimal("21.00")))

    assert _auditorias(crear_sesion, "cambio_porcentaje_iva") == []
    assert len(_auditorias(crear_sesion, "actualizar_tipo_iva")) == 1


def test_actualizar_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(TipoIvaNoEncontrado):
            _svc(s, datos_base).actualizar(
                999999, DatosTipoIva(nombre="X", porcentaje=Decimal("21.00")))


def test_desactivar_no_borra(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(
            DatosTipoIva(nombre="Temporal", porcentaje=Decimal("2.00")))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(nuevo_id)

    with crear_sesion() as s:
        tipo = s.get(TipoIVA, nuevo_id)
        assert tipo is not None and tipo.activo is False
    assert len(_auditorias(crear_sesion, "desactivar_tipo_iva")) == 1


def test_cambiar_porcentaje_no_altera_ventas_ya_emitidas(crear_sesion, motor, datos_base):
    """INVARIANTE FISCAL: el porcentaje de la linea esta congelado; editar el tipo de IVA
    despues de emitir NO reescribe la cuota historica."""
    with crear_sesion() as s:
        art = Articulo(nombre="Neon", nombre_corto="Neon",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
        s.add(art)
        s.commit()
        articulo_id = art.id

    with crear_sesion() as s:
        resultado = EmitirVenta(UnidadDeTrabajoSQL(s), motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))])
        venta_id = resultado.venta_id

    # Se cambia el IVA general del 21% al 5% DESPUES de emitir.
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(
            datos_base["iva21_id"], DatosTipoIva(nombre="General", porcentaje=Decimal("5.00")))

    with crear_sesion() as s:
        linea = s.query(VentaLinea).filter_by(venta_id=venta_id).one()
        assert linea.tipo_iva_porcentaje == Decimal("21.00")  # congelado, intacto
