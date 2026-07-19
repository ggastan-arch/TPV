"""Caso de uso: convertir 1..N facturas simplificadas (serie T, cobradas) en
una unica factura completa F3 en sustitucion.

Cambio fiscal-CRITICO pero ADITIVO (ver design.md): no toca huella, cadena,
numeracion, redondeo ni los triggers de inmutabilidad (invariante 1). La F3
copia como nuevas `VentaLinea` TODAS las lineas ya congeladas de cada
simplificada origen (valores YA cuantizados, JAMAS recalculados) y delega en
el motor fiscal existente (`motor.emit(serie="F", tipo_factura="F3")`) para
la numeracion y el encadenamiento. Transaccion todo-o-nada: ninguna
verificacion de elegibilidad ni de destinatario toca la sesion antes de que
TODAS pasen (spec conversion-factura-f3, Requirement "Conversion atomica").
Sin dependencias de HTTP."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from app.dominio.puertos import MotorFiscal, UnidadDeTrabajo
from app.dominio.servicios.validadores import normalizar_documento, validar_documento
from app.infraestructura.persistencia.modelos import (
    Cliente,
    RegistroFacturaSustituida,
    Venta,
    VentaLinea,
    VentaSustitucion,
)

# Estados de una T que el caso de uso reconoce ANTES de decidir el tipo de
# rechazo (fase 2.4 distingue 'sustituida' -> YaSustituida del resto -> SimplificadaNoElegible).
_ESTADOS_T_RECONOCIDOS = ("cobrada", "sustituida")


@dataclass
class DatosDestinatario:
    nif: str
    nombre: str
    domicilio: str


@dataclass
class ResultadoConversion:
    venta_id: int
    num_serie: str
    fecha: str
    total: str
    num_origenes: int


class SinSimplificadas(Exception):
    """`simplificada_ids` vacio: no hay nada que convertir (HTTP 422)."""


class SimplificadaNoElegible(Exception):
    """El id no existe, no es serie 'T', o no esta en un estado reconocido
    (ni 'cobrada' ni 'sustituida') (HTTP 409)."""

    def __init__(self, venta_id: int):
        super().__init__(f"Venta {venta_id} no es una simplificada convertible")
        self.venta_id = venta_id


class YaSustituida(Exception):
    """La T ya fue convertida en una F3 anteriormente (HTTP 409)."""

    def __init__(self, venta_id: int):
        super().__init__(f"Venta {venta_id} ya fue sustituida por una F3")
        self.venta_id = venta_id


class DestinatarioInvalido(Exception):
    """El NIF del destinatario no supera el digito de control, o su nombre/domicilio
    vienen vacios (art. 6 ROF: contenido minimo de una factura completa) (HTTP 422)."""


class RegistroOrigenNoEncontrado(Exception):
    """Invariante roto: una simplificada ya validada como elegible no tiene un
    registro de ALTA fiscal propio (nunca deberia ocurrir con datos consistentes,
    toda venta serie T 'cobrada'/'sustituida' fue emitida por el motor fiscal).
    Defensa en profundidad, no un camino de negocio esperado."""

    def __init__(self, venta_id: int):
        super().__init__(f"Venta {venta_id} no tiene registro de alta fiscal")
        self.venta_id = venta_id


class ConvertirEnFacturaF3:
    def __init__(self, uow: UnidadDeTrabajo, motor: MotorFiscal):
        self.uow = uow
        self.motor = motor

    def ejecutar(
        self, *, usuario_id: int, origen: str, simplificada_ids: list[int],
        destinatario: DatosDestinatario,
    ) -> ResultadoConversion:
        if not simplificada_ids:
            raise SinSimplificadas()

        # De-duplicar preservando orden ANTES de cualquier validacion/escritura: una
        # seleccion repetida convierte esa factura una sola vez (sin esto, [5, 5]
        # duplica lineas/totales y solo el UNIQUE de venta_sustitucion lo aborta con
        # un IntegrityError crudo).
        simplificada_ids = list(dict.fromkeys(simplificada_ids))

        # Revalidar CADA id (pre-check de negocio, no confiar solo en el UNIQUE de
        # BD: decision.md "elegibilidad en el caso de uso, no en la BD"). Ninguna
        # de estas lecturas muta la sesion.
        origenes = [self._validar_elegible(vid) for vid in simplificada_ids]

        if not validar_documento(destinatario.nif):
            raise DestinatarioInvalido(destinatario.nif)
        # Art. 6 ROF: la factura completa exige nombre y domicilio del destinatario
        # (mismo guardarraiz que `EmitirVenta._exigir_datos_cualificada` para domicilio).
        if not destinatario.nombre.strip() or not destinatario.domicilio.strip():
            raise DestinatarioInvalido(destinatario.nif)

        # A partir de aqui TODAS las validaciones pasaron: recien ahora se toca
        # la sesion (2.6, atomicidad por construccion: nada se persiste antes).
        cliente = self._resolver_cliente(destinatario)

        # Snapshot CONGELADO del destinatario RESUELTO para ESTA F3 (fix Judgment
        # Day, migracion 0010): se fija AQUI, mientras la venta aun esta
        # `aparcada` (antes de `motor.emit`), con el valor de `cliente` REALMENTE
        # usado -- inmune a cualquier edicion posterior del `Cliente` (invariante
        # 1: un documento fiscal expedido es inmutable). `RemitirLote` debe leer
        # este snapshot, NUNCA `venta.cliente` en vivo (ver remitir_lote.py).
        f3 = Venta(
            estado="aparcada", usuario_id=usuario_id, cliente_id=cliente.id,
            destinatario_nombre=cliente.nombre, destinatario_nif=cliente.nif,
            base_total=Decimal("0.00"), cuota_total=Decimal("0.00"),
            total_con_iva=Decimal("0.00"),
        )
        self._copiar_lineas(f3, origenes)
        self.uow.ventas.agregar(f3)

        registro = self.motor.emit(self.uow.session, f3, serie="F", tipo_factura="F3")

        num_series_origen = []
        for origen_venta in origenes:
            registro_origen = self.uow.registros.buscar_alta_por_venta(origen_venta.id)
            if registro_origen is None:
                raise RegistroOrigenNoEncontrado(origen_venta.id)
            self.uow.session.add(RegistroFacturaSustituida(
                registro_fiscal_id=registro.id,
                id_emisor=registro_origen.id_emisor,
                num_serie_factura=registro_origen.num_serie_factura,
                fecha_expedicion=registro_origen.fecha_expedicion,
            ))
            self.uow.session.add(VentaSustitucion(
                venta_sustituta_id=f3.id, venta_sustituida_id=origen_venta.id,
            ))
            origen_venta.estado = "sustituida"
            num_series_origen.append(origen_venta.num_serie_factura)

        # Invariante 4 (CLAUDE.md): auditoria append-only en la MISMA transaccion.
        self.uow.auditoria.registrar(
            accion="conversion_f3", entidad="venta", entidad_id=str(f3.id),
            detalle=", ".join(num_series_origen), usuario_id=usuario_id, origen=origen,
        )

        self.uow.commit()

        return ResultadoConversion(
            venta_id=f3.id, num_serie=f3.num_serie_factura,
            fecha=registro.fecha_expedicion, total=str(f3.total_con_iva),
            num_origenes=len(origenes),
        )

    # -- helpers -----------------------------------------------------------------

    def _validar_elegible(self, venta_id: int) -> Venta:
        venta = self.uow.ventas.buscar(venta_id)
        if venta is None or venta.serie != "T" or venta.estado not in _ESTADOS_T_RECONOCIDOS:
            raise SimplificadaNoElegible(venta_id)
        # No fiarse solo de `estado`: un `VentaSustitucion` ya registrado para este
        # id es la MISMA fuente de verdad que usa `RepositorioVentasSQL.convertibles()`
        # (hardening: mata la teoria de "dos fuentes de verdad" -- una `cobrada` ya
        # sustituida por una inconsistencia previa no debe llegar al UNIQUE de BD).
        ya_referenciada = self.uow.session.execute(
            select(VentaSustitucion.id).where(VentaSustitucion.venta_sustituida_id == venta_id)
        ).first()
        if venta.estado == "sustituida" or ya_referenciada is not None:
            raise YaSustituida(venta_id)
        return venta

    def _resolver_cliente(self, destinatario: DatosDestinatario) -> Cliente:
        """Reutiliza un `Cliente` existente por NIF o crea uno nuevo con los
        datos capturados inline (design.md: "Destinatarios via Cliente + parametro
        a XML, SIN migracion, SIN huella"). `f3.cliente_id` queda congelado por el
        INSERT (la venta aun es 'aparcada' en este punto)."""
        cliente = self.uow.clientes.buscar_por_nif(destinatario.nif)
        if cliente is not None:
            return cliente
        cliente = Cliente(
            nombre=destinatario.nombre, nif=normalizar_documento(destinatario.nif),
            domicilio=destinatario.domicilio, rgpd_consentimiento=False,
        )
        self.uow.clientes.agregar(cliente)
        self.uow.flush()
        return cliente

    def _copiar_lineas(self, f3: Venta, origenes: list[Venta]) -> None:
        """Copia como nuevas `VentaLinea` TODAS las lineas de los origenes,
        preservando sus valores YA CUANTIZADOS (base_linea/cuota_linea/total_linea)
        SIN recalcular nada: sumar `Decimal` ya cuantizados es asociativo y exacto
        (design.md, decision "F3 = suma de lineas congeladas, jamas re-redondeo").
        Los totales de la F3 son la suma de los totales de cada origen."""
        base_total = Decimal("0.00")
        cuota_total = Decimal("0.00")
        total_con_iva = Decimal("0.00")
        for origen_venta in origenes:
            for linea in origen_venta.lineas:
                f3.lineas.append(VentaLinea(
                    articulo_id=linea.articulo_id,
                    descripcion=linea.descripcion,
                    cantidad=linea.cantidad,
                    pvp_unitario=linea.pvp_unitario,
                    tipo_iva_porcentaje=linea.tipo_iva_porcentaje,
                    descuento=linea.descuento,
                    base_linea=linea.base_linea,
                    cuota_linea=linea.cuota_linea,
                    total_linea=linea.total_linea,
                ))
            base_total += origen_venta.base_total
            cuota_total += origen_venta.cuota_total
            total_con_iva += origen_venta.total_con_iva
        f3.base_total = base_total
        f3.cuota_total = cuota_total
        f3.total_con_iva = total_con_iva
