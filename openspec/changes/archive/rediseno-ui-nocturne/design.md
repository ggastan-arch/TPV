# Design: Rediseño de UI — sistema Nocturne (primer corte)

## Technical Approach

Reskin puramente de PRESENTACIÓN: cero cambios en `dominio`/`aplicacion`/`fiscal`. Las
tres superficies (`tpv.html`, `admin.html`, `landing.html`) se sirven hoy con `FileResponse`
desde `app/ui/` y llevan `<style>`+`<script>` inline. La estrategia central es
**enlazar Nocturne como hoja global + una hoja "puente" page-scoped** que remapea los nombres
de clase existentes (que el JS genera vía `innerHTML`) sobre los tokens Nocturne, dejando
los `<script>` y todos los IDs/handlers BYTE A BYTE intactos donde el JS construye markup
(camino de cobro del TPV, editor de botonera). El markup estático (landing, nuevos paneles)
adopta clases Nocturne directas (`.card`, `.table`, `.btn`, `.field`, `.dialog`, `.tag`).
Esto minimiza el riesgo de romper el wiring —el riesgo alto del proposal— y a la vez unifica
el look, porque ambas vías consumen los mismos tokens/escala.

Restricción dura: el cobro debe funcionar sin red. Se **vendoriza** una copia servible de
`styles.css` con el `@import` de Google Fonts ELIMINADO, se autohospeda Inter y los iconos
Phosphor pasan a **SVG inline** (mapa JS). Ningún `@import`, `googleapis` ni `unpkg`.

## Architecture Decisions

| Decisión | Alternativa rechazada | Motivo |
|----------|-----------------------|--------|
| Nuevo mount `/static` desde `app/ui/static/`; vendorizar copia `nocturne.css` | Servir directo desde `design/nocturne/` o symlink | `design/` es la fuente del sistema, no un dir servible; la copia nos deja quitar el `@import` sin mutar la hoja compartida. Co-ubicado con las `*.html` (mismo patrón que `FileResponse` de `app/ui/`) |
| Quitar `@import`; autohospedar `InterVariable.woff2` con `@font-face`; fallback `system-ui` | Mantener `@import` de Google Fonts | El `@import` añade dependencia de red al cobro (inaceptable). El token ya declara `"Inter", system-ui`: si el binario faltara, degrada a `system-ui` sin romper |
| Iconos Phosphor como **SVG inline** vía `/static/nocturne-icons.js` (`window.ICONOS` + `icono(nombre)`), ~20 símbolos, `fill="currentColor"` | CDN unpkg / `<use href>` a sprite externo / font-icon | Sin red; estilable por `currentColor`; encaja con el patrón JS que ya arma botones con `innerHTML`. Un único asset compartido por las 3 páginas |
| Reskin = `<link nocturne.css>` + `<style>` puente page-scoped que remapea clases existentes a tokens | Reescribir todo el markup a clases Nocturne | El JS de TPV/admin genera markup con nombres propios (`.overlay`,`.modal`,`.pinpad`,`.boton-editor`,`.accion`…); reescribirlos toca lógica frágil. El puente conserva JS/IDs intactos |
| Áreas táctiles: override TPV-scoped `#app .btn{min-height:48px}` en el `<style>` de `tpv.html` | Editar la hoja compartida (densidad 0.7×) | No contaminar el sistema para toda la app; el TPV es el único con requisito táctil |
| Tiles con **foto real** primero (`pintarContenido` actual, `/media`+`/media-demo`), fallback icono en placeholder tintado | Iconos de categoría (como el prototipo `.dc`) | Los artículos tienen fotos reales; el prototipo es solo referencia visual. Fallback: `icono()` genérico cuando `imagen==""` |
| Cierre Z: guard de duplicado del día **advisory** (avisar + doble confirmación) | Bloqueo duro en UI | `GenerarCierreZ` NO rechaza un segundo cierre y permite Z de rango vacío POR DISEÑO (docstring). La UI avisa "ya existe Z de hoy (Z-N)" pero no prohíbe (varios Z/día son legales) |
| Funciones sin backend (Convertir F3, Aparcar, Cliente-en-venta) maquetadas `disabled`/"próximamente" | Stub con comportamiento falso | Proposal: sin conducta falsa |

## Data Flow

```
Navegador ─ GET /tpv/ (FileResponse) ─► tpv.html
   │  <link href="/static/nocturne.css">      (tokens + base, SIN @import)
   │  <script src="/static/nocturne-icons.js"> (window.ICONOS → SVG inline)
   ▼
GET /static/nocturne.css      ─► mount StaticFiles(app/ui/static)   [offline]
GET /static/fonts/InterVariable.woff2 ─► @font-face                 [offline]
Fotos de tile ─► /media/… | /media-demo/…  (sin cambios)
Cobro ─► /tpv/api/cobrar (sin red externa: fuentes/iconos locales)  ✔ invariantes 1-7 intactos
```

## File Changes

