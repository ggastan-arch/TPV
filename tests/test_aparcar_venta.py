"""Casos de uso AparcarVenta / ListarAparcadas / RecuperarAparcada (capa de
aplicacion), probados sin HTTP y sin motor fiscal.

Frontera fiscal (design.md / spec aparcar-ticket): ninguno de estos casos de uso
acepta un `MotorFiscal` ni invoca `emit`. Un borrador aparcado es
`Venta(estado='aparcada')` + `VentaLinea` (+ etiqueta); nunca tiene serie,
numero, num_serie_factura, fecha_hora_huso ni `RegistroFiscal` asociado."""
from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from app.aplicacion.aparcar_venta import (
    AparcadaDTO,
    AparcarVenta,
    BorradorNoEncontrado,
    ListarAparcadas,
    RecuperarAparcada,
    TicketVacio,
    UsuarioNoValido,
)
from app.aplicacion.lineas import DescripcionRequerida, ItemVenta
from app.infraestructura.persistencia.modelos import (
    Articulo,
    ContadorSerie,
    RegistroFiscal,
    Venta,
    VentaLinea,
)
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def _uc_aparcar(session):
    return AparcarVenta(UnidadDeTrabajoSQL(session))


def _uc_listar(session):
    return ListarAparcadas(UnidadDeTrabajoSQL(session))


def _uc_recuperar(session):
    return RecuperarAparcada(UnidadDeTrabajoSQL(session))


@pytest.fixture
def tres_articulos(session, datos_base):
    arts = [
        Articulo(nombre=f"Articulo {i}", nombre_corto=f"Art{i}",
                 tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"))
        for i in range(3)
    ]
    session.add_all(arts)
    session.commit()
    return [a.id for a in arts]


# --- 2.1 / 2.2: aparcar persiste el borrador (con/sin etiqueta) y rechaza vacio ---


def test_aparcar_con_etiqueta_persiste_venta_lineas_y_etiqueta(
    crear_sesion, datos_base, tres_articulos
):
    with crear_sesion() as s:
        venta_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=aid) for aid in tres_articulos],
            etiqueta="Mostrador 2",
        )

    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        assert venta.estado == "aparcada"
        assert venta.etiqueta_aparcada == "Mostrador 2"
        assert len(venta.lineas) == 3


def test_aparcar_sin_etiqueta_persiste_etiqueta_null(crear_sesion, datos_base, tres_articulos):
    with crear_sesion() as s:
        venta_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[0])],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        assert venta.etiqueta_aparcada is None


def test_aparcar_carrito_vacio_rechaza_sin_persistir(crear_sesion, datos_base):
    with crear_sesion() as s, pytest.raises(TicketVacio):
        _uc_aparcar(s).ejecutar(usuario_id=datos_base["usuario_id"], items=[])

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0
        assert s.query(VentaLinea).count() == 0


# --- Hardening: usuario_id invalido / descripcion libre exigida al aparcar ----


@pytest.fixture
def articulo_libre(session, datos_base):
    art = Articulo(nombre="Tridacna maxima", nombre_corto="Tridacna",
                   tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("45.00"),
                   modo_precio="libre")
    session.add(art)
    session.commit()
    return art.id


def test_aparcar_usuario_id_invalido_rechaza_sin_persistir(
    crear_sesion, datos_base, tres_articulos
):
    """Antes: un `usuario_id` inexistente llegaba sin validar a `Venta(...)` y
    solo fallaba al hacer commit como `IntegrityError` de la FK (500 en el
    endpoint). Ahora se valida igual que `EmitirVenta` (`uow.usuarios.buscar`)."""
    with crear_sesion() as s, pytest.raises(UsuarioNoValido):
        _uc_aparcar(s).ejecutar(
            usuario_id=999999, items=[ItemVenta(articulo_id=tres_articulos[0])],
        )

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0
        assert s.query(VentaLinea).count() == 0


def test_aparcar_libre_sin_descripcion_rechaza_con_descripcion_requerida(
    crear_sesion, datos_base, articulo_libre
):
    """Cierra el bypass: un articulo `modo_precio == "libre"` sin descripcion
    aparcado hoy congela `descripcion = articulo.nombre` y pasa silenciosamente
    la validacion de `EmitirVenta` al cobrar. Se exige aqui, al aparcar."""
    with crear_sesion() as s, pytest.raises(DescripcionRequerida):
        _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_libre, pvp=Decimal("50.00"))],
        )

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0
        assert s.query(VentaLinea).count() == 0


