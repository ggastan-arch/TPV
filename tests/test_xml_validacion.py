"""El XML de RegistroAlta/RegistroAnulacion valida contra el XSD oficial de la AEAT."""
from __future__ import annotations

from decimal import Decimal

from _helpers import construir_venta
from app.infraestructura.fiscal import validacion
from app.infraestructura.fiscal.xml import (
    NS,
    Destinatario,
    a_bytes,
    registro_alta_xml,
    registro_anulacion_xml,
    sistema_desde_settings,
)
from app.infraestructura.persistencia.modelos import RegistroFacturaSustituida, RegistroFiscal
from app.infraestructura.persistencia.modelos.fiscal import RegistroFiscalDesglose

SISTEMA = sistema_desde_settings()
EMISOR = "AcuaTPV"


def _registro_f2_fijo() -> RegistroFiscal:
    """`RegistroFiscal` construido en memoria (sin BD) con TODOS los campos
    fijos/deterministicos -- fundamental para el golden pinned de abajo: si se
    generara via `motor.emit`, la fecha/hora y la huella cambiarian en cada
    ejecucion y el byte-a-byte nunca podria fijarse."""
    reg = RegistroFiscal(
        orden=1, tipo_registro="alta", venta_id=1,
        id_emisor="00000000T", num_serie_factura="T2026-000001",
        fecha_expedicion="18-07-2026", tipo_factura="F2",
        descripcion_operacion="Venta de mercaderia",
        cuota_total=Decimal("0.53"), importe_total=Decimal("3.03"),
        primer_registro=True, registro_anterior_id=None, huella_anterior=None,
        huella="A" * 64, tipo_huella="01",
        fecha_hora_huso_gen_registro="2026-07-18T10:00:00+02:00",
        estado_remision="no_remitido",
    )
    reg.desglose.append(RegistroFiscalDesglose(
        impuesto="01", clave_regimen="01", calificacion="S1",
        tipo_impositivo=Decimal("21.00"), base_imponible=Decimal("2.50"),
        cuota_repercutida=Decimal("0.53"),
    ))
    return reg


# Golden PINNED, capturado del serializador ACTUAL (revision Judgment Day: el
# test anterior comparaba una llamada por defecto contra una llamada explicita
# `destinatario=None` -- identicas por construccion, nunca podia fallar). Esta
# constante fija byte-a-byte el XML de una F2/T sin destinatario: cualquier
# reordenamiento de elementos, cambio de namespace o de indentacion futuro hara
# fallar este test.
_GOLDEN_XML_F2 = (
    b"<?xml version='1.0' encoding='UTF-8'?>\n"
    b'<sum1:RegistroAlta xmlns:sum1="https://www2.agenciatributaria.gob.es/static_files/'
    b'common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd">\n'
    b"  <sum1:IDVersion>1.0</sum1:IDVersion>\n"
    b"  <sum1:IDFactura>\n"
    b"    <sum1:IDEmisorFactura>00000000T</sum1:IDEmisorFactura>\n"
    b"    <sum1:NumSerieFactura>T2026-000001</sum1:NumSerieFactura>\n"
    b"    <sum1:FechaExpedicionFactura>18-07-2026</sum1:FechaExpedicionFactura>\n"
    b"  </sum1:IDFactura>\n"
    b"  <sum1:NombreRazonEmisor>AcuaTPV</sum1:NombreRazonEmisor>\n"
    b"  <sum1:TipoFactura>F2</sum1:TipoFactura>\n"
    b"  <sum1:DescripcionOperacion>Venta de mercaderia</sum1:DescripcionOperacion>\n"
    b"  <sum1:Desglose>\n"
    b"    <sum1:DetalleDesglose>\n"
    b"      <sum1:Impuesto>01</sum1:Impuesto>\n"
    b"      <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\n"
    b"      <sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\n"
    b"      <sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>\n"
    b"      <sum1:BaseImponibleOimporteNoSujeto>2.50</sum1:BaseImponibleOimporteNoSujeto>\n"
    b"      <sum1:CuotaRepercutida>0.53</sum1:CuotaRepercutida>\n"
    b"    </sum1:DetalleDesglose>\n"
    b"  </sum1:Desglose>\n"
    b"  <sum1:CuotaTotal>0.53</sum1:CuotaTotal>\n"
    b"  <sum1:ImporteTotal>3.03</sum1:ImporteTotal>\n"
    b"  <sum1:Encadenamiento>\n"
    b"    <sum1:PrimerRegistro>S</sum1:PrimerRegistro>\n"
    b"  </sum1:Encadenamiento>\n"
    b"  <sum1:SistemaInformatico>\n"
    b"    <sum1:NombreRazon>AcuaTPV Dev</sum1:NombreRazon>\n"
    b"    <sum1:NIF>00000000T</sum1:NIF>\n"
    b"    <sum1:NombreSistemaInformatico>TPV AcuaTPV</sum1:NombreSistemaInformatico>\n"
    b"    <sum1:IdSistemaInformatico>AT</sum1:IdSistemaInformatico>\n"
    b"    <sum1:Version>0.1.0</sum1:Version>\n"
    b"    <sum1:NumeroInstalacion>1</sum1:NumeroInstalacion>\n"
    b"    <sum1:TipoUsoPosibleSoloVerifactu>S</sum1:TipoUsoPosibleSoloVerifactu>\n"
    b"    <sum1:TipoUsoPosibleMultiOT>N</sum1:TipoUsoPosibleMultiOT>\n"
    b"    <sum1:IndicadorMultiplesOT>N</sum1:IndicadorMultiplesOT>\n"
    b"  </sum1:SistemaInformatico>\n"
    b"  <sum1:FechaHoraHusoGenRegistro>2026-07-18T10:00:00+02:00</sum1:FechaHoraHusoGenRegistro>\n"
    b"  <sum1:TipoHuella>01</sum1:TipoHuella>\n"
    b"  <sum1:Huella>" + b"A" * 64 + b"</sum1:Huella>\n"
    b"</sum1:RegistroAlta>\n"
)


