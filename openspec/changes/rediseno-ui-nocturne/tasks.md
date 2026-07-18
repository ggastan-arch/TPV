# Tasks: Rediseño de UI — sistema Nocturne

> STRICT TDD. `.venv/Scripts/python -m pytest`. Cada bloque: RED (test que falla) → GREEN
> (mínimo para pasar). Tests estructurales (substrings/IDs/atributos del HTML servido, sin
> navegador). Ninguna tarea arranca marcada.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | C1 ~650-800 (dominado por assets vendorizados: css/icons/fuente); C2 ~500-650 |
| 400-line budget risk | High (ambos cortes) |
| Chained PRs recommended | Yes — ya decidido por corte (C1/C2) |
| Suggested split | PR 1 = Corte 1 (base: main) · PR 2 = Corte 2 (base: main, tras fusionar PR 1) |
| Delivery strategy | ask-on-risk (sin override explícito recibido) |
| Chain strategy | stacked-to-main (inferido de design.md: "C1 debe fusionar antes de C2") — confirmar |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Corte 1: assets Nocturne + reskin `tpv.html`/`landing.html` | PR 1 | base `main`; `nocturne.css`/`nocturne-icons.js`/fuente son candidatos a `size:exception` (vendor, bajo esfuerzo real de revisión pese al recuento de líneas) |
| 2 | Corte 2: reskin `admin.html` + panel Cierre Z + panel Clientes | PR 2 | base `main` tras fusionar PR 1; fallback si el diff real supera ~450: 2a (admin + Cierre Z) / 2b (Clientes) como PR 3, misma base `main` |

## Corte 1 (PR#1) — assets Nocturne + reskin tpv/landing

### Fase 1.1 — Assets estáticos
- [x] 1.1.1 RED `tests/test_estatico_nocturne.py` (nuevo): `/static/nocturne.css` 200 contiene `--color-accent`, sin `@import`/`fonts.googleapis.com`; `/static/nocturne-icons.js` 200 contiene `window.ICONOS`/`function icono(`
- [x] 1.1.2 GREEN `app/ui/static/nocturne.css`: copia de `design/nocturne/styles.css` sin la línea `@import`, + bloque `@font-face` Inter al inicio
- [x] 1.1.3 GREEN descargar (build-time) `InterVariable.woff2` a `app/ui/static/fonts/`; fallback `system-ui` si el binario falta
- [x] 1.1.4 GREEN `app/ui/static/nocturne-icons.js`: `window.ICONOS` + `icono(nombre, attrs)` con los ~20 SVG Phosphor (MIT) reales listados en design.md → File Changes; NO inventar path data
- [x] 1.1.5 RED `tests/test_main.py`: `crear_app()` sirve `GET /static/nocturne.css` (200)
- [x] 1.1.6 GREEN `app/main.py`: `app.mount("/static", StaticFiles(app/ui/static), name="static")`

### Fase 1.2 — Reskin `tpv.html`
- [x] 1.2.1 RED `tests/test_main.py`: `/tpv/` enlaza `/static/nocturne.css`+`nocturne-icons.js` (sin `unpkg.com`/`googleapis`); conserva `id="grid"`,`id="carrito"`,`id="total"`,`id="buscarInput"`,`id="demoBanner"`,`id="usuario"`,`/tpv/api/`,`irInicio()`,`abrirCobro()`,`vaciar()`; hoja puente declara `min-height:48px`; "Convertir en factura" presente con `disabled` y sin `fetch` asociado
- [x] 1.2.2 GREEN `app/ui/tpv.html`: quitar `:root` propio; enlazar assets; `<style>` puente remapeando `.btn/.grid/.col-carrito/.linea/.total/.overlay/.modal/.pinpad/.rapidos/.pin-display/.campo/.buscador/#demoBanner` a tokens + `#app .btn{min-height:48px}`; `pintarContenido` cae a `icono()` si `imagen==""`; añadir a la barra de funciones "Convertir en factura"/"Aparcar ticket"/"Desaparcar"/"Cliente en venta" deshabilitados (sin handler); JS/IDs intactos

