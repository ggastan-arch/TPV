"""(Fase 2) Los triggers rechazan modificar/borrar un Cierre Z ya persistido y sus
desgloses (patron `test_inmutabilidad.py`)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.infraestructura.persistencia.modelos import (
    CierreZ,
    CierreZDesgloseIva,
    CierreZDesglosePago,
)
from app.infraestructura.reloj import ahora_huso


def _crear_cierre_z(crear_sesion, usuario_id: int) -> int:
    with crear_sesion() as s, s.begin():
        cierre = CierreZ(
            numero=1,
            fecha_hora_huso=ahora_huso(),
            usuario_id=usuario_id,
            desde_orden=1,
            hasta_orden=3,
            num_tickets=2,
            base_total=Decimal("100.00"),
            cuota_total=Decimal("21.00"),
            total_con_iva=Decimal("121.00"),
        )
        cierre.desglose_iva.append(
            CierreZDesgloseIva(
                tipo_impositivo=Decimal("21.00"),
                base_imponible=Decimal("100.00"),
                cuota_repercutida=Decimal("21.00"),
            )
        )
        cierre.desglose_pago.append(
            CierreZDesglosePago(medio="efectivo", importe=Decimal("121.00"))
        )
        s.add(cierre)
        s.flush()
        cierre_id = cierre.id
    return cierre_id


def test_no_se_puede_modificar_un_cierre_z(crear_sesion, datos_base):
    cierre_id = _crear_cierre_z(crear_sesion, datos_base["usuario_id"])
    with crear_sesion() as s:
        cierre = s.get(CierreZ, cierre_id)
        cierre.num_tickets = 999
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_un_cierre_z(crear_sesion, datos_base):
    cierre_id = _crear_cierre_z(crear_sesion, datos_base["usuario_id"])
    with crear_sesion() as s:
        cierre = s.get(CierreZ, cierre_id)
        s.delete(cierre)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_modificar_el_desglose_iva(crear_sesion, datos_base):
    cierre_id = _crear_cierre_z(crear_sesion, datos_base["usuario_id"])
    with crear_sesion() as s:
        desglose = s.query(CierreZDesgloseIva).filter_by(cierre_z_id=cierre_id).one()
        desglose.base_imponible = Decimal("0.00")
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_el_desglose_pago(crear_sesion, datos_base):
    cierre_id = _crear_cierre_z(crear_sesion, datos_base["usuario_id"])
    with crear_sesion() as s:
        desglose = s.query(CierreZDesglosePago).filter_by(cierre_z_id=cierre_id).one()
        s.delete(desglose)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()
