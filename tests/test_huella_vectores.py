"""Conformidad de la huella contra los VECTORES OFICIALES de la AEAT.

Fuente: docs/Verifactu/Veri-Factu_especificaciones_huella_hash_registros.pdf
(v0.1.2, 27/08/2024), apartado 6. Si estos tres casos pasan, la composicion de la
huella (nombres de campo, orden, formato y algoritmo) es conforme.
"""
from __future__ import annotations

from decimal import Decimal

from app.fiscal.huella import huella_alta, huella_anulacion

# Huellas encadenadas de los ejemplos: caso 2 usa la del caso 1; caso 3 la del caso 2.
HUELLA_CASO_1 = "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"
HUELLA_CASO_2 = "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"
HUELLA_CASO_3 = "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"


def test_caso_1_primer_registro_alta():
    huella = huella_alta(
        id_emisor="89890001K",
        num_serie_factura="12345678/G33",
        fecha_expedicion="01-01-2024",
        tipo_factura="F1",
        cuota_total=Decimal("12.35"),
        importe_total=Decimal("123.45"),
        huella_anterior=None,  # primer registro: sin huella anterior
        fecha_hora_huso_gen="2024-01-01T19:20:30+01:00",
    )
    assert huella == HUELLA_CASO_1


def test_caso_2_alta_encadenada():
    huella = huella_alta(
        id_emisor="89890001K",
        num_serie_factura="12345679/G34",
        fecha_expedicion="01-01-2024",
        tipo_factura="F1",
        cuota_total=Decimal("12.35"),
        importe_total=Decimal("123.45"),
        huella_anterior=HUELLA_CASO_1,
        fecha_hora_huso_gen="2024-01-01T19:20:35+01:00",
    )
    assert huella == HUELLA_CASO_2


def test_caso_3_anulacion_encadenada():
    huella = huella_anulacion(
        id_emisor="89890001K",
        num_serie_factura="12345679/G34",
        fecha_expedicion="01-01-2024",
        huella_anterior=HUELLA_CASO_2,
        fecha_hora_huso_gen="2024-01-01T19:20:40+01:00",
    )
    assert huella == HUELLA_CASO_3
