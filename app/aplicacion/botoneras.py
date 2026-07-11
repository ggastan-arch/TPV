"""Casos de uso de mantenimiento de la botonera del TPV (perfil -> pagina -> boton).

Mismo patron que `ServicioFamilias`/`ServicioArticulos`: cada metodo valida -> muta
-> audita -> commit. El guardado de un layout completo (`guardar_layout`) es la
operacion critica: invoca la funcion pura del dominio (`validar_layout_botonera`)
para rechazar cualquier problema geometrico o de destino ANTES de tocar BD, luego
comprueba que los articulos/familias referenciados EXISTEN, y solo entonces
reemplaza los botones de la pagina de forma atomica (si algo falla despues,
la transaccion no se comitea y no persiste ningun cambio parcial)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.dominio.puertos import UnidadDeTrabajo
from app.dominio.servicios.botonera import BotonSpec, validar_layout_botonera
from app.infraestructura.persistencia.modelos import Boton, PaginaBotonera, PerfilBotonera

# Rango razonable de rejilla (ver design.md, Open Questions): evita layouts absurdos
# sin restringir casos de uso reales de una botonera de TPV tactil.
FILAS_COLUMNAS_MIN = 1
FILAS_COLUMNAS_MAX = 12


@dataclass
class DatosPagina:
    nombre: str
    orden: int = 0
    columnas: int = 5
    filas: int = 4


@dataclass
class DatosBoton:
    """Espejo de un boton a persistir: ademas de lo que valida la funcion pura
    del dominio (geometria + destino), lleva los atributos de presentacion."""

    ref: str
    fila: int
    columna: int
    ancho: int = 1
    alto: int = 1
    articulo_id: int | None = None
    familia_id: int | None = None
    funcion: str | None = None
    color: str | None = None
    icono: str | None = None
    texto: str | None = None


@dataclass
class DatosLayout:
    filas: int
    columnas: int
    botones: list[DatosBoton] = field(default_factory=list)


class PerfilNoEncontrado(Exception):
    pass


class PaginaNoEncontrada(Exception):
    pass


class RangoRejillaInvalido(Exception):
    pass


class DestinoNoExiste(Exception):
    """El `articulo_id`/`familia_id` referenciado por un boton no existe en BD."""


class LayoutInvalido(Exception):
    """Expone `.errores`: la lista completa de motivos de rechazo devueltos por
    `validar_layout_botonera` (ver app/dominio/servicios/botonera.py)."""

    def __init__(self, errores: list[str]):
        super().__init__("; ".join(errores))
        self.errores = errores


class ServicioBotonera:
    def __init__(self, uow: UnidadDeTrabajo, *, usuario_id: int | None = None, origen: str = "local"):
        self.uow = uow
        self.usuario_id = usuario_id
        self.origen = origen

    # -- lectura -----------------------------------------------------------------
    def cargar_arbol(self) -> list[dict]:
        """Estructura perfil -> pagina -> boton lista para el editor (JSON-able)."""
        return [self._perfil_dto(perfil) for perfil in self.uow.botoneras.arbol()]

    # -- perfiles ------------------------------------------------------------------
    def crear_perfil(self, nombre: str) -> int:
        perfil = PerfilBotonera(nombre=nombre, activo=False)
        self.uow.botoneras.agregar_perfil(perfil)
        self.uow.flush()
        self._auditar("crear_perfil_botonera", "perfil_botonera", perfil.id)
        self.uow.commit()
        return perfil.id

    def renombrar_perfil(self, perfil_id: int, nombre: str) -> None:
        perfil = self._buscar_perfil(perfil_id)
        perfil.nombre = nombre
        self._auditar("renombrar_perfil_botonera", "perfil_botonera", perfil_id)
        self.uow.commit()

    def activar_perfil(self, perfil_id: int) -> None:
        perfil = self._buscar_perfil(perfil_id)
        for otro in self.uow.botoneras.perfiles():
            if otro.id != perfil_id and otro.activo:
                otro.activo = False
        perfil.activo = True
        self._auditar("activar_perfil_botonera", "perfil_botonera", perfil_id)
        self.uow.commit()

    def borrar_perfil(self, perfil_id: int) -> None:
        perfil = self._buscar_perfil(perfil_id)
        self.uow.session.delete(perfil)
        self._auditar("borrar_perfil_botonera", "perfil_botonera", perfil_id)
        self.uow.commit()

    # -- paginas ---------------------------------------------------------------------
    def crear_pagina(self, perfil_id: int, datos: DatosPagina) -> int:
        self._buscar_perfil(perfil_id)
        self._validar_rango_rejilla(datos.filas, datos.columnas)
        pagina = PaginaBotonera(perfil_id=perfil_id, nombre=datos.nombre, orden=datos.orden,
                                 columnas=datos.columnas, filas=datos.filas)
        self.uow.botoneras.agregar_pagina(pagina)
        self.uow.flush()
        self._auditar("crear_pagina_botonera", "pagina_botonera", pagina.id)
        self.uow.commit()
        return pagina.id

    def actualizar_pagina(self, pagina_id: int, datos: DatosPagina) -> None:
        pagina = self._buscar_pagina(pagina_id)
        self._validar_rango_rejilla(datos.filas, datos.columnas)
        pagina.nombre = datos.nombre
        pagina.orden = datos.orden
        pagina.columnas = datos.columnas
        pagina.filas = datos.filas
        self._auditar("actualizar_pagina_botonera", "pagina_botonera", pagina_id)
        self.uow.commit()

    def borrar_pagina(self, pagina_id: int) -> None:
        pagina = self._buscar_pagina(pagina_id)
        self.uow.session.delete(pagina)
        self._auditar("borrar_pagina_botonera", "pagina_botonera", pagina_id)
        self.uow.commit()

    # -- layout: guardado atomico --------------------------------------------------
    def guardar_layout(self, pagina_id: int, datos: DatosLayout) -> None:
        pagina = self._buscar_pagina(pagina_id)

        specs = [
            BotonSpec(ref=b.ref, fila=b.fila, columna=b.columna, ancho=b.ancho, alto=b.alto,
                      articulo_id=b.articulo_id, familia_id=b.familia_id, funcion=b.funcion)
            for b in datos.botones
        ]
        errores = validar_layout_botonera(datos.filas, datos.columnas, specs)
        if errores:
            raise LayoutInvalido(errores)

        self._validar_refs_existen(datos.botones)

        pagina.filas = datos.filas
        pagina.columnas = datos.columnas
        nuevos = [
            Boton(fila=b.fila, columna=b.columna, ancho=b.ancho, alto=b.alto,
                  articulo_id=b.articulo_id, familia_id=b.familia_id, funcion=b.funcion,
                  color=b.color, icono=b.icono, texto=b.texto)
            for b in datos.botones
        ]
        self.uow.botoneras.reemplazar_botones(pagina, nuevos)
        self._auditar("guardar_layout_botonera", "pagina_botonera", pagina_id)
        self.uow.commit()

    # -- helpers --------------------------------------------------------------------
    def _buscar_perfil(self, perfil_id: int) -> PerfilBotonera:
        perfil = self.uow.botoneras.buscar_perfil(perfil_id)
        if perfil is None:
            raise PerfilNoEncontrado(perfil_id)
        return perfil

    def _buscar_pagina(self, pagina_id: int) -> PaginaBotonera:
        pagina = self.uow.botoneras.buscar_pagina(pagina_id)
        if pagina is None:
            raise PaginaNoEncontrada(pagina_id)
        return pagina

    def _validar_rango_rejilla(self, filas: int, columnas: int) -> None:
        if not (FILAS_COLUMNAS_MIN <= filas <= FILAS_COLUMNAS_MAX):
            raise RangoRejillaInvalido(
                f"filas={filas} fuera del rango [{FILAS_COLUMNAS_MIN}, {FILAS_COLUMNAS_MAX}]")
        if not (FILAS_COLUMNAS_MIN <= columnas <= FILAS_COLUMNAS_MAX):
            raise RangoRejillaInvalido(
                f"columnas={columnas} fuera del rango [{FILAS_COLUMNAS_MIN}, {FILAS_COLUMNAS_MAX}]")

    def _validar_refs_existen(self, botones: list[DatosBoton]) -> None:
        for boton in botones:
            if boton.articulo_id is not None and self.uow.articulos.buscar(boton.articulo_id) is None:
                raise DestinoNoExiste(f"{boton.ref}: articulo {boton.articulo_id} no existe")
            if boton.familia_id is not None and self.uow.familias.buscar(boton.familia_id) is None:
                raise DestinoNoExiste(f"{boton.ref}: familia {boton.familia_id} no existe")

    def _auditar(self, accion: str, entidad: str, entidad_id: int) -> None:
        self.uow.auditoria.registrar(
            accion=accion, entidad=entidad, entidad_id=str(entidad_id),
            usuario_id=self.usuario_id, origen=self.origen)

    def _perfil_dto(self, perfil: PerfilBotonera) -> dict:
        return {
            "id": perfil.id, "nombre": perfil.nombre, "activo": perfil.activo,
            "paginas": [self._pagina_dto(pagina) for pagina in perfil.paginas],
        }

    def _pagina_dto(self, pagina: PaginaBotonera) -> dict:
        return {
            "id": pagina.id, "nombre": pagina.nombre, "orden": pagina.orden,
            "filas": pagina.filas, "columnas": pagina.columnas,
            "botones": [self._boton_dto(boton) for boton in pagina.botones],
        }

    def _boton_dto(self, boton: Boton) -> dict:
        return {
            "id": boton.id, "fila": boton.fila, "columna": boton.columna,
            "ancho": boton.ancho, "alto": boton.alto,
            "color": boton.color, "icono": boton.icono, "texto": boton.texto,
            "articulo_id": boton.articulo_id, "familia_id": boton.familia_id,
            "funcion": boton.funcion,
        }
