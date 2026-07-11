"""Casos de uso de stock informativo (`RegistrarEntrada`, `RegistrarMerma`,
`ConsultarStock`), probados sin HTTP. Independientes del ajuste global de empresa
(design.md): solo exigen `Articulo.control_stock = true` (el admin puede preparar
el stock antes de activar el control). Reglas verificadas: persistencia + auditoria
(invariante 4), rechazo de merma sin motivo, rechazo de cantidad <= 0 y rechazo de
artículo no rastreado."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.stock import (
    ArticuloNoRastreado,
    CantidadInvalida,
    ConsultarStock,
    MotivoRequerido,
    RegistrarEntrada,
    RegistrarMerma,
)
from app.infraestructura.persistencia.modelos import Articulo, LogAuditoria, MovimientoStock
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _crear_articulo(session, datos_base, *, control_stock: bool, nombre: str = "Guppy") -> int:
    articulo = Articulo(nombre=nombre, nombre_corto=nombre,
                         tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00"),
                         control_stock=control_stock)
    session.add(articulo)
    session.commit()
    return articulo.id


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def test_registrar_entrada_persiste_y_audita(crear_sesion, datos_base, session):
    articulo_id = _crear_articulo(session, datos_base, control_stock=True)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        movimiento_id = RegistrarEntrada(uow).ejecutar(
            articulo_id=articulo_id, cantidad=Decimal("10"),
            usuario_id=datos_base["usuario_id"])

    with crear_sesion() as s:
        movimiento = s.get(MovimientoStock, movimiento_id)
        assert movimiento.tipo == "entrada"
        assert movimiento.cantidad == Decimal("10.000")
        assert movimiento.articulo_id == articulo_id

    logs = _auditorias(crear_sesion, "registrar_entrada_stock")
    assert len(logs) == 1
    assert logs[0].entidad_id == str(articulo_id)
    assert logs[0].usuario_id == datos_base["usuario_id"]


def test_registrar_merma_con_motivo_persiste_y_audita(crear_sesion, datos_base, session):
    articulo_id = _crear_articulo(session, datos_base, control_stock=True)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        movimiento_id = RegistrarMerma(uow).ejecutar(
            articulo_id=articulo_id, cantidad=Decimal("2"), motivo="rotura de bolsa",
            usuario_id=datos_base["usuario_id"])

    with crear_sesion() as s:
        movimiento = s.get(MovimientoStock, movimiento_id)
        assert movimiento.tipo == "merma"
        assert movimiento.motivo == "rotura de bolsa"

    logs = _auditorias(crear_sesion, "registrar_merma_stock")
    assert len(logs) == 1


def test_registrar_merma_sin_motivo_rechaza_y_no_persiste(crear_sesion, datos_base, session):
    articulo_id = _crear_articulo(session, datos_base, control_stock=True)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        with pytest.raises(MotivoRequerido):
            RegistrarMerma(uow).ejecutar(
                articulo_id=articulo_id, cantidad=Decimal("2"), motivo="   ",
                usuario_id=datos_base["usuario_id"])

    with crear_sesion() as s:
        assert s.query(MovimientoStock).count() == 0


def test_registrar_entrada_cantidad_cero_o_negativa_rechaza(crear_sesion, datos_base, session):
    articulo_id = _crear_articulo(session, datos_base, control_stock=True)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        with pytest.raises(CantidadInvalida):
            RegistrarEntrada(uow).ejecutar(
                articulo_id=articulo_id, cantidad=Decimal("0"),
                usuario_id=datos_base["usuario_id"])
        with pytest.raises(CantidadInvalida):
            RegistrarEntrada(uow).ejecutar(
                articulo_id=articulo_id, cantidad=Decimal("-5"),
                usuario_id=datos_base["usuario_id"])

    with crear_sesion() as s:
        assert s.query(MovimientoStock).count() == 0


def test_registrar_entrada_articulo_con_control_stock_false_rechaza(crear_sesion, datos_base, session):
    articulo_id = _crear_articulo(session, datos_base, control_stock=False)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        with pytest.raises(ArticuloNoRastreado):
            RegistrarEntrada(uow).ejecutar(
                articulo_id=articulo_id, cantidad=Decimal("5"),
                usuario_id=datos_base["usuario_id"])


def test_registrar_entrada_articulo_inexistente_rechaza(crear_sesion, datos_base):
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        with pytest.raises(ArticuloNoRastreado):
            RegistrarEntrada(uow).ejecutar(
                articulo_id=999999, cantidad=Decimal("5"),
                usuario_id=datos_base["usuario_id"])


def test_consultar_stock_devuelve_saldo_y_articulos_en_negativo(crear_sesion, datos_base, session):
    articulo_id = _crear_articulo(session, datos_base, control_stock=True)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        RegistrarEntrada(uow).ejecutar(
            articulo_id=articulo_id, cantidad=Decimal("3"),
            usuario_id=datos_base["usuario_id"])

    with crear_sesion() as s:
        consulta = ConsultarStock(UnidadDeTrabajoSQL(s))
        assert consulta.stock_de(articulo_id) == Decimal("3")

        RegistrarMerma(UnidadDeTrabajoSQL(s)).ejecutar(
            articulo_id=articulo_id, cantidad=Decimal("5"), motivo="mortandad",
            usuario_id=datos_base["usuario_id"])

    with crear_sesion() as s:
        consulta = ConsultarStock(UnidadDeTrabajoSQL(s))
        assert consulta.stock_de(articulo_id) == Decimal("-2")
        assert consulta.articulos_en_negativo() == [(articulo_id, Decimal("-2"))]
