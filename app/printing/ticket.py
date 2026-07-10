"""Impresion del ticket (factura simplificada) en impresora termica ESC/POS 80 mm.

Contenido segun art. 7 ROF + representacion grafica de la Orden (arts. 20-21):
QR tributario al principio, leyenda VERI*FACTU, y el contenido de la factura.

La impresora se INYECTA (escpos.printer.*), de modo que en tests se usa `Dummy`, que
captura los bytes ESC/POS sin hardware. El QR se imprime con el comando NATIVO de la
impresora, nivel de correccion M (art. 21).
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from escpos.constants import QR_ECLEVEL_M

from app.core.config import settings
from app.fiscal import qr as qr_mod

if TYPE_CHECKING:
    from app.models.fiscal import RegistroFiscal
    from app.models.venta import Venta


def _eur(valor) -> str:
    return f"{Decimal(valor):.2f}".replace(".", ",")


def _cant(valor) -> str:
    d = Decimal(valor)
    entero = d.to_integral_value()
    return str(int(entero)) if d == entero else f"{d.normalize():f}".replace(".", ",")


def _tipo(valor) -> str:
    d = Decimal(valor).normalize()
    return f"{d:f}".replace(".", ",")


def _fila(izq: str, der: str, ancho: int) -> str:
    espacio = ancho - len(der)
    izq = izq[: max(0, espacio - 1)]
    return f"{izq:<{espacio}}{der}"


def imprimir_ticket(
    printer,
    venta: "Venta",
    registro: "RegistroFiscal",
    *,
    ancho: int | None = None,
    nombre_emisor: str | None = None,
    nif_emisor: str | None = None,
    cortar: bool = True,
) -> None:
    ancho = ancho or settings.ticket_ancho
    nombre_emisor = nombre_emisor or settings.nombre_emisor
    nif_emisor = nif_emisor or settings.nif_emisor
    sep = "-" * ancho

    # --- QR tributario al principio de la factura (Orden 20-21) ---
    printer.set(align="center")
    printer.text("QR tributario:\n")
    url = qr_mod.url_cotejo_registro(registro)
    # El QR nativo se centra por la alineacion activa (center=True no esta soportado).
    printer.qr(url, ec=QR_ECLEVEL_M, size=6, native=True)
    printer.text(qr_mod.LEYENDA_CORTA + "\n")

    # --- Emisor ---
    printer.text(sep + "\n")
    printer.set(align="center", bold=True)
    printer.text(nombre_emisor + "\n")
    printer.set(align="center", bold=False)
    printer.text(f"NIF: {nif_emisor}\n")

    # --- Identificacion de la factura ---
    printer.set(align="left")
    printer.text(sep + "\n")
    printer.text("Factura simplificada\n")
    printer.text(_fila(registro.num_serie_factura, registro.fecha_expedicion, ancho) + "\n")

    # --- Lineas ---
    printer.text(sep + "\n")
    for linea in venta.lineas:
        izq = f"{_cant(linea.cantidad)}x {linea.descripcion}"
        printer.text(_fila(izq, _eur(linea.total_linea), ancho) + "\n")

    # --- Desglose de IVA (incluido en el PVP) ---
    printer.text(sep + "\n")
    for d in registro.desglose:
        etiqueta = f"IVA {_tipo(d.tipo_impositivo)}%  Base {_eur(d.base_imponible)}"
        printer.text(_fila(etiqueta, f"Cuota {_eur(d.cuota_repercutida)}", ancho) + "\n")

    # --- Total ---
    printer.text(sep + "\n")
    printer.set(align="left", bold=True, width=2, height=2)
    printer.text(_fila("TOTAL", f"{_eur(registro.importe_total)} EUR", ancho // 2) + "\n")
    printer.set(align="left", bold=False, width=1, height=1)

    printer.text(sep + "\n")
    printer.set(align="center")
    printer.text("Gracias por su compra\n")

    if cortar:
        printer.cut()


def abrir_cajon(printer, pin: int = 2) -> None:
    """Pulso de apertura del cajon portamonedas (RJ11 de la impresora), pin 2 o 5.
    Registrar la apertura sin venta en el log de auditoria es responsabilidad del que llama."""
    printer.cashdraw(pin)


def crear_impresora():
    """Impresora segun configuracion. Por defecto Dummy (sin hardware)."""
    from escpos import printer as esc

    if settings.impresora_tipo == "network" and settings.impresora_host:
        return esc.Network(settings.impresora_host, settings.impresora_puerto)
    return esc.Dummy()
