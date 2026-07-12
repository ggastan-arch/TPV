# Proposal: Modo de precio por artículo (fijo | libre | al peso) + artículos genéricos

## Intent

Hoy el precio de un artículo solo puede ser fijo (PVP de catálogo) o `precio_libre`
(bool: se ingresa el importe al vender). Faltan dos necesidades de la titular:
- **Al peso**: material como maderas y rocas se cobra precio/kg × peso ingresado en la
  venta. Según el artículo, puede ser al peso O libre.
- **Artículos genéricos** (uno de peces, uno de plantas, uno de material), PVP 0 en modo
  libre, que al vender FUERZAN ingresar precio Y descripción.

El flag booleano `precio_libre` no expresa un tercer modo ("al peso") ni obliga la
descripción: se necesita un **modo de precio por artículo** con valores excluyentes.

**Restricción fiscal:** el cobro sigue offline, en `Decimal`, con la función única de
redondeo por línea (ADR-0002/0005). "Al peso" reutiliza la matemática de línea existente
(`cantidad × pvp_unitario`); no toca la cadena de huellas ni la inmutabilidad (ADR-0003).

## Scope

### In Scope
- **Modo de precio por artículo**: `fijo` | `libre` | `al peso` (excluyentes).
- **Al peso**: precio/kg + entrada de peso en la venta → línea con `cantidad`=peso,
  `pvp_unitario`=precio/kg. `VentaLinea.cantidad` es `Cantidad()` = `DecimalTexto(3)`
  ("permite pesos/tallas") → soportado sin cambios de tipo.
- **Genéricos** sembrados (peces/plantas/material), modo libre, PVP 0.
- **Modo libre exige descripción** al vender (la edición de descripción ya existe del
  cambio #3, `edicion-linea-tpv`).
- Migración del dato: `precio_libre=True → libre`, resto → `fijo`.

### Out of Scope
- Descuentos por volumen; tarifas por cliente; unidades distintas de kg.

## Non-Goals
- Tocar la cadena fiscal, la inmutabilidad post-emisión, los triggers ni el redondeo.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `maestros-crud`: el artículo declara su modo de precio (y precio/kg si al peso).
- `tpv-venta`: al peso calcula precio/kg × peso; el modo libre exige descripción al vender.

## Approach

Introducir el concepto "modo de precio" en `Articulo` y propagarlo por los usos actuales
de `precio_libre` (modelo, CRUD `DatosArticulo`/`ArticuloReq`, DTO `_articulo_dto`,
`tpv.html`, `seed.py`) y por la regla de auditoría de `emitir_venta` ("modo libre nunca
audita precio manual"). El TPV pide peso (al peso) o precio+descripción (libre).
Migración Alembic para el dato existente.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `app/infraestructura/persistencia/modelos/maestros.py` | Modified | Modo de precio (+ precio/kg) en `Articulo` |
| `migrations/` | New | Migrar `precio_libre` → modo |
| `app/aplicacion/lineas.py` | Modified | Resolución de línea al peso (peso × precio/kg) |
| `app/aplicacion/emitir_venta.py` | Modified | Preservar "libre no audita"; exigir descripción |
| `app/aplicacion/articulos.py` | Modified | `DatosArticulo` con modo de precio |
| `app/presentacion/{tpv,admin}.py` | Modified | DTO + `ArticuloReq` con modo |
| `app/ui/tpv.html` | Modified | Entrada de peso; libre pide precio+descripción |
| `app/seed.py` | Modified | Genéricos + migrar ejemplos |
| `tests/` | Modified | Modos, al peso, descripción obligatoria, no-regresión |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|------------|
| Refactor de `precio_libre` ramifica al flujo de cobro (fiscal-adyacente) | Alta | Tests exhaustivos + no-regresión; strict TDD |
| Migración del dato existente incorrecta | Media | Migración idempotente + verificación; probar downgrade |
| Estados de precio ilegales si se modela mal | Media | Valor único excluyente, no flags solapados (ver Q1) |

## Rollback Plan

Revertir el diff y `alembic downgrade` de la migración (restaura `precio_libre`, mapeo
inverso `libre → True`, resto `False`). Sin datos fiscales afectados.

## Dependencies

- Cambio #3 (`edicion-linea-tpv`) ya aporta la descripción editable en el TPV.

## Open Questions for Design (NO resolver aquí)

1. **Modelo (clave)**: ¿refactorizar `precio_libre` (bool) a `modo_precio`
   (enum `fijo|libre|al_peso`), o AGREGAR "al peso" junto al flag actual?
   *Recomendación:* **enum**. Un único concepto excluyente hace IMPOSIBLES los estados
   ilegales (p. ej. libre + al_peso a la vez); ramifica por los usos listados, pero el
   mapeo es mecánico (`precio_libre → modo=='libre'`). Dos flags solapados dejan el
   modelo ambiguo y complican la auditoría.
2. **Precio/kg**: ¿columna nueva `precio_kg` o reutilizar `pvp` como precio por unidad
   (unidad = kg en al peso)? *Recomendación:* reutilizar `pvp` — evita una columna
   nullable con sentido en un solo modo y NO cambia la matemática de línea. Confirmado:
   `cantidad` (Decimal, 3 decimales) soporta el peso.
3. **Libre fuerza descripción**: ¿validación (rechaza emitir sin descripción) o solo
   prompt? *Recomendación:* validación server-side (la titular dijo "fuerza") + prompt
   obligatorio en la UI.
4. **Auditoría (invariante 4)**: preservar "modo libre nunca audita precio manual" tras
   el refactor (`modo=='libre'` reemplaza a `precio_libre` en `_auditar_precios_manuales`).

## Success Criteria

- [ ] Se puede marcar el modo de precio (fijo|libre|al peso) de un artículo.
- [ ] Al peso calcula precio/kg × peso correctamente (Decimal, redondeo único).
- [ ] Los genéricos fuerzan precio + descripción al vender.
- [ ] Producción/ventas sin regresión; datos existentes migrados.
- [ ] Cubierto por tests (modos, al peso, descripción obligatoria, auditoría).
