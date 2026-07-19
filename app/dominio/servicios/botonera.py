"""Validacion pura de layouts de botonera: rejilla + destino de cada boton.

Un boton apunta EXACTAMENTE a uno de: articulo, familia (navega a hijos) o
funcion (accion rapida del TPV: cobrar, convertir_factura, etc.). El conjunto
de funciones soportadas (`FUNCIONES`) es un concepto de DOMINIO: se define
aqui y `app.infraestructura.persistencia.modelos.botonera` lo importa (la
infraestructura depende del dominio, nunca al reves; ver ADR-0001 y el
contrato de dependencias hexagonal en pyproject.toml).

`validar_layout_botonera` es PURA: solo stdlib, sin ORM, sin sesion, sin I/O.
NO valida existencia de articulo/familia en BD (eso depende de sesion y es
responsabilidad de `ServicioBotonera`, capa de aplicacion)."""
from __future__ import annotations

from dataclasses import dataclass

FUNCIONES = (
    "cobrar",
    "convertir_factura",
    "devolucion",
    "aparcar",
    "desaparcar",
    "abrir_cajon",
    "descuento",
    "cierre_caja",
)


@dataclass(frozen=True)
class BotonSpec:
    """Espejo, sin ORM, de un boton a validar. `ref` identifica el boton (id de
    cliente/JS) para localizarlo en los errores devueltos."""

    ref: str
    fila: int
    columna: int
    ancho: int
    alto: int
    articulo_id: int | None = None
    familia_id: int | None = None
    funcion: str | None = None


def validar_layout_botonera(filas: int, columnas: int, botones: list[BotonSpec]) -> list[str]:
    """Devuelve TODOS los errores de un layout completo (lista vacia == valido).
    No corta en el primer error: cada boton problematico se acumula.

    Reglas:
      - limites: fila/columna negativos, ancho/alto < 1, o el boton se sale de
        la rejilla (`fila + alto > filas`, `columna + ancho > columnas`).
      - solape AABB: dos botones cuyos rectangulos
        [columna, columna+ancho) x [fila, fila+alto) se intersectan (bordes
        que solo se tocan NO cuentan como solape).
      - destino unico: exactamente uno de {articulo_id, familia_id, funcion}
        debe estar informado.
      - funcion valida: si el destino es funcion, debe pertenecer a FUNCIONES.
    """
    errores: list[str] = []
    for boton in botones:
        errores.extend(_errores_limites(boton, filas, columnas))
        errores.extend(_errores_destino(boton))
    errores.extend(_errores_solape(botones))
    return errores


def _errores_limites(boton: BotonSpec, filas: int, columnas: int) -> list[str]:
    errores: list[str] = []
    if boton.fila < 0 or boton.columna < 0:
        errores.append(f"{boton.ref}: fila/columna no puede ser negativa")
    if boton.ancho < 1 or boton.alto < 1:
        errores.append(f"{boton.ref}: ancho/alto debe ser >= 1")
    if boton.fila + boton.alto > filas:
        errores.append(f"{boton.ref}: excede el numero de filas de la pagina")
    if boton.columna + boton.ancho > columnas:
        errores.append(f"{boton.ref}: excede el numero de columnas de la pagina")
    return errores


def _errores_destino(boton: BotonSpec) -> list[str]:
    destinos = (boton.articulo_id is not None, boton.familia_id is not None, boton.funcion is not None)
    if sum(destinos) != 1:
        return [f"{boton.ref}: debe referenciar exactamente un destino (articulo, familia o funcion)"]
    if boton.funcion is not None and boton.funcion not in FUNCIONES:
        return [f"{boton.ref}: funcion '{boton.funcion}' no soportada"]
    return []


def _se_solapan(a: BotonSpec, b: BotonSpec) -> bool:
    """AABB: rectangulos [columna, columna+ancho) x [fila, fila+alto)."""
    if a.columna + a.ancho <= b.columna or b.columna + b.ancho <= a.columna:
        return False
    if a.fila + a.alto <= b.fila or b.fila + b.alto <= a.fila:
        return False
    return True


def _errores_solape(botones: list[BotonSpec]) -> list[str]:
    errores: list[str] = []
    for i, a in enumerate(botones):
        for b in botones[i + 1:]:
            if _se_solapan(a, b):
                errores.append(f"{a.ref}/{b.ref}: los botones se solapan")
    return errores
