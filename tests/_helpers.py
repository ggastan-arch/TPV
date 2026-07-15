"""Utilidades compartidas por los tests."""
from __future__ import annotations

from decimal import Decimal

from lxml import etree

from app.dominio.servicios.redondeo import Linea, agregar_totales, calcular_linea
from app.infraestructura.fiscal.remitente import NS_RESP
from app.infraestructura.fiscal.xml import NS as NS_SF
from app.infraestructura.persistencia.modelos import Venta, VentaLinea

_E_RESP = "{%s}" % NS_RESP
_E_SF = "{%s}" % NS_SF
_E_SOAP = "{http://schemas.xmlsoap.org/soap/envelope/}"


def respuesta_remision_xml(lineas, *, csv="CSV-OK", tiempo=60, estado="Correcto") -> bytes:
    """Construye una RespuestaRegFactuSistemaFacturacion de la AEAT (para tests).

    lineas: lista de tuplas (num_serie, estado_registro, codigo_error, descripcion) o,
    para simular el duplicado (codigo 3000), un 5º elemento opcional `duplicado`: un
    dict {"estado": "Correcta"|"AceptadaConErrores"|"Anulada", "id_peticion": ...,
    "codigo": ..., "descripcion": ...} que agrega el bloque RegistroDuplicado (con
    EstadoRegistroDuplicado en vocabulario femenino, distinto del EstadoRegistro de
    línea que usa formas masculinas).

    `lineas=[]` con `estado="Incorrecto"` simula el rechazo de cabecera (respuesta sin
    ningún RespuestaLinea): el XSD RespuestaBaseType no define un código de error a
    nivel de envío, por eso ese caso no necesita datos adicionales aquí."""
    env = etree.Element(_E_SOAP + "Envelope")
    body = etree.SubElement(env, _E_SOAP + "Body")
    resp = etree.SubElement(body, _E_RESP + "RespuestaRegFactuSistemaFacturacion")
    if csv is not None:
        etree.SubElement(resp, _E_RESP + "CSV").text = csv
    etree.SubElement(resp, _E_RESP + "TiempoEsperaEnvio").text = str(tiempo)
    etree.SubElement(resp, _E_RESP + "EstadoEnvio").text = estado
    for linea in lineas:
        num, estado_reg, codigo, desc, *resto = linea
        duplicado = resto[0] if resto else None
        ln = etree.SubElement(resp, _E_RESP + "RespuestaLinea")
        # IDFactura es un elemento LOCAL de RespuestaSuministro.xsd (NS_RESP); solo sus
        # hijos (IDFacturaExpedidaType) viven en SuministroInformacion.xsd (NS_SF). Esta
        # es la estructura real de la respuesta de la AEAT.
        idf = etree.SubElement(ln, _E_RESP + "IDFactura")
        etree.SubElement(idf, _E_SF + "IDEmisorFactura").text = "00000000T"
        etree.SubElement(idf, _E_SF + "NumSerieFactura").text = num
        etree.SubElement(idf, _E_SF + "FechaExpedicionFactura").text = "10-07-2026"
        etree.SubElement(ln, _E_RESP + "EstadoRegistro").text = estado_reg
        if codigo is not None:
            etree.SubElement(ln, _E_RESP + "CodigoErrorRegistro").text = str(codigo)
        if desc is not None:
            etree.SubElement(ln, _E_RESP + "DescripcionErrorRegistro").text = desc
        if duplicado is not None:
            # RegistroDuplicado es local de RespuestaSuministro.xsd (NS_RESP), pero es de
            # tipo RegistroDuplicadoType, definido en SuministroInformacion.xsd: todos sus
            # hijos viven en NS_SF.
            dup = etree.SubElement(ln, _E_RESP + "RegistroDuplicado")
            etree.SubElement(dup, _E_SF + "IdPeticionRegistroDuplicado").text = (
                duplicado.get("id_peticion", "PET-DUP-1")
            )
            etree.SubElement(dup, _E_SF + "EstadoRegistroDuplicado").text = duplicado["estado"]
            if duplicado.get("codigo") is not None:
                etree.SubElement(dup, _E_SF + "CodigoErrorRegistro").text = str(duplicado["codigo"])
            if duplicado.get("descripcion") is not None:
                etree.SubElement(dup, _E_SF + "DescripcionErrorRegistro").text = duplicado["descripcion"]
    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def construir_venta(usuario_id: int, lineas_spec: list[tuple[str, str, str, str]]) -> Venta:
    """Crea una venta aparcada con lineas calculadas.

    lineas_spec: lista de (descripcion, pvp_unitario, cantidad, porcentaje_iva).
    """
    venta = Venta(estado="aparcada", usuario_id=usuario_id)
    calculadas: list[Linea] = []
    for descripcion, pvp, cantidad, porcentaje in lineas_spec:
        ln = calcular_linea(Decimal(pvp), Decimal(cantidad), Decimal(porcentaje))
        venta.lineas.append(
            VentaLinea(
                descripcion=descripcion,
                cantidad=Decimal(cantidad),
                pvp_unitario=Decimal(pvp),
                tipo_iva_porcentaje=Decimal(porcentaje),
                base_linea=ln.base,
                cuota_linea=ln.cuota,
                total_linea=ln.total,
            )
        )
        calculadas.append(ln)
    totales = agregar_totales(calculadas)
    venta.base_total = totales.base_total
    venta.cuota_total = totales.cuota_total
    venta.total_con_iva = totales.total_con_iva
    return venta
