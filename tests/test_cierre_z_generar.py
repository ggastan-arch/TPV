"""Caso de uso `GenerarCierreZ` (Fase 4, RED primero: `GenerarCierreZ` aun no existe).

Cubre: numeracion correlativa global, rango contiguo por `registro_fiscal.orden`,
cuadre de totales y desgloses, Z a cero (rango vacio, sin excepcion) y el escenario
del ticket aparcado que se emite despues de un cierre (no se pierde, cae en el Z
siguiente por orden de emision real)."""
from __future__ import annotations

from decimal import Decimal

from _helpers import construir_venta
from app.aplicacion.generar_cierre_z import GenerarCierreZ
from app.infraestructura.persistencia.modelos import Pago, Venta
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


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
        }
    return orden, totales


def _generar(crear_sesion, usuario_id, origen="local"):
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        return GenerarCierreZ(uow).ejecutar(usuario_id=usuario_id, origen=origen)


# --- Numeracion correlativa global -------------------------------------------

def test_numeracion_correlativa_sin_huecos(crear_sesion, datos_base):
    usuario_id = datos_base["usuario_id"]
    z1 = _generar(crear_sesion, usuario_id)
    z2 = _generar(crear_sesion, usuario_id)
    z3 = _generar(crear_sesion, usuario_id)
    assert (z1.numero, z2.numero, z3.numero) == (1, 2, 3)


def test_primer_cierre_arranca_en_orden_1(crear_sesion, datos_base):
    z1 = _generar(crear_sesion, datos_base["usuario_id"])
    assert z1.desde_orden == 1


# --- Rango contiguo (desde_n = hasta_{n-1} + 1) ------------------------------

def test_rango_contiguo_entre_cierres_consecutivos(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    _emitir(crear_sesion, motor, usuario_id, [("Neon cardenal", "2.50", "1", "21")])
    z1 = _generar(crear_sesion, usuario_id)

    _emitir(crear_sesion, motor, usuario_id, [("Anubias", "6.90", "1", "10")])
    _emitir(crear_sesion, motor, usuario_id, [("Guppy", "3.00", "1", "21")])
    z2 = _generar(crear_sesion, usuario_id)

    assert z2.desde_orden == z1.hasta_orden + 1
    assert z2.hasta_orden == z1.hasta_orden + 2


# --- Cuadre de totales y desgloses (IVA y medio de pago) ---------------------

def test_cuadre_de_totales_y_desgloses(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    _, t1 = _emitir(
        crear_sesion, motor, usuario_id, [("Neon cardenal", "2.50", "2", "21")], medio="efectivo"
    )
    _, t2 = _emitir(
        crear_sesion, motor, usuario_id, [("Anubias", "6.90", "1", "10")], medio="tarjeta"
    )

    z = _generar(crear_sesion, usuario_id)

    assert z.num_tickets == 2
    assert z.base_total == t1["base_total"] + t2["base_total"]
    assert z.cuota_total == t1["cuota_total"] + t2["cuota_total"]
    assert z.total_con_iva == t1["total_con_iva"] + t2["total_con_iva"]
    assert z.base_total + z.cuota_total == z.total_con_iva

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        persistido = uow.cierres_z.buscar(z.numero)

        por_medio = {d.medio: d.importe for d in persistido.desglose_pago}
        assert por_medio["efectivo"] == t1["total_con_iva"]
        assert por_medio["tarjeta"] == t2["total_con_iva"]

        por_tipo = {
            d.tipo_impositivo: (d.base_imponible, d.cuota_repercutida)
            for d in persistido.desglose_iva
        }
        assert por_tipo[Decimal("21.00")] == (t1["base_total"], t1["cuota_total"])
        assert por_tipo[Decimal("10.00")] == (t2["base_total"], t2["cuota_total"])


# --- Z a cero: rango vacio, sin excepcion -------------------------------------

def test_z_a_cero_sin_ventas_nuevas_no_lanza_excepcion(crear_sesion, datos_base):
    usuario_id = datos_base["usuario_id"]
    z1 = _generar(crear_sesion, usuario_id)
    z2 = _generar(crear_sesion, usuario_id)  # sin altas nuevas entre medio

    assert z2.numero == z1.numero + 1
    assert z2.desde_orden == z1.hasta_orden + 1
    assert z2.hasta_orden == z1.hasta_orden
    assert z2.num_tickets == 0
    assert z2.base_total == Decimal("0.00")
    assert z2.cuota_total == Decimal("0.00")
    assert z2.total_con_iva == Decimal("0.00")


# --- Ticket aparcado emitido tras un cierre: no se pierde --------------------

def test_ticket_aparcado_emitido_tras_cierre_cae_en_el_z_siguiente(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]

    # Venta aparcada ANTES del primer cierre (id bajo), aun sin emitir.
    with crear_sesion() as s, s.begin():
        aparcada = construir_venta(usuario_id, [("Guppy", "3.00", "1", "21")])
        s.add(aparcada)
        s.flush()
        aparcada_id = aparcada.id

    _emitir(crear_sesion, motor, usuario_id, [("Neon cardenal", "2.50", "1", "21")])
    z1 = _generar(crear_sesion, usuario_id)

    # La venta aparcada se emite (cobra) DESPUES de que z1 ya se genero.
    with crear_sesion() as s, s.begin():
        venta = s.get(Venta, aparcada_id)
        venta.pagos.append(Pago(medio="efectivo", importe=venta.total_con_iva))
        registro = motor.emit(s, venta)
        orden_aparcada = registro.orden
        total_aparcada = venta.total_con_iva

    assert orden_aparcada > z1.hasta_orden  # confirma que quedo fuera de z1

    z2 = _generar(crear_sesion, usuario_id)

    assert z2.desde_orden <= orden_aparcada <= z2.hasta_orden
    assert z2.num_tickets == 1
    assert z2.total_con_iva == total_aparcada
