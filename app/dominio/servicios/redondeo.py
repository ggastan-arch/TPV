"""Funcion UNICA de redondeo fiscal.

El TPV vende a PVP con IVA incluido. A partir del total con IVA de cada linea se
deriva la base imponible y la cuota repercutida, con redondeo half-up a 2 decimales.

Diseno que garantiza el cuadre (Sigma bases + Sigma cuotas == importe_total):
la BASE se redondea half-up y la CUOTA se calcula como residuo
(cuota = total - base). Asi `base + cuota == total` es exacto por construccion en
cada linea, y al sumar por tipo impositivo el desglose cuadra sin descuadres de
centimos (el bug clasico de TPV).

Todo con `Decimal`. Cero `float`.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, NamedTuple

CENTIMO = Decimal("0.01")


def cuantizar(valor: Decimal | str | int) -> Decimal:
    """Redondea a 2 decimales half-up."""
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    return valor.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def desglosar_total(total_con_iva: Decimal, porcentaje: Decimal) -> tuple[Decimal, Decimal]:
    """Dado el total con IVA y el tipo impositivo (p. ej. 21), devuelve (base, cuota).

    Garantia: base + cuota == cuantizar(total_con_iva).
    """
    total = cuantizar(total_con_iva)
    tipo = Decimal(porcentaje) / Decimal(100)
    base = cuantizar(total / (Decimal(1) + tipo))
    cuota = total - base
    return base, cuota


class Linea(NamedTuple):
    """Resultado del calculo de una linea de venta."""

    total: Decimal
    base: Decimal
    cuota: Decimal
    porcentaje: Decimal


def calcular_linea(
    pvp_unitario: Decimal,
    cantidad: Decimal | int,
    porcentaje: Decimal,
    descuento: Decimal = Decimal("0.00"),
) -> Linea:
    """Calcula el total con IVA de la linea (PVP*cantidad - descuento) y su desglose."""
    bruto = Decimal(pvp_unitario) * Decimal(cantidad)
    total = cuantizar(bruto - Decimal(descuento))
    base, cuota = desglosar_total(total, porcentaje)
    return Linea(total=total, base=base, cuota=cuota, porcentaje=cuantizar(porcentaje))


class Desglose(NamedTuple):
    porcentaje: Decimal
    base: Decimal
    cuota: Decimal


class Totales(NamedTuple):
    base_total: Decimal
    cuota_total: Decimal
    total_con_iva: Decimal
    desglose: list[Desglose]


def agregar_totales(lineas: Iterable[Linea]) -> Totales:
    """Agrupa lineas por tipo impositivo y calcula los totales del ticket.

    Invariante verificado: base_total + cuota_total == total_con_iva.
    """
    bases: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0.00"))
    cuotas: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for ln in lineas:
        bases[ln.porcentaje] += ln.base
        cuotas[ln.porcentaje] += ln.cuota

    desglose = [
        Desglose(porcentaje=p, base=bases[p], cuota=cuotas[p])
        for p in sorted(bases, reverse=True)
    ]
    base_total = sum((d.base for d in desglose), Decimal("0.00"))
    cuota_total = sum((d.cuota for d in desglose), Decimal("0.00"))
    return Totales(
        base_total=base_total,
        cuota_total=cuota_total,
        total_con_iva=base_total + cuota_total,
        desglose=desglose,
    )
