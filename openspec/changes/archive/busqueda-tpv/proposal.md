# Proposal: Búsqueda por nombre (lupa) en el TPV

## Intent

La navegación del TPV es familias → subfamilias (drill-down). Con muchos peces y
plantas, encontrar un artículo concreto obliga a recorrer el árbol. Se añade una
LUPA de ayuda: un buscador incremental por NOMBRE que autocompleta/sugiere artículos
mientras se tipea, offline. Complementa la navegación por familias; no la reemplaza.
NO es búsqueda semántica ni embeddings: un `LIKE` sobre el nombre alcanza para este
catálogo pequeño.

## Scope

### In Scope
- Endpoint de solo lectura `GET /tpv/api/buscar?q=...` que devuelve artículos ACTIVOS
  cuyo nombre (y `nombre_corto`) coincide, case-insensitive, acotado a un top N de
  sugerencias.
- La respuesta usa la MISMA forma de artículo que ya consume el carrito
  (`_articulo_dto`), para poder agregar directo.
- Frontend: caja/lupa con sugerencias al tipear (debounce); tocar una sugerencia
  agrega el artículo al carrito reutilizando el flujo existente `anadir(articulo)`.

### Out of Scope
- Búsqueda semántica / embeddings.
- Sinónimos o alias.
- Búsqueda por código de barras (eso lo cubre el escáner: `/api/articulo/por-codigo`).
- Paginación de resultados.

## Non-Goals
- Reemplazar la navegación por familias.
- Tocar la cadena de huellas fiscal ni el flujo de emisión.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tpv-venta`: nuevo requisito de búsqueda incremental por nombre en el TPV (endpoint
  de sugerencias + integración con el carrito).

## Approach

Adaptador fino: endpoint bajo `/tpv` que consulta el repositorio de artículos con un
filtro `activo=true` + coincidencia por nombre/`nombre_corto`, limitado a N. Reutiliza
`_articulo_dto` para homogeneizar la forma con botonera/familia. El frontend añade una
caja de texto con debounce que pinta sugerencias y las conecta a `anadir(a)`.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `app/presentacion/tpv.py` | Modified | Nuevo endpoint `GET /api/buscar` |
| `app/ui/tpv.html` | Modified | Caja de búsqueda + lista de sugerencias |
| `tests/test_tpv_api.py` | Modified | Tests del endpoint (filtro/límite) |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|------------|
| Cargar todo el catálogo | Baja | Limitar a top N en la consulta |
| Sugerencias irrelevantes | Baja | Definir estrategia de match en design |

## Rollback Plan

Quitar el endpoint y la caja de búsqueda del `tpv.html`. Solo-lectura, sin migraciones
ni efectos sobre datos: revertir el diff basta.

## Dependencies

- Ninguna. El campo `Familia.visible_en_tactil` ya existe (cambio archivado).

## Open Questions for Design (NO resolver aquí)

- Universo de búsqueda: ¿TODOS los artículos activos o solo los "táctiles" (familia con
  `visible_en_tactil=true`, excluyendo los que se escanean)?
- Longitud mínima de `q`.
- N máximo de sugerencias.
- Estrategia de match: prefijo vs substring.
- Si incluye `nombre_corto` además de `nombre`.

## Success Criteria

- [ ] Al tipear parte de un nombre aparecen sugerencias relevantes.
- [ ] Tocar una sugerencia agrega ese artículo al carrito (mismo flujo que un botón).
- [ ] El endpoint filtra por `activo` y limita a N (cubierto por tests de backend).
