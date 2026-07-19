"""Serializacion de RegistroAlta / RegistroAnulacion a XML VERI*FACTU.

Estructura, nombres, namespace y orden de elementos tomados del XSD oficial
schemas/SuministroInformacion.xsd (validado en tests/test_xml_validacion.py).
No se emite ds:Signature: en VERI*FACTU los registros no se firman.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from app.infraestructura.config import settings
from app.dominio.servicios.huella import formato_importe
from app.infraestructura.persistencia.modelos.fiscal import RegistroFiscal

# Namespace de destino del XSD SuministroInformacion (registros de facturacion).
NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd"
)
# Namespace del sobre de remision (SuministroLR).
NS_LR = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd"
)
_NSMAP = {"sum1": NS}
_NSMAP_LR = {"sfLR": NS_LR, "sum1": NS}


@dataclass
class SistemaInformatico:
    """Bloque SistemaInformatico: identifica al productor del software."""

    nombre_razon: str
    nif: str
    nombre_sistema: str
    id_sistema: str
    version: str
    numero_instalacion: str
    solo_verifactu: str = "S"
    multi_ot: str = "N"
    indicador_multiples_ot: str = "N"


def sistema_desde_settings() -> SistemaInformatico:
    return SistemaInformatico(
        nombre_razon=settings.nombre_productor,
        nif=settings.nif_productor,
        nombre_sistema=settings.nombre_sistema,
        id_sistema=settings.id_sistema,
        version=settings.version_sistema,
        numero_instalacion=settings.numero_instalacion,
    )


def _q(tag: str) -> etree.QName:
    return etree.QName(NS, tag)


def _q_lr(tag: str) -> etree.QName:
    return etree.QName(NS_LR, tag)


def _sub(parent, tag: str, text=None):
    el = etree.SubElement(parent, _q(tag))
    if text is not None:
        el.text = str(text)
    return el


def _encadenamiento(parent, reg: RegistroFiscal, anterior: RegistroFiscal | None) -> None:
    enc = _sub(parent, "Encadenamiento")
    if reg.primer_registro:
        _sub(enc, "PrimerRegistro", "S")
    else:
        if anterior is None:
            raise ValueError("Falta el registro anterior para el encadenamiento")
        ra = _sub(enc, "RegistroAnterior")
        _sub(ra, "IDEmisorFactura", anterior.id_emisor)
        _sub(ra, "NumSerieFactura", anterior.num_serie_factura)
        _sub(ra, "FechaExpedicionFactura", anterior.fecha_expedicion)
        _sub(ra, "Huella", anterior.huella)


def _sistema_informatico(parent, sistema: SistemaInformatico) -> None:
    si = _sub(parent, "SistemaInformatico")
    _sub(si, "NombreRazon", sistema.nombre_razon)
    _sub(si, "NIF", sistema.nif)
    _sub(si, "NombreSistemaInformatico", sistema.nombre_sistema)
    _sub(si, "IdSistemaInformatico", sistema.id_sistema)
    _sub(si, "Version", sistema.version)
    _sub(si, "NumeroInstalacion", sistema.numero_instalacion)
    _sub(si, "TipoUsoPosibleSoloVerifactu", sistema.solo_verifactu)
    _sub(si, "TipoUsoPosibleMultiOT", sistema.multi_ot)
    _sub(si, "IndicadorMultiplesOT", sistema.indicador_multiples_ot)


@dataclass
class Destinatario:
    """Bloque Destinatarios/IDDestinatario (F1/F3): NIF y nombre/razon social del
    cliente. NUNCA participa en el computo de la huella -- `huella_alta` (ver
    app.dominio.servicios.huella) no declara este parametro; la huella ya queda
    fijada por `motor.emit` ANTES de que exista ningun destinatario resuelto
    (eso solo ocurre aqui, en la SERIALIZACION, ver app.aplicacion.remitir_lote).

    `nif: str | None` / `nombre: str | None` (honesto, revision Judgment Day): un
    NIF o un NombreRazon vacio/None NUNCA producen un `<NIF/>`/`<NombreRazon/>`
    vacio en el XML (ambos obligatorios en Destinatarios/IDDestinatario, invalido
    contra el XSD, bloquearia la cola FIFO de remision si la AEAT lo rechaza) --
    `registro_alta_xml` omite el bloque ENTERO si `nif` o `nombre` son falsy,
    igual que si `destinatario` fuera `None`. La defensa PRIMARIA es la guarda de
    `remitir_lote.py` (nunca construye un `Destinatario` con NIF o nombre vacio
    en el camino real); esto es defensa en profundidad en el propio
    serializador."""

    nombre: str | None
    nif: str | None


def registro_alta_xml(
    reg: RegistroFiscal,
    *,
    nombre_emisor: str,
    sistema: SistemaInformatico,
    anterior: RegistroFiscal | None = None,
    cualificada: bool = False,
    destinatario: Destinatario | None = None,
) -> etree._Element:
    root = etree.Element(_q("RegistroAlta"), nsmap=_NSMAP)
    _sub(root, "IDVersion", "1.0")

    idf = _sub(root, "IDFactura")
    _sub(idf, "IDEmisorFactura", reg.id_emisor)
    _sub(idf, "NumSerieFactura", reg.num_serie_factura)
    _sub(idf, "FechaExpedicionFactura", reg.fecha_expedicion)

    _sub(root, "NombreRazonEmisor", nombre_emisor)
    _sub(root, "TipoFactura", reg.tipo_factura)

    # F3: facturas simplificadas sustituidas.
    if reg.facturas_sustituidas:
        fs = _sub(root, "FacturasSustituidas")
        for f in reg.facturas_sustituidas:
            idfs = _sub(fs, "IDFacturaSustituida")
            _sub(idfs, "IDEmisorFactura", f.id_emisor)
            _sub(idfs, "NumSerieFactura", f.num_serie_factura)
            _sub(idfs, "FechaExpedicionFactura", f.fecha_expedicion)

    _sub(root, "DescripcionOperacion", reg.descripcion_operacion or "")

    # Simplificada cualificada (art. 7.2/7.3 ROF): minOccurs=0, se OMITE cuando
    # False (la simplificada normal queda byte-idéntica). Posicion XSD exacta
    # (SuministroInformacion.xsd.xml:144): entre DescripcionOperacion y Desglose
    # (los elementos opcionales intermedios del XSD no se emiten en este SIF).
    if cualificada:
        _sub(root, "FacturaSimplificadaArt7273", "S")

    # Destinatarios/IDDestinatario (F1/F3): minOccurs=0, se OMITE cuando None (T/F2
    # quedan byte-identicas). Posicion XSD exacta (SuministroInformacion.xsd.xml:153):
    # entre el bloque cualificada y Desglose (los elementos opcionales intermedios
    # del XSD -- FacturaSinIdentifDestinatarioArt61d, Macrodato,
    # EmitidaPorTerceroODestinatario, Tercero -- no se emiten en este SIF).
    #
    # Guarda (defensa en profundidad, revision Judgment Day): un NIF o un nombre
    # falsy (None/"") NUNCA emiten un `<NIF/>`/`<NombreRazon/>` vacio (invalido
    # contra el XSD, ambos obligatorios) -- se omite el bloque ENTERO, igual que
    # `destinatario=None`. La defensa PRIMARIA vive en `remitir_lote.py` (nunca
    # construye un `Destinatario` sin NIF o sin nombre en el camino real).
    if destinatario is not None and destinatario.nif and destinatario.nombre:
        destinatarios = _sub(root, "Destinatarios")
        idd = _sub(destinatarios, "IDDestinatario")
        _sub(idd, "NombreRazon", destinatario.nombre)
        _sub(idd, "NIF", destinatario.nif)

    desglose = _sub(root, "Desglose")
    for d in reg.desglose:
        det = _sub(desglose, "DetalleDesglose")
        _sub(det, "Impuesto", d.impuesto)
        _sub(det, "ClaveRegimen", d.clave_regimen)
        _sub(det, "CalificacionOperacion", d.calificacion)
        _sub(det, "TipoImpositivo", formato_importe(d.tipo_impositivo))
        _sub(det, "BaseImponibleOimporteNoSujeto", formato_importe(d.base_imponible))
        _sub(det, "CuotaRepercutida", formato_importe(d.cuota_repercutida))

    _sub(root, "CuotaTotal", formato_importe(reg.cuota_total))
    _sub(root, "ImporteTotal", formato_importe(reg.importe_total))

    _encadenamiento(root, reg, anterior)
    _sistema_informatico(root, sistema)
    _sub(root, "FechaHoraHusoGenRegistro", reg.fecha_hora_huso_gen_registro)
    _sub(root, "TipoHuella", reg.tipo_huella)
    _sub(root, "Huella", reg.huella)
    return root


def registro_anulacion_xml(
    reg: RegistroFiscal,
    *,
    sistema: SistemaInformatico,
    anterior: RegistroFiscal | None = None,
) -> etree._Element:
    root = etree.Element(_q("RegistroAnulacion"), nsmap=_NSMAP)
    _sub(root, "IDVersion", "1.0")

    idf = _sub(root, "IDFactura")
    _sub(idf, "IDEmisorFacturaAnulada", reg.id_emisor)
    _sub(idf, "NumSerieFacturaAnulada", reg.num_serie_factura)
    _sub(idf, "FechaExpedicionFacturaAnulada", reg.fecha_expedicion)

    _encadenamiento(root, reg, anterior)
    _sistema_informatico(root, sistema)
    _sub(root, "FechaHoraHusoGenRegistro", reg.fecha_hora_huso_gen_registro)
    _sub(root, "TipoHuella", reg.tipo_huella)
    _sub(root, "Huella", reg.huella)
    return root


@dataclass
class Cabecera:
    """Cabecera del sobre de remision (ObligadoEmision + RemisionVoluntaria)."""

    nombre_obligado: str
    nif_obligado: str
    incidencia: bool = False  # RemisionVoluntaria/Incidencia = S si hubo incidencia previa


def envelope_remision(
    registros_xml: list[etree._Element], *, cabecera: Cabecera
) -> etree._Element:
    """Sobre RegFactuSistemaFacturacion: Cabecera + 1..1000 RegistroFactura.

    Cada elemento de `registros_xml` es un RegistroAlta/RegistroAnulacion ya serializado.
    """
    if not 1 <= len(registros_xml) <= 1000:
        raise ValueError("El sobre agrupa entre 1 y 1000 registros")

    root = etree.Element(_q_lr("RegFactuSistemaFacturacion"), nsmap=_NSMAP_LR)

    cab = etree.SubElement(root, _q_lr("Cabecera"))
    obligado = _sub(cab, "ObligadoEmision")  # elementos del ns SuministroInformacion
    _sub(obligado, "NombreRazon", cabecera.nombre_obligado)
    _sub(obligado, "NIF", cabecera.nif_obligado)
    remision = _sub(cab, "RemisionVoluntaria")
    _sub(remision, "Incidencia", "S" if cabecera.incidencia else "N")

    for registro_xml in registros_xml:
        rf = etree.SubElement(root, _q_lr("RegistroFactura"))
        rf.append(registro_xml)

    return root


def a_bytes(elemento: etree._Element) -> bytes:
    return etree.tostring(elemento, xml_declaration=True, encoding="UTF-8", pretty_print=True)
