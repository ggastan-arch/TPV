"""Caso de uso EmitirVenta (capa de aplicacion), probado sin HTTP."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.emitir_venta import (
    EmitirVenta,
    PagoVenta,
    TicketVacio,
    UsuarioNoValido,
)
from app.aplicacion.lineas import ArticuloNoExiste, ItemVenta
from app.infraestructura.persistencia.repositorios import RepositorioStockSQL
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import (
    Articulo,
    LogAuditoria,
    MovimientoStock,
    RegistroFiscal,
    Venta,
)


def _uc(session, motor):
    return EmitirVenta(UnidadDeTrabajoSQL(session), motor)


@pytest.fixture
def articulo_neon(session, datos_base):
    a = Articulo(nombre="Neon cardenal", nombre_corto="Neon",
                 tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
    session.add(a)
    session.commit()
    return a.id


def _crear_articulo(
    session, datos_base, *, control_stock: bool, nombre: str, precio_libre: bool = False
) -> int:
    a = Articulo(nombre=nombre, nombre_corto=nombre, tipo_iva_id=datos_base["iva21_id"],
                 pvp=Decimal("3.00"), control_stock=control_stock, precio_libre=precio_libre)
    session.add(a)
    session.commit()
    return a.id


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def _activar_control_stock(crear_sesion) -> None:
    with crear_sesion() as s:
        UnidadDeTrabajoSQL(s).configuracion.fijar_control_stock(True)
        s.commit()


def test_emitir_venta_emite_y_encadena(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("2"))],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )
    assert resultado.num_serie.startswith("T")
    assert resultado.total == "5.00"
    assert resultado.cambio == "5.00"

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.estado == "cobrada"
        assert s.query(RegistroFiscal).filter_by(venta_id=venta.id).count() == 1


def test_ticket_vacio(crear_sesion, motor, datos_base):
    with crear_sesion() as s, pytest.raises(TicketVacio):
        _uc(s, motor).ejecutar(usuario_id=datos_base["usuario_id"], items=[], pagos=[])


def test_usuario_no_valido(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s, pytest.raises(UsuarioNoValido):
        _uc(s, motor).ejecutar(
            usuario_id=999999, items=[ItemVenta(articulo_id=articulo_neon)], pagos=[])


def test_articulo_inexistente(crear_sesion, motor, datos_base):
    with crear_sesion() as s, pytest.raises(ArticuloNoExiste):
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"], items=[ItemVenta(articulo_id=999999)], pagos=[])


# --- Fase 4: efecto de stock en EmitirVenta (design.md, "Punto critico") ------------


def test_efecto_stock_toggle_desactivado_no_crea_movimiento(crear_sesion, motor, datos_base):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Guppy")

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("2"))],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.estado == "cobrada"
        assert s.query(MovimientoStock).count() == 0


def test_efecto_stock_toggle_activado_solo_descuenta_lineas_rastreadas(
    crear_sesion, motor, datos_base
):
    with crear_sesion() as s:
        rastreado_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Guppy")
        no_rastreado_id = _crear_articulo(s, datos_base, control_stock=False, nombre="Planta")
    _activar_control_stock(crear_sesion)

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[
                ItemVenta(articulo_id=rastreado_id, cantidad=Decimal("2")),
                ItemVenta(articulo_id=no_rastreado_id, cantidad=Decimal("1")),
            ],
            pagos=[PagoVenta("efectivo", Decimal("20.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.estado == "cobrada"
        movimientos = s.query(MovimientoStock).all()
        assert len(movimientos) == 1
        assert movimientos[0].articulo_id == rastreado_id
        assert movimientos[0].tipo == "venta"
        assert movimientos[0].cantidad == Decimal("2.000")
        assert movimientos[0].venta_id == venta.id


def test_efecto_stock_fallo_del_repositorio_no_aborta_la_venta(
    crear_sesion, motor, datos_base, monkeypatch
):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Guppy")
    _activar_control_stock(crear_sesion)

    def _agregar_que_falla(self, movimiento):  # noqa: ARG001 - firma del puerto
        raise RuntimeError("fallo simulado del repositorio de stock")

    monkeypatch.setattr(RepositorioStockSQL, "agregar", _agregar_que_falla)

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("2"))],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.estado == "cobrada"
        registro = s.query(RegistroFiscal).filter_by(venta_id=venta.id).one()
        assert len(registro.huella) == 64
        assert registro.huella == registro.huella.upper()
        assert s.query(MovimientoStock).count() == 0


def test_efecto_stock_sobreventa_deja_saldo_negativo_y_alarma_lo_cuenta(
    crear_sesion, motor, datos_base
):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Guppy")
        UnidadDeTrabajoSQL(s).stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="entrada", cantidad=Decimal("1"),
            fecha_hora_huso="2026-07-11T00:00:00+02:00"))
        s.commit()
    _activar_control_stock(crear_sesion)

    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("5"))],
            pagos=[PagoVenta("efectivo", Decimal("20.00"))],
        )

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).stock
        assert repo.stock_actual(articulo_id) == Decimal("-4")
        assert repo.rastreados_en_negativo() == [(articulo_id, Decimal("-4"))]


# --- Edicion de linea: congelado y auditoria de precio manual (invariante 4) ---------


def test_emitir_venta_congela_pvp_override_no_precio_libre(
    crear_sesion, motor, datos_base, articulo_neon
):
    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"), pvp=Decimal("1.00"))],
            pagos=[PagoVenta("efectivo", Decimal("1.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.lineas[0].pvp_unitario == Decimal("1.00")


def test_emitir_venta_congela_descripcion_override(
    crear_sesion, motor, datos_base, articulo_neon
):
    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"),
                             descripcion="Guppy macho - promo")],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.lineas[0].descripcion == "Guppy macho - promo"


def test_emitir_venta_congela_cantidad_editada(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("3"))],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.lineas[0].cantidad == Decimal("3")


def test_emitir_venta_registra_auditoria_precio_manual(
    crear_sesion, motor, datos_base, articulo_neon
):
    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"), pvp=Decimal("1.00"))],
            pagos=[PagoVenta("efectivo", Decimal("1.00"))],
        )

    logs = _auditorias(crear_sesion, "precio_manual_venta")
    assert len(logs) == 1
    assert logs[0].entidad == "venta_linea"
    assert logs[0].detalle == f"articulo {articulo_neon}: catalogo 2.50 -> cobrado 1.00"


def test_emitir_venta_sin_diferencia_precio_no_registra_auditoria(
    crear_sesion, motor, datos_base, articulo_neon
):
    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    assert _auditorias(crear_sesion, "precio_manual_venta") == []


def test_emitir_venta_precio_libre_no_registra_auditoria(crear_sesion, motor, datos_base):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(
            s, datos_base, control_stock=False, nombre="Tridacna", precio_libre=True)

    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("1"), pvp=Decimal("50.00"))],
            pagos=[PagoVenta("efectivo", Decimal("50.00"))],
        )

    assert _auditorias(crear_sesion, "precio_manual_venta") == []
