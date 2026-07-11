"""Tests de los casos de uso de `ServicioBotonera` (aplicacion): CRUD de perfiles
y paginas, activacion exclusiva de perfil, y guardado atomico del layout de una
pagina (validacion pura + validacion de referencias en BD + reemplazo atomico).

Mismo patron que tests/test_familias.py (UoW sobre SQLite in-memory con
migracion Alembic real)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.aplicacion.botoneras import (
    DatosBoton,
    DatosLayout,
    DatosPagina,
    DestinoNoExiste,
    LayoutInvalido,
    PaginaNoEncontrada,
    PerfilNoEncontrado,
    RangoRejillaInvalido,
    ServicioBotonera,
)
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
    Familia,
    LogAuditoria,
    PaginaBotonera,
    PerfilBotonera,
)
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _svc(session, datos_base) -> ServicioBotonera:
    return ServicioBotonera(
        UnidadDeTrabajoSQL(session), usuario_id=datos_base["usuario_id"], origen="local")


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def _articulo(session, datos_base, nombre="Neon") -> int:
    a = Articulo(nombre=nombre, nombre_corto=nombre, tipo_iva_id=datos_base["iva21_id"],
                 pvp=Decimal("2.50"))
    session.add(a)
    session.flush()
    return a.id


def _familia(session, nombre="Peces") -> int:
    f = Familia(nombre=nombre)
    session.add(f)
    session.flush()
    return f.id


def _perfil_con_pagina_y_boton(session, datos_base) -> tuple[int, int, int]:
    """Perfil activo con una pagina 5x4 y un solo boton (articulo). Devuelve
    (perfil_id, pagina_id, articulo_id)."""
    articulo_id = _articulo(session, datos_base)
    perfil = PerfilBotonera(nombre="Principal", activo=True)
    session.add(perfil)
    session.flush()
    pagina = PaginaBotonera(perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4)
    session.add(pagina)
    session.flush()
    session.add(Boton(pagina_id=pagina.id, fila=0, columna=0, articulo_id=articulo_id))
    session.commit()
    return perfil.id, pagina.id, articulo_id


def _contar_botones(session, pagina_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(Boton).where(Boton.pagina_id == pagina_id)
    ).scalar_one()


def _estado_pagina(session, pagina_id: int):
    pagina = session.get(PaginaBotonera, pagina_id)
    botones = session.execute(
        select(Boton).where(Boton.pagina_id == pagina_id).order_by(Boton.id)
    ).scalars().all()
    return (pagina.filas, pagina.columnas,
            [(b.fila, b.columna, b.articulo_id, b.familia_id, b.funcion) for b in botones])


# --- excepciones ------------------------------------------------------------

def test_layout_invalido_expone_lista_de_errores():
    exc = LayoutInvalido(["a: error 1", "b: error 2"])
    assert exc.errores == ["a: error 1", "b: error 2"]


# --- perfiles: crear / renombrar --------------------------------------------

def test_crear_perfil_queda_inactivo_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear_perfil("Secundario")

    with crear_sesion() as s:
        perfil = s.get(PerfilBotonera, nuevo_id)
        assert perfil is not None and perfil.activo is False and perfil.nombre == "Secundario"
    logs = _auditorias(crear_sesion, "crear_perfil_botonera")
    assert len(logs) == 1 and logs[0].entidad == "perfil_botonera"


def test_renombrar_perfil_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PerfilNoEncontrado):
            _svc(s, datos_base).renombrar_perfil(999999, "X")


def test_renombrar_perfil_existente_persiste_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        perfil_id = _svc(s, datos_base).crear_perfil("Original")
    with crear_sesion() as s:
        _svc(s, datos_base).renombrar_perfil(perfil_id, "Renombrado")
    with crear_sesion() as s:
        assert s.get(PerfilBotonera, perfil_id).nombre == "Renombrado"
    assert len(_auditorias(crear_sesion, "renombrar_perfil_botonera")) == 1


# --- perfiles: activar (exclusividad) ----------------------------------------

def test_activar_perfil_desactiva_los_demas(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        a = svc.crear_perfil("A")
        b = svc.crear_perfil("B")
        svc.activar_perfil(a)
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        svc.activar_perfil(b)
    with crear_sesion() as s:
        assert s.get(PerfilBotonera, a).activo is False
        assert s.get(PerfilBotonera, b).activo is True
    assert len(_auditorias(crear_sesion, "activar_perfil_botonera")) == 2


def test_activar_perfil_desactiva_multiples_activos_previos(crear_sesion, datos_base):
    # Estado inconsistente hipotetico: 2 perfiles activos a la vez antes de activar un tercero.
    with crear_sesion() as s, s.begin():
        s.add_all([
            PerfilBotonera(nombre="A", activo=True),
            PerfilBotonera(nombre="B", activo=True),
            PerfilBotonera(nombre="C", activo=False),
        ])
    with crear_sesion() as s:
        c_id = s.execute(select(PerfilBotonera.id).where(PerfilBotonera.nombre == "C")).scalar_one()
    with crear_sesion() as s:
        _svc(s, datos_base).activar_perfil(c_id)
    with crear_sesion() as s:
        activos = {p.nombre for p in s.execute(
            select(PerfilBotonera).where(PerfilBotonera.activo.is_(True))
        ).scalars()}
        assert activos == {"C"}


def test_activar_perfil_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PerfilNoEncontrado):
            _svc(s, datos_base).activar_perfil(999999)


# --- perfiles: borrar (cascade) -----------------------------------------------

def test_borrar_perfil_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PerfilNoEncontrado):
            _svc(s, datos_base).borrar_perfil(999999)


def test_borrar_perfil_elimina_paginas_y_botones_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        _svc(s, datos_base).borrar_perfil(perfil_id)
    with crear_sesion() as s:
        assert s.get(PerfilBotonera, perfil_id) is None
        assert s.get(PaginaBotonera, pagina_id) is None
        assert _contar_botones(s, pagina_id) == 0
    assert len(_auditorias(crear_sesion, "borrar_perfil_botonera")) == 1


def test_borrar_ultimo_perfil_activo_se_permite_sin_error(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, _, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        # No debe lanzar ninguna excepcion especial (el TPV degrada a 404 en su propio endpoint).
        _svc(s, datos_base).borrar_perfil(perfil_id)
    with crear_sesion() as s:
        assert s.get(PerfilBotonera, perfil_id) is None


# --- paginas: crear / actualizar / borrar -------------------------------------

def test_crear_pagina_con_perfil_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PerfilNoEncontrado):
            _svc(s, datos_base).crear_pagina(999999, DatosPagina(nombre="Inicio"))


@pytest.mark.parametrize("filas,columnas", [(0, 5), (13, 5), (5, 0), (5, 13)])
def test_crear_pagina_con_rango_fuera_de_1_12_falla(crear_sesion, datos_base, filas, columnas):
    with crear_sesion() as s:
        perfil_id = _svc(s, datos_base).crear_perfil("Principal")
    with crear_sesion() as s:
        with pytest.raises(RangoRejillaInvalido):
            _svc(s, datos_base).crear_pagina(
                perfil_id, DatosPagina(nombre="Inicio", filas=filas, columnas=columnas))


@pytest.mark.parametrize("filas,columnas", [(1, 1), (12, 12), (4, 5)])
def test_crear_pagina_con_rango_en_el_borde_es_valida(crear_sesion, datos_base, filas, columnas):
    with crear_sesion() as s:
        perfil_id = _svc(s, datos_base).crear_perfil("Principal")
    with crear_sesion() as s:
        pagina_id = _svc(s, datos_base).crear_pagina(
            perfil_id, DatosPagina(nombre="Inicio", filas=filas, columnas=columnas))
    with crear_sesion() as s:
        pagina = s.get(PaginaBotonera, pagina_id)
        assert pagina.filas == filas and pagina.columnas == columnas
    assert len(_auditorias(crear_sesion, "crear_pagina_botonera")) >= 1


def test_actualizar_pagina_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PaginaNoEncontrada):
            _svc(s, datos_base).actualizar_pagina(999999, DatosPagina(nombre="X"))


def test_actualizar_pagina_con_rango_fuera_de_1_12_falla(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        with pytest.raises(RangoRejillaInvalido):
            _svc(s, datos_base).actualizar_pagina(
                pagina_id, DatosPagina(nombre="Inicio", filas=13, columnas=5))


def test_actualizar_pagina_valida_persiste_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar_pagina(
            pagina_id, DatosPagina(nombre="Renombrada", orden=2, filas=6, columnas=6))
    with crear_sesion() as s:
        pagina = s.get(PaginaBotonera, pagina_id)
        assert pagina.nombre == "Renombrada" and pagina.orden == 2
        assert pagina.filas == 6 and pagina.columnas == 6
    assert len(_auditorias(crear_sesion, "actualizar_pagina_botonera")) == 1


def test_borrar_pagina_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PaginaNoEncontrada):
            _svc(s, datos_base).borrar_pagina(999999)


def test_borrar_pagina_elimina_botones_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        _svc(s, datos_base).borrar_pagina(pagina_id)
    with crear_sesion() as s:
        assert s.get(PaginaBotonera, pagina_id) is None
        assert _contar_botones(s, pagina_id) == 0
    assert len(_auditorias(crear_sesion, "borrar_pagina_botonera")) == 1


# --- guardar_layout: pagina inexistente ---------------------------------------

def test_guardar_layout_pagina_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PaginaNoEncontrada):
            _svc(s, datos_base).guardar_layout(999999, DatosLayout(filas=4, columnas=5, botones=[]))


# --- guardar_layout: paso 1, validacion pura (LayoutInvalido) -----------------

def test_guardar_layout_invalido_por_bounds_no_persiste_nada(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, articulo_id = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(LayoutInvalido) as exc_info:
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5,
                botones=[DatosBoton(ref="fuera", fila=10, columna=0, articulo_id=articulo_id)],
            ))
        assert "fuera" in exc_info.value.errores[0]
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


def test_guardar_layout_invalido_por_solape_no_persiste_nada(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, articulo_id = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(LayoutInvalido):
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5,
                botones=[
                    DatosBoton(ref="a", fila=0, columna=0, articulo_id=articulo_id),
                    DatosBoton(ref="b", fila=0, columna=0, funcion="cobrar"),
                ],
            ))
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


def test_guardar_layout_invalido_por_destino_no_persiste_nada(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(LayoutInvalido):
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5, botones=[DatosBoton(ref="vacio", fila=0, columna=0)],
            ))
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


def test_guardar_layout_invalido_por_funcion_no_persiste_nada(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(LayoutInvalido):
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5,
                botones=[DatosBoton(ref="mala", fila=0, columna=0, funcion="freir_pescado")],
            ))
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


def test_guardar_layout_rango_invalido_no_persiste_nada(crear_sesion, datos_base):
    # El backend valida el rango 1-12 tambien al guardar layout, no solo al crear pagina:
    # un cliente NO puede fijar filas/columnas absurdas por esta via.
    with crear_sesion() as s, s.begin():
        _, pagina_id, articulo_id = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(RangoRejillaInvalido):
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=999, columnas=5,
                botones=[DatosBoton(ref="a", fila=0, columna=0, articulo_id=articulo_id)],
            ))
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


# --- guardar_layout: paso 2, referencias inexistentes en BD (DestinoNoExiste) --

def test_guardar_layout_con_articulo_inexistente_falla_y_no_persiste(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(DestinoNoExiste):
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5,
                botones=[DatosBoton(ref="x", fila=0, columna=0, articulo_id=999999)],
            ))
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


def test_guardar_layout_con_familia_inexistente_falla_y_no_persiste(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _ = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)
    with crear_sesion() as s:
        with pytest.raises(DestinoNoExiste):
            _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5,
                botones=[DatosBoton(ref="x", fila=0, columna=0, familia_id=999999)],
            ))
    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


# --- guardar_layout: paso 3, reemplazo atomico en exito ------------------------

def test_guardar_layout_valido_reemplaza_el_anterior_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id, _articulo_viejo = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        nuevo_articulo_id = _articulo(s, datos_base, nombre="Guppy")
        nueva_familia_id = _familia(s, nombre="Plantas")
        s.commit()
    with crear_sesion() as s:
        _svc(s, datos_base).guardar_layout(pagina_id, DatosLayout(
            filas=6, columnas=6,
            botones=[
                DatosBoton(ref="a", fila=0, columna=0, articulo_id=nuevo_articulo_id,
                           color="#fff", icono="pez", texto="Guppy"),
                DatosBoton(ref="b", fila=1, columna=1, familia_id=nueva_familia_id),
                DatosBoton(ref="c", fila=5, columna=5, funcion="cobrar"),
            ],
        ))
    with crear_sesion() as s:
        pagina = s.get(PaginaBotonera, pagina_id)
        assert pagina.filas == 6 and pagina.columnas == 6
        botones = s.execute(
            select(Boton).where(Boton.pagina_id == pagina_id).order_by(Boton.fila)
        ).scalars().all()
        assert len(botones) == 3
        primero = botones[0]
        assert primero.articulo_id == nuevo_articulo_id
        assert primero.color == "#fff" and primero.icono == "pez" and primero.texto == "Guppy"
        assert _articulo_viejo not in {b.articulo_id for b in botones if b.articulo_id}
    assert len(_auditorias(crear_sesion, "guardar_layout_botonera")) == 1


def test_guardar_layout_con_excepcion_forzada_tras_reemplazo_hace_rollback_real(
    crear_sesion, datos_base, monkeypatch,
):
    """Confirma que el rollback es REAL (no solo validacion previa): se fuerza
    una excepcion DESPUES de que `reemplazar_botones` ya vacio (flush) la
    coleccion previa, y se verifica que los botones originales siguen intactos."""
    with crear_sesion() as s, s.begin():
        _, pagina_id, articulo_id = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        estado_previo = _estado_pagina(s, pagina_id)

    with crear_sesion() as s:
        svc = _svc(s, datos_base)

        def _auditar_forzado(*args, **kwargs):
            raise RuntimeError("fallo forzado a mitad de transaccion")

        monkeypatch.setattr(svc, "_auditar", _auditar_forzado)
        with pytest.raises(RuntimeError):
            svc.guardar_layout(pagina_id, DatosLayout(
                filas=4, columnas=5,
                botones=[DatosBoton(ref="nuevo", fila=2, columna=2, articulo_id=articulo_id)],
            ))
        # No se hizo commit: al cerrar la sesion sin commit, la transaccion revierte.

    with crear_sesion() as s:
        assert _estado_pagina(s, pagina_id) == estado_previo


# --- cargar_arbol --------------------------------------------------------------

def test_cargar_arbol_devuelve_perfil_pagina_boton(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, pagina_id, articulo_id = _perfil_con_pagina_y_boton(s, datos_base)
    with crear_sesion() as s:
        arbol = _svc(s, datos_base).cargar_arbol()
    assert len(arbol) == 1
    perfil = arbol[0]
    assert perfil["id"] == perfil_id and perfil["activo"] is True
    assert len(perfil["paginas"]) == 1
    pagina = perfil["paginas"][0]
    assert pagina["id"] == pagina_id and pagina["filas"] == 4 and pagina["columnas"] == 5
    assert len(pagina["botones"]) == 1
    assert pagina["botones"][0]["articulo_id"] == articulo_id
