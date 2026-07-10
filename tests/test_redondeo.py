"""(c) El redondeo cuadra en tickets multi-tipo (21% + 10%)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.redondeo import agregar_totales, calcular_linea, desglosar_total


@pytest.mark.parametrize(
    "total,porcentaje",
    [
        ("1.00", "21"),
        ("0.99", "10"),
        ("3.63", "21"),
        ("2.20", "10"),
        ("100.00", "21"),
        ("7.50", "21"),
        ("6.90", "10"),
        ("999.99", "21"),
    ],
)
def test_base_mas_cuota_igual_total(total, porcentaje):
    base, cuota = desglosar_total(Decimal(total), Decimal(porcentaje))
    assert base + cuota == Decimal(total)
    assert base.as_tuple().exponent == -2  # exactamente 2 decimales
    assert cuota.as_tuple().exponent == -2


def test_no_hay_float_en_el_camino():
    base, cuota = desglosar_total(Decimal("1.00"), Decimal("21"))
    assert isinstance(base, Decimal)
    assert isinstance(cuota, Decimal)


def test_ticket_multitipo_cuadra():
    # Ticket con 21% y 10% mezclados.
    lineas = [
        calcular_linea(Decimal("1.00"), Decimal("1"), Decimal("21")),   # total 1.00
        calcular_linea(Decimal("2.50"), Decimal("3"), Decimal("21")),   # total 7.50
        calcular_linea(Decimal("6.90"), Decimal("1"), Decimal("10")),   # total 6.90
    ]
    totales = agregar_totales(lineas)

    # Sigma bases + Sigma cuotas == importe total.
    assert totales.base_total + totales.cuota_total == totales.total_con_iva
    # El importe total coincide con la suma de los totales de linea (sin descuadre).
    assert totales.total_con_iva == sum((ln.total for ln in lineas), Decimal("0.00"))
    assert totales.total_con_iva == Decimal("15.40")

    # Debe haber exactamente dos tramos de desglose (21% y 10%).
    assert {d.porcentaje for d in totales.desglose} == {Decimal("21.00"), Decimal("10.00")}
    for d in totales.desglose:
        assert d.base + d.cuota  # ambos definidos


def test_descuento_por_linea():
    ln = calcular_linea(
        Decimal("10.00"), Decimal("1"), Decimal("21"), descuento=Decimal("1.00")
    )
    assert ln.total == Decimal("9.00")
    assert ln.base + ln.cuota == Decimal("9.00")
