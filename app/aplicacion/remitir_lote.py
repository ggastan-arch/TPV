"""Caso de uso: remitir a la AEAT el lote de registros pendientes.

Orquesta: obtiene los pendientes (FIFO) por el repositorio, construye el sobre, lo envia
por el puerto `Remitente` y registra el resultado de cada registro. Ante incidencia de
conectividad, marca el lote como 'pendiente' para reintento (art. 17).

La serializacion del sobre (XML) se delega en app.infraestructura.fiscal.xml
(compromiso pragmatico, ADR-0001)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.dominio.puertos import UnidadDeTrabajo
from app.dominio.servicios.validaciones_negocio import (
    TIPOS_CON_DESTINATARIO as _TIPOS_CON_DESTINATARIO,
)

if TYPE_CHECKING:
    from app.infraestructura.fiscal.remitente import Remitente, RespuestaEnvio
    from app.infraestructura.fiscal.xml import SistemaInformatico

# F1/F3/R1-R4 llevan destinatario (contraparte de la operacion, art. 6 ROF); F2/T
# (y R5) lo tienen PROHIBIDO (regla AEAT DESTINATARIO_NO_PERMITIDO, 3.1.3.13).
# DERIVADO de `validaciones_negocio.TIPOS_CON_DESTINATARIO` (item 7, revision
# Judgment Day): fuente unica de verdad, para que este modulo NUNCA diverja
# silenciosamente de esa regla de negocio si R1-R4 (rectificativas) se
# implementan sin tocar este fichero -- la guarda de destinatario_nif faltante
# (mas abajo) hace que expandir este conjunto sea SEGURO incluso hoy: cualquier
# R1-R4 sin snapshot simplemente queda `requiere_intervencion`, nunca se remite
# con un destinatario ausente o invalido.


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
        lote_valido = []
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
                # Destinatarios/IDDestinatario (F1/F3/R1-R4): resuelto aqui, en la
                # SERIALIZACION, a partir del SNAPSHOT CONGELADO
                # `venta.destinatario_nombre`/`venta.destinatario_nif` (fix Judgment
                # Day, migracion 0010) -- NUNCA de `venta.cliente` en vivo: el
                # cliente puede editarse DESPUES de emitir, pero la F1/F3 ya
                # expedida es inmutable y debe remitirse con el MISMO destinatario
                # que se emitio/imprimio. Tampoco participa en la huella, ya fijada
                # por `motor.emit` (huella.py).
                destinatario = None
                if reg.tipo_factura in _TIPOS_CON_DESTINATARIO:
                    if venta is None or not venta.destinatario_nif:
                        # Guarda fiscal: nunca remitir un F1/F3/R1-R4 sin
                        # destinatario congelado -- un <NIF/> vacio (o el bloque
                        # ausente) es invalido/incompleto para la AEAT y
                        # bloquearia TODA la cola FIFO si se remitiera. Se marca
                        # 'requiere_intervencion' (invariante "nunca se descarta
                        # un registro en silencio") y se EXCLUYE del sobre; el
                        # resto del lote sigue su curso normal.
                        registros.registrar_resultado(
                            reg, "rechazado",
                            descripcion=(
                                "F1/F3/R1-R4 sin destinatario congelado "
                                "(destinatario_nif ausente en la venta)"),
                            estado_remision_final="requiere_intervencion")
                        continue
                    destinatario = Destinatario(
                        nombre=venta.destinatario_nombre, nif=venta.destinatario_nif)
                elementos.append(
                    registro_alta_xml(reg, nombre_emisor=nombre_emisor, sistema=sistema,
                                       anterior=anterior, cualificada=cualificada,
                                       destinatario=destinatario))
                lote_valido.append(reg)
            else:
                elementos.append(registro_anulacion_xml(reg, sistema=sistema, anterior=anterior))
                lote_valido.append(reg)

        if not elementos:
            # Todo el lote quedo excluido por la guarda de destinatario: nada que
            # remitir, pero las marcas 'requiere_intervencion' ya asentadas arriba
            # deben persistir (envelope_remision rechaza una lista vacia).
            self.uow.commit()
            return None

        cabecera = Cabecera(nombre_obligado=nombre_emisor, nif_obligado=nif_obligado,
                            incidencia=registros.hay_incidencia_pendiente())
        sobre = a_bytes(envelope_remision(elementos, cabecera=cabecera))

        try:
            respuesta = self.remitente.enviar(sobre)
        except RemisionIncidencia as exc:
            for reg in lote_valido:
                registros.registrar_resultado(reg, "incidencia", descripcion=str(exc))
            self.uow.commit()
            return None

        if not respuesta.lineas and respuesta.estado_envio == "Incorrecto":
            # Rechazo de cabecera: no hay desglose por registro, asi que TODO el
            # lote ENVIADO queda con rastro propio en requiere_intervencion
            # (invariante "nunca se descarta un registro en silencio"). Sin marca
            # de incidencia: no es un problema de conectividad, requiere
            # intervencion humana (R2/R3).
            for reg in lote_valido:
                registros.registrar_resultado(
                    reg, "rechazado", codigo_error=respuesta.codigo_error_cabecera,
                    descripcion=respuesta.descripcion_cabecera,
                    estado_remision_final="requiere_intervencion")
            self.uow.commit()
            return respuesta

        por_num = {reg.num_serie_factura: reg for reg in lote_valido}
        for linea in respuesta.lineas:
            reg = por_num.get(linea.num_serie_factura)
            if reg is not None:
                registros.registrar_resultado(
                    reg, linea.resultado, codigo_error=linea.codigo_error,
                    descripcion=linea.descripcion, csv=respuesta.csv,
                    estado_remision_final=linea.estado_final)
        self.uow.commit()
        return respuesta
