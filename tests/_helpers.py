"""Utilidades compartidas por los tests."""
from __future__ import annotations

from decimal import Decimal

from app.core.redondeo import Linea, agregar_totales, calcular_linea
from app.models import Venta, VentaLinea


def construir_venta(usuario_id: int, lineas_spec: list[tuple[str, str, str, str]]) -> Venta:
    """Crea una venta aparcada con lineas calculadas.

    lineas_spec: lista de (descripcion, pvp_unitario, cantidad, porcentaje_iva).
    """
    venta = Venta(estado="aparcada", usuario_id=usuario_id)
    calculadas: list[Linea] = []
    for descripcion, pvp, cantidad, porcentaje in lineas_spec:
        ln = calcular_linea(Decimal(pvp), Decimal(cantidad), Decimal(porcentaje))
        venta.lineas.append(
            VentaLinea(
                descripcion=descripcion,
                cantidad=Decimal(cantidad),
                pvp_unitario=Decimal(pvp),
                tipo_iva_porcentaje=Decimal(porcentaje),
                base_linea=ln.base,
                cuota_linea=ln.cuota,
                total_linea=ln.total,
            )
        )
        calculadas.append(ln)
    totales = agregar_totales(calculadas)
    venta.base_total = totales.base_total
    venta.cuota_total = totales.cuota_total
    venta.total_con_iva = totales.total_con_iva
    return venta
