"""Tests unitarios de la funcion pura `validar_layout_botonera` (sin BD, sin sesion).

Cada test cubre una regla de rechazo del layout de una pagina de botonera:
limites de la rejilla, solape AABB, destino unico y funcion valida. Ver
openspec/changes/editor-botoneras/specs/editor-botoneras/spec.md."""
from __future__ import annotations

import pytest

from app.dominio.servicios.botonera import FUNCIONES, BotonSpec, validar_layout_botonera


def _boton(ref="b1", fila=0, columna=0, ancho=1, alto=1, **destino):
    return BotonSpec(ref=ref, fila=fila, columna=columna, ancho=ancho, alto=alto, **destino)


def test_layout_valido_no_devuelve_errores():
    botones = [
        _boton("cobrar", fila=3, columna=4, funcion="cobrar"),
        _boton("neon", fila=0, columna=0, articulo_id=1),
        _boton("peces", fila=1, columna=0, familia_id=2),
    ]
    assert validar_layout_botonera(filas=4, columnas=5, botones=botones) == []


# --- limites ---

def test_fila_negativa_se_rechaza():
    errores = validar_layout_botonera(4, 5, [_boton(fila=-1, articulo_id=1)])
    assert errores == ["b1: fila/columna no puede ser negativa"]


def test_columna_negativa_se_rechaza():
    errores = validar_layout_botonera(4, 5, [_boton(columna=-1, articulo_id=1)])
    assert errores == ["b1: fila/columna no puede ser negativa"]


@pytest.mark.parametrize("ancho,alto", [(0, 1), (1, 0), (-1, 1)])
def test_ancho_o_alto_menor_a_uno_se_rechaza(ancho, alto):
    errores = validar_layout_botonera(4, 5, [_boton(ancho=ancho, alto=alto, articulo_id=1)])
    assert errores == ["b1: ancho/alto debe ser >= 1"]


def test_boton_justo_en_el_borde_de_filas_es_valido():
    # fila=3, alto=1 -> fila+alto=4 == filas: no excede.
    assert validar_layout_botonera(4, 5, [_boton(fila=3, alto=1, articulo_id=1)]) == []


def test_boton_que_excede_filas_por_uno_se_rechaza():
    # fila=3, alto=2 -> fila+alto=5 > filas(4): excede en 1.
    errores = validar_layout_botonera(4, 5, [_boton(fila=3, alto=2, articulo_id=1)])
    assert errores == ["b1: excede el numero de filas de la pagina"]


def test_boton_justo_en_el_borde_de_columnas_es_valido():
    assert validar_layout_botonera(4, 5, [_boton(columna=4, ancho=1, articulo_id=1)]) == []


def test_boton_que_excede_columnas_por_uno_se_rechaza():
    errores = validar_layout_botonera(4, 5, [_boton(columna=4, ancho=2, articulo_id=1)])
    assert errores == ["b1: excede el numero de columnas de la pagina"]


# --- solape AABB ---

def test_botones_adyacentes_no_se_solapan():
    a = _boton("boton_a", fila=0, columna=0, ancho=1, alto=1, articulo_id=1)
    b = _boton("boton_b", fila=0, columna=1, ancho=1, alto=1, articulo_id=2)
    assert validar_layout_botonera(4, 5, [a, b]) == []


def test_botones_solapados_parcialmente_se_rechazan():
    a = _boton("boton_a", fila=0, columna=0, ancho=2, alto=2, articulo_id=1)
    b = _boton("boton_b", fila=1, columna=1, ancho=2, alto=2, articulo_id=2)
    errores = validar_layout_botonera(4, 5, [a, b])
    assert errores == ["boton_a/boton_b: los botones se solapan"]


def test_boton_contenido_en_otro_se_rechaza():
    a = _boton("boton_a", fila=0, columna=0, ancho=3, alto=3, articulo_id=1)
    b = _boton("boton_b", fila=1, columna=1, ancho=1, alto=1, articulo_id=2)
    errores = validar_layout_botonera(4, 5, [a, b])
    assert errores == ["boton_a/boton_b: los botones se solapan"]


def test_solo_dos_de_tres_botones_se_solapan_sin_falsos_positivos():
    a = _boton("boton_a", fila=0, columna=0, ancho=1, alto=1, articulo_id=1)
    b = _boton("boton_b", fila=0, columna=0, ancho=1, alto=1, articulo_id=2)  # solapa con a
    c = _boton("boton_c", fila=3, columna=4, funcion="cobrar")  # lejos, no solapa
    errores = validar_layout_botonera(4, 5, [a, b, c])
    assert errores == ["boton_a/boton_b: los botones se solapan"]


# --- destino unico ---

def test_boton_sin_destino_se_rechaza():
    errores = validar_layout_botonera(4, 5, [_boton()])
    assert errores == ["b1: debe referenciar exactamente un destino (articulo, familia o funcion)"]


def test_boton_con_mas_de_un_destino_se_rechaza():
    errores = validar_layout_botonera(4, 5, [_boton(articulo_id=1, funcion="cobrar")])
    assert errores == ["b1: debe referenciar exactamente un destino (articulo, familia o funcion)"]


def test_boton_con_exactamente_un_destino_es_valido():
    for kwargs in ({"articulo_id": 1}, {"familia_id": 2}, {"funcion": "cobrar"}):
        assert validar_layout_botonera(4, 5, [_boton(**kwargs)]) == []


# --- funcion valida ---

def test_funcion_fuera_del_conjunto_soportado_se_rechaza():
    errores = validar_layout_botonera(4, 5, [_boton(funcion="freir_pescado")])
    assert errores == ["b1: funcion 'freir_pescado' no soportada"]


@pytest.mark.parametrize("funcion", FUNCIONES)
def test_cada_funcion_soportada_es_valida(funcion):
    assert validar_layout_botonera(4, 5, [_boton(funcion=funcion)]) == []


# --- multiples errores simultaneos, cada uno identificable por ref ---

def test_layout_con_varios_errores_devuelve_todos_identificables_por_ref():
    fuera_de_rango = _boton("fuera", fila=10, columna=0, articulo_id=1)
    sin_destino = _boton("vacio", fila=0, columna=2)
    errores = validar_layout_botonera(4, 5, [fuera_de_rango, sin_destino])
    assert errores == [
        "fuera: excede el numero de filas de la pagina",
        "vacio: debe referenciar exactamente un destino (articulo, familia o funcion)",
    ]


# --- no valida existencia en BD (responsabilidad de ServicioBotonera) ---

def test_no_valida_existencia_de_articulo_en_bd():
    # articulo_id inexistente pasa la funcion pura sin error: la existencia
    # depende de sesion y se valida en la capa de aplicacion.
    assert validar_layout_botonera(4, 5, [_boton(articulo_id=999999)]) == []
