"""API del TPV tactil (bajo /tpv). Sirve la pantalla de venta y su API JSON.

El dinero se calcula SIEMPRE en el servidor con Decimal (la funcion unica de redondeo);
el frontend nunca hace aritmetica de importes. La venta se cierra localmente aunque
falle la impresora (local-first)."""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aplicacion.aparcar_venta import (
    AparcarVenta,
    BorradorNoEncontrado,
    ListarAparcadas,
    RecuperarAparcada,
)
from app.aplicacion.aparcar_venta import TicketVacio as TicketVacioAparcar
from app.aplicacion.aparcar_venta import UsuarioNoValido as UsuarioNoValidoAparcar
from app.aplicacion.clientes import DatosCliente, NifInvalido, ServicioClientes
from app.aplicacion.emitir_venta import (
    CualificadaSinDatos,
    EmitirVenta,
    PagoVenta,
    TicketVacio,
    UsuarioNoValido,
)
from app.aplicacion.lineas import ArticuloNoExiste, DescripcionRequerida
from app.aplicacion.lineas import ItemVenta as ItemAplicacion
from app.aplicacion.lineas import resolver_items
from app.presentacion.deps import get_motor, get_session, get_uow
from app.infraestructura.config import settings
from app.infraestructura.reloj import ahora_huso
from app.infraestructura.seguridad import verificar_pin
from app.infraestructura.fiscal import qr as qr_mod
from app.infraestructura.fiscal.engine import FiscalEngine
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Familia,
    LogAuditoria,
    PerfilBotonera,
    RegistroFiscal,
    Usuario,
    Venta,
)

_log = logging.getLogger(__name__)
_UI = Path(__file__).resolve().parents[1] / "ui" / "tpv.html"

router = APIRouter(prefix="/tpv", tags=["tpv"])


def require_pin(pin: str | None = None, uow=Depends(get_uow)) -> int:
    """Dependencia: exige el PIN de un usuario activo (patron kiosco, sin sesion
    de servidor). Reutiliza el `uow` de la peticion (evita abrir una segunda
    conexion/transaccion SQLite en modo BEGIN IMMEDIATE). Devuelve el usuario_id."""
    if pin:
        for usuario in uow.usuarios.listar(incluir_inactivos=False):
            if verificar_pin(pin, usuario.pin_hash):
                return usuario.id
    raise HTTPException(401, "PIN incorrecto")


# --- esquemas de entrada -------------------------------------------------------
class ItemVenta(BaseModel):
    articulo_id: int
    cantidad: Decimal = Decimal("1")
    pvp: Decimal | None = None  # override de precio unitario (cualquier articulo)
    descripcion: str | None = None  # override de descripcion de linea


class CalcularReq(BaseModel):
    items: list[ItemVenta] = Field(default_factory=list)


class PagoReq(BaseModel):
    medio: str
    importe: Decimal


class CobrarReq(BaseModel):
    usuario_id: int
    items: list[ItemVenta]
    pagos: list[PagoReq] = Field(default_factory=list)
    cliente_id: int | None = None
    cualificada: bool = False


class AparcarReq(BaseModel):
    usuario_id: int  # kiosco: FK NOT NULL de venta.usuario_id
    items: list[ItemVenta]
    etiqueta: str | None = None


class LoginReq(BaseModel):
    pin: str


class CajonReq(BaseModel):
    usuario_id: int | None = None


class ClienteReq(BaseModel):
    nombre: str
    nif: str | None = None
    domicilio: str | None = None
    email: str | None = None
    telefono: str | None = None
    rgpd_consentimiento: bool = False


# --- serializacion -------------------------------------------------------------
def _articulo_dto(a: Articulo) -> dict:
    return {
        "id": a.id,
        "nombre": a.nombre,
        "nombre_corto": a.nombre_corto,
        "pvp": str(a.pvp),
        "tipo_iva": str(a.tipo_iva.porcentaje),
        "modo_precio": a.modo_precio,
        "requiere_cites": a.requiere_cites,
        "color": a.color_boton,
        "imagen": a.imagen,
    }


# --- pagina ---------------------------------------------------------------------
@router.get("/", include_in_schema=False)
def pagina_tpv() -> FileResponse:
    return FileResponse(_UI)


