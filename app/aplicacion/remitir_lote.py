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

# F1/F3 llevan destinatario (contraparte de la operacion, art. 6 ROF); F2/T (y
# R5) lo tienen PROHIBIDO (regla AEAT DESTINATARIO_NO_PERMITIDO, 3.1.3.13; ver
# validaciones_negocio.py _CON_DESTINATARIO/_SIN_DESTINATARIO). Se resuelve
# SOLO para esos dos tipos, nunca para el resto.
_TIPOS_CON_DESTINATARIO = {"F1", "F3"}


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
            Destinatario,
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
                # El flag FacturaSimplificadaArt7273 (D3, design.md) vive en `venta`,
                # no en `registro_fiscal`: se resuelve aqui, en la SERIALIZACION, sin
                # tocar la huella (ya calculada en la emision, ver huella.py).
                #
                # N+1 aceptado (Judgment Day S-2, documentado — sin cambio de
                # comportamiento): este `buscar(reg.venta_id)` por registro es un
                # lookup adicional por alta del lote. Se acepta porque (a) el lote
                # esta acotado (<=1000 registros por remision, ver Remitente/lote),
                # (b) ya sigue el MISMO patron per-registro que `anterior =
                # registros.buscar(...)` dos lineas arriba, y (c) el camino de
                # remision fiscal es el de MAYOR riesgo del sistema (huella/cadena):
                # no se toca por una optimizacion de rendimiento de bajo valor. Si se
                # quisiera batchear, seria un `SELECT venta_id IN (...)` unico ANTES
                # del bucle, pero eso queda fuera de alcance de esta revision.
                venta = self.uow.ventas.buscar(reg.venta_id)
                cualificada = bool(venta.cualificada) if venta is not None else False
                # Destinatarios/IDDestinatario (F1/F3): resuelto aqui, en la
                # SERIALIZACION, a partir de `venta.cliente_id` (ya congelado
                # por ConvertirEnFacturaF3, ver design.md D2). NUNCA participa
                # en la huella, ya fijada por `motor.emit` (huella.py).
                destinatario = None
                if (reg.tipo_factura in _TIPOS_CON_DESTINATARIO
                        and venta is not None and venta.cliente is not None):
                    destinatario = Destinatario(
                        nombre=venta.cliente.nombre, nif=venta.cliente.nif)
                elementos.append(
                    registro_alta_xml(reg, nombre_emisor=nombre_emisor, sistema=sistema,
                                       anterior=anterior, cualificada=cualificada,
                                       destinatario=destinatario))
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
