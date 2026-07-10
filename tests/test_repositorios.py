"""Adaptadores SQLAlchemy de los puertos de repositorio."""
from __future__ import annotations

from decimal import Decimal

from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.persistencia.modelos import Articulo, CodigoBarras


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


def test_repositorio_usuarios(crear_sesion, datos_base):
    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).usuarios
        assert repo.buscar(datos_base["usuario_id"]).rol == "venta"
        assert repo.buscar(999999) is None
