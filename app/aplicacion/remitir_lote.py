"""Caso de uso: remitir a la AEAT el lote de registros pendientes.

Orquesta: obtiene los pendientes (FIFO) por el repositorio, construye el sobre, lo envia
por el puerto `Remitente` y registra el resultado de cada registro. Ante incidencia de
conectividad, marca el lote como 'pendiente' para reintento (art. 17).

La serializacion del sobre (XML) se delega en app.infraestructura.fiscal.xml
(compromiso pragmatico, ADR-0001)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.dominio.puertos import UnidadDeTrabajo

if TYPE_CHECKING:
    from app.infraestructura.fiscal.remitente import Remitente, RespuestaEnvio
    from app.infraestructura.fiscal.xml import SistemaInformatico


class RemitirLote:
    def __init__(self, uow: UnidadDeTrabajo, remitente: "Remitente"):
        self.uow = uow
        self.remitente = remitente

    def ejecutar(
        self, *, nombre_emisor: str, nif_obligado: str, sistema: "SistemaInformatico"
    ) -> "RespuestaEnvio | None":
        from app.infraestructura.fiscal.remitente import RemisionIncidencia
        from app.infraestructura.fiscal.xml import (
            Cabecera,
            a_bytes,
            envelope_remision,
            registro_alta_xml,
            registro_anulacion_xml,
        )

        registros = self.uow.registros
        lote = registros.pendientes()
        if not lote:
            return None

        elementos = []
        for reg in lote:
            anterior = registros.buscar(reg.registro_anterior_id) if reg.registro_anterior_id else None
            if reg.tipo_registro == "alta":
                elementos.append(
                    registro_alta_xml(reg, nombre_emisor=nombre_emisor, sistema=sistema, anterior=anterior))
            else:
                elementos.append(registro_anulacion_xml(reg, sistema=sistema, anterior=anterior))

        cabecera = Cabecera(nombre_obligado=nombre_emisor, nif_obligado=nif_obligado,
                            incidencia=registros.hay_incidencia_pendiente())
        sobre = a_bytes(envelope_remision(elementos, cabecera=cabecera))

        try:
            respuesta = self.remitente.enviar(sobre)
        except RemisionIncidencia as exc:
            for reg in lote:
                registros.registrar_resultado(reg, "incidencia", descripcion=str(exc))
            self.uow.commit()
            return None

        if not respuesta.lineas and respuesta.estado_envio == "Incorrecto":
            # Rechazo de cabecera: no hay desglose por registro, asi que TODO el lote
            # queda con rastro propio en requiere_intervencion (invariante "nunca se
            # descarta un registro en silencio"). Sin marca de incidencia: no es un
            # problema de conectividad, requiere intervencion humana (R2/R3).
            for reg in lote:
                registros.registrar_resultado(
                    reg, "rechazado", codigo_error=respuesta.codigo_error_cabecera,
                    descripcion=respuesta.descripcion_cabecera,
                    estado_remision_final="requiere_intervencion")
            self.uow.commit()
            return respuesta

        por_num = {reg.num_serie_factura: reg for reg in lote}
        for linea in respuesta.lineas:
            reg = por_num.get(linea.num_serie_factura)
            if reg is not None:
                registros.registrar_resultado(
                    reg, linea.resultado, codigo_error=linea.codigo_error,
                    descripcion=linea.descripcion, csv=respuesta.csv,
                    estado_remision_final=linea.estado_final)
        self.uow.commit()
        return respuesta
