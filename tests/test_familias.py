"""Casos de uso de mantenimiento de familias (maestro, arbol de niveles ilimitados).

Reglas fuertes: no se puede crear un ciclo al reasignar el padre (romperia el CTE
recursivo del arbol); no se desactiva una familia con hijos activos (dejaria huerfanos
en la navegacion); nunca hard-delete, solo activo=false."""
from __future__ import annotations

import pytest

from app.aplicacion.familias import (
    CicloEnFamilia,
    DatosFamilia,
    FamiliaConHijos,
    FamiliaNoEncontrada,
    FamiliaPadreNoExiste,
    ServicioFamilias,
)
from app.infraestructura.persistencia.modelos import Familia, LogAuditoria
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _svc(session, datos_base):
    return ServicioFamilias(
        UnidadDeTrabajoSQL(session), usuario_id=datos_base["usuario_id"], origen="local")


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def test_visible_en_tactil_default_true_a_nivel_modelo(session):
    fam = Familia(nombre="Peces")
    session.add(fam)
    session.flush()
    assert fam.visible_en_tactil is True


def test_crear_familia_raiz_persiste_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosFamilia(nombre="Peces"))

    with crear_sesion() as s:
        fam = s.get(Familia, nuevo_id)
        assert fam is not None and fam.parent_id is None and fam.activo is True
    logs = _auditorias(crear_sesion, "crear_familia")
    assert len(logs) == 1 and logs[0].entidad == "familia"


def test_crear_familia_sin_flag_usa_default_true(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosFamilia(nombre="Peces"))
    with crear_sesion() as s:
        assert s.get(Familia, nuevo_id).visible_en_tactil is True


def test_crear_familia_no_visible_en_tactil_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(
            DatosFamilia(nombre="Peces escaneo", visible_en_tactil=False))
    with crear_sesion() as s:
        assert s.get(Familia, nuevo_id).visible_en_tactil is False
    logs = _auditorias(crear_sesion, "crear_familia")
    assert len(logs) == 1 and logs[0].entidad_id == str(nuevo_id)


def test_actualizar_flag_visible_en_tactil_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        fam_id = _svc(s, datos_base).crear(DatosFamilia(nombre="Peces"))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(
            fam_id, DatosFamilia(nombre="Peces", visible_en_tactil=False))
    with crear_sesion() as s:
        assert s.get(Familia, fam_id).visible_en_tactil is False
    logs = _auditorias(crear_sesion, "actualizar_familia")
    assert len(logs) == 1 and logs[0].entidad_id == str(fam_id)


def test_crear_familia_hija(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        raiz = svc.crear(DatosFamilia(nombre="Peces"))
        hija = svc.crear(DatosFamilia(nombre="Ciclidos", parent_id=raiz))
    with crear_sesion() as s:
        assert s.get(Familia, hija).parent_id == raiz


def test_crear_con_padre_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(FamiliaPadreNoExiste):
            _svc(s, datos_base).crear(DatosFamilia(nombre="Huerfana", parent_id=999999))


def test_no_puede_ser_su_propio_padre(crear_sesion, datos_base):
    with crear_sesion() as s:
        fam_id = _svc(s, datos_base).crear(DatosFamilia(nombre="Peces"))
    with crear_sesion() as s:
        with pytest.raises(CicloEnFamilia):
            _svc(s, datos_base).actualizar(fam_id, DatosFamilia(nombre="Peces", parent_id=fam_id))


def test_no_puede_colgar_de_un_descendiente(crear_sesion, datos_base):
    # abuelo -> padre -> hijo ; intentar abuelo.parent = hijo crea un ciclo.
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        abuelo = svc.crear(DatosFamilia(nombre="Acuariofilia"))
        padre = svc.crear(DatosFamilia(nombre="Peces", parent_id=abuelo))
        hijo = svc.crear(DatosFamilia(nombre="Ciclidos", parent_id=padre))
    with crear_sesion() as s:
        with pytest.raises(CicloEnFamilia):
            _svc(s, datos_base).actualizar(
                abuelo, DatosFamilia(nombre="Acuariofilia", parent_id=hijo))


def test_reasignar_padre_valido_ok_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        a = svc.crear(DatosFamilia(nombre="A"))
        b = svc.crear(DatosFamilia(nombre="B"))
        hija = svc.crear(DatosFamilia(nombre="Hija", parent_id=a))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(hija, DatosFamilia(nombre="Hija", parent_id=b))
    with crear_sesion() as s:
        assert s.get(Familia, hija).parent_id == b
    assert len(_auditorias(crear_sesion, "actualizar_familia")) == 1


def test_actualizar_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(FamiliaNoEncontrada):
            _svc(s, datos_base).actualizar(999999, DatosFamilia(nombre="X"))


def test_no_desactivar_con_hijos_activos(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        padre = svc.crear(DatosFamilia(nombre="Peces"))
        svc.crear(DatosFamilia(nombre="Ciclidos", parent_id=padre))
    with crear_sesion() as s:
        with pytest.raises(FamiliaConHijos):
            _svc(s, datos_base).desactivar(padre)
    # No se desactivo.
    with crear_sesion() as s:
        assert s.get(Familia, padre).activo is True


def test_desactivar_hoja_ok_no_borra(crear_sesion, datos_base):
    with crear_sesion() as s:
        fam_id = _svc(s, datos_base).crear(DatosFamilia(nombre="Temporal"))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(fam_id)
    with crear_sesion() as s:
        fam = s.get(Familia, fam_id)
        assert fam is not None and fam.activo is False
    assert len(_auditorias(crear_sesion, "desactivar_familia")) == 1


def test_desactivar_padre_tras_desactivar_hijos(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        padre = svc.crear(DatosFamilia(nombre="Peces"))
        hijo = svc.crear(DatosFamilia(nombre="Ciclidos", parent_id=padre))
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        svc.desactivar(hijo)
        svc.desactivar(padre)  # ya no tiene hijos ACTIVOS
    with crear_sesion() as s:
        assert s.get(Familia, padre).activo is False
