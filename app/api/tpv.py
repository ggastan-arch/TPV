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

from app.api.deps import get_motor, get_session
from app.core.redondeo import agregar_totales, calcular_linea
from app.core.reloj import ahora_huso
from app.core.seguridad import verificar_pin
from app.fiscal import qr as qr_mod
from app.fiscal.engine import FiscalEngine
from app.models import (
    Articulo,
    CodigoBarras,
    Familia,
    LogAuditoria,
    Pago,
    PerfilBotonera,
    RegistroFiscal,
    Usuario,
    Venta,
    VentaLinea,
)

_log = logging.getLogger(__name__)
_UI = Path(__file__).resolve().parents[1] / "ui" / "tpv.html"

router = APIRouter(prefix="/tpv", tags=["tpv"])


# --- esquemas de entrada -------------------------------------------------------
class ItemVenta(BaseModel):
    articulo_id: int
    cantidad: Decimal = Decimal("1")
    pvp: Decimal | None = None  # solo para articulos de precio libre


class CalcularReq(BaseModel):
    items: list[ItemVenta] = Field(default_factory=list)


class PagoReq(BaseModel):
    medio: str
    importe: Decimal


class CobrarReq(BaseModel):
    usuario_id: int
    items: list[ItemVenta]
    pagos: list[PagoReq] = Field(default_factory=list)


class LoginReq(BaseModel):
    pin: str


class CajonReq(BaseModel):
    usuario_id: int | None = None


# --- serializacion -------------------------------------------------------------
def _articulo_dto(a: Articulo) -> dict:
    return {
        "id": a.id,
        "nombre": a.nombre,
        "nombre_corto": a.nombre_corto,
        "pvp": str(a.pvp),
        "tipo_iva": str(a.tipo_iva.porcentaje),
        "precio_libre": a.precio_libre,
        "requiere_cites": a.requiere_cites,
        "color": a.color_boton,
    }


def _resolver_items(items: list[ItemVenta], s: Session):
    """Devuelve [(articulo, pvp, cantidad, Linea)] calculando cada linea en Decimal."""
    resultado = []
    lineas_calc = []
    for it in items:
        articulo = s.get(Articulo, it.articulo_id)
        if articulo is None:
            raise HTTPException(404, f"Articulo {it.articulo_id} no existe")
        pvp = it.pvp if (it.pvp is not None and articulo.precio_libre) else articulo.pvp
        linea = calcular_linea(Decimal(pvp), Decimal(it.cantidad), Decimal(articulo.tipo_iva.porcentaje))
        resultado.append((articulo, Decimal(pvp), Decimal(it.cantidad), linea))
        lineas_calc.append(linea)
    return resultado, agregar_totales(lineas_calc)


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
            dto["familia"] = {"id": fam.id, "nombre": fam.nombre, "color": fam.color}
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
        select(Familia).where(Familia.parent_id == familia_id, Familia.activo.is_(True))
        .order_by(Familia.orden)
    ).scalars().all()
    arts = s.execute(
        select(Articulo).where(Articulo.familia_id == familia_id, Articulo.activo.is_(True))
        .order_by(Articulo.nombre)
    ).scalars().all()
    return {
        "id": fam.id, "nombre": fam.nombre, "parent_id": fam.parent_id,
        "subfamilias": [{"id": x.id, "nombre": x.nombre, "color": x.color} for x in subs],
        "articulos": [_articulo_dto(a) for a in arts],
    }


@router.get("/api/articulo/por-codigo/{codigo}")
def articulo_por_codigo(codigo: str, s: Session = Depends(get_session)) -> dict:
    cb = s.execute(select(CodigoBarras).where(CodigoBarras.codigo == codigo)).scalars().first()
    if cb is None:
        raise HTTPException(404, "Codigo de barras no encontrado")
    return _articulo_dto(s.get(Articulo, cb.articulo_id))


