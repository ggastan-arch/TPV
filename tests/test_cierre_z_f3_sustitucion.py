"""Cuadre del Cierre Z ante conversiones F3 (change `cierre-z-f3-sustitucion`).

Fase 1 (RED): `cobradas_por_rango_orden` hoy filtra estrictamente
`Venta.estado == "cobrada"`. Al convertir una simplificada T en una F3
(`ConvertirEnFacturaF3`), la T pasa a `sustituida` (sale del filtro) y la F3
queda `cobrada` sin filas `Pago` propias (sus totales son la suma congelada de
los orígenes, ver `_copiar_lineas`). Efecto: `desglose_pago` queda corto por el
importe real de la T, `num_tickets` no ve las T reales, y en escenarios
cross-period el total de la T se cuenta dos veces (una en el Z del origen, otra
en el Z que cae sobre el alta de la F3).

Ver design.md (Approach 2: incluir `sustituida` + excluir `venta_sustituta_id`)
y specs/cierre-z/spec.md (requirement "Cuadre de totales y desgloses")."""
from __future__ import annotations

from decimal import Decimal

from _helpers import construir_venta
from app.aplicacion.convertir_en_factura_f3 import ConvertirEnFacturaF3, DatosDestinatario
from app.aplicacion.generar_cierre_z import GenerarCierreZ
from app.infraestructura.persistencia.modelos import Pago, RegistroFiscal
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

_DESTINATARIO_OK = DatosDestinatario(
    nif="A58818501", nombre="Acuario S.L.", domicilio="Calle Mayor 1"
)


def _emitir_t(crear_sesion, motor, usuario_id, ejercicio, lineas, medio="efectivo") -> tuple[int, dict]:
    """Emite una simplificada (serie T) cobrada con un pago del medio indicado.
    Devuelve (id_venta, totales_reales)."""
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, lineas)
        s.add(venta)
        venta.pagos.append(Pago(medio=medio, importe=venta.total_con_iva))
        motor.emit(s, venta, serie="T", ejercicio=ejercicio, tipo_factura="F2")
        venta_id = venta.id
        totales = {
            "base_total": venta.base_total,
            "cuota_total": venta.cuota_total,
            "total_con_iva": venta.total_con_iva,
        }
    return venta_id, totales


def _convertir(crear_sesion, motor, usuario_id, ids: list[int]) -> int:
    """Convierte 1..N simplificadas T en una unica F3; devuelve el id de la F3."""
    with crear_sesion() as s:
        resultado = ConvertirEnFacturaF3(UnidadDeTrabajoSQL(s), motor).ejecutar(
            usuario_id=usuario_id, origen="local",
            simplificada_ids=ids, destinatario=_DESTINATARIO_OK,
        )
    return resultado.venta_id


def _generar(crear_sesion, usuario_id, origen="local"):
    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        return GenerarCierreZ(uow).ejecutar(usuario_id=usuario_id, origen=origen)


# --- Conversion F3 del mismo periodo no rompe el cuadre ----------------------

def test_cuadre_mismo_periodo_conversion_f3(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    t1_id, t1 = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Neon cardenal", "2.50", "2", "21")], medio="efectivo",
    )
    t2_id, t2 = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Anubias", "6.90", "1", "10")], medio="tarjeta",
    )

    _convertir(crear_sesion, motor, usuario_id, [t1_id, t2_id])

    z = _generar(crear_sesion, usuario_id)

    assert z.base_total == t1["base_total"] + t2["base_total"]
    assert z.cuota_total == t1["cuota_total"] + t2["cuota_total"]
    assert z.total_con_iva == t1["total_con_iva"] + t2["total_con_iva"]
    assert z.base_total + z.cuota_total == z.total_con_iva

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        persistido = uow.cierres_z.buscar(z.numero)
        por_medio = {d.medio: d.importe for d in persistido.desglose_pago}

    # HOY (sin el filtro corregido): la F3 no aporta filas `Pago` propias y las T
    # reales quedan fuera por `estado == "sustituida"` -> `por_medio` llega vacio.
    assert por_medio.get("efectivo") == t1["total_con_iva"]
    assert por_medio.get("tarjeta") == t2["total_con_iva"]
    assert sum(por_medio.values(), Decimal("0.00")) == z.total_con_iva


