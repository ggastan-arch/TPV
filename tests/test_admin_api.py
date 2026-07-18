"""Consola de administracion: auth con sesion, panel fiscal, informe y maestros."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _helpers import construir_venta
from app.presentacion.deps import get_session, get_uow
import app.infraestructura.imagenes as imagenes_mod
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL
from app.main import crear_app
from app.infraestructura.persistencia.modelos import Articulo, Familia, LogAuditoria, Usuario


@pytest.fixture
def admin(session, datos_base):
    u = Usuario(nombre="jefa", pin_hash=hash_pin("secreta123"), rol="administracion")
    session.add(u)
    session.commit()
    return {"nombre": "jefa", "password": "secreta123", "usuario_id": u.id}


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
    return TestClient(app)


def _login(cliente, admin):
    return cliente.post("/admin/api/login",
                        json={"nombre": admin["nombre"], "password": admin["password"]})


def test_endpoint_protegido_exige_sesion(cliente, admin):
    assert cliente.get("/admin/api/me").status_code == 401
    assert cliente.get("/admin/api/fiscal/estado").status_code == 401


def test_login_solo_admin(cliente, admin, datos_base):
    # Usuario con rol 'venta' no entra a la consola.
    assert cliente.post("/admin/api/login",
                        json={"nombre": "dependiente", "password": "0000"}).status_code == 401
    # Password incorrecta.
    assert cliente.post("/admin/api/login",
                        json={"nombre": "jefa", "password": "mal"}).status_code == 401
    # Admin correcto.
    assert _login(cliente, admin).status_code == 200


def test_require_admin_demo_devuelve_primer_administrador_activo(session, datos_base):
    """`require_admin_demo` (acceso libre en modo demo, ver `crear_app`) resuelve
    el usuario_id SIN sesion: siempre el primer `Usuario` `rol='administracion'`
    activo sembrado (menor id)."""
    from app.presentacion.admin import require_admin_demo

    admin1 = Usuario(nombre="admin1", pin_hash=hash_pin("1111"), rol="administracion")
    admin2 = Usuario(nombre="admin2", pin_hash=hash_pin("2222"), rol="administracion")
    session.add_all([admin1, admin2])
    session.commit()

    assert require_admin_demo(session) == admin1.id


def test_flujo_completo(cliente, admin):
    assert _login(cliente, admin).status_code == 200
    assert cliente.get("/admin/api/me").json()["nombre"] == "jefa"

    estado = cliente.get("/admin/api/fiscal/estado").json()
    assert "declaracion_responsable" in estado
    assert estado["cola"]["certificado_configurado"] is False
    assert estado["cadena"]["ok"] is True

    assert cliente.get("/admin/api/informes/dia").status_code == 200
    assert cliente.get("/admin/api/maestros/articulos").status_code == 200
    assert cliente.get("/admin/api/maestros/usuarios").status_code == 200

    assert cliente.post("/admin/api/logout").status_code == 200
    assert cliente.get("/admin/api/me").status_code == 401


def test_maestros_usuarios_no_exponen_hash(cliente, admin):
    _login(cliente, admin)
    usuarios = cliente.get("/admin/api/maestros/usuarios").json()
    assert all("pin_hash" not in u for u in usuarios)
    assert any(u["nombre"] == "jefa" for u in usuarios)


def test_acceso_queda_en_auditoria(cliente, admin, crear_sesion):
    _login(cliente, admin)
    with crear_sesion() as s:
        assert s.query(LogAuditoria).filter_by(accion="acceso_admin").count() >= 1


def test_reintentar_sin_certificado(cliente, admin):
    _login(cliente, admin)
    r = cliente.post("/admin/api/fiscal/reintentar")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ok"] is False
    assert "Certificado" in cuerpo["mensaje"]


def test_reencolar_registro_inexistente_da_404(cliente, admin):
    _login(cliente, admin)
    r = cliente.post("/admin/api/fiscal/reencolar", json={"registro_id": 999999})
    assert r.status_code == 404


def test_reencolar_exige_sesion(cliente):
    r = cliente.post("/admin/api/fiscal/reencolar", json={"registro_id": 1})
    assert r.status_code == 401


def test_fiscal_estado_expone_ultimo_error(cliente, admin, crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(venta)
        reg = motor.emit(s, venta)
        reg_id = reg.id
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(
            repo.buscar(reg_id), "rechazado", codigo_error="4109",
            descripcion="Cabecera incorrecta", estado_remision_final="requiere_intervencion")

    _login(cliente, admin)
    # Dos consultas sucesivas, SIN ninguna nueva remision entre medio: el conteo y el
    # ultimo error deben seguir visibles (no son un dato efimero de una unica respuesta).
    estado1 = cliente.get("/admin/api/fiscal/estado").json()
    estado2 = cliente.get("/admin/api/fiscal/estado").json()
    for estado in (estado1, estado2):
        assert estado["cola"]["requiere_intervencion"] == 1
        assert estado["ultimo_error"]["codigo"] == "4109"
        assert estado["ultimo_error"]["descripcion"] == "Cabecera incorrecta"
        assert estado["ultimo_error"]["num_serie"] is not None
        assert estado["ultimo_error"]["registro_id"] == reg_id


def test_reencolar_devuelve_a_pendiente_via_endpoint(cliente, admin, crear_sesion, motor, datos_base):
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(venta)
        reg = motor.emit(s, venta)
        reg_id = reg.id
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(
            repo.buscar(reg_id), "rechazado", codigo_error="4109",
            descripcion="Cabecera incorrecta", estado_remision_final="requiere_intervencion")

    _login(cliente, admin)
    r = cliente.post("/admin/api/fiscal/reencolar", json={"registro_id": reg_id})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.buscar(reg_id).estado_remision == "pendiente"
        assert s.query(LogAuditoria).filter_by(
            accion="reencolar_remision", entidad_id=str(reg_id)).count() == 1


def test_reencolar_rechaza_si_no_requiere_intervencion_via_endpoint(
    cliente, admin, crear_sesion, motor, datos_base,
):
    """Fix de WARNING de verify: el endpoint no debe reencolar un registro que no
    esta en 'requiere_intervencion' (aqui, uno ya 'aceptado')."""
    with crear_sesion() as s, s.begin():
        venta = construir_venta(datos_base["usuario_id"], [("Neon", "2.50", "1", "21")])
        s.add(venta)
        reg = motor.emit(s, venta)
        reg_id = reg.id
    with crear_sesion() as s, s.begin():
        repo = UnidadDeTrabajoSQL(s).registros
        repo.registrar_resultado(repo.buscar(reg_id), "aceptado", csv="CSV-1")

    _login(cliente, admin)
    r = cliente.post("/admin/api/fiscal/reencolar", json={"registro_id": reg_id})
    assert r.status_code == 409

    with crear_sesion() as s:
        repo = UnidadDeTrabajoSQL(s).registros
        assert repo.buscar(reg_id).estado_remision == "aceptado"
        assert s.query(LogAuditoria).filter_by(
            accion="reencolar_remision", entidad_id=str(reg_id)).count() == 0


# --- Maestros: alta/edicion/baja de articulos ----------------------------------
def _nuevo_articulo(datos_base, **extra):
    cuerpo = {"nombre": "Neon cardenal", "nombre_corto": "Neon",
              "tipo_iva_id": datos_base["iva21_id"], "pvp": "2.50"}
    cuerpo.update(extra)
    return cuerpo


def test_crear_articulo_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/articulos",
                        json=_nuevo_articulo(datos_base)).status_code == 401


def test_crear_articulo_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos", json=_nuevo_articulo(datos_base))
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    articulos = cliente.get("/admin/api/maestros/articulos").json()
    assert any(a["id"] == nuevo_id and a["nombre"] == "Neon cardenal" for a in articulos)


def test_crear_articulo_tipo_iva_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos",
                     json=_nuevo_articulo(datos_base, tipo_iva_id=999999))
    assert r.status_code == 422


def test_crear_articulo_modo_precio_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos",
                     json=_nuevo_articulo(datos_base, modo_precio="otro"))
    assert r.status_code == 422


def test_actualizar_articulo_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.put("/admin/api/maestros/articulos/999999", json=_nuevo_articulo(datos_base))
    assert r.status_code == 404


def test_desactivar_articulo(cliente, admin, datos_base):
    _login(cliente, admin)
    nuevo_id = cliente.post("/admin/api/maestros/articulos",
                            json=_nuevo_articulo(datos_base)).json()["id"]
    assert cliente.post(f"/admin/api/maestros/articulos/{nuevo_id}/desactivar").status_code == 200
    articulos = cliente.get("/admin/api/maestros/articulos").json()
    assert any(a["id"] == nuevo_id and a["activo"] is False for a in articulos)


def test_listado_articulos_expone_campos_editables_sin_extra(cliente, admin, datos_base):
    # CRITICAL (verify modos-precio): el modal de edicion perdia familia/coste/color/icono
    # porque el DTO de lectura no los exponia. Caso sin datos opcionales -> null.
    _login(cliente, admin)
    nuevo_id = cliente.post("/admin/api/maestros/articulos",
                            json=_nuevo_articulo(datos_base)).json()["id"]
    articulo = next(a for a in cliente.get("/admin/api/maestros/articulos").json()
                    if a["id"] == nuevo_id)
    assert articulo["nombre_corto"] == "Neon"
    assert articulo["tipo_iva_id"] == datos_base["iva21_id"]
    assert articulo["familia_id"] is None
    assert articulo["coste"] is None
    assert articulo["color_boton"] is None
    assert articulo["icono"] is None


def test_listado_articulos_expone_campos_editables_completos(cliente, admin, datos_base):
    # Caso con todos los campos opcionales completados -> el DTO debe conservarlos
    # (sin esto, el modal de edicion los pisa a null/hardcodeado al guardar).
    _login(cliente, admin)
    familia_id = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]
    nuevo_id = cliente.post(
        "/admin/api/maestros/articulos",
        json=_nuevo_articulo(datos_base, nombre_corto="Neon-c", familia_id=familia_id,
                             coste="1.20", color_boton="#ff0000", icono="pez.svg"),
    ).json()["id"]
    articulo = next(a for a in cliente.get("/admin/api/maestros/articulos").json()
                    if a["id"] == nuevo_id)
    assert articulo["nombre_corto"] == "Neon-c"
    assert articulo["tipo_iva_id"] == datos_base["iva21_id"]
    assert articulo["familia_id"] == familia_id
    assert articulo["coste"] == "1.20"
    assert articulo["color_boton"] == "#ff0000"
    assert articulo["icono"] == "pez.svg"


# --- Maestros: tipos de IVA ----------------------------------------------------
def test_crear_tipo_iva_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/tipos-iva",
                        json={"nombre": "Superreducido", "porcentaje": "4.00"}).status_code == 401


def test_crear_tipo_iva_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/tipos-iva",
                     json={"nombre": "Superreducido 4%", "porcentaje": "4.00"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    tipos = cliente.get("/admin/api/maestros/tipos-iva").json()
    assert any(t["id"] == nuevo_id and t["porcentaje"] == "4.00" for t in tipos)


def test_crear_tipo_iva_porcentaje_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/tipos-iva",
                     json={"nombre": "Malo", "porcentaje": "-1"})
    assert r.status_code == 422


def test_actualizar_tipo_iva_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.put("/admin/api/maestros/tipos-iva/999999",
                    json={"nombre": "X", "porcentaje": "21.00"})
    assert r.status_code == 404


# --- Maestros: familias --------------------------------------------------------
def test_crear_familia_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/familias",
                        json={"nombre": "Peces"}).status_code == 401


def test_crear_familia_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    familias = cliente.get("/admin/api/maestros/familias").json()
    assert any(f["id"] == nuevo_id and f["nombre"] == "Peces" for f in familias)


def test_crear_familia_padre_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/familias",
                     json={"nombre": "Huerfana", "parent_id": 999999})
    assert r.status_code == 422


def test_reasignar_padre_ciclo_devuelve_422(cliente, admin, datos_base):
    _login(cliente, admin)
    padre = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]
    hijo = cliente.post("/admin/api/maestros/familias",
                        json={"nombre": "Ciclidos", "parent_id": padre}).json()["id"]
    # Intentar que el padre cuelgue de su hijo -> ciclo.
    r = cliente.put(f"/admin/api/maestros/familias/{padre}",
                    json={"nombre": "Peces", "parent_id": hijo})
    assert r.status_code == 422


def test_desactivar_familia_con_hijos_devuelve_409(cliente, admin, datos_base):
    _login(cliente, admin)
    padre = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]
    cliente.post("/admin/api/maestros/familias", json={"nombre": "Ciclidos", "parent_id": padre})
    r = cliente.post(f"/admin/api/maestros/familias/{padre}/desactivar")
    assert r.status_code == 409


def test_listado_maestros_familias_expone_visible_en_tactil(cliente, admin, datos_base):
    _login(cliente, admin)
    visible_id = cliente.post("/admin/api/maestros/familias",
                              json={"nombre": "Peces"}).json()["id"]
    oculta_id = cliente.post("/admin/api/maestros/familias",
                             json={"nombre": "Peces escaneo",
                                   "visible_en_tactil": False}).json()["id"]

    familias = cliente.get("/admin/api/maestros/familias").json()

    por_id = {f["id"]: f for f in familias}
    assert por_id[visible_id]["visible_en_tactil"] is True
    assert por_id[oculta_id]["visible_en_tactil"] is False


def test_listado_maestros_familias_expone_orden_y_color(cliente, admin, datos_base):
    # El modal de edicion de familia reemplaza la ficha completa (PUT); si el
    # listado no expone `orden` y `color`, editar cualquier campo los resetearia
    # (orden gobierna el ordenado de la navegacion tactil).
    _login(cliente, admin)
    fam_id = cliente.post("/admin/api/maestros/familias",
                          json={"nombre": "Material", "orden": 7,
                                "color": "#123456"}).json()["id"]

    familias = cliente.get("/admin/api/maestros/familias").json()

    por_id = {f["id"]: f for f in familias}
    assert por_id[fam_id]["orden"] == 7
    assert por_id[fam_id]["color"] == "#123456"


# --- Maestros: clientes --------------------------------------------------------
def test_crear_cliente_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/clientes",
                        json={"nombre": "Cliente"}).status_code == 401


def test_crear_cliente_ok(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/clientes",
                     json={"nombre": "Acuario S.L.", "nif": "a58818501"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    clientes = cliente.get("/admin/api/maestros/clientes").json()
    assert any(c["id"] == nuevo_id and c["nif"] == "A58818501" for c in clientes)


def test_crear_cliente_nif_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/clientes",
                     json={"nombre": "Malo", "nif": "12345678A"})
    assert r.status_code == 422


def test_actualizar_cliente_inexistente(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.put("/admin/api/maestros/clientes/999999", json={"nombre": "X"})
    assert r.status_code == 404


# --- Maestros: usuarios --------------------------------------------------------
def test_crear_usuario_exige_sesion(cliente, datos_base):
    assert cliente.post("/admin/api/maestros/usuarios",
                        json={"nombre": "cajera", "rol": "venta", "pin": "1234"}).status_code == 401


def test_crear_usuario_ok_sin_exponer_hash(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/usuarios",
                     json={"nombre": "cajera", "rol": "venta", "pin": "1234"})
    assert r.status_code == 201
    nuevo_id = r.json()["id"]
    usuarios = cliente.get("/admin/api/maestros/usuarios").json()
    fila = next(u for u in usuarios if u["id"] == nuevo_id)
    assert fila["rol"] == "venta"
    assert "pin_hash" not in fila and "pin" not in fila


def test_crear_usuario_rol_invalido(cliente, admin, datos_base):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/usuarios",
                     json={"nombre": "x", "rol": "jefe", "pin": "1234"})
    assert r.status_code == 422


def test_desactivar_ultimo_admin_devuelve_409(cliente, admin, datos_base):
    # 'admin' (jefa) es el unico administrador activo: no puede autodesactivarse.
    _login(cliente, admin)
    r = cliente.post(f"/admin/api/maestros/usuarios/{admin['usuario_id']}/desactivar")
    assert r.status_code == 409


# --- Maestros: subida de imagen (articulo y familia) ----------------------------
# El tipo se detecta SIEMPRE por los bytes reales (nunca por el content-type
# declarado en la subida multipart): estos tests fuerzan un content-type
# "correcto" con contenido falso para probar justo esa superficie de seguridad.
_JPEG_VALIDO = b"\xff\xd8\xff\xe0" + b"JFIF" + b"\x00" * 200
_PNG_VALIDO = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
_TEXTO_DISFRAZADO_DE_JPEG = b"esto no es una imagen real, es texto plano" * 20


@pytest.fixture
def media_tmp(tmp_path, monkeypatch):
    # Subdirectorio propio: `tmp_path` tambien aloja `test.db` (fixture `engine`
    # en conftest.py) y no debe confundirse con el contenido de MEDIA_DIR.
    destino = tmp_path / "media"
    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", destino)
    return destino


def _archivos_en(media_dir) -> list:
    """Lista los archivos de `media_dir`; vacio (sin lanzar) si aun no existe
    (rechazo antes de escribir disco -> el directorio nunca llega a crearse)."""
    return list(media_dir.iterdir()) if media_dir.exists() else []


def test_subir_imagen_articulo_valida_persiste_archivo_ruta_y_auditoria(
    cliente, admin, datos_base, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    articulo_id = cliente.post("/admin/api/maestros/articulos",
                               json=_nuevo_articulo(datos_base)).json()["id"]

    r = cliente.post(f"/admin/api/maestros/articulos/{articulo_id}/imagen",
                     files={"archivo": ("foto.jpg", _JPEG_VALIDO, "image/jpeg")})
    assert r.status_code == 200
    ruta = r.json()["imagen"]
    assert ruta.startswith("/media/articulo-")

    assert (media_tmp / ruta.removeprefix("/media/")).exists()

    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).imagen == ruta
        assert s.query(LogAuditoria).filter_by(accion="cambiar_imagen_articulo").count() == 1

    # El listado de solo lectura de maestros expone la ruta persistida.
    articulos = cliente.get("/admin/api/maestros/articulos").json()
    assert next(a for a in articulos if a["id"] == articulo_id)["imagen"] == ruta


def test_subir_imagen_articulo_tipo_invalido_no_persiste_nada(
    cliente, admin, datos_base, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    articulo_id = cliente.post("/admin/api/maestros/articulos",
                               json=_nuevo_articulo(datos_base)).json()["id"]

    r = cliente.post(f"/admin/api/maestros/articulos/{articulo_id}/imagen",
                     files={"archivo": ("foto.jpg", _TEXTO_DISFRAZADO_DE_JPEG, "image/jpeg")})
    assert r.status_code == 422
    assert _archivos_en(media_tmp) == []
    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).imagen is None


def test_subir_imagen_articulo_tamano_excedido_no_persiste_nada(
    cliente, admin, datos_base, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    articulo_id = cliente.post("/admin/api/maestros/articulos",
                               json=_nuevo_articulo(datos_base)).json()["id"]

    contenido_grande = _JPEG_VALIDO + b"\x00" * (3 * 1024 * 1024)
    r = cliente.post(f"/admin/api/maestros/articulos/{articulo_id}/imagen",
                     files={"archivo": ("foto.jpg", contenido_grande, "image/jpeg")})
    assert r.status_code == 422
    assert _archivos_en(media_tmp) == []
    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).imagen is None


def test_reemplazar_imagen_articulo_borra_la_anterior(
    cliente, admin, datos_base, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    articulo_id = cliente.post("/admin/api/maestros/articulos",
                               json=_nuevo_articulo(datos_base)).json()["id"]

    r1 = cliente.post(f"/admin/api/maestros/articulos/{articulo_id}/imagen",
                      files={"archivo": ("a.jpg", _JPEG_VALIDO, "image/jpeg")})
    ruta_a = r1.json()["imagen"]
    archivo_a = media_tmp / ruta_a.removeprefix("/media/")
    assert archivo_a.exists()

    r2 = cliente.post(f"/admin/api/maestros/articulos/{articulo_id}/imagen",
                      files={"archivo": ("b.png", _PNG_VALIDO, "image/png")})
    ruta_b = r2.json()["imagen"]
    assert ruta_b != ruta_a
    assert not archivo_a.exists()  # la anterior se borro
    assert (media_tmp / ruta_b.removeprefix("/media/")).exists()

    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).imagen == ruta_b


def test_subir_imagen_articulo_inexistente_da_404_sin_escribir_disco(cliente, admin, media_tmp):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/articulos/999999/imagen",
                     files={"archivo": ("a.jpg", _JPEG_VALIDO, "image/jpeg")})
    assert r.status_code == 404
    assert _archivos_en(media_tmp) == []


def test_subir_imagen_articulo_sin_sesion_da_401(cliente, media_tmp):
    r = cliente.post("/admin/api/maestros/articulos/1/imagen",
                     files={"archivo": ("a.jpg", _JPEG_VALIDO, "image/jpeg")})
    assert r.status_code == 401


def test_subir_imagen_familia_valida_persiste_archivo_ruta_y_auditoria(
    cliente, admin, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    familia_id = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]

    r = cliente.post(f"/admin/api/maestros/familias/{familia_id}/imagen",
                     files={"archivo": ("foto.png", _PNG_VALIDO, "image/png")})
    assert r.status_code == 200
    ruta = r.json()["imagen"]
    assert ruta.startswith("/media/familia-")
    assert (media_tmp / ruta.removeprefix("/media/")).exists()

    with crear_sesion() as s:
        assert s.get(Familia, familia_id).imagen == ruta
        assert s.query(LogAuditoria).filter_by(accion="cambiar_imagen_familia").count() == 1

    familias = cliente.get("/admin/api/maestros/familias").json()
    assert next(f for f in familias if f["id"] == familia_id)["imagen"] == ruta


def test_subir_imagen_familia_tipo_invalido_no_persiste_nada(
    cliente, admin, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    familia_id = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]

    r = cliente.post(f"/admin/api/maestros/familias/{familia_id}/imagen",
                     files={"archivo": ("foto.png", _TEXTO_DISFRAZADO_DE_JPEG, "image/png")})
    assert r.status_code == 422
    assert _archivos_en(media_tmp) == []
    with crear_sesion() as s:
        assert s.get(Familia, familia_id).imagen is None


def test_reemplazar_imagen_familia_cuando_la_anterior_ya_no_existe_en_disco_no_bloquea(
    cliente, admin, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    familia_id = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]

    r1 = cliente.post(f"/admin/api/maestros/familias/{familia_id}/imagen",
                      files={"archivo": ("a.png", _PNG_VALIDO, "image/png")})
    ruta_a = r1.json()["imagen"]
    (media_tmp / ruta_a.removeprefix("/media/")).unlink()  # se borra manualmente antes del reemplazo

    r2 = cliente.post(f"/admin/api/maestros/familias/{familia_id}/imagen",
                      files={"archivo": ("b.jpg", _JPEG_VALIDO, "image/jpeg")})
    assert r2.status_code == 200
    ruta_b = r2.json()["imagen"]
    with crear_sesion() as s:
        assert s.get(Familia, familia_id).imagen == ruta_b


def test_subir_imagen_familia_inexistente_da_404_sin_escribir_disco(cliente, admin, media_tmp):
    _login(cliente, admin)
    r = cliente.post("/admin/api/maestros/familias/999999/imagen",
                     files={"archivo": ("a.png", _PNG_VALIDO, "image/png")})
    assert r.status_code == 404
    assert _archivos_en(media_tmp) == []


def test_subir_imagen_familia_sin_sesion_da_401(cliente, media_tmp):
    r = cliente.post("/admin/api/maestros/familias/1/imagen",
                     files={"archivo": ("a.png", _PNG_VALIDO, "image/png")})
    assert r.status_code == 401


# --- cierre de la ruta arbitraria: "imagen" en el PUT JSON se ignora -----------
def test_put_familia_con_imagen_en_el_body_se_ignora(
    cliente, admin, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    familia_id = cliente.post("/admin/api/maestros/familias", json={"nombre": "Peces"}).json()["id"]
    cliente.post(f"/admin/api/maestros/familias/{familia_id}/imagen",
                files={"archivo": ("foto.png", _PNG_VALIDO, "image/png")})
    with crear_sesion() as s:
        ruta_original = s.get(Familia, familia_id).imagen
    assert ruta_original is not None

    r = cliente.put(f"/admin/api/maestros/familias/{familia_id}",
                    json={"nombre": "Peces tropicales", "imagen": "/media/ruta-inyectada.png"})
    assert r.status_code == 200
    with crear_sesion() as s:
        fam = s.get(Familia, familia_id)
        assert fam.nombre == "Peces tropicales"
        assert fam.imagen == ruta_original  # el campo del body JSON se ignora


def test_put_articulo_con_imagen_en_el_body_se_ignora(
    cliente, admin, datos_base, crear_sesion, media_tmp,
):
    _login(cliente, admin)
    articulo_id = cliente.post("/admin/api/maestros/articulos",
                               json=_nuevo_articulo(datos_base)).json()["id"]
    cliente.post(f"/admin/api/maestros/articulos/{articulo_id}/imagen",
                files={"archivo": ("foto.jpg", _JPEG_VALIDO, "image/jpeg")})
    with crear_sesion() as s:
        ruta_original = s.get(Articulo, articulo_id).imagen
    assert ruta_original is not None

    r = cliente.put(f"/admin/api/maestros/articulos/{articulo_id}",
                    json={**_nuevo_articulo(datos_base), "imagen": "/media/ruta-inyectada.jpg"})
    assert r.status_code == 200
    with crear_sesion() as s:
        assert s.get(Articulo, articulo_id).imagen == ruta_original
