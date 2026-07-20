"""Casos de uso de mantenimiento de usuarios (operadores del TPV).

Reglas: el PIN se almacena hasheado (PBKDF2), nunca en claro ni en el log de auditoria;
el rol se valida; el nombre es unico; y el sistema NUNCA puede quedarse sin un
administrador activo (ni por baja ni por degradacion de rol), o el titular se autobloquea
fuera de la consola. Los usuarios no se borran: solo se activan/desactivan."""
from __future__ import annotations

from dataclasses import dataclass

from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.modelos import Usuario

ROLES = ("venta", "administracion")
# Longitud minima de credencial por rol. El operador de venta usa un PIN tactil
# corto; el administrador entra por una consola accesible en remoto (Tailscale),
# asi que exige una credencial mas larga.
PIN_LONGITUD_MINIMA = 4
PIN_LONGITUD_MINIMA_ADMIN = 8


def _longitud_minima(rol: str) -> int:
    return PIN_LONGITUD_MINIMA_ADMIN if rol == "administracion" else PIN_LONGITUD_MINIMA


@dataclass
class DatosUsuario:
    nombre: str
    rol: str
    pin: str | None = None  # requerido al crear; en actualizar SOLO se usa al promover a administracion (los cambios de PIN van por cambiar_pin)


class NombreDuplicado(Exception):
    pass


class RolInvalido(Exception):
    pass


class PinInvalido(Exception):
    pass


class UsuarioNoEncontrado(Exception):
    pass


class UltimoAdministrador(Exception):
    pass


class ServicioUsuarios:
    def __init__(self, uow: UnidadDeTrabajo, *, usuario_id: int | None = None, origen: str = "local"):
        self.uow = uow
        self.usuario_id = usuario_id
        self.origen = origen

    def crear(self, datos: DatosUsuario) -> int:
        self._validar_rol(datos.rol)
        self._validar_nombre_libre(datos.nombre)
        pin_hash = self._hashear_pin(datos.pin, datos.rol)
        usuario = Usuario(nombre=datos.nombre, rol=datos.rol, pin_hash=pin_hash)
        self.uow.usuarios.agregar(usuario)
        self.uow.flush()
        self._auditar("crear_usuario", usuario.id)
        self.uow.commit()
        return usuario.id

    def actualizar(self, usuario_id: int, datos: DatosUsuario) -> None:
        usuario = self._obtener(usuario_id)
        self._validar_rol(datos.rol)
        self._validar_nombre_libre(datos.nombre, excluir_id=usuario_id)
        # No dejar el sistema sin administrador activo por degradacion de rol.
        if self._deja_sin_administrador(usuario, nuevo_rol=datos.rol, nuevo_activo=usuario.activo):
            raise UltimoAdministrador(usuario_id)
        # Promover a administracion exige una credencial acorde al rol: `actualizar`
        # NO re-hashea el PIN, asi que un usuario de venta (PIN >=4) promovido
        # heredaria una credencial debil en una consola accesible en remoto. Se
        # obliga a indicar un PIN nuevo que cumpla la politica de administracion.
        if datos.rol == "administracion" and usuario.rol != "administracion":
            if datos.pin is None:
                raise PinInvalido(
                    "promover a administracion exige un PIN nuevo de al menos "
                    f"{PIN_LONGITUD_MINIMA_ADMIN} caracteres")
            usuario.pin_hash = self._hashear_pin(datos.pin, "administracion")
        usuario.nombre = datos.nombre
        usuario.rol = datos.rol
        self._auditar("actualizar_usuario", usuario.id)
        self.uow.commit()

    def cambiar_pin(self, usuario_id: int, nuevo_pin: str) -> None:
        usuario = self._obtener(usuario_id)
        usuario.pin_hash = self._hashear_pin(nuevo_pin, usuario.rol)
        # El detalle NO incluye el PIN.
        self._auditar("cambio_pin", usuario.id)
        self.uow.commit()

    def desactivar(self, usuario_id: int) -> None:
        usuario = self._obtener(usuario_id)
        if self._deja_sin_administrador(usuario, nuevo_rol=usuario.rol, nuevo_activo=False):
            raise UltimoAdministrador(usuario_id)
        usuario.activo = False
        self._auditar("desactivar_usuario", usuario.id)
        self.uow.commit()

    def activar(self, usuario_id: int) -> None:
        usuario = self._obtener(usuario_id)
        usuario.activo = True
        self._auditar("activar_usuario", usuario.id)
        self.uow.commit()

    # -- helpers ---------------------------------------------------------------
    def _obtener(self, usuario_id: int) -> Usuario:
        usuario = self.uow.usuarios.buscar(usuario_id)
        if usuario is None:
            raise UsuarioNoEncontrado(usuario_id)
        return usuario

    def _deja_sin_administrador(self, usuario: Usuario, *, nuevo_rol: str, nuevo_activo: bool) -> bool:
        """True si aplicar (nuevo_rol, nuevo_activo) sobre `usuario` dejaria el sistema sin
        ningun administrador activo. Solo puede ocurrir si el usuario ES hoy admin activo,
        deja de serlo, y no hay OTRO administrador activo."""
        es_admin_activo_hoy = usuario.rol == "administracion" and usuario.activo
        seguira_siendo_admin_activo = nuevo_rol == "administracion" and nuevo_activo
        if not es_admin_activo_hoy or seguira_siendo_admin_activo:
            return False
        otros = self.uow.usuarios.contar_administradores_activos(excluir_id=usuario.id)
        return otros == 0

    def _validar_rol(self, rol: str) -> None:
        if rol not in ROLES:
            raise RolInvalido(rol)

    def _validar_nombre_libre(self, nombre: str, *, excluir_id: int | None = None) -> None:
        existente = self.uow.usuarios.buscar_por_nombre(nombre)
        if existente is not None and existente.id != excluir_id:
            raise NombreDuplicado(nombre)

    def _hashear_pin(self, pin: str | None, rol: str) -> str:
        minimo = _longitud_minima(rol)
        if pin is None or len(pin.strip()) < minimo:
            raise PinInvalido(f"La credencial del rol '{rol}' debe tener al menos {minimo} caracteres")
        return hash_pin(pin)

    def _auditar(self, accion: str, usuario_afectado_id: int) -> None:
        self.uow.auditoria.registrar(
            accion=accion, entidad="usuario", entidad_id=str(usuario_afectado_id),
            usuario_id=self.usuario_id, origen=self.origen)
