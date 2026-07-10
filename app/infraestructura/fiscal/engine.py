"""Interfaz unica del motor fiscal (`FiscalEngine`) y `NullEngine`.

- `FiscalEngine`: contrato emit / cancel / verify_chain (CLAUDE.md, FiscalEngine).
- `NullEngine` (FASE 1): genera el registro y la cadena de huellas IGUALMENTE, pero
  NO remite a la AEAT ni serializa XML/QR. La emision asigna serie+numero y crea el
  registro en la MISMA transaccion que la venta.
- `VerifactuEngine` (FASE 2): alta/anulacion, QR, XML validado contra XSD y remision.

El encadenamiento es secuencial y serializado (nunca en paralelo): la cadena es
unica por sistema (docs 5). La serializacion de la transaccion la garantiza el
BEGIN IMMEDIATE del engine de BD; aqui solo se orquesta contador + venta + registro.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infraestructura.reloj import ahora_huso, fecha_expedicion_hoy
from app.dominio.servicios.huella import huella_alta, huella_anulacion
from app.infraestructura.persistencia.modelos.fiscal import (
    ContadorSerie,
    RegistroFiscal,
    RegistroFiscalDesglose,
)
from app.infraestructura.persistencia.modelos.venta import Venta


@dataclass
class InformeCadena:
    ok: bool
    registros: int
    errores: list[str]


class FiscalEngine(ABC):
    @abstractmethod
    def emit(self, session: Session, venta: Venta, **kwargs) -> RegistroFiscal:
        """Genera el registro de alta de una venta y lo encadena."""

    @abstractmethod
    def cancel(self, session: Session, registro: RegistroFiscal) -> RegistroFiscal:
        """Genera el registro de anulacion encadenado (RegistroAnulacion)."""

    @abstractmethod
    def verify_chain(
        self, session: Session, desde: int | None = None, hasta: int | None = None
    ) -> InformeCadena:
        """Recorre la cadena y verifica huella y encadenamiento."""


class NullEngine(FiscalEngine):
    """Motor de desarrollo: encadena de verdad, no remite."""

    def __init__(self, id_emisor: str, nombre_emisor: str):
        self.id_emisor = id_emisor
        self.nombre_emisor = nombre_emisor

    # -- emision ---------------------------------------------------------------
    def emit(
        self,
        session: Session,
        venta: Venta,
        *,
        serie: str = "T",
        ejercicio: int | None = None,
        tipo_factura: str = "F2",
        descripcion: str = "Venta al por menor acuariofilia",
    ) -> RegistroFiscal:
        ejercicio = ejercicio or datetime.now().astimezone().year

        numero = self._siguiente_numero(session, serie, ejercicio)
        num_serie = f"{serie}{ejercicio}-{numero:06d}"

        venta.serie = serie
        venta.ejercicio = ejercicio
        venta.numero = numero
        venta.num_serie_factura = num_serie
        venta.estado = "cobrada"
        if venta.fecha_hora_huso is None:
            venta.fecha_hora_huso = ahora_huso()
        # Persistir la cabecera emitida (INSERT, aun no dispara triggers de UPDATE)
        # para disponer de venta.id al encadenar el registro.
        session.add(venta)
        session.flush()

        anterior = self._ultimo_registro(session)
        orden = 1 if anterior is None else anterior.orden + 1
        huella_anterior = None if anterior is None else anterior.huella
        fhh = ahora_huso()
        fecha_exp = fecha_expedicion_hoy()

        registro = RegistroFiscal(
            orden=orden,
            tipo_registro="alta",
            venta_id=venta.id,
            id_emisor=self.id_emisor,
            num_serie_factura=num_serie,
            fecha_expedicion=fecha_exp,
            tipo_factura=tipo_factura,
            descripcion_operacion=descripcion,
            cuota_total=venta.cuota_total,
            importe_total=venta.total_con_iva,
            primer_registro=(anterior is None),
            registro_anterior_id=(anterior.id if anterior else None),
            huella_anterior=huella_anterior,
            tipo_huella="01",
            fecha_hora_huso_gen_registro=fhh,
            estado_remision="no_remitido",
        )
        registro.huella = huella_alta(
            id_emisor=self.id_emisor,
            num_serie_factura=num_serie,
            fecha_expedicion=fecha_exp,
            tipo_factura=tipo_factura,
            cuota_total=venta.cuota_total,
            importe_total=venta.total_con_iva,
            huella_anterior=huella_anterior,
            fecha_hora_huso_gen=fhh,
        )
        for porcentaje, (base, cuota) in self._desglose(venta).items():
            registro.desglose.append(
                RegistroFiscalDesglose(
                    tipo_impositivo=porcentaje,
                    base_imponible=base,
                    cuota_repercutida=cuota,
                )
            )
        session.add(registro)
        session.flush()
        return registro

    def cancel(self, session: Session, registro: RegistroFiscal) -> RegistroFiscal:
        """Genera el RegistroAnulacion encadenado de una factura ya emitida.

        No remite (eso es fase 2); genera el registro, su huella y encadena, y pasa
        la venta a 'anulada_con_rastro' (transicion permitida por el trigger).
        """
        if registro.tipo_registro != "alta":
            raise ValueError("Solo se anula un registro de alta")
        venta = session.get(Venta, registro.venta_id)
        if venta is None or venta.estado != "cobrada":
            raise ValueError("Solo se anula una venta en estado 'cobrada'")

        anterior = self._ultimo_registro(session)  # siempre existe (al menos el alta)
        orden = anterior.orden + 1
        huella_anterior = anterior.huella
        fhh = ahora_huso()

        anulacion = RegistroFiscal(
            orden=orden,
            tipo_registro="anulacion",
            venta_id=venta.id,
            # IDFactura de la anulacion = la factura anulada.
            id_emisor=registro.id_emisor,
            num_serie_factura=registro.num_serie_factura,
            fecha_expedicion=registro.fecha_expedicion,
            # Campos de referencia (el XML de anulacion no emite importes/tipo).
            tipo_factura=registro.tipo_factura,
            descripcion_operacion=None,
            cuota_total=registro.cuota_total,
            importe_total=registro.importe_total,
            primer_registro=False,
            registro_anterior_id=anterior.id,
            huella_anterior=huella_anterior,
            tipo_huella="01",
            fecha_hora_huso_gen_registro=fhh,
            estado_remision="no_remitido",
            registro_alta_anulado_id=registro.id,
        )
        anulacion.huella = huella_anulacion(
            id_emisor=registro.id_emisor,
            num_serie_factura=registro.num_serie_factura,
            fecha_expedicion=registro.fecha_expedicion,
            huella_anterior=huella_anterior,
            fecha_hora_huso_gen=fhh,
        )
        venta.estado = "anulada_con_rastro"
        session.add(anulacion)
        session.flush()
        return anulacion

    # -- verificacion de la cadena --------------------------------------------
    def verify_chain(
        self, session: Session, desde: int | None = None, hasta: int | None = None
    ) -> InformeCadena:
        stmt = select(RegistroFiscal).order_by(RegistroFiscal.orden)
        if desde is not None:
            stmt = stmt.where(RegistroFiscal.orden >= desde)
        if hasta is not None:
            stmt = stmt.where(RegistroFiscal.orden <= hasta)
        registros = list(session.execute(stmt).scalars())

        errores: list[str] = []
        huella_previa: str | None = None
        orden_esperado: int | None = None
        for reg in registros:
            if orden_esperado is not None and reg.orden != orden_esperado:
                errores.append(f"Hueco en la cadena: se esperaba orden {orden_esperado}, "
                               f"hay {reg.orden}")
            if reg.tipo_registro == "alta":
                calculada = huella_alta(
                    id_emisor=reg.id_emisor,
                    num_serie_factura=reg.num_serie_factura,
                    fecha_expedicion=reg.fecha_expedicion,
                    tipo_factura=reg.tipo_factura,
                    cuota_total=reg.cuota_total,
                    importe_total=reg.importe_total,
                    huella_anterior=reg.huella_anterior,
                    fecha_hora_huso_gen=reg.fecha_hora_huso_gen_registro,
                )
            else:  # anulacion
                calculada = huella_anulacion(
                    id_emisor=reg.id_emisor,
                    num_serie_factura=reg.num_serie_factura,
                    fecha_expedicion=reg.fecha_expedicion,
                    huella_anterior=reg.huella_anterior,
                    fecha_hora_huso_gen=reg.fecha_hora_huso_gen_registro,
                )
            if calculada != reg.huella:
                errores.append(f"Huella no cuadra en orden {reg.orden}")
            if desde is None and reg.huella_anterior != huella_previa:
                errores.append(f"Encadenamiento roto en orden {reg.orden}")
            huella_previa = reg.huella
            orden_esperado = reg.orden + 1

        return InformeCadena(ok=not errores, registros=len(registros), errores=errores)

    # -- helpers ---------------------------------------------------------------
    def _siguiente_numero(self, session: Session, serie: str, ejercicio: int) -> int:
        session.execute(
            update(ContadorSerie)
            .where(ContadorSerie.serie == serie, ContadorSerie.ejercicio == ejercicio)
            .values(ultimo_numero=ContadorSerie.ultimo_numero + 1)
        )
        numero = session.execute(
            select(ContadorSerie.ultimo_numero).where(
                ContadorSerie.serie == serie, ContadorSerie.ejercicio == ejercicio
            )
        ).scalar_one()
        return numero

    def _ultimo_registro(self, session: Session) -> RegistroFiscal | None:
        return session.execute(
            select(RegistroFiscal).order_by(RegistroFiscal.orden.desc()).limit(1)
        ).scalars().first()

    def _desglose(self, venta: Venta) -> dict[Decimal, tuple[Decimal, Decimal]]:
        bases: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0.00"))
        cuotas: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for linea in venta.lineas:
            bases[linea.tipo_iva_porcentaje] += linea.base_linea
            cuotas[linea.tipo_iva_porcentaje] += linea.cuota_linea
        return {p: (bases[p], cuotas[p]) for p in bases}
