# Design: Búsqueda por nombre (lupa) en el TPV

## Technical Approach

Adaptador fino de solo lectura sobre el patrón existente. Se añade un método
`buscar_por_nombre` al puerto `RepositorioArticulos` y a su adaptador SQL
(`RepositorioArticulosSQL`), siguiendo el precedente de `buscar_por_codigo`. Un nuevo
endpoint `GET /tpv/api/buscar` bajo `/tpv` lo invoca vía `uow.articulos` y serializa con
el helper ya existente `_articulo_dto`, de modo que la forma del artículo devuelto es
idéntica a la de la botonera y la vista de familia. El frontend añade una caja de texto
(lupa) que, con debounce, llama al endpoint y pinta las sugerencias en `#grid`
reutilizando el mismo render de botón-artículo que `abrirFamilia`; al tocar una,
llama a `anadir(a)` — el flujo idéntico a pulsar un botón. Sin dominio nuevo, sin
migración, sin efectos de escritura.

## Architecture Decisions

### Decisión: dónde vive la consulta

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Método en `RepositorioArticulos` (puerto + SQL) | Consistente con `buscar_por_codigo`; unidad testeable aislada (TDD) | **Elegida** |
| `select()` inline en el endpoint (como `familia`/`botonera`) | Menos código, pero la regla de búsqueda queda fuera del repo y menos testeable como unidad | Rechazada |

**Rationale**: con TDD estricto en backend, concentrar filtro + límite + guarda en un
método del repositorio da una unidad clara sobre la que escribir el test que falla
primero, y sigue el patrón ya usado para lookups de artículo (`buscar_por_codigo`).

### Decisión: estrategia de match y guardas

**Choice**: `Articulo.nombre.ilike(f"%{q}%") | Articulo.nombre_corto.ilike(f"%{q}%")`,
filtrando `activo == True`, `order_by(Articulo.nombre)`, `limit(LIMITE=20)`. La guarda
de longitud mínima (`len(q.strip()) < 2 → []`) y el `strip()` viven **dentro** del
método del repo, para que la regla se cumpla sea cual sea el llamador.
**Alternatives considered**: match por prefijo (`q%`) — rechazado, no encuentra
subcadenas internas; guarda en el endpoint — rechazada, deja el repo dependiente del
llamador.
**Rationale**: substring `ilike` es lo pedido y suficiente para un catálogo pequeño;
universo = TODOS los activos (no solo táctiles), porque la lupa es ayuda transversal.

### Decisión: forma de respuesta y no-colisión con el escáner

**Choice**: el endpoint devuelve una **lista** JSON de `_articulo_dto`. El frontend
renderiza en `#grid` (no un dropdown nuevo). La caja es un `<input>`; el listener del
escáner ya ignora `INPUT` (`tpv.html:263`), así que no hay conflicto con el wedge.
**Alternatives considered**: envolver en `{"resultados": [...]}` — innecesario para una
lista; dropdown flotante propio — más CSS/JS para un cambio chico.
**Rationale**: reutiliza `imgBoton`/`eur`/`anadir` sin código nuevo de UI; volver a
Inicio o vaciar la caja restaura la botonera.

## Data Flow

    input (debounce ~250ms) ──→ GET /tpv/api/buscar?q= ──→ uow.articulos.buscar_por_nombre
              │                                                        │
        render #grid  ◀── [_articulo_dto(a)] ◀── activos + ilike + limit + order
              │
        onclick → anadir(a) → carrito (mismo flujo que un botón)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/dominio/puertos.py` | Modify | Firma `buscar_por_nombre(q: str, limite: int = 20) -> list[Articulo]` en `RepositorioArticulos` |
| `app/infraestructura/persistencia/repositorios.py` | Modify | Implementar `buscar_por_nombre` en `RepositorioArticulosSQL` (activo + ilike nombre/nombre_corto, guarda `<2`, order, limit) |
| `app/presentacion/tpv.py` | Modify | Endpoint `GET /api/buscar` que llama al repo y mapea con `_articulo_dto` |
| `app/ui/tpv.html` | Modify | Caja/lupa en `.col-botonera`; `buscar()` con debounce que pinta sugerencias en `#grid` → `anadir(a)` |
| `tests/test_tpv_api.py` | Modify | Tests de repo + endpoint (ver estrategia) |

## Interfaces / Contracts

```python
# app/dominio/puertos.py — RepositorioArticulos
def buscar_por_nombre(self, q: str, limite: int = 20) -> list["Articulo"]: ...
```

`GET /tpv/api/buscar?q=<texto>` → `200 [ {id, nombre, nombre_corto, pvp, tipo_iva,
precio_libre, requiere_cites, color, imagen}, ... ]` (exactamente `_articulo_dto`).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (repo, TDD) | Match por `nombre` (subcadena interna); match por `nombre_corto`; case-insensitive; `q<2` → `[]`; respeta `limite` (crear N+1); excluye `activo=False`; orden por `nombre` | pytest sobre `RepositorioArticulosSQL` con SQLite en memoria |
| Integration (TDD) | `GET /api/buscar` → 200 + lista; forma del DTO idéntica a la del carrito/botonera; `q` corto/vacío → `[]` | TestClient en `tests/test_tpv_api.py` |
| Manual | Caja: debounce, tocar sugerencia agrega al carrito; no colisiona con escáner | Verificación en el equipo táctil |

## Migration / Rollout

No migration required. Solo lectura; rollback = revertir el diff.

## Open Questions

- [ ] Acentos/ñ: `LIKE`/`ilike` de SQLite NO pliega diacríticos ni mayúsculas
      no-ASCII por defecto (busca "cebra" no encontraría "Cébra"). ¿Aceptable para
      esta primera versión, o normalizar (columna plegada / `unicode`) más adelante?
- [ ] Escapado de comodines: si el usuario teclea `%` o `_` se interpretan como
      comodín. ¿Escapar en el repo (bajo impacto) o ignorar por ser un TPV de tienda?
