"""Reskin Nocturne de la consola de administracion (Corte 2) + paneles nuevos
(Cierres Z, Clientes). Comprobacion ESTRUCTURAL del HTML/JS servido (sin
navegador, sin motor de plantillas), mismo patron que
tests/test_navegacion.py y tests/test_main.py."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import crear_app


def _html() -> str:
    return TestClient(crear_app()).get("/admin/").text


# --- Fase 2.1: reskin admin.html ------------------------------------------
def test_admin_enlaza_nocturne_css():
    assert '<link rel="stylesheet" href="/static/nocturne.css">' in _html()


def test_admin_sin_cdn():
    html = _html()
    for prohibido in ("unpkg.com", "fonts.googleapis.com", "@import"):
        assert prohibido not in html


def test_admin_conserva_wiring_esencial():
    html = _html()
    assert 'window.esDemo ? "" :' in html
    assert "if (btnSalir)" in html
    assert "Ir al TPV" in html
    assert 'id="salir"' in html


# --- pulido visual: marca compacta (logo-mark.png) antes del h1 de cabecera --
def test_admin_marca_compacta_en_cabecera():
    html = _html()
    inicio = html.index("async function dashboard")
    fin = html.index("function marcarTab")
    bloque = html[inicio:fin]
    assert '/static/img/logo-mark.png' in bloque
    assert 'class="brand-mark-sm"' in bloque
    assert bloque.index("brand-mark-sm") < bloque.index("<h1>TPV AcuaTPV")


# --- Fase 2.2: panel Cierres Z (guardarrail advisory, NO bloqueo duro) -----
def test_admin_tab_cierres_presente():
    html = _html()
    assert 'data-t="cierres"' in html
    assert "pintarCierresZ" in html
    assert "/admin/api/maestros/cierres-z" in html


def _bloque_pintar_cierres_z(html: str) -> str:
    inicio = html.index("async function pintarCierresZ")
    fin = html.index("async function detalleCierreZ")
    return html[inicio:fin]


def test_admin_cierres_generar_exige_doble_confirmacion():
    bloque = _bloque_pintar_cierres_z(_html())
    assert bloque.count("confirm(") >= 2
    assert bloque.index("confirm(") < bloque.index('method: "POST"')


def test_admin_cierres_generar_no_deshabilitado_por_aviso():
    """El aviso de "ya existe un Z de hoy" es advisory: el boton "Generar"
    NUNCA lleva `disabled` (el backend permite varios Z/dia por diseno)."""
    bloque = _bloque_pintar_cierres_z(_html())
    assert 'id="czGenerar"' in bloque
    assert '<button class="accion" id="czGenerar" disabled' not in bloque
    assert "czGenerar.disabled" not in bloque
    assert "yaHoy" in bloque


def test_admin_cierres_aviso_texto_presente():
    bloque = _bloque_pintar_cierres_z(_html())
    assert "ya existe" in bloque.lower() or "ya se genero" in bloque.lower()


def test_admin_cierres_detalle_pinta_desgloses():
    html = _html()
    assert "detalleCierreZ" in html
    assert "desglose_iva" in html
    assert "desglose_pago" in html


def test_admin_cierres_refresca_listado_tras_generar():
    bloque = _bloque_pintar_cierres_z(_html())
    assert "await pintarCierresZ()" in bloque
    assert "await detalleCierreZ(" in bloque


# --- Fase 2.3: panel Clientes CRUD -----------------------------------------
def test_admin_tab_clientes_presente():
    html = _html()
    assert 'data-t="clientes"' in html
    assert "pintarClientes" in html
    assert "/admin/api/maestros/clientes" in html


def test_admin_clientes_alta_usa_dialog_nocturne():
    html = _html()
    inicio = html.index("function modalCliente")
    bloque = html[inicio:]
    assert 'className = "dialog-backdrop"' in bloque
    assert 'class="dialog"' in bloque
    assert 'class="field"' in bloque
    assert 'class="input"' in bloque


def test_admin_clientes_error_se_muestra_sin_cerrar_dialogo():
    html = _html()
    inicio = html.index("function modalCliente")
    bloque = html[inicio:]
    assert '$("#clError", ov).textContent = e.message;' in bloque


def test_admin_clientes_toggle_activo_sin_confirmacion_extra():
    html = _html()
    inicio = html.index("async function pintarClientes")
    fin = html.index("function modalCliente")
    bloque = html[inicio:fin]
    assert "desactivar" in bloque
    assert "activar" in bloque
    assert "confirm(" not in bloque


# --- Fase 2.4: cierre C2 (no regresion) -------------------------------------
def test_tpv_funciones_sin_backend_siguen_deshabilitadas_tras_reskin_admin():
    """No regresion: el reskin de admin.html (Corte 2) no toca tpv.html. De los
    4 botones de funciones maquetados en Corte 1, solo 'Convertir en factura'
    sigue sin backend (`disabled`); 'Aparcar ticket'/'Desaparcar' (aparcar-
    desaparcar) y 'Cliente en venta' (cliente-en-venta) pasaron a tener backend."""
    html = TestClient(crear_app()).get("/tpv/").text
    for texto in ("Convertir en factura", "Aparcar ticket", "Desaparcar", "Cliente en venta"):
        assert texto in html
    assert html.count('<button class="btn fn-btn" disabled') == 1


# --- Fase 6: panel "Convertir en factura" (Requirement: Panel Convertir en factura --
# consola-administracion spec). Smoke estatico, mismo patron que 2.10 en
# cliente-en-venta/tasks.md (sin motor de plantillas, sin navegador). --------------


def test_admin_tab_convertir_presente():
    html = _html()
    assert 'data-t="convertir"' in html
    assert "pintarConvertir" in html
    assert "/admin/api/ventas/convertibles" in html


def _bloque_pintar_convertir(html: str) -> str:
    inicio = html.index("async function pintarConvertir")
    fin = html.index("/* ---- BOTONERAS", inicio)
    return html[inicio:fin]


def test_admin_convertir_multiseleccion_y_form_destinatario():
    bloque = _bloque_pintar_convertir(_html())
    # Multiseleccion 1..N: checkboxes con el id de cada convertible.
    assert 'class="cvSel"' in bloque
    assert "value=\"${v.id}\"" in bloque
    # Form inline NIF + nombre + domicilio.
    assert 'id="cvNif"' in bloque
    assert 'id="cvNombre"' in bloque
    assert 'id="cvDomicilio"' in bloque


def test_admin_convertir_boton_confirma_y_llama_endpoint():
    bloque = _bloque_pintar_convertir(_html())
    assert "Convertir en factura" in bloque
    assert "confirm(" in bloque
    assert "/admin/api/ventas/convertir" in bloque
    assert 'method: "POST"' in bloque


def test_admin_convertir_refresca_listado_tras_exito():
    bloque = _bloque_pintar_convertir(_html())
    assert "await pintarConvertir()" in bloque
    # Muestra la referencia (num_serie) de la F3 resultante tras convertir.
    assert "r.num_serie" in bloque


def test_admin_convertir_confirmacion_sobrevive_al_refresco():
    """Regresion: el refresco (`await pintarConvertir()`) reescribe
    `#main.innerHTML` completo, lo que DESTRUYE cualquier nodo `#cvMsg` fijado
    ANTES del refresco -- el operador nunca llegaba a ver el `num_serie` de la
    F3 en el camino feliz (objetivo declarado de la tarea 6.1). No hay capa de
    test de navegador/motor de plantillas en este repo (mismo patron estatico
    que el resto de `test_admin_ui.py`): esta prueba asegura, a nivel de
    ORDEN EN EL FUENTE, que la asignacion de `#cvMsg` con el mensaje de exito
    ocurre DESPUES de `await pintarConvertir()` (sobre el nodo recien
    reconstruido), nunca antes."""
    bloque = _bloque_pintar_convertir(_html())
    pos_refresco = bloque.index("await pintarConvertir()")
    pos_confirmacion = bloque.index('$("#cvMsg").textContent = `Convertido en factura')
    assert pos_confirmacion > pos_refresco
