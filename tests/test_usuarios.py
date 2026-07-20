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


def test_crear_admin_credencial_corta_falla(crear_sesion, datos_base):
    """El rol administracion exige una credencial mas larga que el PIN tactil de
    venta (consola accesible en remoto por Tailscale): un PIN de 4 no basta."""
    with crear_sesion() as s:
        with pytest.raises(PinInvalido):
            _svc(s, datos_base).crear(DatosUsuario(nombre="jefa", rol="administracion", pin="1234"))


def test_crear_admin_credencial_larga_ok(crear_sesion, datos_base):
    with crear_sesion() as s:
        admin_id = _svc(s, datos_base).crear(
            DatosUsuario(nombre="jefa", rol="administracion", pin="clave-fuerte"))
    with crear_sesion() as s:
        assert verificar_pin("clave-fuerte", s.get(Usuario, admin_id).pin_hash) is True


def test_cambiar_pin_admin_a_corto_falla(crear_sesion, datos_base):
    """cambiar_pin resuelve el rol del usuario: bajar un admin a credencial de 4 falla."""
    with crear_sesion() as s:
        admin_id = _svc(s, datos_base).crear(
            DatosUsuario(nombre="jefa", rol="administracion", pin="clave-fuerte"))
    with crear_sesion() as s:
        with pytest.raises(PinInvalido):
            _svc(s, datos_base).cambiar_pin(admin_id, "1234")


def test_actualizar_cambia_nombre_y_rol_y_audita(crear_sesion, datos_base):
    with crear_sesion() as s:
        nuevo_id = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        # Promover a administracion exige una credencial acorde al rol (>=8).
        _svc(s, datos_base).actualizar(
            nuevo_id, DatosUsuario(nombre="cajera jefa", rol="administracion", pin="clave-fuerte"))
    with crear_sesion() as s:
        usuario = s.get(Usuario, nuevo_id)
        assert usuario.nombre == "cajera jefa" and usuario.rol == "administracion"
    assert len(_auditorias(crear_sesion, "actualizar_usuario")) == 1


def test_promover_venta_a_admin_sin_pin_falla(crear_sesion, datos_base):
    """Cerrar el bypass: `actualizar` no re-hashea el PIN, asi que un usuario de
    venta con PIN de 4 promovido a administracion quedaria como admin con
    credencial debil. Promover a admin exige un PIN nuevo >=8."""
    with crear_sesion() as s:
        vid = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        with pytest.raises(PinInvalido):
            _svc(s, datos_base).actualizar(vid, DatosUsuario(nombre="cajera", rol="administracion"))
    # No se promovio: sigue siendo venta con su PIN corto.
    with crear_sesion() as s:
        u = s.get(Usuario, vid)
        assert u.rol == "venta"
        assert verificar_pin("1234", u.pin_hash) is True


def test_promover_venta_a_admin_con_pin_corto_falla(crear_sesion, datos_base):
    """Promover con un PIN nuevo pero por debajo del minimo de admin tambien falla."""
    with crear_sesion() as s:
        vid = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        with pytest.raises(PinInvalido):
            _svc(s, datos_base).actualizar(vid, DatosUsuario(nombre="cajera", rol="administracion", pin="12"))
    with crear_sesion() as s:
        assert s.get(Usuario, vid).rol == "venta"  # no se promovio


def test_promover_venta_a_admin_con_pin_valido_ok(crear_sesion, datos_base):
    with crear_sesion() as s:
        vid = _svc(s, datos_base).crear(DatosUsuario(nombre="cajera", rol="venta", pin="1234"))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(
            vid, DatosUsuario(nombre="cajera", rol="administracion", pin="clave-fuerte"))
    with crear_sesion() as s:
        u = s.get(Usuario, vid)
        assert u.rol == "administracion"
        assert verificar_pin("clave-fuerte", u.pin_hash) is True
        assert verificar_pin("1234", u.pin_hash) is False  # el PIN corto ya no vale


def test_actualizar_admin_sin_promover_no_exige_pin(crear_sesion, datos_base):
    """Editar el nombre de un admin (sin cambiar el rol) no exige re-indicar el PIN."""
    with crear_sesion() as s:
        aid = _svc(s, datos_base).crear(
            DatosUsuario(nombre="jefa", rol="administracion", pin="clave-fuerte"))
    with crear_sesion() as s:
        _svc(s, datos_base).actualizar(aid, DatosUsuario(nombre="jefa renombrada", rol="administracion"))
    with crear_sesion() as s:
        u = s.get(Usuario, aid)
        assert u.nombre == "jefa renombrada"
        assert verificar_pin("clave-fuerte", u.pin_hash) is True  # PIN intacto


def test_no_desactivar_ultimo_administrador(crear_sesion, datos_base):
    with crear_sesion() as s:
        admin_id = _svc(s, datos_base).crear(DatosUsuario(nombre="jefa", rol="administracion", pin="clave-jefa"))
    with crear_sesion() as s:
        with pytest.raises(UltimoAdministrador):
            _svc(s, datos_base).desactivar(admin_id)
    with crear_sesion() as s:
        assert s.get(Usuario, admin_id).activo is True  # sigue activo


def test_desactivar_admin_si_hay_otro_activo(crear_sesion, datos_base):
    with crear_sesion() as s:
        svc = _svc(s, datos_base)
        admin1 = svc.crear(DatosUsuario(nombre="jefa", rol="administracion", pin="clave-jefa"))
        svc.crear(DatosUsuario(nombre="jefe2", rol="administracion", pin="clave-jefe2"))
    with crear_sesion() as s:
        _svc(s, datos_base).desactivar(admin1)  # hay otro admin activo -> permitido
    with crear_sesion() as s:
        assert s.get(Usuario, admin1).activo is False


def test_no_degradar_a_venta_al_ultimo_administrador(crear_sesion, datos_base):
    with crear_sesion() as s:
        admin_id = _svc(s, datos_base).crear(DatosUsuario(nombre="jefa", rol="administracion", pin="clave-jefa"))
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
