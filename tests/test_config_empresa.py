"""(Fase 1) `ConfiguracionEmpresa`: ajuste de empresa singleton que gobierna el
control de stock (design.md, control-stock). Sigue el patron de
`test_cierre_z_modelos.py`: create_all efimero para el modelo ORM; el esquema de
produccion (migracion 0004) lo cubre el fixture `engine` (migracion Alembic real)."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from app.infraestructura.persistencia.modelos import Base, ConfiguracionEmpresa


def test_configuracion_empresa_tiene_las_columnas_del_diseno():
    columnas = {c.name for c in ConfiguracionEmpresa.__table__.columns}
    assert {"id", "control_stock_activo"} <= columnas
    assert ConfiguracionEmpresa.__tablename__ == "configuracion_empresa"


def test_control_stock_activo_es_no_nulo():
    columna = ConfiguracionEmpresa.__table__.columns["control_stock_activo"]
    assert columna.nullable is False


def _sesion_efimera() -> sessionmaker:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def test_persistir_configuracion_empresa_y_leerla_de_vuelta():
    crear_sesion = _sesion_efimera()
    with crear_sesion() as s, s.begin():
        s.add(ConfiguracionEmpresa(id=1, control_stock_activo=False))

    with crear_sesion() as s:
        cfg = s.get(ConfiguracionEmpresa, 1)
        assert cfg.control_stock_activo is False


def test_la_migracion_crea_la_fila_singleton_desactivada_por_defecto(session):
    cfg = session.get(ConfiguracionEmpresa, 1)
    assert cfg is not None
    assert cfg.control_stock_activo is False


def test_la_migracion_crea_el_indice_de_movimiento_stock_por_articulo(engine):
    inspector = inspect(engine)
    indices = {ix["name"] for ix in inspector.get_indexes("movimiento_stock")}
    assert "ix_movimiento_stock_articulo" in indices