### Fase 1.3 — Reskin `landing.html`
- [x] 1.3.1 RED `tests/test_main.py`: `/` conserva `href="/tpv/"`,`href="/admin/"`,`#demoBadge`,`#demoBlocks`,`fetch("/health")`; usa clases `.card`/`.tag`/`.table`; sin CDN
- [x] 1.3.2 GREEN `app/ui/landing.html`: markup a clases Nocturne; enlazar `nocturne.css`; conservar enlaces/bloques/script existentes

### Fase 1.4 — Cierre C1
- [x] 1.4.1 `pytest` verde completo, sin tocar `admin.html` (Corte 2); confirmar 0 diffs en `dominio`/`aplicacion`/`fiscal`

## Corte 2 (PR#2, base `main` tras fusionar C1) — reskin admin + paneles

### Fase 2.1 — Reskin `admin.html`
- [ ] 2.1.1 RED `tests/test_navegacion.py::test_salir_presente_en_produccion`: actualizar la aserción en lock-step con el nuevo markup de "Salir"
- [ ] 2.1.2 RED `tests/test_admin_ui.py` (nuevo): `/admin/` enlaza `/static/nocturne.css`; conserva `window.esDemo ? "" :`,`if (btnSalir)`,"Ir al TPV"; sin CDN
- [ ] 2.1.3 GREEN `app/ui/admin.html`: enlazar `nocturne.css`; `<style>` puente para clases JS-generadas (`.card/.tabs/table/button.accion/.modal/.overlay`); conservar verbatim el bloque de perfil/"Salir"

### Fase 2.2 — Panel Cierre Z (guardarraíl advisory, NO bloqueo duro)
- [ ] 2.2.1 RED `tests/test_admin_ui.py`: pestaña `data-t="cierres"` usa `pintarCierresZ` y `/admin/api/maestros/cierres-z`; "Generar" exige doble confirmación antes del `POST`
- [ ] 2.2.2 RED mismo archivo: tras generar, el listado y `detalleCierreZ` (desglose IVA/pago) se actualizan
- [ ] 2.2.3 RED mismo archivo: con un Z de hoy ya existente se muestra un aviso junto a "Generar"; el botón sigue habilitado (advisory, sin `disabled` — el backend permite varios Z/día)
- [ ] 2.2.4 GREEN `app/ui/admin.html`: `pintarCierresZ`/`detalleCierreZ`; doble `confirm()` antes del `POST`; aviso no bloqueante si hay Z de hoy
- [ ] 2.2.5 Alinear `specs/consola-administracion/spec.md`: corregir el escenario "Bloqueo de un segundo cierre" (dice "deshabilitando 'Generar'") a advisory, para no contradecir design.md — ver Risks del resumen

### Fase 2.3 — Panel Clientes CRUD
- [ ] 2.3.1 RED `tests/test_admin_ui.py`: pestaña `data-t="clientes"` usa `pintarClientes` y `/admin/api/maestros/clientes`
- [ ] 2.3.2 RED mismo archivo: alta con NIF inválido muestra el 422 del backend sin crear el cliente
- [ ] 2.3.3 RED mismo archivo: "Desactivar"/"Activar" alternan `activo` sin confirmación adicional
- [ ] 2.3.4 GREEN `app/ui/admin.html`: `pintarClientes`/`modalCliente` (alta/edición); botones activar/desactivar

### Fase 2.4 — Cierre C2
- [ ] 2.4.1 RED `tests/test_admin_ui.py`: las entradas sin backend maquetadas en Corte 1 siguen `disabled` tras el reskin de admin
- [ ] 2.4.2 `pytest` verde completo; confirmar 0 diffs en `dominio`/`aplicacion`/`fiscal`
