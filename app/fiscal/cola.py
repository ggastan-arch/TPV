"""Cola de remision VERI*FACTU (Orden HAC/1177/2024, art. 16-17; docs 7).

Reglas implementadas:
- FIFO por orden de generacion del registro (cadena unica del SIF).
- Agrupacion de 1..1000 registros por mensaje.
- Reintento de los pendientes al menos una vez por hora.
- Marca de incidencia en el siguiente envio si hubo una incidencia previa.
- Contador de registros pendientes (para la alarma en TPV/consola).

El transporte real (SOAP con certificado) se implementa detras de `Remitente` en la
tanda de remision; aqui va la orquestacion, que NO depende del certificado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.reloj import ahora_huso
from app.models.fiscal import RegistroFiscal, RemisionIntento

# Estados terminales de aceptacion: ya no hace falta reintentar.
ESTADOS_ACEPTADOS = ("aceptado", "aceptado_con_errores")


@dataclass
class ResultadoRemision:
    """Resultado de enviar UN registro (lo devuelve el `Remitente`)."""

    resultado: str  # aceptado | aceptado_con_errores | rechazado | incidencia
    codigo_error: str | None = None
    descripcion: str | None = None
    csv: str | None = None


class ColaRemision:
    def __init__(self, session: Session):
        self.s = session

    # -- consulta -------------------------------------------------------------
    def pendientes(self, maximo: int = 1000) -> list[RegistroFiscal]:
        """Registros aun no aceptados, en orden FIFO, hasta `maximo` (<=1000)."""
        stmt = (
            select(RegistroFiscal)
            .where(RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS))
            .order_by(RegistroFiscal.orden)
            .limit(min(maximo, 1000))
        )
        return list(self.s.execute(stmt).scalars())

    def contar_pendientes(self) -> int:
        stmt = (
            select(func.count())
            .select_from(RegistroFiscal)
            .where(RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS))
        )
        return self.s.execute(stmt).scalar_one()

    def hay_incidencia_pendiente(self) -> bool:
        """True si algun registro no aceptado arrastra una incidencia previa."""
        stmt = (
            select(RemisionIntento.id)
            .join(RegistroFiscal, RemisionIntento.registro_fiscal_id == RegistroFiscal.id)
            .where(
                RemisionIntento.incidencia.is_(True),
                RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS),
            )
            .limit(1)
        )
        return self.s.execute(stmt).first() is not None

    def registros_a_reintentar(
        self, ahora: datetime | None = None, intervalo_horas: int = 1
    ) -> list[RegistroFiscal]:
        """Pendientes sin intento previo o cuyo ultimo intento supera el intervalo."""
        ahora = ahora or datetime.now().astimezone()
        limite = timedelta(hours=intervalo_horas)
        a_reintentar = []
        for reg in self.pendientes():
            ultimo = self._ultimo_intento(reg.id)
            if ultimo is None:
                a_reintentar.append(reg)
            elif ahora - datetime.fromisoformat(ultimo.fecha_hora_huso) >= limite:
                a_reintentar.append(reg)
        return a_reintentar

    # -- registro de resultados ----------------------------------------------
    def registrar_resultado(
        self, registro: RegistroFiscal, resultado: ResultadoRemision
    ) -> RemisionIntento:
        """Anota el intento (append-only) y actualiza el estado canonico del registro.

        El registro local NUNCA se modifica salvo `estado_remision`: la subsanacion de
        un rechazo es un nuevo envio, no una alteracion de la cadena.
        """
        es_incidencia = resultado.resultado == "incidencia"
        intento = RemisionIntento(
            registro_fiscal_id=registro.id,
            fecha_hora_huso=ahora_huso(),
            resultado=resultado.resultado,
            incidencia=es_incidencia,
            codigo_error=resultado.codigo_error,
            descripcion=resultado.descripcion,
            csv=resultado.csv,
        )
        self.s.add(intento)
        # Una incidencia (no se pudo remitir) deja el registro 'pendiente' para reintento.
        registro.estado_remision = "pendiente" if es_incidencia else resultado.resultado
        self.s.flush()
        return intento

    # -- remision (orquestacion) ----------------------------------------------
    def remitir(self, remitente, *, nombre_emisor=None, nif_obligado=None, sistema=None):
        """Construye el sobre con los pendientes (FIFO), lo envia por `remitente` y
        registra el resultado de cada registro. Ante incidencia de red, marca todos
        los del lote como 'pendiente' para reintento. Devuelve la RespuestaEnvio (o None)."""
        # Imports diferidos para no acoplar la cola con lxml/XML salvo al remitir.
        from app.core.config import settings
        from app.fiscal.remitente import RemisionIncidencia
        from app.fiscal.xml import (
            Cabecera,
            a_bytes,
            envelope_remision,
            registro_alta_xml,
            registro_anulacion_xml,
            sistema_desde_settings,
        )

        nombre_emisor = nombre_emisor or settings.nombre_emisor
        nif_obligado = nif_obligado or settings.nif_emisor
        sistema = sistema or sistema_desde_settings()

        lote = self.pendientes()
        if not lote:
            return None

        elementos = []
        for reg in lote:
            anterior = (
                self.s.get(RegistroFiscal, reg.registro_anterior_id)
                if reg.registro_anterior_id
                else None
            )
            if reg.tipo_registro == "alta":
                elementos.append(
                    registro_alta_xml(reg, nombre_emisor=nombre_emisor, sistema=sistema, anterior=anterior)
                )
            else:
                elementos.append(
                    registro_anulacion_xml(reg, sistema=sistema, anterior=anterior)
                )

        cabecera = Cabecera(
            nombre_obligado=nombre_emisor,
            nif_obligado=nif_obligado,
            incidencia=self.hay_incidencia_pendiente(),
        )
        sobre = a_bytes(envelope_remision(elementos, cabecera=cabecera))

        try:
            respuesta = remitente.enviar(sobre)
        except RemisionIncidencia as exc:
            for reg in lote:
                self.registrar_resultado(reg, ResultadoRemision("incidencia", descripcion=str(exc)))
            return None

        por_num = {reg.num_serie_factura: reg for reg in lote}
        for linea in respuesta.lineas:
            reg = por_num.get(linea.num_serie_factura)
            if reg is not None:
                self.registrar_resultado(
                    reg,
                    ResultadoRemision(
                        resultado=linea.resultado,
                        codigo_error=linea.codigo_error,
                        descripcion=linea.descripcion,
                        csv=respuesta.csv,
                    ),
                )
        return respuesta

    # -- helpers --------------------------------------------------------------
    def _ultimo_intento(self, registro_id: int) -> RemisionIntento | None:
        stmt = (
            select(RemisionIntento)
            .where(RemisionIntento.registro_fiscal_id == registro_id)
            .order_by(RemisionIntento.id.desc())
            .limit(1)
        )
        return self.s.execute(stmt).scalars().first()
