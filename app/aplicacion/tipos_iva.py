"""Casos de uso de mantenimiento de tipos de IVA (maestro).

El tipo de IVA es un parametro fiscal configurable (nunca hardcodeado). Reglas: el
porcentaje no puede ser negativo; el cambio de porcentaje queda auditado (afecta a las
ventas FUTURAS, nunca a las emitidas, que llevan el porcentaje congelado en la linea);
los tipos NUNCA se borran, solo se activan/desactivan."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import TipoIVA


@dataclass
class DatosTipoIva:
    nombre: str
    porcentaje: Decimal
    calificacion: str = "S1"


class PorcentajeInvalido(Exception):
    pass


class TipoIvaNoEncontrado(Exception):
    pass


class ServicioTiposIva:
    def __init__(self, uow: UnidadDeTrabajo, *, usuario_id: int | None = None, origen: str = "local"):
        self.uow = uow
        self.usuario_id = usuario_id
        self.origen = origen

    def crear(self, datos: DatosTipoIva) -> int:
        porcentaje = self._validar_porcentaje(datos.porcentaje)
        tipo = TipoIVA(nombre=datos.nombre, porcentaje=porcentaje, calificacion=datos.calificacion)
        self.uow.tipos_iva.agregar(tipo)
        self.uow.flush()
        self._auditar("crear_tipo_iva", tipo.id)
        self.uow.commit()
        return tipo.id

    def actualizar(self, tipo_iva_id: int, datos: DatosTipoIva) -> None:
        tipo = self.uow.tipos_iva.buscar(tipo_iva_id)
        if tipo is None:
            raise TipoIvaNoEncontrado(tipo_iva_id)
        nuevo_porcentaje = self._validar_porcentaje(datos.porcentaje)

        porcentaje_anterior = tipo.porcentaje
        tipo.nombre = datos.nombre
        tipo.porcentaje = nuevo_porcentaje
        tipo.calificacion = datos.calificacion

        if nuevo_porcentaje != porcentaje_anterior:
            self._auditar("cambio_porcentaje_iva", tipo.id,
                          detalle=f"{porcentaje_anterior} -> {nuevo_porcentaje}")
        else:
            self._auditar("actualizar_tipo_iva", tipo.id)
        self.uow.commit()

    def desactivar(self, tipo_iva_id: int) -> None:
        self._cambiar_activo(tipo_iva_id, False, "desactivar_tipo_iva")

    def activar(self, tipo_iva_id: int) -> None:
        self._cambiar_activo(tipo_iva_id, True, "activar_tipo_iva")

    # -- helpers ---------------------------------------------------------------
    def _cambiar_activo(self, tipo_iva_id: int, activo: bool, accion: str) -> None:
        tipo = self.uow.tipos_iva.buscar(tipo_iva_id)
        if tipo is None:
            raise TipoIvaNoEncontrado(tipo_iva_id)
        tipo.activo = activo
        self._auditar(accion, tipo.id)
        self.uow.commit()

    def _validar_porcentaje(self, porcentaje: Decimal) -> Decimal:
        valor = Decimal(porcentaje)
        if valor < 0 or valor > 100:
            raise PorcentajeInvalido(valor)
        return valor

    def _auditar(self, accion: str, tipo_iva_id: int, detalle: str | None = None) -> None:
        self.uow.auditoria.registrar(
            accion=accion, entidad="tipo_iva", entidad_id=str(tipo_iva_id),
            detalle=detalle, usuario_id=self.usuario_id, origen=self.origen)
