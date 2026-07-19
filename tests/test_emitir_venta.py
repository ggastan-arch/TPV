"""Caso de uso EmitirVenta (capa de aplicacion), probado sin HTTP."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.clientes import DatosCliente, ServicioClientes
from app.aplicacion.emitir_venta import (
    CualificadaSinDatos,
    EmitirVenta,
    PagoVenta,
    TicketVacio,
    UsuarioNoValido,
)
from app.aplicacion.lineas import ArticuloNoExiste, DescripcionRequerida, ItemVenta
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
    session, datos_base, *, control_stock: bool, nombre: str, modo_precio: str = "fijo"
) -> int:
    a = Articulo(nombre=nombre, nombre_corto=nombre, tipo_iva_id=datos_base["iva21_id"],
                 pvp=Decimal("3.00"), control_stock=control_stock, modo_precio=modo_precio)
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


def test_emitir_venta_congela_pvp_override_modo_fijo(
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


def test_emitir_venta_registra_auditoria_precio_manual_modo_fijo(
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


def test_emitir_venta_registra_auditoria_precio_manual_modo_al_peso(
    crear_sesion, motor, datos_base
):
    """`al_peso` audita igual que `fijo`: solo `libre` esta exento (invariante 4)."""
    with crear_sesion() as s:
        madera = Articulo(nombre="Madera flotante", nombre_corto="Madera",
                          tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("4.50"),
                          modo_precio="al_peso")
        s.add(madera)
        s.commit()
        madera_id = madera.id

    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=madera_id, cantidad=Decimal("1.000"),
                             pvp=Decimal("5.00"))],
            pagos=[PagoVenta("efectivo", Decimal("5.00"))],
        )

    logs = _auditorias(crear_sesion, "precio_manual_venta")
    assert len(logs) == 1
    assert logs[0].detalle == f"articulo {madera_id}: catalogo 4.50 -> cobrado 5.00"


def test_emitir_venta_modo_libre_no_registra_auditoria(crear_sesion, motor, datos_base):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(
            s, datos_base, control_stock=False, nombre="Tridacna", modo_precio="libre")

    with crear_sesion() as s:
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("1"), pvp=Decimal("50.00"),
                             descripcion="Tridacna maxima - ejemplar unico")],
            pagos=[PagoVenta("efectivo", Decimal("50.00"))],
        )

    assert _auditorias(crear_sesion, "precio_manual_venta") == []


# --- Fase 4: modo libre exige descripcion al EMITIR (no en /calcular) ---------


@pytest.mark.parametrize("descripcion", [None, "   "])
def test_emitir_venta_modo_libre_sin_descripcion_rechaza(
    crear_sesion, motor, datos_base, descripcion
):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(
            s, datos_base, control_stock=False, nombre="Generico", modo_precio="libre")

    with crear_sesion() as s, pytest.raises(DescripcionRequerida):
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("1"), pvp=Decimal("10.00"),
                             descripcion=descripcion)],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0
        assert s.query(RegistroFiscal).count() == 0


def test_emitir_venta_modo_libre_con_descripcion_ok(crear_sesion, motor, datos_base):
    with crear_sesion() as s:
        articulo_id = _crear_articulo(
            s, datos_base, control_stock=False, nombre="Generico", modo_precio="libre")

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("1"), pvp=Decimal("10.00"),
                             descripcion="Roca decorativa 2kg")],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.lineas[0].descripcion == "Roca decorativa 2kg"


def test_emitir_venta_articulo_migrado_modo_libre_no_regresion(crear_sesion, motor, datos_base):
    """Articulo que ANTES de la migracion 0007 tenia `precio_libre=True`: tras migrar
    a `modo_precio='libre'`, se emite igual que antes (con descripcion) y sin auditoria."""
    with crear_sesion() as s:
        articulo_id = _crear_articulo(
            s, datos_base, control_stock=False, nombre="Tridacna migrada", modo_precio="libre")

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_id, cantidad=Decimal("1"), pvp=Decimal("50.00"),
                             descripcion="Tridacna maxima - ejemplar unico")],
            pagos=[PagoVenta("efectivo", Decimal("50.00"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.estado == "cobrada"
        assert venta.lineas[0].pvp_unitario == Decimal("50.00")

    assert _auditorias(crear_sesion, "precio_manual_venta") == []


# --- cliente-en-venta (Fase 2/A): cliente_id opcional en EmitirVenta.ejecutar --------


def test_emitir_venta_persiste_cliente_id_opcional(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(DatosCliente(nombre="Juan Perez"))

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
            cliente_id=cliente_id,
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.cliente_id == cliente_id


def test_emitir_venta_sin_cliente_id_no_regresion(crear_sesion, motor, datos_base, articulo_neon):
    """Llamada existente sin `cliente_id`: se comporta exactamente igual que antes
    de este cambio (no-regresion, ver specs/tpv-venta)."""
    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.cliente_id is None


# --- cliente-en-venta (Fase 3/B): simplificada cualificada (art. 7.2/7.3 ROF) --------


def test_cualificada_sin_nif_o_domicilio_rechaza(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Sin datos"))  # sin nif ni domicilio

    with crear_sesion() as s, pytest.raises(CualificadaSinDatos):
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
            cliente_id=cliente_id, cualificada=True,
        )

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0


def test_cualificada_con_cliente_inactivo_rechaza(crear_sesion, motor, datos_base, articulo_neon):
    """Judgment Day W-2: un cliente `activo=False` (baja logica RGPD, ver
    ServicioClientes.desactivar) con NIF+domicilio completos NO debe poder
    sostener una simplificada cualificada -- la baja logica debe pesar tanto
    como la falta de NIF/domicilio."""
    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501", domicilio="Calle Mayor 1"))
        ServicioClientes(UnidadDeTrabajoSQL(s)).desactivar(cliente_id)

    with crear_sesion() as s, pytest.raises(CualificadaSinDatos):
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
            cliente_id=cliente_id, cualificada=True,
        )

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0


def test_cualificada_sin_cliente_asignado_rechaza(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s, pytest.raises(CualificadaSinDatos):
        _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
            cualificada=True,
        )


def test_cualificada_con_datos_completos_marca_venta(crear_sesion, motor, datos_base, articulo_neon):
    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501", domicilio="Calle Mayor 1"))

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
            cliente_id=cliente_id, cualificada=True,
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert venta.cualificada is True


def test_sin_cualificada_no_marca_venta_aunque_cliente_este_completo(
    crear_sesion, motor, datos_base, articulo_neon
):
    """Asignar un cliente con NIF+domicilio completos NO auto-marca la venta como
    cualificada (spec: 'Asignar cliente no auto-marca cualificada')."""
    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501", domicilio="Calle Mayor 1"))

    with crear_sesion() as s:
        resultado = _uc(s, motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_neon, cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
            cliente_id=cliente_id,
        )

    with crear_sesion() as s:
        venta = s.get(Venta, resultado.venta_id)
        assert not venta.cualificada
