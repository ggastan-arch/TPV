"""Tests de integracion del repositorio de botonera (UoW sobre SQLite in-memory
con migracion real), mismo patron que tests/test_repositorios.py."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
    Familia,
    PaginaBotonera,
    PerfilBotonera,
)
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _articulo(s, datos_base, nombre="Neon") -> int:
    a = Articulo(nombre=nombre, nombre_corto=nombre, tipo_iva_id=datos_base["iva21_id"],
                 pvp=Decimal("2.50"))
    s.add(a)
    s.flush()
    return a.id


def _familia(s, nombre="Peces") -> int:
    f = Familia(nombre=nombre)
    s.add(f)
    s.flush()
    return f.id


def _perfil_con_pagina_y_botones(s, datos_base) -> tuple[int, int]:
    """Crea un perfil con una pagina de 3 botones (articulo, familia, funcion)."""
    articulo_id = _articulo(s, datos_base)
    familia_id = _familia(s)
    perfil = PerfilBotonera(nombre="Principal", activo=True)
    s.add(perfil)
    s.flush()
    pagina = PaginaBotonera(perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4)
    s.add(pagina)
    s.flush()
    s.add_all([
        Boton(pagina_id=pagina.id, fila=0, columna=0, articulo_id=articulo_id),
        Boton(pagina_id=pagina.id, fila=1, columna=0, familia_id=familia_id),
        Boton(pagina_id=pagina.id, fila=3, columna=4, funcion="cobrar"),
    ])
    s.flush()
    return perfil.id, pagina.id


def _contar_botones(s, pagina_id: int) -> int:
    return s.execute(
        select(func.count()).select_from(Boton).where(Boton.pagina_id == pagina_id)
    ).scalar_one()


def test_arbol_devuelve_perfiles_con_paginas_y_botones(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, pagina_id = _perfil_con_pagina_y_botones(s, datos_base)

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).botoneras
        arbol = repo.arbol()
        assert len(arbol) == 1
        perfil = arbol[0]
        assert perfil.id == perfil_id
        assert len(perfil.paginas) == 1
        assert perfil.paginas[0].id == pagina_id
        assert len(perfil.paginas[0].botones) == 3


def test_buscar_perfil_existente_y_inexistente(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, _ = _perfil_con_pagina_y_botones(s, datos_base)

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).botoneras
        assert repo.buscar_perfil(perfil_id).nombre == "Principal"
        assert repo.buscar_perfil(999999) is None


def test_buscar_pagina_existente_y_inexistente(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id = _perfil_con_pagina_y_botones(s, datos_base)

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).botoneras
        assert repo.buscar_pagina(pagina_id).nombre == "Inicio"
        assert repo.buscar_pagina(999999) is None


def test_agregar_perfil_persiste(crear_sesion):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).botoneras
        nuevo = PerfilBotonera(nombre="Secundario", activo=False)
        repo.agregar_perfil(nuevo)
        s.commit()
        nuevo_id = nuevo.id

    with crear_sesion() as s:
        recargado = UnidadDeTrabajoSQL(s).botoneras.buscar_perfil(nuevo_id)
        assert recargado.nombre == "Secundario"
        assert recargado.activo is False


def test_agregar_pagina_persiste(crear_sesion):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).botoneras
        perfil = PerfilBotonera(nombre="Principal", activo=True)
        repo.agregar_perfil(perfil)
        s.flush()
        pagina = PaginaBotonera(perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4)
        repo.agregar_pagina(pagina)
        s.commit()
        pagina_id = pagina.id

    with crear_sesion() as s:
        recargada = UnidadDeTrabajoSQL(s).botoneras.buscar_pagina(pagina_id)
        assert recargada.nombre == "Inicio"
        assert recargada.columnas == 5 and recargada.filas == 4


def test_perfiles_devuelve_todos(crear_sesion):
    with crear_sesion() as s, s.begin():
        s.add_all([
            PerfilBotonera(nombre="Uno", activo=True),
            PerfilBotonera(nombre="Dos", activo=False),
        ])

    with crear_sesion() as s:
        nombres = {p.nombre for p in UnidadDeTrabajoSQL(s).botoneras.perfiles()}
        assert nombres == {"Uno", "Dos"}


def test_reemplazar_botones_borra_los_previos_de_bd(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id = _perfil_con_pagina_y_botones(s, datos_base)

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).botoneras
        pagina = repo.buscar_pagina(pagina_id)
        assert _contar_botones(s, pagina_id) == 3
        nuevo_articulo_id = _articulo(s, datos_base, nombre="Guppy")
        repo.reemplazar_botones(pagina, [
            Boton(fila=2, columna=2, articulo_id=nuevo_articulo_id),
        ])
        s.commit()

    with crear_sesion() as s:
        assert _contar_botones(s, pagina_id) == 1
        boton = s.execute(select(Boton).where(Boton.pagina_id == pagina_id)).scalars().first()
        assert boton.fila == 2 and boton.columna == 2 and boton.articulo_id == nuevo_articulo_id


def test_borrar_perfil_elimina_en_cascada_paginas_y_botones(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        perfil_id, pagina_id = _perfil_con_pagina_y_botones(s, datos_base)

    with crear_sesion() as s:
        assert _contar_botones(s, pagina_id) == 3
        perfil = s.get(PerfilBotonera, perfil_id)
        s.delete(perfil)
        s.commit()

    with crear_sesion() as s:
        assert s.get(PerfilBotonera, perfil_id) is None
        assert s.get(PaginaBotonera, pagina_id) is None
        assert _contar_botones(s, pagina_id) == 0


def test_borrar_pagina_elimina_en_cascada_botones(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        _, pagina_id = _perfil_con_pagina_y_botones(s, datos_base)

    with crear_sesion() as s:
        assert _contar_botones(s, pagina_id) == 3
        pagina = s.get(PaginaBotonera, pagina_id)
        s.delete(pagina)
        s.commit()

    with crear_sesion() as s:
        assert s.get(PaginaBotonera, pagina_id) is None
        assert _contar_botones(s, pagina_id) == 0
