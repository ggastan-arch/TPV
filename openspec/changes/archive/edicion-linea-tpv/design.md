# Design: Edición de línea en el TPV (precio, cantidad, descripción)

## Technical Approach

Cambio FORWARD, fiscal-ADYACENTE, SIN migración: `VentaLinea` ya tiene
`descripcion`, `pvp_unitario` y `cantidad`. Se abre el override de precio a
CUALQUIER artículo (hoy limitado a `precio_libre`) y se añade override de
`descripcion`. La resolución de líneas congela los valores editados al construir
`VentaLinea` en la emisión. Nueva regla de auditoría (invariante 4): al EMITIR, se
registra un evento por línea cuyo precio cobrado difiera del PVP de catálogo. El
frontend gana un editor de línea en el carrito (pre-emisión). No se toca la
inmutabilidad post-emisión, los triggers ni la cadena de huellas.

## Architecture Decisions

### Decisión: override de precio para cualquier línea
**Choice**: Quitar `and articulo.precio_libre` en `resolver_items`; el `pvp`
override aplica a todo artículo. **Alternatives**: mantener solo `precio_libre`
(rechazada: no cumple el requisito) / columna `descuento` dormida (rechazada:
"precio manual" es más simple y no requiere UI de descuento). **Rationale**:
minimiza superficie; el hecho fiscal auditable es "precio cobrado ≠ catálogo",
independiente de `precio_libre`.

### Decisión: nombre y disparo del evento de auditoría
**Choice**: `accion="precio_manual_venta"`, `entidad="venta_linea"`, disparado en
`EmitirVenta` SOLO cuando `lr.pvp != lr.articulo.pvp`. **Alternatives**:
`cambio_precio` (rechazada: colisiona semánticamente con el cambio de PVP de
maestro en `articulos.py`) / auditar en `/api/calcular` (rechazada: un carrito no
cobrado NO audita). **Rationale**: nombre distinto y buscable; la traza nace en la
misma transacción que emite (invariante 4).

### Decisión: descripción override congela `VentaLinea.descripcion`
**Choice**: `descripcion = (override).strip() or articulo.nombre`. **Alternatives**:
persistir siempre `articulo.nombre` (rechazada: no permite editar). **Rationale**:
la columna ya existe; sin override se conserva el comportamiento actual.

### Decisión: la descripción NO se audita
**Choice**: Solo el precio genera evento. **Rationale**: el invariante 4 cita
"cambios de precio" y "descuentos", no descripciones de línea. Ver Open Questions.

## Data Flow

```
tpv.html (carrito: cantidad/pvp/descripcion por línea)
     │  POST /api/calcular  ──→ resolver_items ──→ LineaResuelta (pvp/desc resueltos) ──→ eco al carrito
     │  POST /api/cobrar    ──→ EmitirVenta.ejecutar
     │                              ├─ resolver_items → congela en VentaLinea
     │                              ├─ motor.emit (asigna ids + numeración)
     │                              └─ auditoría: por línea con pvp≠catálogo → LogAuditoria
     └───────────────────────────── commit (atómico)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/aplicacion/lineas.py` | Modify | `ItemVenta.descripcion`; `LineaResuelta.descripcion`; abrir override pvp y resolver descripción |
| `app/aplicacion/emitir_venta.py` | Modify | Congelar `descripcion=lr.descripcion`; auditar precio manual tras `motor.emit` |
| `app/presentacion/tpv.py` | Modify | DTO `ItemVenta.descripcion`; mapear a `ItemAplicacion`; eco `descripcion` en `/api/calcular` |
| `app/ui/tpv.html` | Modify | Editor de línea (cantidad/precio/descripción); enviar overrides en calcular y cobrar |
| `tests/` | Add | Tests de override congelado y auditoría (TDD backend) |

## Interfaces / Contracts

```python
# lineas.py
@dataclass
class ItemVenta:
    articulo_id: int
    cantidad: Decimal = field(default_factory=lambda: Decimal("1"))
    pvp: Decimal | None = None          # override de precio unitario (cualquier articulo)
    descripcion: str | None = None       # override de descripcion de linea

@dataclass
class LineaResuelta:
    articulo: "Articulo"; pvp: Decimal; cantidad: Decimal
    descripcion: str; calculo: Linea

# resolver_items (núcleo del cambio)
pvp = it.pvp if it.pvp is not None else articulo.pvp
descripcion = (getattr(it, "descripcion", None) or "").strip() or articulo.nombre

# emitir_venta.py — tras motor.emit (ids ya asignados)
def _auditar_precios_manuales(self, venta, lineas, usuario_id) -> None:
    for vl, lr in zip(venta.lineas, lineas):
        if lr.pvp != lr.articulo.pvp:
            self.uow.auditoria.registrar(
                accion="precio_manual_venta", entidad="venta_linea",
                entidad_id=str(vl.id),
                detalle=f"articulo {lr.articulo.id}: catalogo {lr.articulo.pvp} -> cobrado {lr.pvp}",
                usuario_id=usuario_id, origen="local")  # cobro siempre local
```

El DTO pydantic `ItemVenta` (tpv.py) suma `descripcion: str | None = None`; se
mapea en `cobrar` a `ItemAplicacion(..., descripcion=i.descripcion)`.

## Testing Strategy (TDD estricto — backend)

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Override pvp en artículo NO `precio_libre` se resuelve (antes se ignoraba) | `resolver_items` → `LineaResuelta.pvp == override` |
| Unit | Sin override usa catálogo | pvp `None` → `LineaResuelta.pvp == articulo.pvp` |
| Unit | Descripción override congela; vacía usa `articulo.nombre` | `LineaResuelta.descripcion` |
| Unit | Cantidad arbitraria propaga al cálculo | `calculo` refleja cantidad |
| Integration | Emitir con precio manual congela en `VentaLinea` | `pvp_unitario`/`descripcion` persistidos |
| Integration | Emitir con precio manual audita 1 evento | 1 fila `LogAuditoria(accion="precio_manual_venta")` |
| Integration | Emitir sin diferencia NO audita | 0 filas del `accion` |

Frontend: verificación manual (editar cantidad/precio/descripción; no toca ventas emitidas).

## Migration / Rollout

No migration required. Revertir el diff restaura el comportamiento actual.

## Open Questions

- [ ] ¿Debe auditarse también el override de descripción, o basta el precio? (diseño actual: solo precio).
- [ ] Merge al re-agregar (`anadir` hace +1): con overrides por línea, ¿el +1 sobre una línea con precio/descr editados es aceptable o debe crear línea nueva? (diseño actual: conserva el merge).