| File | Action | Integración exacta |
|------|--------|--------------------|
| `app/ui/static/nocturne.css` | Create | Copia de `design/nocturne/styles.css` con la línea `@import` borrada y un bloque `@font-face` de Inter al inicio |
| `app/ui/static/fonts/InterVariable.woff2` | Create | Inter variable autohospedado (fallback `system-ui` si ausente) |
| `app/ui/static/nocturne-icons.js` | Create | `window.ICONOS` (mapa nombre→SVG) + `icono(nombre, attrs)`; ~20 iconos: shopping-cart-simple, house, gear, flask, user-circle, magnifying-glass, receipt, basket, minus, plus, x, caret-left/right, file-text, pause-circle, play-circle, chart-bar, moon-stars, cash-register, money, credit-card, arrow-right, check-circle |
| `app/main.py` | Modify | `app.mount("/static", StaticFiles(directory=str(Path(__file__).parent/"ui"/"static")), name="static")` (incondicional; los assets van commiteados) |
| `app/ui/tpv.html` | Modify | Quitar `:root` ad-hoc; `<link nocturne.css>`+`<script icons>`; `<style>` puente que remapea `.btn/.grid/.col-carrito/.linea/.total/.overlay/.modal/.pinpad/.rapidos/.pin-display/.campo/.buscador/#demoBanner` a tokens + `#app .btn{min-height:48px}`. JS/IDs intactos; `pintarContenido` gana fallback de icono |
| `app/ui/landing.html` | Modify | Markup a `.card/.tag/.table/.btn` Nocturne; conservar `href="/tpv/"`,`href="/admin/"`, `#demoBadge`,`#demoBlocks` y el `<script>` de `/health` |
| `app/ui/admin.html` | Modify | Puente de tokens para clases JS-generadas; nueva pestaña **Clientes** y **Cierres Z**; funciones `pintarClientes`/`modalCliente` y `pintarCierresZ`/`detalleCierreZ`. Conservar verbatim `window.esDemo ? "" :`, `#salir`, `if (btnSalir)`, "Ir al TPV" |
| `tests/test_navegacion.py`, `tests/test_main.py`, `tests/test_admin_api.py` | Modify | Ver Testing Strategy |

## Interfaces / Contracts

```js
// nocturne-icons.js — servido desde /static, offline
window.ICONOS = { "shopping-cart-simple": "<svg …>…</svg>", /* …~20… */ };
function icono(nombre, attrs = "") { return (window.ICONOS[nombre] || "").replace("<svg", `<svg ${attrs}`); }
```
Paneles nuevos (endpoints YA existentes, sin cambio de backend):
- **Cierres Z**: `GET /admin/api/maestros/cierres-z` (lista: numero, fecha_hora_huso, desde/hasta_orden, num_tickets, base_total, cuota_total, total_con_iva) · `GET …/{numero}` (+ `desglose_iva[]`, `desglose_pago[]`) · `POST …/cierres-z` (genera; confirmar antes).
- **Clientes**: `GET /admin/api/maestros/clientes` · `POST` · `PUT …/{id}` · `POST …/{id}/desactivar|activar`. `ClienteReq{nombre, nif?, domicilio?, email?, telefono?, rgpd_consentimiento}`.

## Testing Strategy (TDD — test primero, sin navegador)

| Layer | Qué testear | Enfoque |
|-------|-------------|---------|
| Static/offline | `GET /static/nocturne.css` 200 y contiene `--color-accent`; NO contiene `fonts.googleapis.com` | `TestClient` sobre `crear_app()` |
| Offline HTML | `/tpv/`,`/admin/`,`/` no contienen `unpkg.com` ni `googleapis` | substring |
| TPV wiring | `<link href="/static/nocturne.css">` y IDs/handlers preservados (`id="grid"`,`id="carrito"`,`id="buscarInput"`,`id="total"`, `irInicio()`,`abrirCobro()`,`vaciar()`, `#demoBanner`, `/health`) | substring del servido |
| Landing (no-reg) | `/tpv`,`/admin` presentes (test_main existente) + `#demoBadge` | substring |
| Admin wiring (no-reg) | `window.esDemo ? "" :`, `id="salir"` (string actualizado en lock-step), `if (btnSalir)`, "Ir al TPV" | actualizar `test_salir_presente_en_produccion` al nuevo markup |
| Panel Clientes | admin.html contiene `data-t="clientes"`, `pintarClientes`, `/admin/api/maestros/clientes` | substring |
| Panel Cierre Z | contiene `data-t="cierres"`, `pintarCierresZ`, `/admin/api/maestros/cierres-z` y el confirm/guard | substring |

## Migration / Rollout

Sin migración de esquema/datos. **Corte 1 (PR#1):** assets (`nocturne.css`+`nocturne-icons.js`+fuente) + mount `/static` en `main.py` + reskin `tpv.html` y `landing.html` + tests C1. **Corte 2 (PR#2, apila sobre C1):** reskin `admin.html` + panel Cierre Z + panel Cliente CRUD + tests C2. Único solape: `nocturne.css` (creado en C1, consumido —sin editar— por C2), por eso **C1 debe fusionar antes de C2**. Rollback: restaurar las `*.html`, quitar el mount y borrar `app/ui/static/`.

## Open Questions

- [ ] ¿Vendorizar `InterVariable.woff2` en C1 o degradar a `system-ui` en este corte y autohospedar la fuente en un cambio posterior? (recomendación: incluir la fuente en C1; el fallback protege igualmente).
- [ ] Fallback de icono por categoría en el tile: ¿mapa familia→icono, o un único icono genérico? (recomendación provisional: genérico; el mapa por categoría queda fuera de alcance).
