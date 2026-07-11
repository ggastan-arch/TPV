"""Casos de uso de mantenimiento de usuarios (operadores del TPV), sin HTTP.

Reglas: el PIN se guarda hasheado (nunca en claro ni en el log de auditoria); rol validado;
nombre unico; y la regla que no se puede violar: el sistema NUNCA queda sin un
administrador activo (ni por baja ni por degradacion de rol)."""
from __future__ import annotations

import pytest

from app.aplicacion.usuarios import (
    DatosUsuario,
    NombreDuplicado,
    PinInvalido,
    RolInvalido,
    ServicioUsuarios,
    UltimoAdministrador,
    UsuarioNoEncontrado,
)
from app.infraestructura.persistencia.modelos import LogAuditoria, Usuario
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.seguridad import verificar_pin


def _svc(session, datos_base):
    return ServicioUsuarios(
        UnidadDeTrabajoSQL(session), usuario_id=datos_base["usuario_id"], origen="local")


def _auditorias(crear_sesion, accion):
    with crear_sesion() as s:
        return s.query(LogAuditoria).filter_by(accion=accion).all()


def test_crear_usuario_hashea_pin_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))

    with crear_sesion() as s:
        usuario = s.get(Usuario, nuevo_id)
        assert usuario is not None and usuario.rol == "venta" and usuario.activo is True
        assert usuario.pin_hash != "1234"  # nunca en claro
        assert verificar_pin("1234", usuario.pin_hash) is True
    assert len(_auditorias(crear_sesion, "crear_usuario")) == 1


def test_crear_nombre_duplicado_falla(crear_sesion, datos_base):
    # 'dependiente' ya existe (datos_base).
    with crear_sesion() as s:
        with pytest.raises(NombreDuplicado):
            _svc(s, datos_base).crear(DatosUsuario(nombre="dependiente", rol="venta", pin="1234"))


def test_crear_rol_invalido_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(RolInvalido):
            _svc(s, datos_base).crear(DatosUsuario(nombre="x", rol="jefe", pin="1234"))


def test_crear_pin_corto_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(PinInvalido):
            _svc(s, datos_base).crear(DatosUsuario(nombre="x", rol="venta", pin="12"))


def test_actualizar_cambia_nombre_y_rol_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(nuevo_id, DatosUsuario(nombre="cajera jefa", rol="administracion"))
    with crear_sesion() as s:
        usuario = s.get(Usuario, nuevo_id)
        assert usuario.nombre == "cajera jefa" and usuario.rol == "administracion"
    assert len(_auditorias(crear_sesion, "actualizar_usuario")) == 1


def test_no_desactivar_ultimo_administrador(crear_sesion, datos_base):
    with crear_sesion() as s:
        admin_id = _svc(s, datos_base).crear(DatosUsuario(nombre="jefa", rol="administracion", pin="9999"))
    with crear_sesion() as s:
        with pytest.raises(UltimoAdministrador):
            _svc(s, datos_base).desactivar(admin_id)
    with crear_sesion() as s:
        assert s.get(Usuario, admin_id).activo is True  # sigue activo


def test_desactivar_admin_si_hay_otro_activo(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        admin1 = svc.crear(DatosUsuario(nombre="jefa", rol="administracion", pin="9999"))
        svc.crear(DatosUsuario(nombre="jefe2", rol="administracion", pin="8888"))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(admin1)  # hay otro admin activo -> permitido
    with crear_sesion() as s:
        assert s.get(Usuario, admin1).activo is False


def test_no_degradar_a_venta_al_ultimo_administrador(crear_sesion, datos_base):
    with crear_sesion() as s:
        admin_id = _svc(s, datos_base).crear(DatosUsuario(nombre="jefa", rol="administracion", pin="9999"))
    with crear_sesion() as s:
        with pytest.raises(UltimoAdministrador):
            _svc(s, datos_base).actualizar(admin_id, DatosUsuario(nombre="jefa", rol="venta"))


def test_cambiar_pin_no_expone_el_pin(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        _svc(s, datos_base).cambiar_pin(nuevo_id, "5678")

    with crear_sesion() as s:
        usuario = s.get(Usuario, nuevo_id)
        assert verificar_pin("5678", usuario.pin_hash) is True
        assert verificar_pin("1234", usuario.pin_hash) is False
    assert len(_auditorias(crear_sesion, "cambio_pin")) == 1
    # El PIN jamas aparece en el log de auditoria.
    with crear_sesion() as s:
        detalles = [log.detalle or "" for log in s.query(LogAuditoria).all()]
        assert all("5678" not in d and "1234" not in d for d in detalles)


def test_desactivar_usuario_venta_ok(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(nuevo_id)
    with crear_sesion() as s:
        assert s.get(Usuario, nuevo_id).activo is False


def test_actualizar_inexistente_falla(crear_sesion, datos_base):
    with crear_sesion() as s:
        with pytest.raises(UsuarioNoEncontrado):
            _svc(s, datos_base).actualizar(999999, DatosUsuario(nombre="x", rol="venta"))
