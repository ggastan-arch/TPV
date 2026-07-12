"""Casos de uso de mantenimiento de articulos (maestro).

Reglas: se validan las FK (tipo de IVA y familia); el cambio de precio queda en el log
de auditoria (invariante 4); los articulos NUNCA se borran, solo se activan/desactivan
(activo=false), porque pueden tener ventas asociadas."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import Articulo, CodigoBarras


@dataclass
class DatosArticulo:
    nombre: str
    nombre_corto: str
    tipo_iva_id: int
    pvp: Decimal
    familia_id: int | None = None
    coste: Decimal | None = None
    control_stock: bool = False
    precio_libre: bool = False
    requiere_cites: bool = False
    color_boton: str | None = None
    icono: str | None = None
    codigos: list[str] = field(default_factory=list)


class TipoIvaNoExiste(Exception):
    pass


class FamiliaNoExiste(Exception):
    pass


class ArticuloNoEncontrado(Exception):
    pass


class ServicioArticulos:
    def __init__(self, uow: UnidadDeTrabajo, *, usuario_id: int | None = None, origen: str = "local"):
        self.uow = uow
        self.usuario_id = usuario_id
        self.origen = origen

    def crear(self, datos: DatosArticulo) -> int:
        self._validar_refs(datos)
        articulo = Articulo(
            nombre=datos.nombre, nombre_corto=datos.nombre_corto,
            familia_id=datos.familia_id, tipo_iva_id=datos.tipo_iva_id,
            pvp=Decimal(datos.pvp),
            coste=Decimal(datos.coste) if datos.coste is not None else None,
            control_stock=datos.control_stock, precio_libre=datos.precio_libre,
            requiere_cites=datos.requiere_cites, color_boton=datos.color_boton,
            icono=datos.icono,
        )
        for codigo in datos.codigos:
            articulo.codigos.append(CodigoBarras(codigo=codigo))
        self.uow.articulos.agregar(articulo)
        self.uow.flush()  # asignar id antes de auditar
        self._auditar("crear_articulo", articulo.id)
        self.uow.commit()
        return articulo.id

    def actualizar(self, articulo_id: int, datos: DatosArticulo) -> None:
        articulo = self.uow.articulos.buscar(articulo_id)
        if articulo is None:
            raise ArticuloNoEncontrado(articulo_id)
        self._validar_refs(datos)

        precio_anterior = articulo.pvp
        nuevo_precio = Decimal(datos.pvp)
        articulo.nombre = datos.nombre
        articulo.nombre_corto = datos.nombre_corto
        articulo.familia_id = datos.familia_id
        articulo.tipo_iva_id = datos.tipo_iva_id
        articulo.pvp = nuevo_precio
        articulo.coste = Decimal(datos.coste) if datos.coste is not None else None
        articulo.control_stock = datos.control_stock
        articulo.precio_libre = datos.precio_libre
        articulo.requiere_cites = datos.requiere_cites
        articulo.color_boton = datos.color_boton
        articulo.icono = datos.icono

        if nuevo_precio != precio_anterior:
            self._auditar("cambio_precio", articulo.id, detalle=f"{precio_anterior} -> {nuevo_precio}")
        else:
            self._auditar("actualizar_articulo", articulo.id)
        self.uow.commit()

    def desactivar(self, articulo_id: int) -> None:
        self._cambiar_activo(articulo_id, False, "desactivar_articulo")

    def activar(self, articulo_id: int) -> None:
        self._cambiar_activo(articulo_id, True, "activar_articulo")

    def fijar_imagen(self, articulo_id: int, ruta: str) -> str | None:
        """Fija `Articulo.imagen` a `ruta` (ya validada y guardada en disco por
        el endpoint de subida) y devuelve la ruta anterior (o `None`), para que
        el endpoint pueda borrar el archivo huerfano tras el commit."""
        articulo = self.uow.articulos.buscar(articulo_id)
        if articulo is None:
            raise ArticuloNoEncontrado(articulo_id)
        anterior = articulo.imagen
        articulo.imagen = ruta
        self._auditar("cambiar_imagen_articulo", articulo.id, detalle=ruta)
        self.uow.commit()
        return anterior

    # -- helpers ---------------------------------------------------------------
    def _cambiar_activo(self, articulo_id: int, activo: bool, accion: str) -> None:
        articulo = self.uow.articulos.buscar(articulo_id)
        if articulo is None:
            raise ArticuloNoEncontrado(articulo_id)
        articulo.activo = activo
        self._auditar(accion, articulo.id)
        self.uow.commit()

    def _validar_refs(self, datos: DatosArticulo) -> None:
        if self.uow.tipos_iva.buscar(datos.tipo_iva_id) is None:
            raise TipoIvaNoExiste(datos.tipo_iva_id)
        if datos.familia_id is not None and self.uow.familias.buscar(datos.familia_id) is None:
            raise FamiliaNoExiste(datos.familia_id)

    def _auditar(self, accion: str, articulo_id: int, detalle: str | None = None) -> None:
        self.uow.auditoria.registrar(
            accion=accion, entidad="articulo", entidad_id=str(articulo_id),
            detalle=detalle, usuario_id=self.usuario_id, origen=self.origen)