# --- num_tickets refleja ventas reales, no la F3 en papel ---------------------

def test_num_tickets_no_incluye_f3_en_conversion(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    t1_id, _ = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Neon cardenal", "2.50", "1", "21")], medio="efectivo",
    )
    t2_id, _ = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Guppy", "3.00", "1", "21")], medio="efectivo",
    )

    _convertir(crear_sesion, motor, usuario_id, [t1_id, t2_id])

    z = _generar(crear_sesion, usuario_id)

    # HOY: solo la F3 pasa el filtro `estado == "cobrada"` -> num_tickets == 1.
    assert z.num_tickets == 2


# --- Conversion F3 cross-period no duplica el efectivo ------------------------

def test_cross_period_no_duplica_efectivo(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    t_id, t = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Neon cardenal", "2.50", "3", "21")], medio="efectivo",
    )

    z1 = _generar(crear_sesion, usuario_id)  # incluye el alta de la T, Z ya cerrado
    assert z1.total_con_iva == t["total_con_iva"]

    _convertir(crear_sesion, motor, usuario_id, [t_id])  # alta F3: orden nuevo, posterior

    z2 = _generar(crear_sesion, usuario_id)  # rango que solo contiene el alta de la F3

    # HOY: la F3 sigue `cobrada` y pasa el filtro -> z2 vuelve a sumar el total de la
    # T (ya contado en z1), duplicando el efectivo real.
    assert z2.num_tickets == 0
    assert z2.total_con_iva == Decimal("0.00")


# --- Guarda: una venta anulada no aporta al cuadre ---------------------------
#
# Regresion, no RED->GREEN: bloquea que un futuro cambio anada
# 'anulada_con_rastro' a la tupla de estados de `cobradas_por_rango_orden`.

def test_z_excluye_venta_anulada_con_rastro(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    t_id, _ = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Neon cardenal", "2.50", "2", "21")], medio="efectivo",
    )

    with crear_sesion() as s, s.begin():
        alta = s.query(RegistroFiscal).filter_by(venta_id=t_id, tipo_registro="alta").one()
        motor.cancel(s, alta)

    z = _generar(crear_sesion, usuario_id)

    assert z.num_tickets == 0
    assert z.base_total == Decimal("0.00")
    assert z.cuota_total == Decimal("0.00")
    assert z.total_con_iva == Decimal("0.00")

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        persistido = uow.cierres_z.buscar(z.numero)
        assert persistido.desglose_pago == []


# --- Guarda: el NOT IN de la conversion no sobre-excluye cobradas ajenas -----
#
# Regresion: en un rango que SI contiene una conversion F3 (VentaSustitucion no
# vacia), una venta cobrada normal, sin ninguna relacion con esa conversion,
# debe seguir contando integra -- el `notin_(venta_sustituta_id)` solo debe
# alcanzar al lado sustituto real.

def test_z_no_sobre_excluye_cobrada_independiente_junto_a_conversion(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    t1_id, t1 = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Neon cardenal", "2.50", "2", "21")], medio="efectivo",
    )
    t2_id, t2 = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Anubias", "6.90", "1", "10")], medio="tarjeta",
    )

    _convertir(crear_sesion, motor, usuario_id, [t1_id, t2_id])

    # Venta cobrada normal, sin relacion con la conversion, en el MISMO rango.
    t3_id, t3 = _emitir_t(
        crear_sesion, motor, usuario_id, ejercicio,
        [("Guppy", "3.00", "1", "21")], medio="efectivo",
    )

    z = _generar(crear_sesion, usuario_id)

    assert z.total_con_iva == t1["total_con_iva"] + t2["total_con_iva"] + t3["total_con_iva"]

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        persistido = uow.cierres_z.buscar(z.numero)
        por_medio = {d.medio: d.importe for d in persistido.desglose_pago}

    assert por_medio["efectivo"] == t1["total_con_iva"] + t3["total_con_iva"]
    assert por_medio["tarjeta"] == t2["total_con_iva"]