# --- API ------------------------------------------------------------------------
@router.post("/api/login")
def login(req: LoginReq, s: Session = Depends(get_session)) -> dict:
    for usuario in s.execute(select(Usuario).where(Usuario.activo.is_(True))).scalars():
        if verificar_pin(req.pin, usuario.pin_hash):
            return {"usuario_id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}
    raise HTTPException(401, "PIN incorrecto")


@router.get("/api/botonera")
def botonera(s: Session = Depends(get_session)) -> dict:
    perfil = s.execute(
        select(PerfilBotonera).where(PerfilBotonera.activo.is_(True)).order_by(PerfilBotonera.id)
    ).scalars().first()
    if perfil is None or not perfil.paginas:
        raise HTTPException(404, "No hay botonera configurada")
    pagina = sorted(perfil.paginas, key=lambda p: p.orden)[0]

    botones = []
    for b in pagina.botones:
        dto = {"fila": b.fila, "columna": b.columna, "ancho": b.ancho, "alto": b.alto,
               "color": b.color, "icono": b.icono, "texto": b.texto}
        if b.articulo_id is not None:
            dto["tipo"] = "articulo"
            dto["articulo"] = _articulo_dto(s.get(Articulo, b.articulo_id))
        elif b.familia_id is not None:
            fam = s.get(Familia, b.familia_id)
            dto["tipo"] = "familia"
            dto["familia"] = {"id": fam.id, "nombre": fam.nombre, "color": fam.color,
                              "imagen": fam.imagen}
        else:
            dto["tipo"] = "funcion"
            dto["funcion"] = b.funcion
        botones.append(dto)

    return {
        "perfil": perfil.nombre,
        "pagina": {"id": pagina.id, "nombre": pagina.nombre,
                   "columnas": pagina.columnas, "filas": pagina.filas},
        "botones": botones,
    }


@router.get("/api/familia/{familia_id}")
def familia(familia_id: int, s: Session = Depends(get_session)) -> dict:
    fam = s.get(Familia, familia_id)
    if fam is None:
        raise HTTPException(404, "Familia no encontrada")
    subs = s.execute(
        select(Familia).where(Familia.parent_id == familia_id, Familia.activo.is_(True),
                              Familia.visible_en_tactil.is_(True))
        .order_by(Familia.orden)
    ).scalars().all()
    arts = s.execute(
        select(Articulo).where(Articulo.familia_id == familia_id, Articulo.activo.is_(True))
        .order_by(Articulo.nombre)
    ).scalars().all()
    return {
        "id": fam.id, "nombre": fam.nombre, "parent_id": fam.parent_id,
        "subfamilias": [{"id": x.id, "nombre": x.nombre, "color": x.color,
                        "imagen": x.imagen} for x in subs],
        "articulos": [_articulo_dto(a) for a in arts],
    }


@router.get("/api/buscar")
def buscar(q: str = "", uow=Depends(get_uow)) -> list[dict]:
    """Busqueda incremental por nombre (lupa): solo lectura, sin efectos.
    Universo = todos los articulos activos (ver `buscar_por_nombre`)."""
    return [_articulo_dto(a) for a in uow.articulos.buscar_por_nombre(q)]


@router.get("/api/articulo/por-codigo/{codigo}")
def articulo_por_codigo(codigo: str, uow=Depends(get_uow)) -> dict:
    articulo = uow.articulos.buscar_por_codigo(codigo)
    if articulo is None:
        raise HTTPException(404, "Codigo de barras no encontrado")
    return _articulo_dto(articulo)


@router.post("/api/calcular")
def calcular(req: CalcularReq, uow=Depends(get_uow)) -> dict:
    try:
        lineas, totales = resolver_items(uow.articulos, req.items)
    except ArticuloNoExiste as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "lineas": [
            {"articulo_id": lr.articulo.id, "descripcion": lr.descripcion,
             "cantidad": str(lr.cantidad), "pvp": str(lr.pvp),
             "tipo_iva": str(lr.calculo.porcentaje), "total": str(lr.calculo.total),
             "requiere_cites": lr.articulo.requiere_cites}
            for lr in lineas
        ],
        "base_total": str(totales.base_total),
        "cuota_total": str(totales.cuota_total),
        "total": str(totales.total_con_iva),
        "desglose": [{"tipo": str(d.porcentaje), "base": str(d.base), "cuota": str(d.cuota)}
                     for d in totales.desglose],
    }


@router.post("/api/cobrar")
def cobrar(
    req: CobrarReq,
    uow=Depends(get_uow),
    motor: FiscalEngine = Depends(get_motor),
) -> dict:
    # El endpoint es un adaptador fino: mapea el DTO HTTP y delega en el caso de uso.
    try:
        resultado = EmitirVenta(uow, motor).ejecutar(
            usuario_id=req.usuario_id,
            items=[ItemAplicacion(articulo_id=i.articulo_id, cantidad=i.cantidad,
                                   pvp=i.pvp, descripcion=i.descripcion)
                   for i in req.items],
            pagos=[PagoVenta(medio=p.medio, importe=p.importe) for p in req.pagos],
            cliente_id=req.cliente_id, cualificada=req.cualificada,
        )
    except TicketVacio as exc:
        raise HTTPException(400, "El ticket esta vacio") from exc
    except UsuarioNoValido as exc:
        raise HTTPException(401, "Usuario no valido") from exc
    except ArticuloNoExiste as exc:
        raise HTTPException(404, str(exc)) from exc
    except DescripcionRequerida as exc:
        raise HTTPException(422, str(exc)) from exc
    except CualificadaSinDatos as exc:
        raise HTTPException(
            422, "Simplificada cualificada exige cliente con NIF y domicilio"
        ) from exc

    _imprimir_ticket_seguro(resultado.venta_id)
    return {
        "venta_id": resultado.venta_id,
        "num_serie": resultado.num_serie,
        "fecha": resultado.fecha,
        "total": resultado.total,
        "cambio": resultado.cambio,
    }


