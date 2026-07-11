"""Caso de uso: emitir (cobrar) una venta.

Orquesta el calculo de lineas (dominio) + la persistencia (sesion) + el motor fiscal
(puerto). Es una transaccion atomica: la venta se cierra y el registro fiscal se genera
y encadena en el mismo commit. Sin dependencias de HTTP."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.aplicacion.lineas import ItemVenta, resolver_items
from app.dominio.puertos import MotorFiscal, UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import MovimientoStock, Pago, Venta, VentaLinea
from app.infraestructura.reloj import ahora_huso

_log = logging.getLogger(__name__)


@dataclass
class PagoVenta:
    medio: str
    importe: Decimal


@dataclass
class ResultadoVenta:
    venta_id: int
    num_serie: str
    fecha: str
    total: str   # str para preservar el Decimal exacto hacia el exterior
    cambio: str


class TicketVacio(Exception):
    pass


class UsuarioNoValido(Exception):
    pass


class EmitirVenta:
    def __init__(self, uow: UnidadDeTrabajo, motor: MotorFiscal):
        self.uow = uow
        self.motor = motor

    def ejecutar(
        self, *, usuario_id: int, items: list[ItemVenta], pagos: list[PagoVenta]
    ) -> ResultadoVenta:
        if not items:
            raise TicketVacio()
        usuario = self.uow.usuarios.buscar(usuario_id)  # 1a operacion -> BEGIN IMMEDIATE
        if usuario is None:
            raise UsuarioNoValido()

        lineas, totales = resolver_items(self.uow.articulos, items)
        venta = Venta(estado="aparcada", usuario_id=usuario.id,
                      base_total=totales.base_total, cuota_total=totales.cuota_total,
                      total_con_iva=totales.total_con_iva)
        for lr in lineas:
            venta.lineas.append(VentaLinea(
                articulo_id=lr.articulo.id, descripcion=lr.articulo.nombre,
                cantidad=lr.cantidad, pvp_unitario=lr.pvp,
                tipo_iva_porcentaje=lr.calculo.porcentaje, base_linea=lr.calculo.base,
                cuota_linea=lr.calculo.cuota, total_linea=lr.calculo.total))
        for p in pagos:
            venta.pagos.append(Pago(medio=p.medio, importe=Decimal(p.importe)))
        self.uow.ventas.agregar(venta)

        # El motor es un adaptador de infraestructura y opera sobre la sesion (ADR-0001).
        registro = self.motor.emit(self.uow.session, venta)

        self._efecto_stock(venta, usuario_id)

        total = venta.total_con_iva
        efectivo = sum((Decimal(p.importe) for p in pagos if p.medio == "efectivo"),
                       Decimal("0.00"))
        cambio = efectivo - total if efectivo > total else Decimal("0.00")
        resultado = ResultadoVenta(
            venta_id=venta.id, num_serie=venta.num_serie_factura,
            fecha=registro.fecha_expedicion, total=str(total), cambio=str(cambio))
        self.uow.commit()
        return resultado

    def _efecto_stock(self, venta: Venta, usuario_id: int) -> None:
        """Efecto de stock NO bloqueante (informativo, ver design.md "Punto critico").

        Un fallo aqui NUNCA aborta la venta ni el registro fiscal ya flusheado
        (invariante de cobro offline, CLAUDE.md): se aisla en un SAVEPOINT anidado
        y se captura CUALQUIER excepcion sin propagarla. El `commit()` de la venta
        se ejecuta despues, fuera de este try, para jamas enmascarar un fallo real
        del cierre de la venta."""
        if not self.uow.configuracion.control_stock_activo():
            return
        try:
            with self.uow.session.begin_nested():  # SAVEPOINT sp_stock
                for linea in venta.lineas:
                    articulo = self.uow.articulos.buscar(linea.articulo_id)
                    if articulo is not None and articulo.control_stock:
                        self.uow.stock.agregar(MovimientoStock(
                            tipo="venta", articulo_id=articulo.id, cantidad=linea.cantidad,
                            venta_id=venta.id, usuario_id=usuario_id,
                            fecha_hora_huso=ahora_huso()))
        except Exception as exc:  # noqa: BLE001 - el stock jamas aborta la venta
            _log.warning("efecto de stock no aplicado para venta %s: %s", venta.id, exc)
