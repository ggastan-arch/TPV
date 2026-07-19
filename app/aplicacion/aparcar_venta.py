"""Casos de uso: aparcar/listar/recuperar borradores no fiscales de venta.

Frontera fiscal por CONSTRUCCION (ADR-0004, spec aparcar-ticket): ninguno de
estos tres casos de uso recibe un `MotorFiscal` ni puede invocar `emit`. Un
borrador aparcado es `Venta(estado='aparcada')` + `VentaLinea` (+ etiqueta);
nunca tiene serie, numero, num_serie_factura, fecha_hora_huso ni
`RegistroFiscal` asociado, y no muta `ContadorSerie`.

El cobro de un borrador recuperado NO ocurre aqui: `RecuperarAparcada` CONSUME
(borra) el borrador y el cliente re-emite por el camino intacto
`EmitirVenta` / `POST /tpv/api/cobrar` ("delete-and-emit-fresh", ver design.md).
Sin dependencias de HTTP."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.aplicacion.lineas import ItemVenta, construir_lineas, resolver_items
from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import Venta


class TicketVacio(Exception):
    pass


class UsuarioNoValido(Exception):
    pass


class BorradorNoEncontrado(Exception):
    def __init__(self, venta_id: int):
        super().__init__(f"Borrador aparcado {venta_id} no existe")
        self.venta_id = venta_id


@dataclass
class AparcadaDTO:
    venta_id: int
    etiqueta: str | None
    total: Decimal
    n_lineas: int


@dataclass
class LineaCarritoDTO:
    articulo_id: int | None
    cantidad: Decimal
    pvp: Decimal
    descripcion: str


class AparcarVenta:
    """Persiste el carrito activo como `Venta(estado='aparcada')`. SIN `motor`:
    frontera fiscal por construccion (jamas puede invocar `emit`)."""

    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def ejecutar(
        self, *, usuario_id: int, items: list[ItemVenta], etiqueta: str | None = None
    ) -> int:
        if not items:
            raise TicketVacio()
        usuario = self.uow.usuarios.buscar(usuario_id)
        if usuario is None:
            raise UsuarioNoValido()
        # Un borrador no se emite, pero SI exige la misma validacion de
        # descripcion libre que `EmitirVenta` (mismo contrato): un articulo
        # `modo_precio == "libre"` sin descripcion se rechaza YA al aparcar,
        # para no dejar pasar en silencio un borrador que fallaria recien al
        # desaparcar+cobrar.
        lineas, totales = resolver_items(
            self.uow.articulos, items, exigir_descripcion_libre=True
        )
        venta = Venta(
            estado="aparcada", usuario_id=usuario.id, etiqueta_aparcada=etiqueta,
            base_total=totales.base_total, cuota_total=totales.cuota_total,
            total_con_iva=totales.total_con_iva,
        )
        venta.lineas.extend(construir_lineas(lineas))
        self.uow.ventas.agregar(venta)
        self.uow.commit()
        return venta.id


class ListarAparcadas:
    """Listado de solo lectura de todos los borradores aparcados (kiosco: sin
    filtrar por `usuario_id` creador), orden `id` DESC, sin limite."""

    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def ejecutar(self) -> list[AparcadaDTO]:
        return [
            AparcadaDTO(
                venta_id=venta.id, etiqueta=venta.etiqueta_aparcada,
                total=venta.total_con_iva, n_lineas=len(venta.lineas),
            )
            for venta in self.uow.ventas.listar_por_estado("aparcada")
        ]


class RecuperarAparcada:
    """Desaparca un borrador: devuelve sus lineas (para repoblar el carrito) y
    ELIMINA en la misma operacion la `Venta` aparcada (+ `VentaLinea`, cascade).
    Un id ya consumido o inexistente se rechaza sin efecto."""

    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def ejecutar(self, venta_id: int) -> list[LineaCarritoDTO]:
        venta = self.uow.ventas.buscar(venta_id)
        if venta is None or venta.estado != "aparcada":
            raise BorradorNoEncontrado(venta_id)
        lineas = [
            LineaCarritoDTO(
                articulo_id=linea.articulo_id, cantidad=linea.cantidad,
                pvp=linea.pvp_unitario, descripcion=linea.descripcion,
            )
            for linea in venta.lineas
        ]
        self.uow.ventas.eliminar(venta)
        self.uow.commit()
        return lineas
