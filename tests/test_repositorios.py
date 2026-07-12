"""Adaptadores SQLAlchemy de los puertos de repositorio."""
from __future__ import annotations

from decimal import Decimal

from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import Articulo, CodigoBarras, MovimientoStock
from app.infraestructura.reloj import ahora_huso


def test_repositorio_articulos(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        a = Articulo(nombre="Neon cardenal", nombre_corto="Neon",
                     tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
        s.add(a)
        s.flush()
        s.add(CodigoBarras(articulo_id=a.id, codigo="8412345678905", principal=True))
        articulo_id = a.id

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        assert repo.buscar(articulo_id).nombre_corto == "Neon"
        assert repo.buscar(999999) is None
        assert repo.buscar_por_codigo("8412345678905").id == articulo_id
        assert repo.buscar_por_codigo("no-existe") is None


def test_repositorio_articulos_buscar_por_nombre_coincide_por_nombre(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Betta Splendens Macho", nombre_corto="Betta",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("5.00")))
        s.add(Articulo(nombre="Guppy Endler", nombre_corto="Guppy",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        resultado = repo.buscar_por_nombre("splendens")
        assert [a.nombre for a in resultado] == ["Betta Splendens Macho"]


def test_repositorio_articulos_buscar_por_nombre_coincide_por_nombre_corto(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Pez tetra", nombre_corto="xyzcorto",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00")))
        s.add(Articulo(nombre="Otro pez", nombre_corto="Otro",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        resultado = repo.buscar_por_nombre("xyz")
        assert [a.nombre for a in resultado] == ["Pez tetra"]


def test_repositorio_articulos_buscar_por_nombre_case_insensitive(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Betta Splendens Macho", nombre_corto="Betta",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("5.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        resultado = repo.buscar_por_nombre("BETTA")
        assert [a.nombre for a in resultado] == ["Betta Splendens Macho"]


def test_repositorio_articulos_buscar_por_nombre_query_corta_devuelve_vacio(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Betta Splendens Macho", nombre_corto="Betta",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("5.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        assert repo.buscar_por_nombre("") == []
        assert repo.buscar_por_nombre("a") == []


def test_repositorio_articulos_buscar_por_nombre_excluye_inactivos(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Guppy activo", nombre_corto="Guppy",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00")))
        s.add(Articulo(nombre="Guppy inactivo", nombre_corto="Guppy2",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00"), activo=False))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        resultado = repo.buscar_por_nombre("guppy")
        assert [a.nombre for a in resultado] == ["Guppy activo"]


def test_repositorio_articulos_buscar_por_nombre_respeta_limite_y_orden(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        for i in range(25):
            s.add(Articulo(nombre=f"Pez {i:02d}", nombre_corto=f"P{i:02d}",
                           tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        resultado = repo.buscar_por_nombre("pez", limite=20)
        assert len(resultado) == 20
        nombres = [a.nombre for a in resultado]
        assert nombres == sorted(nombres)


def test_repositorio_articulos_buscar_por_nombre_escapa_comodin_guion_bajo(crear_sesion, datos_base):
    """Si `_` no se escapara actuaria como comodin LIKE de "cualquier caracter",
    y "Xavier azul"/"Yavier azul" tambien coincidirian con q="_a" (X/Y + "a")."""
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Test_awesome", nombre_corto="TestA",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00")))
        s.add(Articulo(nombre="Xavier azul", nombre_corto="Xa",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00")))
        s.add(Articulo(nombre="Yavier azul", nombre_corto="Ya",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        resultado = repo.buscar_por_nombre("_a")
        assert [a.nombre for a in resultado] == ["Test_awesome"]


def test_repositorio_articulos_buscar_por_nombre_query_de_un_caracter_wildcard_no_devuelve_todo(
    crear_sesion, datos_base
):
    with crear_sesion() as s, s.begin():
        s.add(Articulo(nombre="Betta Splendens Macho", nombre_corto="Betta",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("5.00")))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).articulos
        assert repo.buscar_por_nombre("%") == []


def test_repositorio_usuarios(crear_sesion, datos_base):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).usuarios
        assert repo.buscar(datos_base["usuario_id"]).rol == "venta"
        assert repo.buscar(999999) is None


def _crear_articulo(s, datos_base, *, control_stock: bool, nombre: str = "Guppy") -> int:
    articulo = Articulo(nombre=nombre, nombre_corto=nombre,
                         tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00"),
                         control_stock=control_stock)
    s.add(articulo)
    s.flush()
    return articulo.id


def test_repositorio_configuracion_control_stock_desactivado_por_defecto(crear_sesion):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).configuracion
        assert repo.control_stock_activo() is False


def test_repositorio_configuracion_fijar_control_stock_persiste(crear_sesion):
    with crear_sesion() as s:
        UnidadDeTrabajoSQL(s).configuracion.fijar_control_stock(True)
        s.commit()

    with crear_sesion() as s:
        assert UnidadDeTrabajoSQL(s).configuracion.control_stock_activo() is True


def test_repositorio_stock_calcula_saldo_con_entrada_venta_merma(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        articulo_id = _crear_articulo(s, datos_base, control_stock=True)
        uow = UnidadDeTrabajoSQL(s)
        uow.stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="entrada", cantidad=Decimal("10"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="venta", cantidad=Decimal("3"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=articulo_id, tipo="merma", cantidad=Decimal("2"), motivo="rotura",
            fecha_hora_huso=ahora_huso()))

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).stock
        assert repo.stock_actual(articulo_id) == Decimal("5")
        assert len(repo.movimientos(articulo_id)) == 3


def test_repositorio_stock_rastreados_en_negativo_solo_lista_negativos(crear_sesion, datos_base):
    with crear_sesion() as s, s.begin():
        negativo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Molly")
        positivo_id = _crear_articulo(s, datos_base, control_stock=True, nombre="Platy")
        no_rastreado_id = _crear_articulo(s, datos_base, control_stock=False, nombre="Planta")
        uow = UnidadDeTrabajoSQL(s)
        uow.stock.agregar(MovimientoStock(
            articulo_id=negativo_id, tipo="venta", cantidad=Decimal("4"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=positivo_id, tipo="entrada", cantidad=Decimal("4"),
            fecha_hora_huso=ahora_huso()))
        uow.stock.agregar(MovimientoStock(
            articulo_id=no_rastreado_id, tipo="venta", cantidad=Decimal("10"),
            fecha_hora_huso=ahora_huso()))

    with crear_sesion() as s:
        negativos = UnidadDeTrabajoSQL(s).stock.rastreados_en_negativo()
        assert negativos == [(negativo_id, Decimal("-4"))]
