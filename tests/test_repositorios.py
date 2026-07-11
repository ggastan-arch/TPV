"""Adaptadores SQLAlchemy de los puertos de repositorio."""
from __future__ import annotations

from decimal import Decimal

from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import Articulo, CodigoBarras, MovimientoStock
from app.infraestructura.reloj import ahora_huso


def test_repositorio_articulos(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        a = Articulo(nombre="Neon cardenal", nombre_corto="Neon",
                     tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
        s.add(a)
        s.flush()
        s.add(CodigoBarras(articulo_id=a.id, codigo="8412345678905", principal=True))
        articulo_id = a.id

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        assert repo.buscar(articulo_id).nombre_corto == "Neon"
        assert repo.buscar(999999) is None
        assert repo.buscar_por_codigo("8412345678905").id == articulo_id
        assert repo.buscar_por_codigo("no-existe") is None


def test_repositorio_usuarios(crear_sesion, datos_base):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).usuarios
        assert repo.buscar(datos_base["usuario_id"]).rol == "venta"
        assert repo.buscar(999999) is None


def _crear_articulo(s, datos_base, *, control_stock: bool, nombre: str = "Guppy") -> int:
    articulo = Articulo(nombre=nombre, nombre_corto=nombre,
                         tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00"),
                         control_stock=control_stock)
    s.add(articulo)
    s.flush()
    return articulo.id


def test_repositorio_configuracion_control_stock_desactivado_por_defecto(crear_sesion):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).configuracion
        assert repo.control_stock_activo() is False


def test_repositorio_configuracion_fijar_control_stock_persiste(crear_sesion):
    with crear_sesion() as s:
        UnidadDeTrabajoSQL(s).configuracion.fijar_control_stock(True)
        s.commit()

    with crear_sesion() as s:
        assert UnidadDeTrabajoSQL(s).configuracion.control_stock_activo() is True


def test_repositorio_stock_calcula_saldo_con_entrada_venta_merma(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        articulo_id = _crear_articulo(s, datos_base, control_stock=True)
        uow = UnidadDeTrabajoSQL(s)
        uow.stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="entrada", cantidad=Decimal("10"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="venta", cantidad=Decimal("3"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="merma", cantidad=Decimal("2"), motivo="rotura",
            fecha_hora_huso=ahora_huso()))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).stock
        assert repo.stock_actual(articulo_id) == Decimal("5")
        assert len(repo.movimientos(articulo_id)) == 3


def test_repositorio_stock_rastreados_en_negativo_solo_lista_negativos(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        negativo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Molly")
        positivo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Platy")
        no_rastreado_id = _crear_articulo(s, datos_base, control_stock=False, nombre="Planta")
        uow = UnidadDeTrabajoSQL(s)
        uow.stock.agregar(MovimientoStock(
            articulo_id=negativo_id, tipo="venta", cantidad=Decimal("4"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=positivo_id, tipo="entrada", cantidad=Decimal("4"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=no_rastreado_id, tipo="venta", cantidad=Decimal("10"),
            fecha_hora_huso=ahora_huso()))

    with crear_sesion() as s:
        negativos = UnidadDeTrabajoSQL(s).stock.rastreados_en_negativo()
        assert negativos == [(negativo_id, Decimal("-4"))]