@router.post("/api/calcular")
def calcular(req: CalcularReq, s: Session = Depends(get_session)) -> dict:
    lineas, totales = _resolver_items(req.items, s)
    return {
        "lineas": [
            {"articulo_id": a.id, "descripcion": a.nombre, "cantidad": str(cant),
             "pvp": str(pvp), "tipo_iva": str(ln.porcentaje), "total": str(ln.total),
             "requiere_cites": a.requiere_cites}
            for (a, pvp, cant, ln) in lineas
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
    s: Session = Depends(get_session),
    motor: FiscalEngine = Depends(get_motor),
) -> dict:
    if not req.items:
        raise HTTPException(400, "El ticket esta vacio")
    usuario = s.get(Usuario, req.usuario_id)  # 1a operacion -> abre BEGIN IMMEDIATE
    if usuario is None:
        raise HTTPException(401, "Usuario no valido")

    lineas, totales = _resolver_items(req.items, s)
    venta = Venta(estado="aparcada", usuario_id=usuario.id,
                  base_total=totales.base_total, cuota_total=totales.cuota_total,
                  total_con_iva=totales.total_con_iva)
    for (a, pvp, cant, ln) in lineas:
        venta.lineas.append(VentaLinea(
            articulo_id=a.id, descripcion=a.nombre, cantidad=cant, pvp_unitario=pvp,
            tipo_iva_porcentaje=ln.porcentaje, base_linea=ln.base,
            cuota_linea=ln.cuota, total_linea=ln.total))
    for p in req.pagos:
        venta.pagos.append(Pago(medio=p.medio, importe=Decimal(p.importe)))
    s.add(venta)
    registro = motor.emit(s, venta)

    total = venta.total_con_iva
    efectivo = sum((Decimal(p.importe) for p in req.pagos if p.medio == "efectivo"),
                   Decimal("0.00"))
    cambio = efectivo - total if efectivo > total else Decimal("0.00")
    datos = {
        "venta_id": venta.id,
        "num_serie": venta.num_serie_factura,
        "fecha": registro.fecha_expedicion,
        "total": str(total),
        "cambio": str(cambio),
        "qr_url": qr_mod.url_cotejo_registro(registro),
    }
    s.commit()

    _imprimir_ticket_seguro(datos["venta_id"])
    return datos


@router.post("/api/cajon")
def abrir_cajon_sin_venta(req: CajonReq, s: Session = Depends(get_session)) -> dict:
    # Toda apertura de cajon sin venta queda en el log de auditoria (invariante 4).
    with s.begin():
        s.add(LogAuditoria(
            fecha_hora_huso=ahora_huso(), usuario_id=req.usuario_id,
            accion="apertura_cajon_sin_venta", entidad="caja", origen="local"))
    try:
        from app.printing.ticket import abrir_cajon, crear_impresora

        abrir_cajon(crear_impresora())
    except Exception as exc:  # noqa: BLE001 - local-first
        _log.warning("No se pudo abrir el cajon: %s", exc)
    return {"ok": True}


@router.get("/api/venta/{venta_id}/qr.png")
def qr_venta(venta_id: int, s: Session = Depends(get_session)) -> Response:
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
        from app.core.db import SessionLocal
        from app.printing.ticket import crear_impresora, imprimir_ticket

        with SessionLocal() as s:
            venta = s.get(Venta, venta_id)
            registro = s.execute(
                select(RegistroFiscal).where(RegistroFiscal.venta_id == venta_id,
                                             RegistroFiscal.tipo_registro == "alta")
            ).scalars().first()
            if venta is None or registro is None:
                return
            _ = venta.lineas, registro.desglose
            imprimir_ticket(crear_impresora(), venta, registro)
    except Exception as exc:  # noqa: BLE001 - local-first: no romper la venta
        _log.warning("No se pudo imprimir el ticket de la venta %s: %s", venta_id, exc)