def _emitir(crear_sesion, motor, usuario_id, lineas, **kw) -> int:
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, lineas)
        s.add(venta)
        reg = motor.emit(s, venta, **kw)
        return reg.id


def test_registro_alta_valida_contra_xsd(crear_sesion, motor, datos_base):
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"],
        [("Neon cardenal", "2.50", "2", "21"), ("Anubias", "6.90", "1", "10")],
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        xml = registro_alta_xml(reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None)
        assert reg.primer_registro is True
        assert validacion.errores(xml) == []


def test_segunda_alta_encadenada_valida_contra_xsd(crear_sesion, motor, datos_base):
    _emitir(crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
    reg2_id = _emitir(crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
    with crear_sesion() as s:
        reg2 = s.get(RegistroFiscal, reg2_id)
        anterior = s.get(RegistroFiscal, reg2.registro_anterior_id)
        xml = registro_alta_xml(reg2, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=anterior)
        assert reg2.primer_registro is False
        assert validacion.errores(xml) == []


def test_registro_anulacion_valida_contra_xsd(crear_sesion, motor, datos_base):
    reg_id = _emitir(crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
    with crear_sesion() as s, s.begin():
        anulacion = motor.cancel(s, s.get(RegistroFiscal, reg_id))
        anulacion_id = anulacion.id
    with crear_sesion() as s:
        anulacion = s.get(RegistroFiscal, anulacion_id)
        anterior = s.get(RegistroFiscal, anulacion.registro_anterior_id)
        xml = registro_anulacion_xml(anulacion, sistema=SISTEMA, anterior=anterior)
        assert validacion.errores(xml) == []


def test_alta_f3_con_facturas_sustituidas_valida_contra_xsd(crear_sesion, motor, datos_base):
    ejercicio = datos_base["ejercicio"]
    # F2 simplificada a sustituir.
    f2_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "2", "21")],
        serie="T", ejercicio=ejercicio, tipo_factura="F2",
    )
    # F3 en sustitucion, con su bloque FacturasSustituidas.
    with crear_sesion() as s, s.begin():
        f2reg = s.query(RegistroFiscal).filter_by(venta_id=f2_id).one()
        f3 = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "2", "21")])
        s.add(f3)
        reg_f3 = motor.emit(s, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
        s.add(RegistroFacturaSustituida(
            registro_fiscal_id=reg_f3.id,
            id_emisor=f2reg.id_emisor,
            num_serie_factura=f2reg.num_serie_factura,
            fecha_expedicion=f2reg.fecha_expedicion,
        ))
        reg_f3_id = reg_f3.id

    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_f3_id)
        anterior = s.get(RegistroFiscal, reg.registro_anterior_id)
        xml = registro_alta_xml(reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=anterior)
        assert reg.tipo_factura == "F3"
        assert len(reg.facturas_sustituidas) == 1
        assert validacion.errores(xml) == []


