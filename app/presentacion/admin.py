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
from app.presentacion.deps import get_session, get_uow
from app.infraestructura.config import settings
from app.infraestructura.reloj import ahora_huso
from app.infraestructura.seguridad import verificar_pin
from app.infraestructura.fiscal.engine import NullEngine
from app.infraestructura.persistencia.modelos import (
    Articulo,
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
