"""Consola de administracion (bajo /admin). Protegida con sesion + rol administracion.

Cada acceso y accion de administracion queda en el log de auditoria (invariante 4),
distinguiendo origen local/remoto. El panel fiscal expone la cola de remision, la
verificacion de la cadena de huellas y la declaracion responsable.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aplicacion.articulos import (
    ArticuloNoEncontrado,
    DatosArticulo,
    FamiliaNoExiste,
    ServicioArticulos,
    TipoIvaNoExiste,
)
from app.aplicacion.clientes import (
    ClienteNoEncontrado,
    DatosCliente,
    NifInvalido,
    ServicioClientes,
)
from app.aplicacion.usuarios import (
    DatosUsuario,
    NombreDuplicado,
    PinInvalido,
    RolInvalido,
    ServicioUsuarios,
    UltimoAdministrador,
    UsuarioNoEncontrado,
)
from app.aplicacion.familias import (
    CicloEnFamilia,
    DatosFamilia,
    FamiliaConHijos,
    FamiliaNoEncontrada,
    FamiliaPadreNoExiste,
    ServicioFamilias,
)
from app.aplicacion.generar_cierre_z import GenerarCierreZ
from app.aplicacion.tipos_iva import (
    DatosTipoIva,
    PorcentajeInvalido,
    ServicioTiposIva,
    TipoIvaNoEncontrado,
)
from app.presentacion.deps import get_session, get_uow
from app.infraestructura.config import settings
from app.infraestructura.reloj import ahora_huso
from app.infraestructura.seguridad import verificar_pin
from app.infraestructura.fiscal.engine import NullEngine
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Cliente,
    Familia,
    LogAuditoria,
    TipoIVA,
    Usuario,
    Venta,
)

_UI = Path(__file__).resolve().parents[1] / "ui" / "admin.html"

router = APIRouter(prefix="/admin", tags=["admin"])


class LoginAdminReq(BaseModel):
    nombre: str
    password: str


class ArticuloReq(BaseModel):
    nombre: str
    nombre_corto: str
    tipo_iva_id: int
    pvp: Decimal
    familia_id: int | None = None
    coste: Decimal | None = None
    control_stock: bool = False
    precio_libre: bool = False
    requiere_cites: bool = False
    color_boton: str | None = None
    icono: str | None = None
    codigos: list[str] = []


class TipoIvaReq(BaseModel):
    nombre: str
    porcentaje: Decimal
    calificacion: str = "S1"


class FamiliaReq(BaseModel):
    nombre: str
    parent_id: int | None = None
    orden: int = 0
    color: str | None = None
    imagen: str | None = None


class ClienteReq(BaseModel):
    nombre: str
    nif: str | None = None
    domicilio: str | None = None
    email: str | None = None
    telefono: str | None = None
    rgpd_consentimiento: bool = False


class UsuarioCrearReq(BaseModel):
    nombre: str
    rol: str
    pin: str


class UsuarioActualizarReq(BaseModel):
    nombre: str
    rol: str


class PinReq(BaseModel):
    pin: str


def _origen(request: Request) -> str:
    host = request.client.host if request.client else ""
    return "local" if host in ("127.0.0.1", "::1", "localhost") else "remoto"


def require_admin(request: Request) -> int:
    """Dependencia: exige sesion de administrador. Devuelve el usuario_id."""
    usuario_id = request.session.get("usuario_id")
    if usuario_id is None or request.session.get("rol") != "administracion":
        raise HTTPException(401, "No autenticado")
    return usuario_id


@router.get("/", include_in_schema=False)
def pagina_admin() -> FileResponse:
    return FileResponse(_UI)


@router.post("/api/login")
def login(req: LoginAdminReq, request: Request, s: Session = Depends(get_session)) -> dict:
    usuario = s.execute(
        select(Usuario).where(Usuario.nombre == req.nombre, Usuario.activo.is_(True))
    ).scalars().first()
    if usuario is None or usuario.rol != "administracion" or not verificar_pin(req.password, usuario.pin_hash):
        raise HTTPException(401, "Credenciales invalidas")

    request.session["usuario_id"] = usuario.id
    request.session["rol"] = usuario.rol
    s.add(LogAuditoria(fecha_hora_huso=ahora_huso(), usuario_id=usuario.id,
                       accion="acceso_admin", entidad="consola", origen=_origen(request)))
    s.commit()
    return {"usuario_id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}


@router.post("/api/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
def me(request: Request, s: Session = Depends(get_session)) -> dict:
    usuario_id = require_admin(request)
    usuario = s.get(Usuario, usuario_id)
    return {"usuario_id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}


# --- Panel fiscal --------------------------------------------------------------
@router.get("/api/fiscal/estado")
def fiscal_estado(_: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    motor = NullEngine(settings.nif_emisor, settings.nombre_emisor)
    informe = motor.verify_chain(uow.session)
    return {
        "declaracion_responsable": {
            "software": settings.nombre_sistema,
            "id_sistema": settings.id_sistema,
            "version": settings.version_sistema,
            "productor": settings.nombre_productor,
            "nif_productor": settings.nif_productor,
            "obligado": settings.nombre_emisor,
            "nif_obligado": settings.nif_emisor,
            "entorno": settings.entorno_aeat,
        },
        "cola": {
            "pendientes": uow.registros.contar_pendientes(),
            "incidencia": uow.registros.hay_incidencia_pendiente(),
            "certificado_configurado": bool(settings.certificado_cert_path),
        },
        "cadena": {"ok": informe.ok, "registros": informe.registros, "errores": informe.errores},
        "ultimos_registros": [
            {"orden": r.orden, "tipo": r.tipo_registro, "num_serie": r.num_serie_factura,
             "estado_remision": r.estado_remision, "huella": (r.huella or "")[:16] + "..."}
            for r in uow.registros.ultimos(10)
        ],
    }


@router.post("/api/fiscal/reintentar")
def fiscal_reintentar(request: Request, usuario_id: int = Depends(require_admin),
                      uow=Depends(get_uow)) -> dict:
    if not settings.certificado_cert_path:
        return {"ok": False, "mensaje": "Certificado no configurado: la remision no esta disponible."}
    from app.aplicacion.remitir_lote import RemitirLote
    from app.infraestructura.fiscal.remitente import remitente_desde_settings
    from app.infraestructura.fiscal.xml import sistema_desde_settings

    respuesta = RemitirLote(uow, remitente_desde_settings()).ejecutar(
        nombre_emisor=settings.nombre_emisor, nif_obligado=settings.nif_emisor,
        sistema=sistema_desde_settings())
    uow.session.add(LogAuditoria(fecha_hora_huso=ahora_huso(), usuario_id=usuario_id,
                                 accion="reintento_remision", entidad="cola_fiscal",
                                 origen=_origen(request)))
    uow.commit()
    if respuesta is None:
        return {"ok": False, "mensaje": "Incidencia de conectividad; se reintentara."}
    return {"ok": True, "estado_envio": respuesta.estado_envio, "csv": respuesta.csv,
            "lineas": len(respuesta.lineas)}


# --- Informe del dia -----------------------------------------------------------
@router.get("/api/informes/dia")
def informe_dia(_: int = Depends(require_admin), s: Session = Depends(get_session)) -> dict:
    hoy = datetime.now().astimezone().strftime("%Y-%m-%d")
    ventas = s.execute(
        select(Venta).where(Venta.estado == "cobrada", Venta.fecha_hora_huso.like(f"{hoy}%"))
    ).scalars().all()
    total = sum((v.total_con_iva for v in ventas), Decimal("0.00"))
    por_medio: dict[str, Decimal] = {}
    for v in ventas:
        for p in v.pagos:
            por_medio[p.medio] = por_medio.get(p.medio, Decimal("0.00")) + p.importe
    return {
        "fecha": hoy,
        "num_ventas": len(ventas),
        "total": str(total),
        "por_medio": {k: str(val) for k, val in por_medio.items()},
    }


# --- Maestros (solo lectura) ---------------------------------------------------
@router.get("/api/maestros/tipos-iva")
def maestros_iva(_: int = Depends(require_admin), s: Session = Depends(get_session)) -> list[dict]:
    return [{"id": t.id, "nombre": t.nombre, "porcentaje": str(t.porcentaje), "activo": t.activo}
            for t in s.execute(select(TipoIVA).order_by(TipoIVA.id)).scalars()]


@router.get("/api/maestros/familias")
def maestros_familias(_: int = Depends(require_admin), s: Session = Depends(get_session)) -> list[dict]:
    return [{"id": f.id, "nombre": f.nombre, "parent_id": f.parent_id, "activo": f.activo}
            for f in s.execute(select(Familia).order_by(Familia.orden)).scalars()]


@router.get("/api/maestros/articulos")
def maestros_articulos(_: int = Depends(require_admin), s: Session = Depends(get_session)) -> list[dict]:
    return [{"id": a.id, "nombre": a.nombre, "pvp": str(a.pvp),
             "tipo_iva": str(a.tipo_iva.porcentaje), "control_stock": a.control_stock,
             "requiere_cites": a.requiere_cites, "activo": a.activo}
            for a in s.execute(select(Articulo).order_by(Articulo.nombre)).scalars()]


@router.get("/api/maestros/usuarios")
def maestros_usuarios(_: int = Depends(require_admin), s: Session = Depends(get_session)) -> list[dict]:
    # Nunca se expone el hash del PIN.
    return [{"id": u.id, "nombre": u.nombre, "rol": u.rol, "activo": u.activo}
            for u in s.execute(select(Usuario).order_by(Usuario.nombre)).scalars()]


@router.get("/api/maestros/clientes")
def maestros_clientes(_: int = Depends(require_admin), s: Session = Depends(get_session)) -> list[dict]:
    return [{"id": c.id, "nombre": c.nombre, "nif": c.nif, "domicilio": c.domicilio,
             "email": c.email, "telefono": c.telefono,
             "rgpd_consentimiento": c.rgpd_consentimiento, "activo": c.activo}
            for c in s.execute(select(Cliente).order_by(Cliente.nombre)).scalars()]


# --- Maestros: articulos (escritura) -------------------------------------------
def _servicio_articulos(request: Request, usuario_id: int, uow) -> ServicioArticulos:
    return ServicioArticulos(uow, usuario_id=usuario_id, origen=_origen(request))


@router.post("/api/maestros/articulos", status_code=201)
def crear_articulo(req: ArticuloReq, request: Request,
                   usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        nuevo_id = _servicio_articulos(request, usuario_id, uow).crear(DatosArticulo(**req.model_dump()))
    except TipoIvaNoExiste:
        raise HTTPException(422, "El tipo de IVA indicado no existe")
    except FamiliaNoExiste:
        raise HTTPException(422, "La familia indicada no existe")
    return {"id": nuevo_id}


@router.put("/api/maestros/articulos/{articulo_id}")
def actualizar_articulo(articulo_id: int, req: ArticuloReq, request: Request,
                        usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_articulos(request, usuario_id, uow).actualizar(articulo_id, DatosArticulo(**req.model_dump()))
    except ArticuloNoEncontrado:
        raise HTTPException(404, "Articulo no encontrado")
    except TipoIvaNoExiste:
        raise HTTPException(422, "El tipo de IVA indicado no existe")
    except FamiliaNoExiste:
        raise HTTPException(422, "La familia indicada no existe")
    return {"ok": True}


@router.post("/api/maestros/articulos/{articulo_id}/desactivar")
def desactivar_articulo(articulo_id: int, request: Request,
                        usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_articulos(request, usuario_id, uow).desactivar(articulo_id)
    except ArticuloNoEncontrado:
        raise HTTPException(404, "Articulo no encontrado")
    return {"ok": True}


@router.post("/api/maestros/articulos/{articulo_id}/activar")
def activar_articulo(articulo_id: int, request: Request,
                     usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_articulos(request, usuario_id, uow).activar(articulo_id)
    except ArticuloNoEncontrado:
        raise HTTPException(404, "Articulo no encontrado")
    return {"ok": True}


# --- Maestros: tipos de IVA (escritura) ----------------------------------------
def _servicio_tipos_iva(request: Request, usuario_id: int, uow) -> ServicioTiposIva:
    return ServicioTiposIva(uow, usuario_id=usuario_id, origen=_origen(request))


@router.post("/api/maestros/tipos-iva", status_code=201)
def crear_tipo_iva(req: TipoIvaReq, request: Request,
                   usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        nuevo_id = _servicio_tipos_iva(request, usuario_id, uow).crear(DatosTipoIva(**req.model_dump()))
    except PorcentajeInvalido:
        raise HTTPException(422, "El porcentaje de IVA no es valido (0-100)")
    return {"id": nuevo_id}


@router.put("/api/maestros/tipos-iva/{tipo_iva_id}")
def actualizar_tipo_iva(tipo_iva_id: int, req: TipoIvaReq, request: Request,
                        usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_tipos_iva(request, usuario_id, uow).actualizar(tipo_iva_id, DatosTipoIva(**req.model_dump()))
    except TipoIvaNoEncontrado:
        raise HTTPException(404, "Tipo de IVA no encontrado")
    except PorcentajeInvalido:
        raise HTTPException(422, "El porcentaje de IVA no es valido (0-100)")
    return {"ok": True}


@router.post("/api/maestros/tipos-iva/{tipo_iva_id}/desactivar")
def desactivar_tipo_iva(tipo_iva_id: int, request: Request,
                        usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_tipos_iva(request, usuario_id, uow).desactivar(tipo_iva_id)
    except TipoIvaNoEncontrado:
        raise HTTPException(404, "Tipo de IVA no encontrado")
    return {"ok": True}


@router.post("/api/maestros/tipos-iva/{tipo_iva_id}/activar")
def activar_tipo_iva(tipo_iva_id: int, request: Request,
                     usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_tipos_iva(request, usuario_id, uow).activar(tipo_iva_id)
    except TipoIvaNoEncontrado:
        raise HTTPException(404, "Tipo de IVA no encontrado")
    return {"ok": True}


# --- Maestros: familias (escritura) --------------------------------------------
def _servicio_familias(request: Request, usuario_id: int, uow) -> ServicioFamilias:
    return ServicioFamilias(uow, usuario_id=usuario_id, origen=_origen(request))


@router.post("/api/maestros/familias", status_code=201)
def crear_familia(req: FamiliaReq, request: Request,
                  usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        nuevo_id = _servicio_familias(request, usuario_id, uow).crear(DatosFamilia(**req.model_dump()))
    except FamiliaPadreNoExiste:
        raise HTTPException(422, "La familia padre indicada no existe")
    return {"id": nuevo_id}


@router.put("/api/maestros/familias/{familia_id}")
def actualizar_familia(familia_id: int, req: FamiliaReq, request: Request,
                       usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_familias(request, usuario_id, uow).actualizar(familia_id, DatosFamilia(**req.model_dump()))
    except FamiliaNoEncontrada:
        raise HTTPException(404, "Familia no encontrada")
    except FamiliaPadreNoExiste:
        raise HTTPException(422, "La familia padre indicada no existe")
    except CicloEnFamilia:
        raise HTTPException(422, "La reasignacion de padre crearia un ciclo en el arbol")
    return {"ok": True}


@router.post("/api/maestros/familias/{familia_id}/desactivar")
def desactivar_familia(familia_id: int, request: Request,
                       usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_familias(request, usuario_id, uow).desactivar(familia_id)
    except FamiliaNoEncontrada:
        raise HTTPException(404, "Familia no encontrada")
    except FamiliaConHijos:
        raise HTTPException(409, "La familia tiene subfamilias activas; desactivelas primero")
    return {"ok": True}


@router.post("/api/maestros/familias/{familia_id}/activar")
def activar_familia(familia_id: int, request: Request,
                    usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_familias(request, usuario_id, uow).activar(familia_id)
    except FamiliaNoEncontrada:
        raise HTTPException(404, "Familia no encontrada")
    return {"ok": True}


# --- Maestros: clientes (escritura) --------------------------------------------
def _servicio_clientes(request: Request, usuario_id: int, uow) -> ServicioClientes:
    return ServicioClientes(uow, usuario_id=usuario_id, origen=_origen(request))


@router.post("/api/maestros/clientes", status_code=201)
def crear_cliente(req: ClienteReq, request: Request,
                  usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        nuevo_id = _servicio_clientes(request, usuario_id, uow).crear(DatosCliente(**req.model_dump()))
    except NifInvalido:
        raise HTTPException(422, "El NIF/NIE/CIF indicado no es valido")
    return {"id": nuevo_id}


@router.put("/api/maestros/clientes/{cliente_id}")
def actualizar_cliente(cliente_id: int, req: ClienteReq, request: Request,
                       usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_clientes(request, usuario_id, uow).actualizar(cliente_id, DatosCliente(**req.model_dump()))
    except ClienteNoEncontrado:
        raise HTTPException(404, "Cliente no encontrado")
    except NifInvalido:
        raise HTTPException(422, "El NIF/NIE/CIF indicado no es valido")
    return {"ok": True}


@router.post("/api/maestros/clientes/{cliente_id}/desactivar")
def desactivar_cliente(cliente_id: int, request: Request,
                       usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_clientes(request, usuario_id, uow).desactivar(cliente_id)
    except ClienteNoEncontrado:
        raise HTTPException(404, "Cliente no encontrado")
    return {"ok": True}


@router.post("/api/maestros/clientes/{cliente_id}/activar")
def activar_cliente(cliente_id: int, request: Request,
                    usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_clientes(request, usuario_id, uow).activar(cliente_id)
    except ClienteNoEncontrado:
        raise HTTPException(404, "Cliente no encontrado")
    return {"ok": True}


# --- Maestros: usuarios (escritura) --------------------------------------------
def _servicio_usuarios(request: Request, usuario_id: int, uow) -> ServicioUsuarios:
    return ServicioUsuarios(uow, usuario_id=usuario_id, origen=_origen(request))


@router.post("/api/maestros/usuarios", status_code=201)
def crear_usuario(req: UsuarioCrearReq, request: Request,
                  usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        nuevo_id = _servicio_usuarios(request, usuario_id, uow).crear(
            DatosUsuario(nombre=req.nombre, rol=req.rol, pin=req.pin))
    except NombreDuplicado:
        raise HTTPException(409, "Ya existe un usuario con ese nombre")
    except RolInvalido:
        raise HTTPException(422, "Rol invalido (venta | administracion)")
    except PinInvalido:
        raise HTTPException(422, "El PIN no es valido (minimo 4 caracteres)")
    return {"id": nuevo_id}


@router.put("/api/maestros/usuarios/{usuario_objetivo_id}")
def actualizar_usuario(usuario_objetivo_id: int, req: UsuarioActualizarReq, request: Request,
                       usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_usuarios(request, usuario_id, uow).actualizar(
            usuario_objetivo_id, DatosUsuario(nombre=req.nombre, rol=req.rol))
    except UsuarioNoEncontrado:
        raise HTTPException(404, "Usuario no encontrado")
    except NombreDuplicado:
        raise HTTPException(409, "Ya existe un usuario con ese nombre")
    except RolInvalido:
        raise HTTPException(422, "Rol invalido (venta | administracion)")
    except UltimoAdministrador:
        raise HTTPException(409, "No se puede dejar el sistema sin un administrador activo")
    return {"ok": True}


@router.post("/api/maestros/usuarios/{usuario_objetivo_id}/pin")
def cambiar_pin_usuario(usuario_objetivo_id: int, req: PinReq, request: Request,
                        usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_usuarios(request, usuario_id, uow).cambiar_pin(usuario_objetivo_id, req.pin)
    except UsuarioNoEncontrado:
        raise HTTPException(404, "Usuario no encontrado")
    except PinInvalido:
        raise HTTPException(422, "El PIN no es valido (minimo 4 caracteres)")
    return {"ok": True}


@router.post("/api/maestros/usuarios/{usuario_objetivo_id}/desactivar")
def desactivar_usuario(usuario_objetivo_id: int, request: Request,
                       usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_usuarios(request, usuario_id, uow).desactivar(usuario_objetivo_id)
    except UsuarioNoEncontrado:
        raise HTTPException(404, "Usuario no encontrado")
    except UltimoAdministrador:
        raise HTTPException(409, "No se puede dejar el sistema sin un administrador activo")
    return {"ok": True}


@router.post("/api/maestros/usuarios/{usuario_objetivo_id}/activar")
def activar_usuario(usuario_objetivo_id: int, request: Request,
                    usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    try:
        _servicio_usuarios(request, usuario_id, uow).activar(usuario_objetivo_id)
    except UsuarioNoEncontrado:
        raise HTTPException(404, "Usuario no encontrado")
    return {"ok": True}


# --- Maestros: cierres Z (informe Z inmutable) ---------------------------------
def _cierre_z_resumen(cierre) -> dict:
    return {
        "numero": cierre.numero,
        "fecha_hora_huso": cierre.fecha_hora_huso,
        "desde_orden": cierre.desde_orden,
        "hasta_orden": cierre.hasta_orden,
        "num_tickets": cierre.num_tickets,
        "base_total": str(cierre.base_total),
        "cuota_total": str(cierre.cuota_total),
        "total_con_iva": str(cierre.total_con_iva),
    }


def _cierre_z_detalle(cierre) -> dict:
    resumen = _cierre_z_resumen(cierre)
    resumen["desglose_iva"] = [
        {"tipo_impositivo": str(d.tipo_impositivo), "base_imponible": str(d.base_imponible),
         "cuota_repercutida": str(d.cuota_repercutida)}
        for d in cierre.desglose_iva
    ]
    resumen["desglose_pago"] = [
        {"medio": d.medio, "importe": str(d.importe)} for d in cierre.desglose_pago
    ]
    return resumen


@router.post("/api/maestros/cierres-z", status_code=201)
def generar_cierre_z(request: Request, usuario_id: int = Depends(require_admin),
                     uow=Depends(get_uow)) -> dict:
    # `GenerarCierreZ` ya audita la generacion internamente (accion="generar_cierre_z");
    # no se duplica la auditoria aqui.
    resultado = GenerarCierreZ(uow).ejecutar(usuario_id=usuario_id, origen=_origen(request))
    return _cierre_z_resumen(resultado)


@router.get("/api/maestros/cierres-z")
def listar_cierres_z(_: int = Depends(require_admin), uow=Depends(get_uow)) -> list[dict]:
    return [_cierre_z_resumen(c) for c in uow.cierres_z.listar()]


@router.get("/api/maestros/cierres-z/{numero}")
def detalle_cierre_z(numero: int, _: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    cierre = uow.cierres_z.buscar(numero)
    if cierre is None:
        raise HTTPException(404, "Cierre Z no encontrado")
    return _cierre_z_detalle(cierre)