# --- Fase 3 (B): FacturaSimplificadaArt7273 (simplificada cualificada) --------


def test_simplificada_normal_xml_byte_identico(crear_sesion, motor, datos_base):
    """Guarda de regresion fiscal: sin el flag (o `cualificada=False` explicito),
    el XML es byte-idéntico al de antes de este cambio — el elemento nuevo
    (`minOccurs=0`) se OMITE por completo."""
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon cardenal", "2.50", "2", "21")],
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        xml_llamada_previa = registro_alta_xml(reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None)
        xml_flag_explicito = registro_alta_xml(
            reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None, cualificada=False)
        assert a_bytes(xml_llamada_previa) == a_bytes(xml_flag_explicito)
        assert b"FacturaSimplificadaArt7273" not in a_bytes(xml_llamada_previa)
        assert validacion.errores(xml_llamada_previa) == []


def test_cualificada_emite_flag_s_valida_xsd(crear_sesion, motor, datos_base):
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon cardenal", "2.50", "2", "21")],
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        xml = registro_alta_xml(
            reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None, cualificada=True)
        cuerpo = a_bytes(xml)
        assert b"<sum1:FacturaSimplificadaArt7273>S</sum1:FacturaSimplificadaArt7273>" in cuerpo
        assert validacion.errores(xml) == []
        # Posicion exacta del XSD (SuministroInformacion.xsd.xml:144): entre
        # DescripcionOperacion y Desglose (los elementos opcionales intermedios
        # -- FacturaSinIdentifDestinatarioArt61d, Macrodato,
        # EmitidaPorTerceroODestinatario, Tercero, Destinatarios, Cupon -- no se
        # emiten, asi que la validez de secuencia del XSD solo exige este orden).
        assert cuerpo.index(b"</sum1:DescripcionOperacion>") < cuerpo.index(b"<sum1:FacturaSimplificadaArt7273>")
        assert cuerpo.index(b"</sum1:FacturaSimplificadaArt7273>") < cuerpo.index(b"<sum1:Desglose>")


# --- Fase 3: bloque Destinatarios/IDDestinatario (F1/F3) ----------------------


def test_xml_simplificada_t_byte_identica(crear_sesion, motor, datos_base):
    """Guarda de regresion fiscal (golden PINNED, revision Judgment Day): una F2/T
    sin destinatario produce byte-a-byte el MISMO XML que el capturado ANTES de
    este cambio -- el `RegistroFiscal` es fijo/deterministico (sin `motor.emit`),
    por lo que este assert SI detecta cualquier reordenamiento de elementos,
    cambio de namespace o de indentacion (el test anterior comparaba
    `destinatario` por defecto contra `destinatario=None` explicito, identicos
    por construccion: nunca podia fallar)."""
    reg = _registro_f2_fijo()
    xml = registro_alta_xml(reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None)
    cuerpo = a_bytes(xml)
    assert cuerpo == _GOLDEN_XML_F2
    assert b"Destinatarios" not in cuerpo
    assert validacion.errores(xml) == []


def test_registro_alta_xml_omite_destinatario_con_nif_vacio(crear_sesion, motor, datos_base):
    """Defensa en profundidad (item 6, revision Judgment Day): un `Destinatario`
    con NIF vacio/None NUNCA produce un `<NIF/>` vacio (invalido contra el XSD) --
    se omite el bloque ENTERO, igual que si `destinatario=None`. La defensa
    PRIMARIA es la guarda en `remitir_lote.py` (nunca se construye un
    `Destinatario` con NIF vacio en el camino real); esto es un segundo cinturon
    de seguridad en el propio serializador."""
    ejercicio = datos_base["ejercicio"]
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "2", "21")],
        serie="F", ejercicio=ejercicio, tipo_factura="F3",
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        for nif_vacio in (None, ""):
            destinatario = Destinatario(nombre="Acuario S.L.", nif=nif_vacio)
            xml = registro_alta_xml(
                reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None,
                destinatario=destinatario)
            cuerpo = a_bytes(xml)
            assert b"Destinatarios" not in cuerpo
            assert b"<sum1:NIF/>" not in cuerpo
            assert b"<sum1:NIF></sum1:NIF>" not in cuerpo
            assert validacion.errores(xml) == []