# --- Cliente en venta: busqueda (PIN-gated) y alta inline con RGPD ------------
def _cliente_dto(c) -> dict:
    return {
        "id": c.id, "nombre": c.nombre, "nif": c.nif, "domicilio": c.domicilio,
        "email": c.email, "telefono": c.telefono,
        "rgpd_consentimiento": c.rgpd_consentimiento,
    }


def _cliente_resumen_dto(c) -> dict:
    """DTO recortado para resultados de BUSQUEDA (picker del TPV): el panel
    "Cliente en venta" solo necesita id/nombre/nif/domicilio para mostrar y
    asignar; email/telefono son PII que la UI no consume aqui (Judgment Day
    S-4). El alta inline (`crear_cliente_inline`) sigue devolviendo el DTO
    completo porque nada exige recortarlo alli."""
    return {"id": c.id, "nombre": c.nombre, "nif": c.nif, "domicilio": c.domicilio}


@router.get("/api/clientes")
def buscar_clientes(
    q: str = "", _: int = Depends(require_pin), uow=Depends(get_uow),
) -> list[dict]:
    """Busqueda de cliente por nombre (subcadena) o NIF (exacto) desde el panel
    "Cliente en venta" del TPV. PIN-gated (nunca bajo `require_admin`, ver spec)."""
    por_nif = uow.clientes.buscar_por_nif(q) if q.strip() else None
    if por_nif is not None:
        return [_cliente_resumen_dto(por_nif)]
    return [_cliente_resumen_dto(c) for c in uow.clientes.buscar_por_nombre(q)]


@router.post("/api/clientes")
def crear_cliente_inline(
    req: ClienteReq, usuario_id: int = Depends(require_pin), uow=Depends(get_uow),
) -> dict:
    """Alta inline de cliente sin salir del TPV (reusa `ServicioClientes.crear`:
    validacion de NIF + auditoria + consentimiento RGPD, ver spec).

    Nota RGPD (Judgment Day S-3, documentado — NO se cambia el comportamiento):
    para una simplificada cualificada (art. 7.2/7.3 ROF) el cliente aporta
    NIF+domicilio por OBLIGACION FISCAL (el es quien pide la factura
    cualificada), no por una relacion comercial que requiera base de consentimiento
    del art. 6.1.a RGPD -- la base aqui es el cumplimiento de una obligacion legal
    (art. 6.1.c). `rgpd_consentimiento` se sigue capturando y persistiendo por
    trazabilidad/transparencia hacia el cliente, pero NO es (ni debe convertirse
    en) una puerta de creacion: exigir `rgpd_consentimiento=true` para poder
    dar de alta o asignar el cliente seria juridicamente incorrecto para esta
    base de tratamiento (forzaria consentimiento donde la base real es
    obligacion legal). No añadir esa validacion."""
    try:
        cliente_id = ServicioClientes(uow, usuario_id=usuario_id, origen="local").crear(
            DatosCliente(
                nombre=req.nombre, nif=req.nif, domicilio=req.domicilio,
                email=req.email, telefono=req.telefono,
                rgpd_consentimiento=req.rgpd_consentimiento,
            )
        )
    except NifInvalido as exc:
        raise HTTPException(422, "NIF no valido") from exc
    return _cliente_dto(uow.clientes.buscar(cliente_id))


# --- Aparcar / listar / desaparcar (borradores no fiscales, ver ADR-0004) ------
@router.post("/api/aparcar")
def aparcar(req: AparcarReq, uow=Depends(get_uow)) -> dict:
    # Endpoint fino: mapea el DTO HTTP y delega en el caso de uso (SIN motor:
    # frontera fiscal por construccion, nunca invoca emit).
    try:
        venta_id = AparcarVenta(uow).ejecutar(
            usuario_id=req.usuario_id,
            items=[ItemAplicacion(articulo_id=i.articulo_id, cantidad=i.cantidad,
                                   pvp=i.pvp, descripcion=i.descripcion)
                   for i in req.items],
            etiqueta=req.etiqueta,
        )
    except TicketVacioAparcar as exc:
        raise HTTPException(400, "El ticket esta vacio") from exc
    except UsuarioNoValidoAparcar as exc:
        raise HTTPException(401, "Usuario no valido") from exc
    except ArticuloNoExiste as exc:
        raise HTTPException(404, str(exc)) from exc
    except DescripcionRequerida as exc:
        raise HTTPException(422, str(exc)) from exc

    venta = uow.ventas.buscar(venta_id)
    return {
        "venta_id": venta.id,
        "etiqueta": venta.etiqueta_aparcada,
        "total": str(venta.total_con_iva),
        "n_lineas": len(venta.lineas),
    }


