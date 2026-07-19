"""Conformidad de la huella contra los VECTORES OFICIALES de la AEAT.

Fuente: docs/Verifactu/Veri-Factu_especificaciones_huella_hash_registros.pdf
(v0.1.2, 27/08/2024), apartado 6. Si estos tres casos pasan, la composicion de la
huella (nombres de campo, orden, formato y algoritmo) es conforme.
"""
from __future__ import annotations

from decimal import Decimal

from _helpers import construir_venta
from app.dominio.servicios.huella import huella_alta, huella_anulacion
from app.infraestructura.fiscal.xml import (
    NS,
    Destinatario,
    registro_alta_xml,
    sistema_desde_settings,
)
from app.infraestructura.persistencia.modelos import RegistroFiscal

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


def test_flag_cualificada_no_altera_huella():
    """Guarda de regresion (D3, design.md; corregido en revision Judgment Day
    S-1): el flag `cualificada` de la venta NUNCA entra en la composicion de la
    huella. `huella_alta` no declara ese parametro en su firma -- ni siquiera
    puede recibirlo -- lo cual es la prueba real de que ninguna variacion del
    flag puede alterar el hash. (Una version anterior de este test comparaba
    `huella_alta(**campos)` contra si misma con los MISMOS argumentos, lo cual
    era tautologico: la igualdad era trivial y no probaba nada sobre el flag.
    Ver test_migracion_cualificada.py y RemitirLote para la cobertura real de
    extremo a extremo de que `NullEngine.emit`/`huella_alta` ignoran
    `venta.cualificada`.)"""
    import inspect

    assert "cualificada" not in inspect.signature(huella_alta).parameters


def test_huella_f3_independiente_del_destinatario(crear_sesion, motor, datos_base):
    """Frontera fiscal (design D2, tasks.md 3.4): el bloque XML
    Destinatarios/IDDestinatario NUNCA participa en el computo de la huella. La
    huella ya queda fijada por `motor.emit` (`huella_alta`, ver arriba) en el
    momento de la EMISION -- ANTES de que exista ningun destinatario resuelto
    (eso solo ocurre en `registro_alta_xml`, en la SERIALIZACION, ver
    app.aplicacion.remitir_lote). Serializar el MISMO `RegistroFiscal` F3 con
    destinatarios distintos (o sin destinatario) debe producir siempre el mismo
    elemento <Huella>, igual que `huella_alta` ni siquiera declara el parametro
    (test anterior)."""
    ejercicio = datos_base["ejercicio"]
    with crear_sesion() as s, s.begin():
        f3 = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "2", "21")])
        s.add(f3)
        registro = motor.emit(s, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
        reg_id = registro.id

    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        sistema = sistema_desde_settings()
        xml_sin = registro_alta_xml(reg, nombre_emisor="AcuaTPV", sistema=sistema, anterior=None)
        xml_con_a = registro_alta_xml(
            reg, nombre_emisor="AcuaTPV", sistema=sistema, anterior=None,
            destinatario=Destinatario(nombre="Acuario S.L.", nif="A58818501"))
        xml_con_b = registro_alta_xml(
            reg, nombre_emisor="AcuaTPV", sistema=sistema, anterior=None,
            destinatario=Destinatario(nombre="Otro Cliente Distinto", nif="B98765432"))

        huella_tag = f"{{{NS}}}Huella"
        huellas = {xml.find(huella_tag).text for xml in (xml_sin, xml_con_a, xml_con_b)}
        assert huellas == {reg.huella}
