"""(e) El log de auditoria es append-only (ni UPDATE ni DELETE)."""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.core.reloj import ahora_huso
from app.infraestructura.persistencia.modelos import LogAuditoria


def _insertar(crear_sesion) -> int:
    with crear_sesion() as s, s.begin():
        log = LogAuditoria(
            fecha_hora_huso=ahora_huso(),
            accion="apertura_cajon_sin_venta",
            entidad="caja",
            detalle="prueba",
            origen="local",
        )
        s.add(log)
        s.flush()
        return log.id


def test_se_puede_insertar_en_el_log(crear_sesion):
    log_id = _insertar(crear_sesion)
    with crear_sesion() as s:
        assert s.get(LogAuditoria, log_id) is not None


def test_no_se_puede_modificar_el_log(crear_sesion):
    log_id = _insertar(crear_sesion)
    with crear_sesion() as s:
        log = s.get(LogAuditoria, log_id)
        log.accion = "manipulado"
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()


def test_no_se_puede_borrar_del_log(crear_sesion):
    log_id = _insertar(crear_sesion)
    with crear_sesion() as s:
        log = s.get(LogAuditoria, log_id)
        s.delete(log)
        with pytest.raises(sa.exc.DatabaseError):
            s.flush()
        s.rollback()