@router.get("/api/aparcadas")
def aparcadas(uow=Depends(get_uow)) -> list[dict]:
    return [
        {"venta_id": a.venta_id, "etiqueta": a.etiqueta, "total": str(a.total),
         "n_lineas": a.n_lineas}
        for a in ListarAparcadas(uow).ejecutar()
    ]


@router.delete("/api/aparcadas/{venta_id}")
def desaparcar(venta_id: int, uow=Depends(get_uow)) -> dict:
    try:
        lineas = RecuperarAparcada(uow).ejecutar(venta_id)
    except BorradorNoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc

    resultado = []
    for l in lineas:
        articulo = uow.articulos.buscar(l.articulo_id) if l.articulo_id is not None else None
        resultado.append({
            "articulo_id": l.articulo_id,
            "cantidad": str(l.cantidad),
            "pvp": str(l.pvp),
            "descripcion": l.descripcion,
            "modo_precio": articulo.modo_precio if articulo else None,
            "nombre_corto": articulo.nombre_corto if articulo else None,
        })
    return {"lineas": resultado}


@router.get("/api/stock/alarma")
def stock_alarma(_: int = Depends(require_pin), uow=Depends(get_uow)) -> dict:
    """Senal informativa de stock negativo; NUNCA bloquea el cobro (CLAUDE.md)."""
    negativos = uow.stock.rastreados_en_negativo()
    return {
        "control_activo": uow.configuracion.control_stock_activo(),
        "articulos_en_negativo": len(negativos),
    }


@router.post("/api/cajon")
def abrir_cajon_sin_venta(req: CajonReq, s: Session = Depends(get_session)) -> dict:
    # Toda apertura de cajon sin venta queda en el log de auditoria (invariante 4).
    with s.begin():
        s.add(LogAuditoria(
            fecha_hora_huso=ahora_huso(), usuario_id=req.usuario_id,
            accion="apertura_cajon_sin_venta", entidad="caja", origen="local"))
    try:
        from app.infraestructura.impresion.ticket import abrir_cajon, crear_impresora

        abrir_cajon(crear_impresora())
    except Exception as exc:  # noqa: BLE001 - local-first
        _log.warning("No se pudo abrir el cajon: %s", exc)
    return {"ok": True}


@router.get("/api/venta/{venta_id}/qr.png")
def qr_venta(venta_id: int, s: Session = Depends(get_session)) -> Response:
    if settings.perfil == "demo":
        # El ticket digital del demo es un DOCUMENTO DE PRUEBA SIN VALIDEZ FISCAL: no se
        # genera un QR de cotejo tipo-AEAT con datos de prueba (invariante 7, honestidad
        # del demo). La UI /tpv oculta el QR en demo; esto es la defensa en profundidad.
        raise HTTPException(404, "QR de cotejo no disponible en modo demo (sin validez fiscal)")
    registro = s.execute(
        select(RegistroFiscal).where(RegistroFiscal.venta_id == venta_id,
                                     RegistroFiscal.tipo_registro == "alta")
    ).scalars().first()
    if registro is None:
        raise HTTPException(404, "Venta sin registro fiscal")
    png = qr_mod.qr_png(qr_mod.url_cotejo_registro(registro), scale=5)
    return Response(content=png, media_type="image/png")


def _imprimir_ticket_seguro(venta_id: int) -> None:
    """Imprime el ticket, pero la venta ya esta cerrada: un fallo de impresora no la rompe."""
    try:
        from app.infraestructura.db import SessionLocal
        from app.infraestructura.impresion.ticket import crear_impresora, imprimir_ticket

        with SessionLocal() as s:
            venta = s.get(Venta, venta_id)
            registro = s.execute(
                select(RegistroFiscal).where(RegistroFiscal.venta_id == venta_id,
                                             RegistroFiscal.tipo_registro == "alta")
            ).scalars().first()
            if venta is None or registro is None:
                return
            _ = venta.lineas, registro.desglose, venta.cliente
            imprimir_ticket(crear_impresora(), venta, registro, cliente=venta.cliente)
    except Exception as exc:  # noqa: BLE001 - local-first: no romper la venta
        _log.warning("No se pudo imprimir el ticket de la venta %s: %s", venta_id, exc)