def test_aparcar_libre_con_descripcion_persiste_ok(crear_sesion, datos_base, articulo_libre):
    with crear_sesion() as s:
        venta_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=articulo_libre, pvp=Decimal("50.00"),
                              descripcion="Promo verano")],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        assert venta.estado == "aparcada"
        assert venta.lineas[0].descripcion == "Promo verano"


# --- 2.3: frontera fiscal -- aparcar NUNCA asigna identidad fiscal ------------


def test_aparcar_no_asigna_identidad_fiscal(crear_sesion, datos_base, tres_articulos):
    with crear_sesion() as s:
        contador_antes = {
            (c.serie, c.ejercicio): c.ultimo_numero for c in s.query(ContadorSerie).all()
        }

    with crear_sesion() as s:
        venta_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[0])],
        )

    with crear_sesion() as s:
        venta = s.get(Venta, venta_id)
        assert venta.serie is None
        assert venta.numero is None
        assert venta.num_serie_factura is None
        assert venta.fecha_hora_huso is None
        assert s.query(RegistroFiscal).filter_by(venta_id=venta_id).count() == 0
        contador_despues = {
            (c.serie, c.ejercicio): c.ultimo_numero for c in s.query(ContadorSerie).all()
        }
        assert contador_despues == contador_antes


def test_aparcar_venta_init_no_acepta_motor():
    parametros = inspect.signature(AparcarVenta.__init__).parameters
    assert "motor" not in parametros


# --- 2.6: listar solo devuelve borradores aparcados, orden id DESC ------------


def test_listar_aparcadas_devuelve_solo_aparcadas_orden_desc(
    crear_sesion, datos_base, tres_articulos
):
    with crear_sesion() as s:
        primero = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[0])],
            etiqueta="Mostrador 1",
        )
    with crear_sesion() as s:
        segundo = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[1]),
                   ItemVenta(articulo_id=tres_articulos[2])],
        )

    with crear_sesion() as s:
        resultado = _uc_listar(s).ejecutar()

    assert [d.venta_id for d in resultado] == [segundo, primero]
    dto_primero = next(d for d in resultado if d.venta_id == primero)
    dto_segundo = next(d for d in resultado if d.venta_id == segundo)
    assert isinstance(dto_primero, AparcadaDTO)
    assert dto_primero.etiqueta == "Mostrador 1"
    assert dto_primero.n_lineas == 1
    assert dto_segundo.etiqueta is None
    assert dto_segundo.n_lineas == 2


def test_listar_aparcadas_no_incluye_ventas_cobradas(
    crear_sesion, motor, datos_base, tres_articulos
):
    from app.aplicacion.emitir_venta import EmitirVenta, PagoVenta

    with crear_sesion() as s:
        EmitirVenta(UnidadDeTrabajoSQL(s), motor).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[0])],
            pagos=[PagoVenta("efectivo", Decimal("10.00"))],
        )
    with crear_sesion() as s:
        aparcada_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[1])],
        )

    with crear_sesion() as s:
        resultado = _uc_listar(s).ejecutar()

    assert [d.venta_id for d in resultado] == [aparcada_id]


# --- 2.9: recuperar (desaparcar) consume el borrador ---------------------------


def test_recuperar_aparcada_devuelve_lineas_y_borra(crear_sesion, datos_base, tres_articulos):
    with crear_sesion() as s:
        venta_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[0], cantidad=Decimal("2")),
                   ItemVenta(articulo_id=tres_articulos[1])],
        )

    with crear_sesion() as s:
        lineas = _uc_recuperar(s).ejecutar(venta_id)

    assert len(lineas) == 2
    assert {l.articulo_id for l in lineas} == set(tres_articulos[:2])
    linea_doble = next(l for l in lineas if l.cantidad == Decimal("2"))
    assert linea_doble.pvp == Decimal("2.50")
    assert linea_doble.descripcion

    with crear_sesion() as s:
        assert s.get(Venta, venta_id) is None
        assert s.query(VentaLinea).filter_by(venta_id=venta_id).count() == 0


def test_recuperar_aparcada_dos_veces_rechaza_sin_duplicar(
    crear_sesion, datos_base, tres_articulos
):
    with crear_sesion() as s:
        venta_id = _uc_aparcar(s).ejecutar(
            usuario_id=datos_base["usuario_id"],
            items=[ItemVenta(articulo_id=tres_articulos[0])],
        )

    with crear_sesion() as s:
        _uc_recuperar(s).ejecutar(venta_id)

    with crear_sesion() as s, pytest.raises(BorradorNoEncontrado):
        _uc_recuperar(s).ejecutar(venta_id)
