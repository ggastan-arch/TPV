"""Listado de facturas (simplificadas y completas) con filtros -- panel
"Facturas" de la consola de administracion (`GET /admin/api/facturas`).

Cubre `RepositorioRegistrosSQL.buscar_facturas` (repo) y el endpoint (sesion,
serializacion, filtros combinados). Feature de solo LECTURA: los registros se
siembran SIEMPRE con el motor fiscal real (`NullEngine.emit`), nunca insertados
a mano -- la cadena de huellas debe seguir siendo real incluso en datos de test
(invariante 3, CLAUDE.md). El listado devuelve unicamente registros de tipo
`alta` (facturas emitidas); las anulaciones no aparecen aqui."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.infraestructura.fiscal.engine as engine_mod
from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import (
    Cliente,
    ContadorSerie,
    RegistroFiscal,
    Serie,
    Usuario,
)
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.infraestructura.seguridad import hash_pin
from app.main import crear_app
from app.presentacion.deps import get_session, get_uow


# --- Fixtures (mismo patron que test_cierre_z_api.py: admin/cliente locales) ----
@pytest.fixture
def admin(session, datos_base):
    u = Usuario(nombre="jefa", pin_hash=hash_pin("secreta123"), rol="administracion")
    session.add(u)
    session.commit()
    return {"nombre": "jefa", "password": "secreta123", "usuario_id": u.id}


@pytest.fixture
def cliente_http(crear_sesion):
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
    return TestClient(app)


def _login(cliente_http, admin):
    return cliente_http.post(
        "/admin/api/login", json={"nombre": admin["nombre"], "password": admin["password"]}
    )


def _emitir(
    crear_sesion, motor, usuario_id, lineas, *, serie="T", tipo_factura="F2",
    fecha=None, cliente_id=None, monkeypatch=None,
):
    """Emite una venta con el motor fiscal REAL (huella y encadenamiento
    verdaderos). `fecha`, si se da, fuerza `fecha_hora_huso_gen_registro`
    (monkeypatch de `ahora_huso` SOLO para este emit; el registro sigue siendo
    real, solo se controla el reloj para poder probar el filtro de rango)."""
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, lineas)
        if cliente_id is not None:
            venta.cliente_id = cliente_id
        s.add(venta)
        if fecha is not None:
            assert monkeypatch is not None
            monkeypatch.setattr(engine_mod, "ahora_huso", lambda: fecha)
        registro = motor.emit(s, venta, serie=serie, tipo_factura=tipo_factura)
        return registro.id


def _sembrar_serie_r(session, ejercicio):
    """Serie 'R' (rectificativas): `datos_base` (conftest.py) solo siembra T/F,
    porque devolucion/rectificativa aun no es una feature emitida (CLAUDE.md).
    Se anade aqui solo para poder sembrar un registro de tipo R1-R5 en tests."""
    session.add(Serie(codigo="R", descripcion="Rectificativas", tipo_factura_default="R5"))
    session.flush()
    session.add(ContadorSerie(serie="R", ejercicio=ejercicio, ultimo_numero=0))
    session.commit()


LINEA = [("Neon cardenal", "2.50", "2", "21")]


# --- Repo: RepositorioRegistrosSQL.buscar_facturas -----------------------------
def test_repo_sin_filtro_lista_todas_mas_reciente_primero(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    id1 = _emitir(crear_sesion, motor, usuario_id, LINEA, serie="T", tipo_factura="F2")
    id2 = _emitir(crear_sesion, motor, usuario_id, LINEA, serie="F", tipo_factura="F1")

    with crear_sesion() as s:
        filas = UnidadDeTrabajoSQL(s).registros.buscar_facturas()

    assert len(filas) == 2
    # Orden por `orden` desc: la emitida en segundo lugar aparece primero.
    assert filas[0].num_serie_factura != filas[1].num_serie_factura
    assert filas[0].tipo_factura == "F1"
    assert filas[1].tipo_factura == "F2"
    assert id1 and id2  # sembrados correctamente (evita ids None silenciosos)


def test_repo_solo_altas_no_incluye_anulaciones(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, LINEA)
        s.add(venta)
        registro = motor.emit(s, venta, serie="T", tipo_factura="F2")
        motor.cancel(s, registro)

    with crear_sesion() as s:
        filas = UnidadDeTrabajoSQL(s).registros.buscar_facturas()

    assert len(filas) == 1
    assert filas[0].tipo_factura == "F2"


@pytest.mark.parametrize(
    "tipo,tipos_factura_esperados",
    [
        ("simplificada", {"F2"}),
        ("completa", {"F1", "F3"}),
        ("rectificativa", {"R1"}),
    ],
)
def test_repo_filtra_por_tipo(
    crear_sesion, motor, datos_base, session, tipo, tipos_factura_esperados
):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]
    _sembrar_serie_r(session, ejercicio)

    _emitir(crear_sesion, motor, usuario_id, LINEA, serie="T", tipo_factura="F2")
    _emitir(crear_sesion, motor, usuario_id, LINEA, serie="F", tipo_factura="F1")
    _emitir(crear_sesion, motor, usuario_id, LINEA, serie="F", tipo_factura="F3")
    _emitir(crear_sesion, motor, usuario_id, LINEA, serie="R", tipo_factura="R1")

    with crear_sesion() as s:
        filas = UnidadDeTrabajoSQL(s).registros.buscar_facturas(tipo=tipo)

    assert {f.tipo_factura for f in filas} == tipos_factura_esperados


def test_repo_filtra_por_rango_de_fechas(crear_sesion, motor, datos_base, monkeypatch):
    usuario_id = datos_base["usuario_id"]
    _emitir(
        crear_sesion, motor, usuario_id, LINEA,
        fecha="2026-01-10T10:00:00+01:00", monkeypatch=monkeypatch,
    )
    id_junio = _emitir(
        crear_sesion, motor, usuario_id, LINEA,
        fecha="2026-06-15T09:30:00+02:00", monkeypatch=monkeypatch,
    )

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        solo_junio = uow.registros.buscar_facturas(desde="2026-05-01", hasta="2026-12-31")
        todas = uow.registros.buscar_facturas()
        ninguna = uow.registros.buscar_facturas(desde="2027-01-01")

    assert len(solo_junio) == 1
    assert solo_junio[0].fecha_hora_huso.startswith("2026-06-15")
    assert len(todas) == 2
    assert ninguna == []
    assert id_junio  # sembrado correctamente


def test_repo_filtra_por_texto_libre_num_serie_nombre_nif(crear_sesion, motor, datos_base, session):
    usuario_id = datos_base["usuario_id"]
    cli = Cliente(nombre="Pepe Perez", nif="12345678Z")
    session.add(cli)
    session.commit()
    cliente_id = cli.id

    id_con_cliente = _emitir(
        crear_sesion, motor, usuario_id, LINEA, cliente_id=cliente_id
    )
    _emitir(crear_sesion, motor, usuario_id, LINEA)  # sin cliente

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        registro = uow.registros.buscar(id_con_cliente)
        num_serie = registro.num_serie_factura

        por_nombre = uow.registros.buscar_facturas(q="pepe")
        por_nif = uow.registros.buscar_facturas(q="12345678Z")
        por_serie = uow.registros.buscar_facturas(q=num_serie)
        sin_match = uow.registros.buscar_facturas(q="Zutano")

    assert [f.num_serie_factura for f in por_nombre] == [num_serie]
    assert por_nombre[0].cliente_nombre == "Pepe Perez"
    assert por_nombre[0].cliente_nif == "12345678Z"
    assert [f.num_serie_factura for f in por_nif] == [num_serie]
    assert [f.num_serie_factura for f in por_serie] == [num_serie]
    assert sin_match == []


def test_repo_filtra_por_estado_remision(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    id_pendiente = _emitir(crear_sesion, motor, usuario_id, LINEA)
    id_aceptado = _emitir(crear_sesion, motor, usuario_id, LINEA)

    with crear_sesion() as s, s.begin():
        # Cambiar SOLO estado_remision esta permitido por el trigger de
        # inmutabilidad (ver ddl.py, _REGISTRO_CAMPOS_CONGELADOS).
        reg = s.get(RegistroFiscal, id_aceptado)
        reg.estado_remision = "aceptado"

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        aceptados = uow.registros.buscar_facturas(estado="aceptado")
        no_remitidos = uow.registros.buscar_facturas(estado="no_remitido")
        todas = uow.registros.buscar_facturas(estado="todas")

    assert len(aceptados) == 1
    assert len(no_remitidos) == 1
    assert len(todas) == 2
    assert id_pendiente and id_aceptado


def test_repo_combina_filtros_con_and(crear_sesion, motor, datos_base, session):
    usuario_id = datos_base["usuario_id"]
    cli = Cliente(nombre="Ana Ruiz", nif="87654321X")
    session.add(cli)
    session.commit()

    _emitir(crear_sesion, motor, usuario_id, LINEA, serie="T", tipo_factura="F2", cliente_id=cli.id)
    _emitir(crear_sesion, motor, usuario_id, LINEA, serie="F", tipo_factura="F1", cliente_id=cli.id)

    with crear_sesion() as s:
        uow = UnidadDeTrabajoSQL(s)
        combinado = uow.registros.buscar_facturas(q="Ana Ruiz", tipo="simplificada")
        sin_match = uow.registros.buscar_facturas(q="Ana Ruiz", tipo="rectificativa")

    assert len(combinado) == 1
    assert combinado[0].tipo_factura == "F2"
    assert sin_match == []


def test_repo_prioriza_destinatario_congelado_sobre_cliente_en_vivo(
    crear_sesion, motor, datos_base, session
):
    """Una F3 (convertir en factura) congela destinatario_nombre/nif en la
    venta; el listado debe mostrar ese snapshot, no el cliente editado despues
    (mismo criterio que evito el bug de remision con destinatario editado,
    ver venta.py)."""
    usuario_id = datos_base["usuario_id"]
    cli = Cliente(nombre="Nombre Original", nif="11111111H")
    session.add(cli)
    session.commit()
    cliente_id = cli.id

    with crear_sesion() as s, s.begin():
        venta = construir_venta(usuario_id, LINEA)
        venta.cliente_id = cliente_id
        venta.destinatario_nombre = "Nombre Congelado SL"
        venta.destinatario_nif = "11111111H"
        s.add(venta)
        motor.emit(s, venta, serie="F", tipo_factura="F3")

    # El cliente se edita DESPUES de emitir (nunca se toca la venta/registro).
    with crear_sesion() as s, s.begin():
        c = s.get(Cliente, cliente_id)
        c.nombre = "Nombre Editado Despues"

    with crear_sesion() as s:
        filas = UnidadDeTrabajoSQL(s).registros.buscar_facturas(tipo="completa")

    assert filas[0].cliente_nombre == "Nombre Congelado SL"


# --- Endpoint GET /admin/api/facturas ------------------------------------------
def test_endpoint_exige_sesion(cliente_http, datos_base):
    assert cliente_http.get("/admin/api/facturas").status_code == 401


def test_endpoint_lista_y_serializa(cliente_http, admin, datos_base, crear_sesion, motor):
    _login(cliente_http, admin)
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA, serie="T", tipo_factura="F2")

    r = cliente_http.get("/admin/api/facturas")
    assert r.status_code == 200
    filas = r.json()
    assert len(filas) == 1
    fila = filas[0]
    assert set(fila.keys()) == {
        "num_serie_factura", "tipo_factura", "fecha_hora_huso",
        "total_con_iva", "cliente", "estado_remision",
    }
    assert fila["tipo_factura"] == "F2"
    assert fila["total_con_iva"] == "5.00"  # PVP con IVA incluido: 2.50 x 2
    assert fila["estado_remision"] == "no_remitido"
    assert fila["cliente"] == {"nombre": None, "nif": None}


def test_endpoint_filtra_por_tipo(cliente_http, admin, datos_base, crear_sesion, motor):
    _login(cliente_http, admin)
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA, serie="T", tipo_factura="F2")
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA, serie="F", tipo_factura="F1")

    r = cliente_http.get("/admin/api/facturas", params={"tipo": "completa"})
    assert r.status_code == 200
    filas = r.json()
    assert len(filas) == 1
    assert filas[0]["tipo_factura"] == "F1"


def test_endpoint_filtra_por_texto_libre(cliente_http, admin, datos_base, session, crear_sesion, motor):
    _login(cliente_http, admin)
    cli = Cliente(nombre="Maria Lopez", nif="55555555Q")
    session.add(cli)
    session.commit()
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA, cliente_id=cli.id)
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA)

    r = cliente_http.get("/admin/api/facturas", params={"q": "Maria"})
    assert r.status_code == 200
    filas = r.json()
    assert len(filas) == 1
    assert filas[0]["cliente"]["nombre"] == "Maria Lopez"


def test_endpoint_filtra_por_estado_remision(cliente_http, admin, datos_base, crear_sesion, motor):
    _login(cliente_http, admin)
    id_aceptado = _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA)
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA)

    with crear_sesion() as s, s.begin():
        reg = s.get(RegistroFiscal, id_aceptado)
        reg.estado_remision = "aceptado"

    r = cliente_http.get("/admin/api/facturas", params={"estado": "no_remitido"})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_endpoint_combina_filtros(cliente_http, admin, datos_base, crear_sesion, motor):
    _login(cliente_http, admin)
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA, serie="T", tipo_factura="F2")
    _emitir(crear_sesion, motor, datos_base["usuario_id"], LINEA, serie="F", tipo_factura="F1")

    r = cliente_http.get(
        "/admin/api/facturas", params={"tipo": "simplificada", "estado": "no_remitido"}
    )
    assert r.status_code == 200
    filas = r.json()
    assert len(filas) == 1
    assert filas[0]["tipo_factura"] == "F2"
