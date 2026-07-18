# Proposal: Rediseño de UI — sistema Nocturne (primer corte)

## Intent

La UI del TPV, la consola y la portada usa estilos inline ad hoc (`system-ui`, sin
tokens): inconsistente y difícil de mantener. Ya existe un sistema de diseño —**Nocturne**
(oscuro, compacto, acento blurple, Inter + Phosphor, tokens CSS)— con su `styles.css` en
disco. Además, dos funciones ya implementadas en backend no tienen entrada en la UI:
**Cierre Z** y **CRUD de clientes**. Este corte aplica Nocturne a las tres superficies HTML
sin tocar el flujo fiscal/cobro y cablea esas dos funciones a sus endpoints existentes.

## Scope

### In Scope
- Vendorizar `styles.css` como asset estático (nuevo mount en `app/main.py`); cargar Inter + Phosphor.
- Reskin de `tpv.html`, `admin.html`, `landing.html`, **preservando IDs, handlers y fetch a `/tpv/api/*`, `/admin/api/*`, `/health`** (reskin visual, no cambio de comportamiento).
- Nueva UI de consola para **Cierre Z** (generar/listar/detalle) y **Cliente CRUD** (crear/editar/activar/desactivar), cableada a endpoints existentes.
- Maquetar entradas de funciones sin backend (Convertir F3, Aparcar, Cliente-en-venta) **deshabilitadas / "próximamente"**: sin comportamiento falso ni stub.
- Adaptar áreas táctiles del TPV (Nocturne es denso 0.7×; los controles de venta pueden necesitar mayor superficie de toque).

### Out of Scope
- Backend de Convertir F3, Aparcar/desaparcar, Cliente-en-venta (cambios futuros propios).
- Cualquier cambio en motor fiscal, huella/cadena/numeración, triggers de inmutabilidad o lógica de cobro/emisión.

## Non-Goals
- Alterar el comportamiento del flujo de venta o de la remisión fiscal: es reskin + cableado de UI.

## Capabilities

### New Capabilities
- `interfaz-nocturne`: diseño servido como asset + reskin de las tres superficies preservando comportamiento; adaptación táctil; entradas "próximamente" deshabilitadas; conservación del banner `esDemo` y del "Salir" oculto en demo.

### Modified Capabilities
- `consola-administracion`: paneles de Cierre Z (generar/listar/detalle) y de gestión de clientes cableados a los endpoints existentes.

## Approach

Servir `styles.css` (+ fuentes/iconos) desde un nuevo mount estático; reescribir el markup
con clases Nocturne (`.btn`, `.card`, `.field`, `.table`, `.dialog`, `.nav`, `.tag`) y
tokens, manteniendo intactos los `<script>` inline y los contratos de endpoints (o
actualizándolos en lock-step). Añadir paneles de consola que consumen
`GET/POST /admin/api/maestros/cierres-z` y `/admin/api/maestros/clientes`. Actualizar los
tests estructurales de HTML y cubrir los paneles nuevos.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/ui/tpv.html` | Modified | Reskin; preservar JS/IDs; áreas táctiles |
| `app/ui/admin.html` | Modified | Reskin + paneles Cierre Z y Cliente CRUD |
| `app/ui/landing.html` | Modified | Reskin Nocturne |
| `app/main.py` | Modified | Nuevo mount estático (styles.css + fuentes/iconos) |
| assets estáticos | New | `styles.css` vendorizado + Inter/Phosphor |
| `tests/` | Modified | Actualizar tests de HTML; cubrir paneles nuevos |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Romper el wiring JS al reescribir markup | High | Preservar IDs/handlers; actualizar en lock-step; tests estructurales |
| `@import` CDN de Google Fonts en `styles.css` añade dependencia de red al cobro | Med | Self-host de Inter/Phosphor; quitar el `@import` (lo decide sdd-design) |
| Diff muy grande (3 pantallas + 2 paneles) | High | Encadenar PRs por pantalla/panel |
| Densidad 0.7× insuficiente para toque | Med | Override de áreas táctiles en el TPV |

## Rollback Plan

Restaurar las tres `*.html` y quitar el mount estático nuevo; no hay migración de esquema
ni cambios de datos. El backend de Cierre Z/clientes queda intacto (solo se le añade UI).

## Dependencies

- `styles.css` de Nocturne (ya en disco en `design/nocturne/`).
- Endpoints ya existentes de Cierre Z y clientes.

## Success Criteria

- [ ] Las tres superficies renderizan con Nocturne sin regresión (JS y endpoints intactos).
- [ ] Cierre Z operable desde la consola (generar/listar/detalle) contra sus endpoints.
- [ ] Cliente CRUD operable desde la consola (crear/editar/activar/desactivar).
- [ ] Entradas de funciones sin backend visibles pero deshabilitadas ("próximamente").
- [ ] `esDemo` y "Salir" oculto en demo se conservan; el cobro sigue offline.
- [ ] Tests de HTML actualizados y paneles nuevos cubiertos (TDD estricto).
