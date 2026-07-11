"""Fase 5: snapshot inmutable del Cierre Z.

Anular una venta del rango DESPUES de generar el Z no debe alterar los totales ya
persistidos (el Z solo lee en el momento de generarse; nunca recomputa)."""
from __future__ import annotations

from decimal import Decimal

from _helpers import construir_venta
from app.aplicacion.generar_cierre_z import GenerarCierreZ
from app.infraestructura.persistencia.modelos import Pago, RegistroFiscal
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def test_anular_venta_del_rango_tras_el_cierre_no_altera_el_z(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]

    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, [("Neon cardenal", "2.50", "2", "21")])
        s.add(venta)
        venta.pagos.append(Pago(medio="efectivo", importe=venta.total_con_iva))
        registro_alta = motor.emit(s, venta)
        registro_alta_id = registro_alta.id

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        z = GenerarCierreZ(uow).ejecutar(usuario_id=usuario_id)

    totales_antes = (z.num_tickets, z.base_total, z.cuota_total, z.total_con_iva)
    assert totales_antes == (1, Decimal("4.13"), Decimal("0.87"), Decimal("5.00"))

    # Anular la venta DESPUES de que el Z ya fue generado.
    with crear_sesion() as s, s.begin():
        registro_alta_recargado = s.get(RegistroFiscal, registro_alta_id)
        motor.cancel(s, registro_alta_recargado)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        z_releido = uow.cierres_z.buscar(z.numero)

    assert (
        z_releido.num_tickets,
        z_releido.base_total,
        z_releido.cuota_total,
        z_releido.total_con_iva,
    ) == totales_antes
