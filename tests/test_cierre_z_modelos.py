"""(Fase 1) Modelos ORM del Cierre Z: columnas, constraints y relaciones.

No depende de la migracion Alembic (aun no existe en esta fase): usa un motor
SQLite efimero propio via `Base.metadata.create_all` para probar el mapeo
declarativo y el comportamiento de cascada, no el esquema de produccion (eso lo
cubre `test_esquema.py` una vez exista la migracion 0003)."""
from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session, class_mapper, sessionmaker

from app.infraestructura.persistencia.modelos import (
    Base,
    CierreZ,
    CierreZDesgloseIva,
    CierreZDesglosePago,
    Usuario,
)
from app.infraestructura.seguridad import hash_pin


def test_cierre_z_tiene_las_columnas_y_constraint_del_diseno():
    columnas = {c.name for c in CierreZ.__table__.columns}
    esperadas = {
        "id", "numero", "fecha_hora_huso", "usuario_id",
        "desde_orden", "hasta_orden", "num_tickets",
        "base_total", "cuota_total", "total_con_iva",
    }
    assert esperadas <= columnas
    assert CierreZ.__tablename__ == "cierre_z"

    fk_usuario = next(iter(CierreZ.__table__.columns["usuario_id"].foreign_keys))
    assert fk_usuario.column.table.name == "usuario"

    nombres_unique = {
        c.name for c in CierreZ.__table__.constraints if isinstance(c, sa.UniqueConstraint)
    }
    assert "uq_cierre_z_numero" in nombres_unique


def test_desgloses_del_cierre_z_tienen_las_columnas_del_diseno():
    columnas_iva = {c.name for c in CierreZDesgloseIva.__table__.columns}
    assert {"id", "cierre_z_id", "tipo_impositivo", "base_imponible", "cuota_repercutida"} <= columnas_iva
    assert CierreZDesgloseIva.__tablename__ == "cierre_z_desglose_iva"

    columnas_pago = {c.name for c in CierreZDesglosePago.__table__.columns}
    assert {"id", "cierre_z_id", "medio", "importe"} <= columnas_pago
    assert CierreZDesglosePago.__tablename__ == "cierre_z_desglose_pago"

    nombres_check_pago = {
        c.name for c in CierreZDesglosePago.__table__.constraints
        if isinstance(c, sa.CheckConstraint)
    }
    assert nombres_check_pago  # existe una CheckConstraint sobre el medio de pago


def test_relaciones_de_desglose_cascadean_delete_orphan():
    mapper = class_mapper(CierreZ)
    for nombre in ("desglose_iva", "desglose_pago"):
        cascade = mapper.relationships[nombre].cascade
        assert "delete-orphan" in cascade
        assert "delete" in cascade


def _sesion_efimera() -> sessionmaker:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def test_persistir_un_cierre_z_con_sus_desgloses_y_leerlo_de_vuelta():
    crear_sesion = _sesion_efimera()
    with crear_sesion() as s, s.begin():
        usuario = Usuario(nombre="admin", pin_hash=hash_pin("1234"), rol="administracion")
        s.add(usuario)
        s.flush()
        cierre = CierreZ(
            numero=1,
            fecha_hora_huso="2026-07-11T09:00:00+02:00",
            usuario_id=usuario.id,
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

    with crear_sesion() as s:
        leido = s.get(CierreZ, cierre_id)
        assert leido.total_con_iva == Decimal("121.00")
        assert len(leido.desglose_iva) == 1
        assert leido.desglose_iva[0].tipo_impositivo == Decimal("21.00")
        assert len(leido.desglose_pago) == 1
        assert leido.desglose_pago[0].medio == "efectivo"

    # Cascade delete-orphan: quitar un hijo de la lista y guardar lo borra de la BD.
    with crear_sesion() as s, s.begin():
        cierre = s.get(CierreZ, cierre_id)
        cierre.desglose_pago.clear()

    with crear_sesion() as s:
        assert s.query(CierreZDesglosePago).count() == 0
        assert s.query(CierreZDesgloseIva).count() == 1
