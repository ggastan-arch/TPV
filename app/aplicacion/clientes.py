"""Casos de uso de mantenimiento de clientes (maestro con datos personales).

Reglas: el NIF es opcional (la factura simplificada no lo exige; si lo pide la
"cualificada" del art. 7.2 ROF); si se aporta, debe ser un documento valido (NIF/NIE/CIF)
y se almacena normalizado. Los clientes NUNCA se borran: el derecho de supresion RGPD cede
ante la obligacion de conservacion fiscal de las ventas asociadas, asi que solo se
desactivan (activo=false)."""
from __future__ import annotations

from dataclasses import dataclass

from app.dominio.servicios.validadores import normalizar_documento, validar_documento
from app.dominio.puertos import UnidadDeTrabajo
from app.infraestructura.persistencia.modelos import Cliente


@dataclass
class DatosCliente:
    nombre: str
    nif: str | None = None
    domicilio: str | None = None
    email: str | None = None
    telefono: str | None = None
    rgpd_consentimiento: bool = False


class NifInvalido(Exception):
    pass


class ClienteNoEncontrado(Exception):
    pass


class ServicioClientes:
    def __init__(self, uow: UnidadDeTrabajo, *, usuario_id: int | None = None, origen: str = "local"):
        self.uow = uow
        self.usuario_id = usuario_id
        self.origen = origen

    def crear(self, datos: DatosCliente) -> int:
        # Nota RGPD (Judgment Day S-3, documentado — sin cambio de comportamiento):
        # `rgpd_consentimiento` se persiste tal cual lo declara el llamante, sin
        # exigirlo como condicion para crear. Para el caso de uso "cualificada"
        # (ver presentacion/tpv.py::crear_cliente_inline), NIF+domicilio se piden
        # por obligacion fiscal (art. 7.2/7.3 ROF), no por consentimiento
        # comercial; forzar `rgpd_consentimiento=True` aqui seria incorrecto
        # (la base legal de ese tratamiento es la obligacion legal, art. 6.1.c
        # RGPD, no el consentimiento del art. 6.1.a). No añadir esa validacion.
        nif = self._validar_nif(datos.nif)
        cliente = Cliente(
            nombre=datos.nombre, nif=nif, domicilio=datos.domicilio,
            email=datos.email, telefono=datos.telefono,
            rgpd_consentimiento=datos.rgpd_consentimiento)
        self.uow.clientes.agregar(cliente)
        self.uow.flush()
        self._auditar("crear_cliente", cliente.id)
        self.uow.commit()
        return cliente.id

    def actualizar(self, cliente_id: int, datos: DatosCliente) -> None:
        cliente = self.uow.clientes.buscar(cliente_id)
        if cliente is None:
            raise ClienteNoEncontrado(cliente_id)
        cliente.nif = self._validar_nif(datos.nif)
        cliente.nombre = datos.nombre
        cliente.domicilio = datos.domicilio
        cliente.email = datos.email
        cliente.telefono = datos.telefono
        cliente.rgpd_consentimiento = datos.rgpd_consentimiento
        self._auditar("actualizar_cliente", cliente.id)
        self.uow.commit()

    def desactivar(self, cliente_id: int) -> None:
        self._cambiar_activo(cliente_id, False, "desactivar_cliente")

    def activar(self, cliente_id: int) -> None:
        self._cambiar_activo(cliente_id, True, "activar_cliente")

    # -- helpers ---------------------------------------------------------------
    def _cambiar_activo(self, cliente_id: int, activo: bool, accion: str) -> None:
        cliente = self.uow.clientes.buscar(cliente_id)
        if cliente is None:
            raise ClienteNoEncontrado(cliente_id)
        cliente.activo = activo
        self._auditar(accion, cliente.id)
        self.uow.commit()

    def _validar_nif(self, nif: str | None) -> str | None:
        if nif is None or not nif.strip():
            return None
        if not validar_documento(nif):
            raise NifInvalido(nif)
        return normalizar_documento(nif)

    def _auditar(self, accion: str, cliente_id: int) -> None:
        # No se registra el detalle de los datos personales en el log de auditoria.
        self.uow.auditoria.registrar(
            accion=accion, entidad="cliente", entidad_id=str(cliente_id),
            usuario_id=self.usuario_id, origen=self.origen)
