"""Casos de uso de mantenimiento de articulos (maestro), probados sin HTTP.

Reglas verificadas: validacion de FK (tipo de IVA/familia), auditoria del cambio de
precio (invariante 4) y borrado logico (activo=false, nunca DELETE)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text

from app.aplicacion.articulos import (
    ArticuloNoEncontrado,
    DatosArticulo,
    FamiliaNoExiste,
    ModoPrecioInvalido,
    ServicioArticulos,
    TipoIvaNoExiste,
)
from app.infraestructura.persistencia.modelos import Articulo, Familia, LogAuditoria
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _svc(session, datos_base):
    return ServicioArticulos(
        UnidadDeTrabajoSQL(session), usuario_id=datos_base["usuario_id"], origen="local")


def _datos(datos_base, **extra):
    base = dict(nombre="Neon cardenal", nombre_corto="Neon",
                tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
    base.update(extra)
    return DatosArticulo(**base)


@pytest.fixture
def familia_id(session):
    fam = Familia(nombre="Peces", orden=0)
    session.add(fam)
    session.commit()
    return fam.id


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def test_crear_articulo_persiste_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))

    with crear_sesion() as s:
        articulo = s.get(Articulo, articulo_id)
        assert articulo is not None
        assert articulo.nombre == "Neon cardenal"
        assert articulo.pvp == Decimal("2.50")
        assert articulo.activo is True

    logs = _auditorias(crear_sesion, "crear_articulo")
    assert len(logs) == 1
    assert logs[0].entidad == "articulo"
    assert logs[0].entidad_id == str(articulo_id)
    assert logs[0].usuario_id == datos_base["usuario_id"]


def test_crear_articulo_con_codigo_de_barras(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base, codigos=["8412345678905"]))

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        encontrado = uow.articulos.buscar_por_codigo("8412345678905")
        assert encontrado is not None
        assert encontrado.id == articulo_id


def test_crear_con_familia_valida(crear_sesion, datos_base, familia_id):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base, familia_id=familia_id))
    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).familia_id == familia_id


def test_crear_tipo_iva_inexistente_falla_y_no_persiste(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(TipoIvaNoExiste):
            _svc(s, datos_base).crear(_datos(datos_base, tipo_iva_id=999999))

    with crear_sesion() as s:
        assert s.query(Articulo).count() == 0


def test_crear_familia_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(FamiliaNoExiste):
            _svc(s, datos_base).crear(_datos(datos_base, familia_id=999999))


def test_actualizar_cambia_precio_y_audita_cambio_precio(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(articulo_id, _datos(datos_base, pvp=Decimal("3.00")))

    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).pvp == Decimal("3.00")

    logs = _auditorias(crear_sesion, "cambio_precio")
    assert len(logs) == 1
    assert "2.50" in logs[0].detalle and "3.00" in logs[0].detalle


def test_actualizar_sin_cambio_de_precio_no_audita_cambio_precio(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(articulo_id, _datos(datos_base, nombre="Neon rey"))

    assert _auditorias(crear_sesion, "cambio_precio") == []
    assert len(_auditorias(crear_sesion, "actualizar_articulo")) == 1
    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).nombre == "Neon rey"


def test_actualizar_articulo_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(ArticuloNoEncontrado):
            _svc(s, datos_base).actualizar(999999, _datos(datos_base))


def test_desactivar_no_borra_marca_inactivo(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(articulo_id)

    with crear_sesion() as s:
        articulo = s.get(Articulo, articulo_id)
        assert articulo is not None  # sigue existiendo (borrado logico)
        assert articulo.activo is False
    assert len(_auditorias(crear_sesion, "desactivar_articulo")) == 1


def test_activar_reactiva(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))
        _svc(s, datos_base).desactivar(articulo_id)
    with crear_sesion() as s:
        _svc(s, datos_base).activar(articulo_id)
    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).activo is True


def test_listar_puede_excluir_inactivos(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        id_activo = svc.crear(_datos(datos_base, nombre="Activo"))
        id_inactivo = svc.crear(_datos(datos_base, nombre="Inactivo"))
        svc.desactivar(id_inactivo)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        ids_visibles = [a.id for a in uow.articulos.listar(incluir_inactivos=False)]
        assert id_activo in ids_visibles
        assert id_inactivo not in ids_visibles
        assert len(uow.articulos.listar(incluir_inactivos=True)) == 2


# --- Migracion 0007: precio_libre (bool) -> modo_precio (fijo|libre|al_peso) ---


def _insertar_articulo_pre_migracion(conn, *, id_: int, precio_libre: int) -> None:
    conn.execute(text(
        "INSERT INTO articulo (id, nombre, nombre_corto, tipo_iva_id, pvp, control_stock, "
        "precio_libre, requiere_cites, activo) "
        "VALUES (:id, :nombre, :nombre, 1, '10.00', 0, :precio_libre, 0, 1)"
    ), {"id": id_, "nombre": f"Articulo {id_}", "precio_libre": precio_libre})


def test_migracion_precio_libre_a_modo_precio(tmp_path, aplicar_migraciones, bajar_migraciones):
    db = tmp_path / "migracion_modo_precio.db"
    url = f"sqlite:///{db}"

    aplicar_migraciones(url, "0006_articulo_imagen")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO tipo_iva (id, nombre, porcentaje, calificacion, activo) "
            "VALUES (1, 'General', '21.00', 'S1', 1)"
        ))
        _insertar_articulo_pre_migracion(conn, id_=1, precio_libre=1)
        _insertar_articulo_pre_migracion(conn, id_=2, precio_libre=0)

    aplicar_migraciones(url, "0007_modo_precio_articulo")

    with engine.connect() as conn:
        filas = dict(conn.execute(text("SELECT id, modo_precio FROM articulo ORDER BY id")).all())
    assert filas == {1: "libre", 2: "fijo"}

    columnas = {c["name"] for c in inspect(engine).get_columns("articulo")}
    assert "precio_libre" not in columnas
    assert "modo_precio" in columnas
    engine.dispose()

    bajar_migraciones(url, "0006_articulo_imagen")

    engine = create_engine(url)
    with engine.connect() as conn:
        filas = dict(conn.execute(text("SELECT id, precio_libre FROM articulo ORDER BY id")).all())
    assert filas == {1: 1, 2: 0}

    columnas = {c["name"] for c in inspect(engine).get_columns("articulo")}
    assert "modo_precio" not in columnas
    assert "precio_libre" in columnas
    engine.dispose()


# --- CRUD: modo_precio editable, validado y auditado ---------------------------


def test_crear_articulo_sin_modo_precio_usa_default_fijo(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))

    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).modo_precio == "fijo"


def test_crear_articulo_modo_al_peso(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(
            _datos(datos_base, modo_precio="al_peso", pvp=Decimal("12.00")))

    with crear_sesion() as s:
        articulo = s.get(Articulo, articulo_id)
        assert articulo.modo_precio == "al_peso"
        assert articulo.pvp == Decimal("12.00")


def test_actualizar_modo_precio_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        articulo_id = _svc(s, datos_base).crear(_datos(datos_base))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(articulo_id, _datos(datos_base, modo_precio="libre"))

    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).modo_precio == "libre"

    logs = _auditorias(crear_sesion, "actualizar_articulo")
    assert len(logs) == 1
    assert logs[0].entidad_id == str(articulo_id)


def test_modo_precio_invalido_falla_y_no_persiste(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(ModoPrecioInvalido):
            _svc(s, datos_base).crear(_datos(datos_base, modo_precio="otro"))

    with crear_sesion() as s:
        assert s.query(Articulo).count() == 0
