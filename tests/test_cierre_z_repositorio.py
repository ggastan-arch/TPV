"""(Fase 3) Puertos y adaptadores del Cierre Z: `uow.cierres_z` y
`uow.registros.max_orden_alta()` (patron `test_repositorios.py`)."""
from __future__ import annotations

from decimal import Decimal

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import CierreZ, Pago
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.reloj import ahora_huso


def _emitir(crear_sesion, motor, usuario_id, lineas, medio="efectivo") -> tuple[int, dict]:
    """Emite una venta y devuelve (orden_del_registro_de_alta, totales_reales)."""
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, lineas)
        s.add(venta)
        venta.pagos.append(Pago(medio=medio, importe=venta.total_con_iva))
        registro = motor.emit(s, venta)
        orden = registro.orden
        totales = {
            "base_total": venta.base_total,
            "cuota_total": venta.cuota_total,
            "total_con_iva": venta.total_con_iva,
            "medio": medio,
        }
    return orden, totales


# --- RepositorioRegistros.max_orden_alta() ---------------------------------------

def test_max_orden_alta_es_0_sin_registros(crear_sesion):
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        assert uow.registros.max_orden_alta() == 0


def test_max_orden_alta_devuelve_el_mayor_orden_de_alta(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    _emitir(crear_sesion, motor, usuario_id, [("Neon cardenal", "2.50", "1", "21")])
    orden2, _ = _emitir(crear_sesion, motor, usuario_id, [("Anubias", "6.90", "1", "10")])
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        assert uow.registros.max_orden_alta() == orden2


# --- RepositorioCierresZ: agregar / ultimo / buscar / listar ---------------------

def _nuevo_cierre(usuario_id: int, numero: int, desde: int, hasta: int) -> CierreZ:
    return CierreZ(
        numero=numero, fecha_hora_huso=ahora_huso(), usuario_id=usuario_id,
        desde_orden=desde, hasta_orden=hasta, num_tickets=0,
        base_total=Decimal("0.00"), cuota_total=Decimal("0.00"), total_con_iva=Decimal("0.00"),
    )


def test_ultimo_es_none_sin_cierres_previos(crear_sesion):
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        assert uow.cierres_z.ultimo() is None


def test_agregar_ultimo_buscar_y_listar(crear_sesion, datos_base):
    usuario_id = datos_base["usuario_id"]
    with crear_sesion() as s, s.begin():
        uow = UnidadDeTrabajoSQL(s)
        uow.cierres_z.agregar(_nuevo_cierre(usuario_id, numero=1, desde=1, hasta=0))
        uow.flush()
        uow.cierres_z.agregar(_nuevo_cierre(usuario_id, numero=2, desde=1, hasta=5))
        uow.flush()

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)

        ultimo = uow.cierres_z.ultimo()
        assert ultimo.numero == 2
        assert ultimo.hasta_orden == 5

        encontrado = uow.cierres_z.buscar(1)
        assert encontrado is not None
        assert encontrado.desde_orden == 1
        assert uow.cierres_z.buscar(999) is None

        listado = uow.cierres_z.listar()
        assert [c.numero for c in listado] == [2, 1]


# --- RepositorioCierresZ.cobradas_por_rango_orden --------------------------------

def test_cobradas_por_rango_orden_agrega_totales_y_desglose(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    orden1, t1 = _emitir(
        crear_sesion, motor, usuario_id, [("Neon cardenal", "2.50", "2", "21")], medio="efectivo"
    )
    orden2, t2 = _emitir(
        crear_sesion, motor, usuario_id, [("Anubias", "6.90", "1", "10")], medio="tarjeta"
    )

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        totales = uow.cierres_z.cobradas_por_rango_orden(orden1, orden2)

    assert totales.num_tickets == 2
    assert totales.base_total == t1["base_total"] + t2["base_total"]
    assert totales.cuota_total == t1["cuota_total"] + t2["cuota_total"]
    assert totales.total_con_iva == t1["total_con_iva"] + t2["total_con_iva"]
    assert totales.base_total + totales.cuota_total == totales.total_con_iva

    por_medio = dict(totales.desglose_pago)
    assert por_medio["efectivo"] == t1["total_con_iva"]
    assert por_medio["tarjeta"] == t2["total_con_iva"]

    por_tipo = {tipo: (base, cuota) for tipo, base, cuota in totales.desglose_iva}
    assert por_tipo[Decimal("21.00")] == (t1["base_total"], t1["cuota_total"])
    assert por_tipo[Decimal("10.00")] == (t2["base_total"], t2["cuota_total"])


def test_cobradas_por_rango_orden_vacio_devuelve_totales_cero(crear_sesion):
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        totales = uow.cierres_z.cobradas_por_rango_orden(5, 4)  # hasta < desde: rango vacio

    assert totales.num_tickets == 0
    assert totales.base_total == Decimal("0.00")
    assert totales.cuota_total == Decimal("0.00")
    assert totales.total_con_iva == Decimal("0.00")
    assert totales.desglose_iva == []
    assert totales.desglose_pago == []
