"""Caso de uso: generar el Cierre Z (informe Z inmutable).

Snapshot congelado de un rango de ventas cobradas, delimitado por el orden de emision
de la cadena fiscal (`registro_fiscal.orden`), no por `venta.id` (ver design.md): el
`orden` es monotono en el momento real de la emision, asi que un ticket aparcado que
se emite despues de un cierre no se pierde, cae en el Z siguiente.

El caso de uso SOLO LEE sobre `venta`/`registro_fiscal` (invariante 1): jamas los
muta. La numeracion (Z-1, Z-2...) es una secuencia global derivada (ultimo + 1) bajo
`BEGIN IMMEDIATE`, disparado por la primera lectura de la transaccion (ADR-0004). Z a
cero esta permitido por diseno: un rango vacio no lanza excepcion, persiste totales en
cero (requisito resuelto en spec.md)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import CierreZ, CierreZDesgloseIva, CierreZDesglosePago
from app.infraestructura.reloj import ahora_huso


@dataclass
class ResultadoCierreZ:
    id: int
    numero: int
    fecha_hora_huso: str
    desde_orden: int
    hasta_orden: int
    num_tickets: int
    base_total: Decimal
    cuota_total: Decimal
    total_con_iva: Decimal


class GenerarCierreZ:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    def ejecutar(self, *, usuario_id: int, origen: str = "local") -> ResultadoCierreZ:
        # 1a lectura de la transaccion -> BEGIN IMMEDIATE (evita que dos cierres
        # concurrentes deriven el mismo numero o el mismo desde_orden).
        ultimo = self.uow.cierres_z.ultimo()
        numero = (ultimo.numero + 1) if ultimo is not None else 1
        desde_orden = (ultimo.hasta_orden + 1) if ultimo is not None else 1

        hasta_orden = self.uow.registros.max_orden_alta()
        totales = self.uow.cierres_z.cobradas_por_rango_orden(desde_orden, hasta_orden)

        cierre = CierreZ(
            numero=numero,
            fecha_hora_huso=ahora_huso(),
            usuario_id=usuario_id,
            desde_orden=desde_orden,
            hasta_orden=hasta_orden,
            num_tickets=totales.num_tickets,
            base_total=totales.base_total,
            cuota_total=totales.cuota_total,
            total_con_iva=totales.total_con_iva,
        )
        for tipo, base, cuota in totales.desglose_iva:
            cierre.desglose_iva.append(
                CierreZDesgloseIva(tipo_impositivo=tipo, base_imponible=base, cuota_repercutida=cuota)
            )
        for medio, importe in totales.desglose_pago:
            cierre.desglose_pago.append(CierreZDesglosePago(medio=medio, importe=importe))

        self.uow.cierres_z.agregar(cierre)
        self.uow.flush()  # asignar id antes de auditar

        self.uow.auditoria.registrar(
            accion="generar_cierre_z", entidad="cierre_z", entidad_id=str(cierre.id),
            usuario_id=usuario_id, origen=origen,
        )
        self.uow.commit()

        return ResultadoCierreZ(
            id=cierre.id,
            numero=cierre.numero,
            fecha_hora_huso=cierre.fecha_hora_huso,
            desde_orden=cierre.desde_orden,
            hasta_orden=cierre.hasta_orden,
            num_tickets=cierre.num_tickets,
            base_total=cierre.base_total,
            cuota_total=cierre.cuota_total,
            total_con_iva=cierre.total_con_iva,
        )
