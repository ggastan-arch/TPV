"""Validaciones de NEGOCIO previas a la remision (docs Validaciones_Errores_Veri-Factu.pdf).

Son las que la AEAT aplica ademas de las estructurales (XSD) y sintacticas. Ejecutar
ANTES de encolar para no remitir registros que serian rechazados. Alcance: la operativa
de esta tienda (F2 simplificadas y F3, regimen general 01, IVA, calificacion S1, sin
recargo de equivalencia repercutido).

Cada hallazgo se clasifica en:
- 'rechazo' (error no admisible): la AEAT rechazaria el registro.
- 'aviso'   (error admisible): la AEAT lo acepta "con errores" pero debe subsanarse.

Los codigos numericos oficiales no estan en el PDF (van en errores.properties de sede y
llegan en la respuesta de la AEAT); aqui se usan codigos propios + la seccion del doc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from app.dominio.servicios.validadores import validar_documento

if TYPE_CHECKING:  # evitar dependencia en tiempo de ejecucion con el modulo XML (lxml)
    from app.infraestructura.fiscal.xml import SistemaInformatico


# Tipos impositivos de IVA admitidos para CalificacionOperacion S1 (doc 15.1).
TIPOS_IVA_PERMITIDOS = {
    Decimal("0"), Decimal("2"), Decimal("4"), Decimal("5"),
    Decimal("7.5"), Decimal("10"), Decimal("21"),
}
FECHA_MINIMA = date(2024, 10, 28)  # entrada en vigor de la Orden (doc 3.1.3.1)
LIMITE_SIMPLIFICADA = Decimal("3000")  # doc 15.8
MARGEN = Decimal("10.00")  # margen admitido en los cuadres (doc 16, 17, 15.7)
_NUMSERIE_PROHIBIDOS = set('"\'<>=')  # ASCII 34,39,60,62,61 (doc 3.1.3.1)
_RE_HUELLA = re.compile(r"^[0-9A-F]{64}$")
_RE_ID_SISTEMA = re.compile(r"^[A-Z0-9]{2}$")  # 2 posiciones, mayus (sin Ñ) o digito
_CON_DESTINATARIO = {"F1", "F3", "R1", "R2", "R3", "R4"}
_SIN_DESTINATARIO = {"F2", "R5"}
# Alias PUBLICO (sin guion bajo) para reutilizacion desde otras capas -- fuente
# unica de verdad de "que tipos de factura llevan destinatario" (revision Judgment
# Day, item 7): `app.aplicacion.remitir_lote` deriva su propio conjunto de este
# mismo objeto para no divergir silenciosamente si este conjunto cambia aqui.
TIPOS_CON_DESTINATARIO = _CON_DESTINATARIO


@dataclass(frozen=True)
class Incidencia:
    codigo: str
    mensaje: str
    nivel: str  # 'rechazo' | 'aviso'


class _Sistema(Protocol):
    id_sistema: str
    nombre_sistema: str
    solo_verifactu: str
    multi_ot: str


def hay_rechazos(incidencias: list[Incidencia]) -> bool:
    return any(i.nivel == "rechazo" for i in incidencias)


def _fecha(valor: str) -> date:
    return datetime.strptime(valor, "%d-%m-%Y").date()


def validar_sistema_informatico(sistema: _Sistema) -> list[Incidencia]:
    inc: list[Incidencia] = []
    if not _RE_ID_SISTEMA.match(sistema.id_sistema or ""):
        inc.append(Incidencia("IDSISTEMA_FORMATO",
                              "IdSistemaInformatico debe ser 2 caracteres [A-Z0-9] (3.1.5)",
                              "rechazo"))
    if not (sistema.nombre_sistema or "").strip():
        inc.append(Incidencia("NOMBRE_SISTEMA_VACIO", "NombreSistemaInformatico obligatorio", "rechazo"))
    if not (sistema.solo_verifactu or "").strip():
        inc.append(Incidencia("SOLO_VERIFACTU_VACIO", "TipoUsoPosibleSoloVerifactu obligatorio", "rechazo"))
    if not (sistema.multi_ot or "").strip():
        inc.append(Incidencia("MULTI_OT_VACIO", "TipoUsoPosibleMultiOT obligatorio", "rechazo"))
    return inc


def _validar_comunes(reg, *, nif_obligado: str, ahora: datetime) -> list[Incidencia]:
    inc: list[Incidencia] = []

    if not validar_documento(reg.id_emisor):
        inc.append(Incidencia("NIF_EMISOR_INVALIDO", "NIF del emisor no valido", "rechazo"))
    if reg.id_emisor != nif_obligado:
        inc.append(Incidencia("NIF_EMISOR_DISTINTO",
                              "IDEmisorFactura debe coincidir con ObligadoEmision (3.1.3.1)",
                              "rechazo"))

    if any(c in _NUMSERIE_PROHIBIDOS or not (32 <= ord(c) <= 126) for c in reg.num_serie_factura):
        inc.append(Incidencia("NUMSERIE_CARACTERES",
                              "NumSerieFactura con caracteres no permitidos (3.1.3.1)", "rechazo"))

    fecha = _fecha(reg.fecha_expedicion)
    if fecha > ahora.date():
        inc.append(Incidencia("FECHA_FUTURA", "FechaExpedicionFactura posterior a hoy", "rechazo"))
    if fecha < FECHA_MINIMA:
        inc.append(Incidencia("FECHA_ANTERIOR_VIGENCIA",
                              "FechaExpedicionFactura anterior al 28-10-2024", "rechazo"))

    if not _RE_HUELLA.match(reg.huella or ""):
        inc.append(Incidencia("HUELLA_FORMATO", "Huella no es SHA-256 hex de 64 mayusculas", "aviso"))
    if reg.huella_anterior and not _RE_HUELLA.match(reg.huella_anterior):
        inc.append(Incidencia("HUELLA_ANTERIOR_FORMATO", "Huella anterior con formato invalido", "aviso"))
    if reg.primer_registro and reg.orden != 1:
        inc.append(Incidencia("PRIMER_REGISTRO", "PrimerRegistro=S con registros previos", "aviso"))
    if datetime.fromisoformat(reg.fecha_hora_huso_gen_registro) > ahora:
        inc.append(Incidencia("FECHAHORA_FUTURA", "FechaHoraHusoGenRegistro en el futuro", "aviso"))
    return inc


def validar_alta(
    reg,
    *,
    nif_obligado: str,
    sistema: _Sistema,
    ahora: datetime | None = None,
    tiene_destinatario: bool = False,
    cualificada_incompleta: bool = False,
) -> list[Incidencia]:
    ahora = ahora or datetime.now().astimezone()
    inc = _validar_comunes(reg, nif_obligado=nif_obligado, ahora=ahora)

    if reg.facturas_sustituidas and reg.tipo_factura != "F3":
        inc.append(Incidencia("FACTURAS_SUSTITUIDAS_SOLO_F3",
                              "FacturasSustituidas solo en F3 (3.1.3.5)", "rechazo"))
    if reg.tipo_factura in _SIN_DESTINATARIO and tiene_destinatario:
        inc.append(Incidencia("DESTINATARIO_NO_PERMITIDO",
                              "F2/R5 no puede llevar destinatario (3.1.3.13)", "rechazo"))
    if reg.tipo_factura in _CON_DESTINATARIO and not tiene_destinatario:
        inc.append(Incidencia("FALTA_DESTINATARIO",
                              "F1/F3/R1-R4 requieren destinatario (3.1.3.13)", "rechazo"))
    # Simplificada cualificada (art. 7.2/7.3 ROF): el cliente asignado debe tener
    # NIF y domicilio. La precondicion que SI se ejecuta en tiempo real vive en
    # EmitirVenta._exigir_datos_cualificada (unico sitio con acceso a la entidad
    # Cliente — ver design.md D5). Este kwarg (`cualificada_incompleta`) NO esta
    # wireado desde NullEngine.emit ni desde RemitirLote hoy: solo lo ejercen
    # tests/test_validaciones_negocio.py. Es una regla a nivel de test / pensada
    # para un futuro VerifactuEngine que valide antes de remitir; corregido en
    # revision Judgment Day W-1 (el comentario anterior sobreestimaba esto como
    # "defensa en profundidad" activa). NO wirear validar_alta al camino de
    # emision/remision desde aqui sin evaluar el riesgo fiscal.
    if cualificada_incompleta:
        inc.append(Incidencia("CUALIFICADA_SIN_NIF_DOMICILIO",
                              "Simplificada cualificada sin NIF/domicilio del cliente (art. 7.2/7.3 ROF)",
                              "rechazo"))

    suma_cuota = Decimal("0.00")
    suma_base_cuota = Decimal("0.00")
    for d in reg.desglose:
        tipo = Decimal(d.tipo_impositivo)
        base = Decimal(d.base_imponible)
        cuota = Decimal(d.cuota_repercutida)
        if tipo not in TIPOS_IVA_PERMITIDOS:
            inc.append(Incidencia("TIPO_IMPOSITIVO_NO_PERMITIDO",
                                  f"TipoImpositivo {tipo} no admitido para IVA/S1 (15.1)", "rechazo"))
        if base and cuota and (base < 0) != (cuota < 0):
            inc.append(Incidencia("SIGNO_BASE_CUOTA",
                                  "Base y cuota deben tener el mismo signo (15.7)", "rechazo"))
        if abs(cuota - base * tipo / Decimal(100)) > MARGEN:
            inc.append(Incidencia("CUOTA_LINEA",
                                  "CuotaRepercutida fuera del margen respecto a base*tipo (15.7)", "aviso"))
        suma_cuota += cuota
        suma_base_cuota += base + cuota

    if abs(suma_cuota - Decimal(reg.cuota_total)) > MARGEN:
        inc.append(Incidencia("CUOTA_TOTAL", "CuotaTotal no cuadra con el desglose (16)", "aviso"))
    if abs(suma_base_cuota - Decimal(reg.importe_total)) > MARGEN:
        inc.append(Incidencia("IMPORTE_TOTAL", "ImporteTotal no cuadra con el desglose (17)", "aviso"))
    if reg.tipo_factura == "F2" and suma_base_cuota > LIMITE_SIMPLIFICADA + MARGEN:
        inc.append(Incidencia("F2_LIMITE_3000",
                              "Simplificada > 3.000 EUR: debe emitirse factura completa (15.8)", "rechazo"))

    inc += validar_sistema_informatico(sistema)
    return inc


def validar_anulacion(
    reg, *, nif_obligado: str, sistema: _Sistema, ahora: datetime | None = None
) -> list[Incidencia]:
    ahora = ahora or datetime.now().astimezone()
    inc = _validar_comunes(reg, nif_obligado=nif_obligado, ahora=ahora)
    inc += validar_sistema_informatico(sistema)
    return inc


_KWARGS_SOLO_ALTA = {"tiene_destinatario", "cualificada_incompleta"}


def validar_registro(reg, **kwargs) -> list[Incidencia]:
    """Despacha segun el tipo de registro."""
    if reg.tipo_registro == "anulacion":
        return validar_anulacion(
            reg, **{k: v for k, v in kwargs.items() if k not in _KWARGS_SOLO_ALTA})
    return validar_alta(reg, **kwargs)
