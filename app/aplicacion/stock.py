"""Casos de uso de stock informativo: entradas, mermas (motivo obligatorio) y
consulta de saldo/alarma. El stock NUNCA condiciona el cobro (CLAUDE.md); estas
son operaciones manuales de administracion, independientes del ajuste global de
empresa (design.md): solo exigen `Articulo.control_stock = true` (el admin puede
preparar el stock antes de activar el control global)."""
from __future__ import annotations

from decimal import Decimal

from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import MovimientoStock
from app.infraestructura.reloj import ahora_huso


class ArticuloNoRastreado(Exception):
    """Artículo inexistente o con `control_stock = false`."""


class CantidadInvalida(Exception):
    """Cantidad de movimiento <= 0."""


class MotivoRequerido(Exception):
    """Merma sin motivo (justificacion obligatoria de la perdida de existencias)."""


class RegistrarEntrada:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def ejecutar(
        self, *, articulo_id: int, cantidad: Decimal, usuario_id: int, origen: str = "local",
    ) -> int:
        _validar_articulo_rastreado(self.uow, articulo_id)
        _validar_cantidad(cantidad)
        movimiento = MovimientoStock(
            articulo_id=articulo_id, tipo="entrada", cantidad=Decimal(cantidad),
            usuario_id=usuario_id, fecha_hora_huso=ahora_huso())
        self.uow.stock.agregar(movimiento)
        self.uow.flush()  # asignar id antes de auditar
        self.uow.auditoria.registrar(
            accion="registrar_entrada_stock", entidad="articulo", entidad_id=str(articulo_id),
            detalle=str(cantidad), usuario_id=usuario_id, origen=origen)
        self.uow.commit()
        return movimiento.id


class RegistrarMerma:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def ejecutar(
        self, *, articulo_id: int, cantidad: Decimal, motivo: str, usuario_id: int,
        origen: str = "local",
    ) -> int:
        _validar_articulo_rastreado(self.uow, articulo_id)
        _validar_cantidad(cantidad)
        if motivo is None or not motivo.strip():
            raise MotivoRequerido()
        movimiento = MovimientoStock(
            articulo_id=articulo_id, tipo="merma", cantidad=Decimal(cantidad), motivo=motivo,
            usuario_id=usuario_id, fecha_hora_huso=ahora_huso())
        self.uow.stock.agregar(movimiento)
        self.uow.flush()  # asignar id antes de auditar
        self.uow.auditoria.registrar(
            accion="registrar_merma_stock", entidad="articulo", entidad_id=str(articulo_id),
            detalle=f"{cantidad} ({motivo})", usuario_id=usuario_id, origen=origen)
        self.uow.commit()
        return movimiento.id


class ConsultarStock:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def stock_de(self, articulo_id: int) -> Decimal:
        return self.uow.stock.stock_actual(articulo_id)

    def articulos_en_negativo(self) -> list[tuple[int, Decimal]]:
        return self.uow.stock.rastreados_en_negativo()


def _validar_articulo_rastreado(uow: UnidadDeTrabajo, articulo_id: int) -> None:
    articulo = uow.articulos.buscar(articulo_id)
    if articulo is None or not articulo.control_stock:
        raise ArticuloNoRastreado(articulo_id)


def _validar_cantidad(cantidad: Decimal) -> None:
    if Decimal(cantidad) <= 0:
        raise CantidadInvalida(cantidad)
