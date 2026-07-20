"""Resolucion y calculo de las lineas de un ticket (reutilizado por calcular y cobrar).

Usa la funcion unica de redondeo (dominio) y busca los articulos por el puerto de
repositorio (inversion de dependencias; sin acceso directo al ORM)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from app.dominio.servicios.redondeo import Linea, Totales, agregar_totales, calcular_linea
from app.infraestructura.persistencia.modelos.venta import VentaLinea

if TYPE_CHECKING:
    from app.dominio.puertos import RepositorioArticulos
    from app.infraestructura.persistencia.modelos.maestros import Articulo


@dataclass
class ItemVenta:
    articulo_id: int
    cantidad: Decimal = field(default_factory=lambda: Decimal("1"))
    pvp: Decimal | None = None  # override de precio unitario (cualquier articulo)
    descripcion: str | None = None  # override de descripcion de linea


@dataclass
class LineaResuelta:
    articulo: "Articulo"
    pvp: Decimal
    cantidad: Decimal
    descripcion: str
    calculo: Linea


class ArticuloNoExiste(Exception):
    def __init__(self, articulo_id: int):
        super().__init__(f"Articulo {articulo_id} no existe")
        self.articulo_id = articulo_id


class PrecioLibreRequerido(Exception):
    """Modo `libre`: exige un precio (override o catalogo) mayor que 0,00 EUR
    SOLO al emitir/aparcar; el preview `/calcular` nunca bloquea por esto (ver
    design.md). La descripcion, en cambio, es OPCIONAL: un generico siempre
    trae un nombre de catalogo, que basta para describir el bien (art. 7 ROF)."""

    def __init__(self, articulo_id: int):
        super().__init__(f"El articulo {articulo_id} (modo libre) exige un precio mayor que 0,00")
        self.articulo_id = articulo_id


def resolver_items(
    articulos: "RepositorioArticulos", items, *, exigir_precio_libre: bool = False
) -> tuple[list[LineaResuelta], Totales]:
    resueltas: list[LineaResuelta] = []
    calculos: list[Linea] = []
    for it in items:
        articulo = articulos.buscar(it.articulo_id)
        if articulo is None:
            raise ArticuloNoExiste(it.articulo_id)
        # El override de pvp aplica a CUALQUIER articulo (no solo modo_precio == "libre"):
        # el hecho fiscal auditable es "precio cobrado != catalogo" (ver EmitirVenta).
        pvp = it.pvp if it.pvp is not None else articulo.pvp
        descripcion_override = (getattr(it, "descripcion", None) or "").strip()
        if exigir_precio_libre and articulo.modo_precio == "libre" and Decimal(pvp) <= 0:
            raise PrecioLibreRequerido(articulo.id)
        descripcion = descripcion_override or articulo.nombre
        calculo = calcular_linea(
            Decimal(pvp), Decimal(it.cantidad), Decimal(articulo.tipo_iva.porcentaje)
        )
        resueltas.append(
            LineaResuelta(articulo, Decimal(pvp), Decimal(it.cantidad), descripcion, calculo)
        )
        calculos.append(calculo)
    return resueltas, agregar_totales(calculos)


def construir_lineas(resueltas: list[LineaResuelta]) -> list[VentaLinea]:
    """Construye las `VentaLinea` (precios/descripcion CONGELADOS) a partir de
    lineas ya resueltas. Compartido por `EmitirVenta` y `AparcarVenta`: DRY sin
    cambiar los objetos que produce cada linea (mismos campos, mismo orden)."""
    return [
        VentaLinea(
            articulo_id=lr.articulo.id, descripcion=lr.descripcion,
            cantidad=lr.cantidad, pvp_unitario=lr.pvp,
            tipo_iva_porcentaje=lr.calculo.porcentaje, base_linea=lr.calculo.base,
            cuota_linea=lr.calculo.cuota, total_linea=lr.calculo.total,
        )
        for lr in resueltas
    ]
