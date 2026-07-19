"""API del TPV tactil: login, botonera, calcular y cobrar (TestClient)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.infraestructura.config import settings
from app.presentacion.deps import get_motor, get_session, get_uow
from app.infraestructura.fiscal.engine import NullEngine
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
    CodigoBarras,
    Familia,
    PaginaBotonera,
    PerfilBotonera,
    RegistroFiscal,
    Venta,
)


@pytest.fixture
def datos_tpv(session, datos_base):
    fam = Familia(nombre="Peces", orden=1)
    session.add(fam)
    session.flush()
    neon = Articulo(nombre="Neon cardenal", nombre_corto="Neon", familia_id=fam.id,
                    tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"), control_stock=True)
    tridacna = Articulo(nombre="Tridacna maxima", nombre_corto="Tridacna", familia_id=fam.id,
                        tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("45.00"),
                        modo_precio="libre", requiere_cites=True)
    session.add_all([neon, tridacna])
    session.flush()
    session.add(CodigoBarras(articulo_id=neon.id, codigo="8412345678905", principal=True))
    perfil = PerfilBotonera(nombre="Principal")
    session.add(perfil)
    session.flush()
    pagina = PaginaBotonera(perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4)
    session.add(pagina)
    session.flush()
    session.add_all([
        Boton(pagina_id=pagina.id, fila=0, columna=0, texto="Neon", articulo_id=neon.id),
        Boton(pagina_id=pagina.id, fila=1, columna=0, texto="Peces", familia_id=fam.id),
        Boton(pagina_id=pagina.id, fila=3, columna=4, texto="Cobrar", funcion="cobrar"),
    ])
    session.commit()
    return {"neon_id": neon.id, "tridacna_id": tridacna.id, "familia_id": fam.id, **datos_base}


@pytest.fixture
def cliente(crear_sesion):
    app = crear_app()

    def _get_session():
        s = crear_sesion()
        try:
            yield s
        finally:
            s.close()

    def _get_uow():
        s = crear_sesion()
        try:
            yield UnidadDeTrabajoSQL(s)
        finally:
            s.close()

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_uow] = _get_uow
    app.dependency_overrides[get_motor] = lambda: NullEngine("00000000T", "AcuaTPV")
    return TestClient(app)


def test_pagina_tpv_sirve_html(cliente):
    r = cliente.get("/tpv/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "TPV AcuaTPV" in r.text


def _bloque_boton_que_contiene(html: str, etiqueta: str) -> str:
    idx = html.index(etiqueta)
    inicio = html.rindex("<button", 0, idx)
    fin = html.index("</button>", idx) + len("</button>")
    return html[inicio:fin]


def test_tpv_aparcar_y_desaparcar_habilitados_y_referencian_su_api(cliente):
    """Fase 4 (contenido estatico): 'Aparcar ticket'/'Desaparcar' dejan de estar
    `disabled` y su wiring referencia los endpoints nuevos."""
    html = cliente.get("/tpv/").text

    for etiqueta in ("Aparcar ticket", "Desaparcar"):
        bloque = _bloque_boton_que_contiene(html, etiqueta)
        assert "disabled" not in bloque, f"boton '{etiqueta}' sigue disabled"

    assert "/tpv/api/aparcar" in html
    assert "/tpv/api/aparcadas" in html


def test_login_ok_y_ko(cliente, datos_tpv):
    r = cliente.post("/tpv/api/login", json={"pin": "0000"})
    assert r.status_code == 200
    assert r.json()["usuario_id"] == datos_tpv["usuario_id"]
    assert cliente.post("/tpv/api/login", json={"pin": "9999"}).status_code == 401


def test_botonera_incluye_articulo(cliente, datos_tpv):
    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    tipos = {b["tipo"] for b in r.json()["botones"]}
    assert {"articulo", "familia", "funcion"} <= tipos


def test_botonera_refleja_layout_editado_por_el_editor(cliente, crear_sesion, datos_tpv):
    """Requisito 'Compatibilidad del contrato de lectura del TPV' (spec): editar
    el layout del perfil activo vía `ServicioBotonera.guardar_layout` no cambia
    la FORMA de `GET /tpv/api/botonera` y refleja el nuevo layout guardado."""
    from app.aplicacion.botoneras import DatosBoton, DatosLayout, ServicioBotonera
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    # Layout original (fixture `datos_tpv`): 3 botones. Lo reemplazamos por uno
    # nuevo, distinto, vía el servicio de aplicación (no HTTP, ver tasks.md Tarea 5).
    with crear_sesion() as s:
        svc = ServicioBotonera(UnidadDeTrabajoSQL(s))
        arbol = svc.cargar_arbol()
        pagina_id = arbol[0]["paginas"][0]["id"]
        svc.guardar_layout(pagina_id, DatosLayout(
            filas=4, columnas=5,
            botones=[
                DatosBoton(ref="solo", fila=2, columna=3,
                           articulo_id=datos_tpv["neon_id"], texto="Neon nuevo"),
            ],
        ))

    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    cuerpo = r.json()

    # Forma SIN cambios: mismas claves de siempre (regresion de shape).
    assert set(cuerpo.keys()) == {"perfil", "pagina", "botones"}
    assert set(cuerpo["pagina"].keys()) == {"id", "nombre", "columnas", "filas"}
    assert cuerpo["botones"] and set(cuerpo["botones"][0].keys()) == {
        "fila", "columna", "ancho", "alto", "color", "icono", "texto", "tipo", "articulo",
    }

    # Refleja el layout recien guardado (un solo boton, el nuevo).
    assert len(cuerpo["botones"]) == 1
    boton = cuerpo["botones"][0]
    assert boton["fila"] == 2 and boton["columna"] == 3 and boton["texto"] == "Neon nuevo"
    assert boton["tipo"] == "articulo"
    assert boton["articulo"]["id"] == datos_tpv["neon_id"]


def test_articulo_por_codigo(cliente, datos_tpv):
    r = cliente.get("/tpv/api/articulo/por-codigo/8412345678905")
    assert r.status_code == 200
    assert r.json()["nombre_corto"] == "Neon"
    assert cliente.get("/tpv/api/articulo/por-codigo/000").status_code == 404


def test_calcular_totales_en_servidor(cliente, datos_tpv):
    r = cliente.post("/tpv/api/calcular",
                     json={"items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}]})
    assert r.status_code == 200
    assert r.json()["total"] == "5.00"  # 2 x 2,50


def test_calcular_modo_libre(cliente, datos_tpv):
    r = cliente.post("/tpv/api/calcular", json={"items": [
        {"articulo_id": datos_tpv["tridacna_id"], "cantidad": "1", "pvp": "50.00"}]})
    assert r.json()["total"] == "50.00"
    assert r.json()["lineas"][0]["requiere_cites"] is True


# --- Edicion de linea: override de precio/descripcion (cualquier articulo) -----
def test_calcular_override_pvp_articulo_modo_fijo(cliente, datos_tpv):
    """El override de `pvp` aplica a CUALQUIER articulo, no solo a los de `modo_precio`
    "libre" (antes se ignoraba en silencio para el `neon`, que es `modo_precio` "fijo")."""
    r = cliente.post("/tpv/api/calcular", json={"items": [
        {"articulo_id": datos_tpv["neon_id"], "cantidad": "1", "pvp": "1.00"}]})
    assert r.status_code == 200
    assert r.json()["lineas"][0]["pvp"] == "1.00"
    assert r.json()["total"] == "1.00"


def test_calcular_modo_al_peso_con_peso_decimal(cliente, crear_sesion, datos_base):
    """Al peso reutiliza la formula existente (cantidad x pvp_unitario): `pvp` es el
    precio/kg de catalogo y `cantidad` es el peso ingresado en la venta."""
    with crear_sesion() as s:
        madera = Articulo(nombre="Madera flotante", nombre_corto="Madera",
                          tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("4.50"),
                          modo_precio="al_peso")
        s.add(madera)
        s.commit()
        madera_id = madera.id

    r = cliente.post("/tpv/api/calcular",
                     json={"items": [{"articulo_id": madera_id, "cantidad": "1.250"}]})
    assert r.status_code == 200
    assert r.json()["total"] == "5.63"  # 4.50 x 1.250, half-up


def test_calcular_sin_override_usa_pvp_catalogo(cliente, datos_tpv):
    """No-regresion: sin `pvp` en el item, la linea sigue usando el PVP de
    catalogo del articulo, igual que antes del cambio."""
    r = cliente.post("/tpv/api/calcular", json={"items": [
        {"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}]})
    assert r.status_code == 200
    assert r.json()["lineas"][0]["pvp"] == "2.50"
    assert r.json()["total"] == "2.50"


def test_calcular_eco_descripcion_override(cliente, datos_tpv):
    """Un `descripcion` override en el item se hace eco en la linea calculada;
    sin override se conserva `articulo.nombre` (comportamiento actual)."""
    r = cliente.post("/tpv/api/calcular", json={"items": [
        {"articulo_id": datos_tpv["neon_id"], "cantidad": "1", "descripcion": "Promo verano"}]})
    assert r.status_code == 200
    assert r.json()["lineas"][0]["descripcion"] == "Promo verano"


def test_cobrar_con_cliente_asignado(cliente, crear_sesion, datos_tpv):
    from app.aplicacion.clientes import DatosCliente, ServicioClientes
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(DatosCliente(nombre="Juan Perez"))

    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}],
        "pagos": [{"medio": "efectivo", "importe": "10.00"}],
        "cliente_id": cliente_id,
    })
    assert r.status_code == 200
    datos = r.json()

    with crear_sesion() as s:
        venta = s.get(Venta, datos["venta_id"])
        assert venta.cliente_id == cliente_id


def test_cobrar_cualificada_sin_datos_devuelve_422(cliente, crear_sesion, datos_tpv):
    from app.aplicacion.clientes import DatosCliente, ServicioClientes
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Sin datos"))  # sin nif ni domicilio

    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
        "pagos": [{"medio": "efectivo", "importe": "2.50"}],
        "cliente_id": cliente_id, "cualificada": True,
    })
    assert r.status_code == 422

    with crear_sesion() as s:
        assert s.query(Venta).count() == 0


def test_cobrar_cualificada_con_datos_completos_marca_venta(cliente, crear_sesion, datos_tpv):
    from app.aplicacion.clientes import DatosCliente, ServicioClientes
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501", domicilio="Calle Mayor 1"))

    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
        "pagos": [{"medio": "efectivo", "importe": "2.50"}],
        "cliente_id": cliente_id, "cualificada": True,
    })
    assert r.status_code == 200
    datos = r.json()

    with crear_sesion() as s:
        venta = s.get(Venta, datos["venta_id"])
        assert venta.cualificada is True


def test_cobrar_cualificada_pasa_cliente_a_imprimir_ticket(
    cliente, crear_sesion, datos_tpv, monkeypatch
):
    """`_imprimir_ticket_seguro` debe cargar `venta.cliente` y pasarlo a
    `imprimir_ticket` (tasks.md 3.14), para que el ticket cualificado pueda
    imprimir el destinatario (NIF + domicilio)."""
    from app.aplicacion.clientes import DatosCliente, ServicioClientes
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        cliente_id = ServicioClientes(UnidadDeTrabajoSQL(s)).crear(
            DatosCliente(nombre="Acuario S.L.", nif="A58818501", domicilio="Calle Mayor 1"))

    llamadas: list[tuple] = []
    monkeypatch.setattr("app.infraestructura.db.SessionLocal", crear_sesion)
    monkeypatch.setattr("app.infraestructura.impresion.ticket.crear_impresora", lambda: object())
    monkeypatch.setattr(
        "app.infraestructura.impresion.ticket.imprimir_ticket",
        lambda *a, **k: llamadas.append((a, k)),
    )

    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
        "pagos": [{"medio": "efectivo", "importe": "2.50"}],
        "cliente_id": cliente_id, "cualificada": True,
    })
    assert r.status_code == 200

    assert len(llamadas) == 1
    _, kwargs = llamadas[0]
    assert kwargs.get("cliente") is not None
    assert kwargs["cliente"].nombre == "Acuario S.L."


def test_cobrar_sin_cliente_pasa_cliente_none_a_imprimir_ticket(
    cliente, crear_sesion, datos_tpv, monkeypatch
):
    """No-regresion: sin cliente asignado, `_imprimir_ticket_seguro` pasa
    `cliente=None` (mismo comportamiento por defecto de `imprimir_ticket`)."""
    llamadas: list[tuple] = []
    monkeypatch.setattr("app.infraestructura.db.SessionLocal", crear_sesion)
    monkeypatch.setattr("app.infraestructura.impresion.ticket.crear_impresora", lambda: object())
    monkeypatch.setattr(
        "app.infraestructura.impresion.ticket.imprimir_ticket",
        lambda *a, **k: llamadas.append((a, k)),
    )

    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
        "pagos": [{"medio": "efectivo", "importe": "2.50"}],
    })
    assert r.status_code == 200

    assert len(llamadas) == 1
    _, kwargs = llamadas[0]
    assert kwargs.get("cliente") is None


def test_cobrar_emite_venta(cliente, crear_sesion, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}],
        "pagos": [{"medio": "efectivo", "importe": "10.00"}],
    })
    assert r.status_code == 200
    datos = r.json()
    assert datos["num_serie"].startswith("T")
    assert datos["total"] == "5.00"
    assert datos["cambio"] == "5.00"

    with crear_sesion() as s:
        venta = s.get(Venta, datos["venta_id"])
        assert venta.estado == "cobrada"
        assert s.query(RegistroFiscal).filter_by(venta_id=venta.id).count() == 1

    # El QR de la venta se sirve como PNG.
    qr = cliente.get(f"/tpv/api/venta/{datos['venta_id']}/qr.png")
    assert qr.status_code == 200 and qr.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_qr_cotejo_no_disponible_en_modo_demo(cliente, crear_sesion, datos_tpv, monkeypatch):
    """En modo demo el QR de cotejo tipo-AEAT NO se genera: el ticket digital es un
    documento SIN VALIDEZ FISCAL. Defensa en profundidad — mas alla de que la UI lo
    oculte, el endpoint nunca emite un QR de cotejo con datos de prueba (invariante 7)."""
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
        "pagos": [{"medio": "efectivo", "importe": "5.00"}],
    })
    assert r.status_code == 200
    venta_id = r.json()["venta_id"]

    monkeypatch.setattr(settings, "perfil", "demo")
    qr = cliente.get(f"/tpv/api/venta/{venta_id}/qr.png")
    assert qr.status_code == 404


def test_cobrar_acepta_pvp_y_descripcion_override(cliente, crear_sesion, datos_tpv):
    """El endpoint de cobro acepta `pvp` y `descripcion` opcionales por item y los
    congela en la venta emitida (edicion de linea, pre-emision)."""
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1",
                   "pvp": "1.00", "descripcion": "Promo verano"}],
        "pagos": [{"medio": "efectivo", "importe": "1.00"}],
    })
    assert r.status_code == 200
    datos = r.json()

    with crear_sesion() as s:
        venta = s.get(Venta, datos["venta_id"])
        assert venta.lineas[0].pvp_unitario == Decimal("1.00")
        assert venta.lineas[0].descripcion == "Promo verano"


def test_calcular_modo_libre_sin_descripcion_no_bloquea(cliente, datos_tpv):
    """El preview (`/calcular`) NUNCA bloquea por descripcion vacia en modo libre;
    la validacion solo aplica al emitir (Fase 4)."""
    r = cliente.post("/tpv/api/calcular", json={"items": [
        {"articulo_id": datos_tpv["tridacna_id"], "cantidad": "1", "pvp": "50.00"}]})
    assert r.status_code == 200
    assert r.json()["total"] == "50.00"


def test_cobrar_modo_libre_sin_descripcion_devuelve_422(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["tridacna_id"], "cantidad": "1", "pvp": "50.00"}],
        "pagos": [{"medio": "efectivo", "importe": "50.00"}],
    })
    assert r.status_code == 422


def test_cobrar_ticket_vacio_rechaza(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/cobrar",
                     json={"usuario_id": login["usuario_id"], "items": [], "pagos": []})
    assert r.status_code == 400


def test_imprimir_ticket_seguro_llega_a_la_impresora(crear_sesion, motor, datos_tpv, monkeypatch):
    """Regresion: `_imprimir_ticket_seguro` debe llegar a `imprimir_ticket` para una
    venta emitida. Bug corregido: `Venta` no estaba importado en `tpv.py`, por lo que
    `s.get(Venta, venta_id)` lanzaba `NameError` (atrapado por el `except Exception`
    local-first) y el ticket nunca llegaba a la impresora en produccion."""
    from app.aplicacion.emitir_venta import EmitirVenta, PagoVenta
    from app.aplicacion.lineas import ItemVenta as ItemUC
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        resultado = EmitirVenta(UnidadDeTrabajoSQL(s), motor).ejecutar(
            usuario_id=datos_tpv["usuario_id"],
            items=[ItemUC(articulo_id=datos_tpv["neon_id"], cantidad=Decimal("1"))],
            pagos=[PagoVenta("efectivo", Decimal("2.50"))],
        )

    llamadas: list[tuple] = []
    monkeypatch.setattr("app.infraestructura.db.SessionLocal", crear_sesion)
    monkeypatch.setattr("app.infraestructura.impresion.ticket.crear_impresora", lambda: object())
    monkeypatch.setattr(
        "app.infraestructura.impresion.ticket.imprimir_ticket",
        lambda *a, **k: llamadas.append((a, k)),
    )

    from app.presentacion.tpv import _imprimir_ticket_seguro
    _imprimir_ticket_seguro(resultado.venta_id)

    assert len(llamadas) == 1


# --- Alarma de stock (informativa, nunca bloquea el cobro) ---------------------
def test_stock_alarma_exige_pin(cliente, datos_tpv):
    assert cliente.get("/tpv/api/stock/alarma").status_code == 401
    assert cliente.get("/tpv/api/stock/alarma?pin=9999").status_code == 401


def test_stock_alarma_sin_sobreventa(cliente, datos_tpv):
    r = cliente.get("/tpv/api/stock/alarma?pin=0000")
    assert r.status_code == 200
    assert r.json() == {"control_activo": False, "articulos_en_negativo": 0}


# --- Drill-down de familias: filtro de visibilidad tactil ---------------------
def test_familia_excluye_subfamilias_no_visibles_en_tactil(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        visible = Familia(nombre="Ciclidos", parent_id=raiz.id, visible_en_tactil=True)
        no_visible = Familia(nombre="Peces escaneo", parent_id=raiz.id, visible_en_tactil=False)
        s.add_all([visible, no_visible])
        s.commit()
        raiz_id, visible_id = raiz.id, visible.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    ids = {sub["id"] for sub in r.json()["subfamilias"]}
    assert ids == {visible_id}


def test_familia_incluye_subfamilias_visibles_y_activas(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        h1 = Familia(nombre="Ciclidos", parent_id=raiz.id)
        h2 = Familia(nombre="Tetras", parent_id=raiz.id)
        s.add_all([h1, h2])
        s.commit()
        raiz_id, h1_id, h2_id = raiz.id, h1.id, h2.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    ids = {sub["id"] for sub in r.json()["subfamilias"]}
    assert ids == {h1_id, h2_id}


def test_familia_excluye_subfamilia_inactiva_aunque_visible_en_tactil(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        activa = Familia(nombre="Ciclidos", parent_id=raiz.id)
        inactiva = Familia(nombre="Descontinuada", parent_id=raiz.id, activo=False)
        s.add_all([activa, inactiva])
        s.commit()
        raiz_id, activa_id = raiz.id, activa.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    ids = {sub["id"] for sub in r.json()["subfamilias"]}
    assert ids == {activa_id}


def test_botonera_respeta_boton_explicito_a_familia_no_visible(cliente, crear_sesion, datos_tpv):
    with crear_sesion() as s:
        pagina = s.query(PaginaBotonera).one()
        no_visible = Familia(nombre="Trastienda", visible_en_tactil=False)
        s.add(no_visible)
        s.flush()
        s.add(Boton(pagina_id=pagina.id, fila=2, columna=2, texto="Trastienda",
                    familia_id=no_visible.id))
        s.commit()
        no_visible_id = no_visible.id

    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    familias_en_botones = [b["familia"]["id"] for b in r.json()["botones"] if b["tipo"] == "familia"]
    assert no_visible_id in familias_en_botones


# --- Imagen efectiva del destino (articulo/familia) en los DTOs del TPV -------
def test_botonera_expone_imagen_de_articulo_y_familia_con_imagen_asignada(cliente, crear_sesion, datos_tpv):
    with crear_sesion() as s:
        s.get(Articulo, datos_tpv["neon_id"]).imagen = "/media/articulo-1-abcd1234.jpg"
        s.get(Familia, datos_tpv["familia_id"]).imagen = "/media/familia-1-abcd1234.png"
        s.commit()

    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    botones = r.json()["botones"]
    boton_articulo = next(b for b in botones if b["tipo"] == "articulo")
    boton_familia = next(b for b in botones if b["tipo"] == "familia")
    assert boton_articulo["articulo"]["imagen"] == "/media/articulo-1-abcd1234.jpg"
    assert boton_familia["familia"]["imagen"] == "/media/familia-1-abcd1234.png"


def test_botonera_destino_sin_imagen_expone_null_y_no_falla(cliente, datos_tpv):
    r = cliente.get("/tpv/api/botonera")
    assert r.status_code == 200
    botones = r.json()["botones"]
    boton_articulo = next(b for b in botones if b["tipo"] == "articulo")
    boton_familia = next(b for b in botones if b["tipo"] == "familia")
    assert boton_articulo["articulo"]["imagen"] is None
    assert boton_familia["familia"]["imagen"] is None


def test_familia_drilldown_expone_imagen_en_subfamilias_y_articulos(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        raiz = Familia(nombre="Peces", orden=1)
        s.add(raiz)
        s.flush()
        sub_con_imagen = Familia(nombre="Ciclidos", parent_id=raiz.id,
                                 imagen="/media/familia-2-aaaa1111.png")
        sub_sin_imagen = Familia(nombre="Tetras", parent_id=raiz.id)
        articulo_con_imagen = Articulo(
            nombre="Neon", nombre_corto="Neon", familia_id=raiz.id,
            tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("2.50"),
            imagen="/media/articulo-3-bbbb2222.jpg")
        s.add_all([sub_con_imagen, sub_sin_imagen, articulo_con_imagen])
        s.commit()
        raiz_id = raiz.id

    r = cliente.get(f"/tpv/api/familia/{raiz_id}")
    assert r.status_code == 200
    cuerpo = r.json()
    sub_dto = next(x for x in cuerpo["subfamilias"] if x["nombre"] == "Ciclidos")
    sub_sin_imagen_dto = next(x for x in cuerpo["subfamilias"] if x["nombre"] == "Tetras")
    art_dto = next(a for a in cuerpo["articulos"] if a["nombre"] == "Neon")
    assert sub_dto["imagen"] == "/media/familia-2-aaaa1111.png"
    assert sub_sin_imagen_dto["imagen"] is None
    assert art_dto["imagen"] == "/media/articulo-3-bbbb2222.jpg"


# --- Busqueda incremental por nombre (lupa) ------------------------------------
def test_buscar_coincide_por_nombre_case_insensitive(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        s.add(Articulo(nombre="Betta Splendens Macho", nombre_corto="Betta",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("5.00")))
        s.commit()

    r = cliente.get("/tpv/api/buscar", params={"q": "BETTA"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert [a["nombre"] for a in cuerpo] == ["Betta Splendens Macho"]
    assert set(cuerpo[0].keys()) == {
        "id", "nombre", "nombre_corto", "pvp", "tipo_iva",
        "modo_precio", "requiere_cites", "color", "imagen",
    }


def test_buscar_coincide_por_nombre_corto(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        s.add(Articulo(nombre="Pez tetra", nombre_corto="xyzcorto",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00")))
        s.commit()

    r = cliente.get("/tpv/api/buscar", params={"q": "xyz"})
    assert r.status_code == 200
    assert [a["nombre"] for a in r.json()] == ["Pez tetra"]


def test_buscar_excluye_articulos_inactivos(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        s.add(Articulo(nombre="Guppy activo", nombre_corto="Guppy",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00")))
        s.add(Articulo(nombre="Guppy inactivo", nombre_corto="Guppy2",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("3.00"), activo=False))
        s.commit()

    r = cliente.get("/tpv/api/buscar", params={"q": "guppy"})
    assert r.status_code == 200
    assert [a["nombre"] for a in r.json()] == ["Guppy activo"]


def test_buscar_query_corta_no_ejecuta_busqueda(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        s.add(Articulo(nombre="Betta Splendens Macho", nombre_corto="Betta",
                       tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("5.00")))
        s.commit()

    assert cliente.get("/tpv/api/buscar").json() == []
    assert cliente.get("/tpv/api/buscar", params={"q": "a"}).json() == []


def test_buscar_limita_a_top_20(cliente, crear_sesion, datos_base):
    with crear_sesion() as s:
        for i in range(25):
            s.add(Articulo(nombre=f"Pez {i:02d}", nombre_corto=f"P{i:02d}",
                           tipo_iva_id=datos_base["iva21_id"], pvp=Decimal("1.00")))
        s.commit()

    r = cliente.get("/tpv/api/buscar", params={"q": "pez"})
    assert r.status_code == 200
    assert len(r.json()) == 20


# --- Aparcar / listar / desaparcar (borradores no fiscales) -------------------


def test_aparcar_ticket_devuelve_venta_id_etiqueta_total_n_lineas(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}],
        "etiqueta": "Mostrador 2",
    })
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo.keys()) == {"venta_id", "etiqueta", "total", "n_lineas"}
    assert cuerpo["etiqueta"] == "Mostrador 2"
    assert cuerpo["total"] == "5.00"
    assert cuerpo["n_lineas"] == 1


def test_aparcar_ticket_vacio_rechaza(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/aparcar",
                     json={"usuario_id": login["usuario_id"], "items": []})
    assert r.status_code == 400


def test_listar_aparcadas_orden_id_desc(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    primero = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
    }).json()
    segundo = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "3"}],
        "etiqueta": "Barra",
    }).json()

    r = cliente.get("/tpv/api/aparcadas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert [item["venta_id"] for item in cuerpo] == [segundo["venta_id"], primero["venta_id"]]
    assert set(cuerpo[0].keys()) == {"venta_id", "etiqueta", "total", "n_lineas"}


def test_desaparcar_devuelve_lineas_enriquecidas_y_borra(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    aparcada = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}],
    }).json()

    r = cliente.delete(f"/tpv/api/aparcadas/{aparcada['venta_id']}")
    assert r.status_code == 200
    lineas = r.json()["lineas"]
    assert len(lineas) == 1
    linea = lineas[0]
    assert linea["articulo_id"] == datos_tpv["neon_id"]
    assert linea["cantidad"] == "2.000"
    assert linea["pvp"] == "2.50"
    assert linea["modo_precio"] == "fijo"
    assert linea["nombre_corto"] == "Neon"

    # Consumido: ya no aparece en el listado.
    assert cliente.get("/tpv/api/aparcadas").json() == []


def test_desaparcar_id_ya_consumido_devuelve_404(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    aparcada = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
    }).json()

    assert cliente.delete(f"/tpv/api/aparcadas/{aparcada['venta_id']}").status_code == 200
    assert cliente.delete(f"/tpv/api/aparcadas/{aparcada['venta_id']}").status_code == 404


def test_aparcar_usuario_id_invalido_devuelve_401(cliente, datos_tpv):
    """Hardening: un `usuario_id` inexistente en `/api/aparcar` debe mapear al
    mismo 401 que `/api/cobrar` usa para `UsuarioNoValido`, no un 500 por
    `IntegrityError` de la FK."""
    r = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": 999999,
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "1"}],
    })
    assert r.status_code == 401


def test_aparcar_libre_sin_descripcion_devuelve_422(cliente, datos_tpv):
    """Hardening: cierra el bypass de `DescripcionRequerida` al aparcar (antes
    solo se exigia al cobrar, permitiendo aparcar un libre sin descripcion)."""
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["tridacna_id"], "cantidad": "1", "pvp": "50.00"}],
    })
    assert r.status_code == 422


def test_aparcar_libre_con_descripcion_devuelve_200(cliente, datos_tpv):
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    r = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["tridacna_id"], "cantidad": "1",
                   "pvp": "50.00", "descripcion": "Promo verano"}],
    })
    assert r.status_code == 200


def test_cobrar_un_carrito_recuperado_emite_venta_nueva(cliente, crear_sesion, datos_tpv):
    """No regresion (spec 'Cobrar un carrito recuperado'): un borrador
    desaparcado se cobra por el camino INTACTO `EmitirVenta`/`/tpv/api/cobrar`,
    igual que cualquier venta emitida desde cero (serie + numero + registro +
    huella)."""
    login = cliente.post("/tpv/api/login", json={"pin": "0000"}).json()
    aparcada = cliente.post("/tpv/api/aparcar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": datos_tpv["neon_id"], "cantidad": "2"}],
    }).json()

    recuperada = cliente.delete(f"/tpv/api/aparcadas/{aparcada['venta_id']}").json()

    r = cliente.post("/tpv/api/cobrar", json={
        "usuario_id": login["usuario_id"],
        "items": [{"articulo_id": l["articulo_id"], "cantidad": l["cantidad"],
                   "pvp": l["pvp"], "descripcion": l["descripcion"]}
                  for l in recuperada["lineas"]],
        "pagos": [{"medio": "efectivo", "importe": "5.00"}],
    })
    assert r.status_code == 200
    datos = r.json()
    assert datos["num_serie"].startswith("T")
    assert datos["total"] == "5.00"

    with crear_sesion() as s:
        venta = s.get(Venta, datos["venta_id"])
        assert venta.estado == "cobrada"
        assert s.query(RegistroFiscal).filter_by(venta_id=venta.id).count() == 1


def test_stock_alarma_refleja_sobreventa(cliente, crear_sesion, datos_tpv):
    from app.infraestructura.persistencia.modelos import MovimientoStock
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        uow.configuracion.fijar_control_stock(True)
        uow.stock.agregar(MovimientoStock(
            articulo_id=datos_tpv["neon_id"], tipo="venta", cantidad=Decimal("4"),
            fecha_hora_huso="2026-07-11T00:00:00+02:00"))
        s.commit()

    r = cliente.get("/tpv/api/stock/alarma?pin=0000")
    assert r.status_code == 200
    assert r.json() == {"control_activo": True, "articulos_en_negativo": 1}