def test_registro_alta_xml_omite_destinatario_con_nombre_vacio(crear_sesion, motor, datos_base):
    """Guarda simetrica (item 5, revision Judgment Day round 2): un `Destinatario`
    con `nombre` vacio/None (NIF presente) TAMPOCO produce un `<NombreRazon/>` vacio
    (invalido contra el XSD, `NombreRazon` es obligatorio dentro de IDDestinatario
    igual que `NIF`) -- se omite el bloque ENTERO, igual que con NIF vacio."""
    ejercicio = datos_base["ejercicio"]
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon cardenal", "2.50", "2", "21")],
        serie="F", ejercicio=ejercicio, tipo_factura="F3",
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        for nombre_vacio in (None, ""):
            destinatario = Destinatario(nombre=nombre_vacio, nif="A58818501")
            xml = registro_alta_xml(
                reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None,
                destinatario=destinatario)
            cuerpo = a_bytes(xml)
            assert b"Destinatarios" not in cuerpo
            assert b"<sum1:NombreRazon/>" not in cuerpo
            assert b"<sum1:NombreRazon></sum1:NombreRazon>" not in cuerpo
            assert validacion.errores(xml) == []


def test_xml_destinatario_con_caracteres_especiales_escapa_correctamente(
    crear_sesion, motor, datos_base
):
    """Item 8 (revision Judgment Day): un nombre/razon social con caracteres
    especiales de XML (`&`, `<`, `>`, `"`) se escapa correctamente en el XML
    serializado y el resultado sigue siendo valido contra el XSD -- lxml escapa
    automaticamente el contenido de texto (`.text = ...`), pero se confirma
    explicitamente porque el destinatario es texto libre capturado por un admin
    (nombre de cliente), no una constante interna."""
    ejercicio = datos_base["ejercicio"]
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "2", "21")],
        serie="F", ejercicio=ejercicio, tipo_factura="F3",
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        destinatario = Destinatario(nombre='Peces & Plantas "El Acuario" <S.L.>', nif="A58818501")
        xml = registro_alta_xml(
            reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None, destinatario=destinatario)
        cuerpo = a_bytes(xml)
        # El nombre crudo (con &/</>/") NUNCA aparece literal en el XML serializado.
        assert destinatario.nombre.encode("utf-8") not in cuerpo
        assert b"&amp;" in cuerpo
        assert b"&lt;" in cuerpo
        assert b"&gt;" in cuerpo
        # lxml solo re-parsea limpio si el escapado es correcto: confirma que
        # `NombreRazon` recupera el texto ORIGINAL exacto tras el roundtrip.
        nombre_recuperado = xml.find(".//{%s}NombreRazon" % NS).text
        assert nombre_recuperado == destinatario.nombre
        assert validacion.errores(xml) == []


def test_xml_f3_con_destinatarios_valida_xsd(crear_sesion, motor, datos_base):
    ejercicio = datos_base["ejercicio"]
    reg_id = _emitir(
        crear_sesion, motor, datos_base["usuario_id"], [("Neon", "2.50", "2", "21")],
        serie="F", ejercicio=ejercicio, tipo_factura="F3",
    )
    with crear_sesion() as s:
        reg = s.get(RegistroFiscal, reg_id)
        destinatario = Destinatario(nombre="Acuario S.L.", nif="A58818501")
        xml = registro_alta_xml(
            reg, nombre_emisor=EMISOR, sistema=SISTEMA, anterior=None, destinatario=destinatario)
        cuerpo = a_bytes(xml)
        assert b"<sum1:Destinatarios>" in cuerpo
        assert b"<sum1:IDDestinatario>" in cuerpo
        assert b"<sum1:NombreRazon>Acuario S.L.</sum1:NombreRazon>" in cuerpo
        assert b"<sum1:NIF>A58818501</sum1:NIF>" in cuerpo
        # Posicion XSD exacta (SuministroInformacion.xsd.xml:153): entre
        # DescripcionOperacion (y el bloque opcional cualificada, si presente) y
        # Desglose.
        assert cuerpo.index(b"</sum1:DescripcionOperacion>") < cuerpo.index(b"<sum1:Destinatarios>")
        assert cuerpo.index(b"</sum1:Destinatarios>") < cuerpo.index(b"<sum1:Desglose>")
        assert validacion.errores(xml) == []
