"""Casos de uso de mantenimiento de familias (maestro, arbol de niveles ilimitados).

Reglas: el padre debe existir; reasignar el padre NUNCA puede crear un ciclo (una familia
no puede colgar de si misma ni de un descendiente suyo, o el CTE recursivo del arbol
entraria en bucle); no se desactiva una familia con hijos activos (dejaria huerfanos en la
navegacion); las familias NUNCA se borran, solo se activan/desactivan."""
from __future__ import annotations

from dataclasses import dataclass

from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import Familia


@dataclass
class DatosFamilia:
    nombre: str
    parent_id: int | None = None
    orden: int = 0
    color: str | None = None
    imagen: str | None = None
    visible_en_tactil: bool = True


class FamiliaNoEncontrada(Exception):
    pass


class FamiliaPadreNoExiste(Exception):
    pass


class CicloEnFamilia(Exception):
    pass


class FamiliaConHijos(Exception):
    pass


class ServicioFamilias:
    def __init__(self, uow: UnidadDeTrabajo, *, usuario_id: int | None = None, origen: str = "local"):
        self.uow = uow
        self.usuario_id = usuario_id
        self.origen = origen

    def crear(self, datos: DatosFamilia) -> int:
        self._validar_padre_existe(datos.parent_id)
        familia = Familia(nombre=datos.nombre, parent_id=datos.parent_id,
                          orden=datos.orden, color=datos.color, imagen=datos.imagen,
                          visible_en_tactil=datos.visible_en_tactil)
        self.uow.familias.agregar(familia)
        self.uow.flush()
        self._auditar("crear_familia", familia.id)
        self.uow.commit()
        return familia.id

    def actualizar(self, familia_id: int, datos: DatosFamilia) -> None:
        familia = self.uow.familias.buscar(familia_id)
        if familia is None:
            raise FamiliaNoEncontrada(familia_id)
        self._validar_padre_existe(datos.parent_id)
        self._validar_sin_ciclo(familia_id, datos.parent_id)

        familia.nombre = datos.nombre
        familia.parent_id = datos.parent_id
        familia.orden = datos.orden
        familia.color = datos.color
        familia.imagen = datos.imagen
        familia.visible_en_tactil = datos.visible_en_tactil
        self._auditar("actualizar_familia", familia.id)
        self.uow.commit()

    def desactivar(self, familia_id: int) -> None:
        familia = self.uow.familias.buscar(familia_id)
        if familia is None:
            raise FamiliaNoEncontrada(familia_id)
        if self.uow.familias.hijos(familia_id, solo_activos=True):
            raise FamiliaConHijos(familia_id)
        familia.activo = False
        self._auditar("desactivar_familia", familia.id)
        self.uow.commit()

    def activar(self, familia_id: int) -> None:
        familia = self.uow.familias.buscar(familia_id)
        if familia is None:
            raise FamiliaNoEncontrada(familia_id)
        familia.activo = True
        self._auditar("activar_familia", familia.id)
        self.uow.commit()

    # -- helpers ---------------------------------------------------------------
    def _validar_padre_existe(self, parent_id: int | None) -> None:
        if parent_id is not None and self.uow.familias.buscar(parent_id) is None:
            raise FamiliaPadreNoExiste(parent_id)

    def _validar_sin_ciclo(self, familia_id: int, parent_id: int | None) -> None:
        """Colgar `familia_id` de `parent_id` crea un ciclo si la propia familia es
        antecesor (o igual) del padre propuesto. Se sube por la cadena de padres."""
        actual = parent_id
        while actual is not None:
            if actual == familia_id:
                raise CicloEnFamilia(familia_id)
            padre = self.uow.familias.buscar(actual)
            actual = padre.parent_id if padre is not None else None

    def _auditar(self, accion: str, familia_id: int) -> None:
        self.uow.auditoria.registrar(
            accion=accion, entidad="familia", entidad_id=str(familia_id),
            usuario_id=self.usuario_id, origen=self.origen)
