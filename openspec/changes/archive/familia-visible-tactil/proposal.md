# Proposal: Familia visible en táctil

## Intent

Hoy no existe forma de decidir qué familias aparecen en el TPV táctil. La persona titular
necesita un control **manual por familia**: las familias cuyos artículos se venden por
escaneo de código de barras no deben ocupar sitio en la botonera; las que **no** tienen
código de barras (peces, plantas) es imprescindible que estén, porque no hay otra forma
de venderlas. Falta el flag y falta honrarlo donde el TPV lista familias.

## Scope

### In Scope
- Campo `visible_en_tactil` (bool) en `Familia` + migración aditiva `0005`
  (`down_revision = 0004_configuracion_empresa`) con `server_default` para filas existentes.
- Editable en el CRUD de familias: `DatosFamilia`, `FamiliaReq`, `ServicioFamilias.crear/actualizar`,
  listado `GET /admin/api/maestros/familias`; queda auditado como el resto de cambios de familia.
- Honrar el flag en la **única** consulta del TPV que hoy lista familias para navegación:
  subfamilias en `GET /tpv/api/familia/{familia_id}` (`tpv.py:155-158`), filtrando
  `visible_en_tactil` **y** `activo`.

### Out of Scope
- Navegación drill-down completa raíz→subfamilias→artículos con rejilla táctil (cambio #2).
- Lupa / autocompletar de búsqueda (cambio #2).
- Imágenes en botones (cambio #5).
- Endpoint nuevo de familias raíz visibles para el TPV (no existe hoy; se decide en #2).

### Non-goals
- No tocar el contrato fiscal, ventas ni registros; no rozar la cadena de huellas ni los
  triggers de inmutabilidad.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `maestros-crud`: el CRUD de familias incorpora `visible_en_tactil` (crear/actualizar/listar, auditado).
- `tpv-venta`: la navegación de familias del TPV solo ofrece familias con `visible_en_tactil` + `activo`.

## Approach

Migración aditiva de una columna booleana con default `True` (visible por defecto; la dueña
**apaga** las familias que se escanean). Propagar el campo por las capas existentes
(modelo → `DatosFamilia` → `ServicioFamilias` → `FamiliaReq`/admin) y añadir el filtro en la
consulta de subfamilias del TPV. Backend con TDD estricto; si se toca UI, verificación manual.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/infraestructura/persistencia/modelos/maestros.py` | Modified | Columna `visible_en_tactil` en `Familia` |
| `migrations/versions/0005_*.py` | New | Añadir columna con `server_default` |
| `app/aplicacion/familias.py` | Modified | `DatosFamilia` + `crear`/`actualizar` |
| `app/presentacion/admin.py` | Modified | `FamiliaReq` + listado maestros |
| `app/presentacion/tpv.py` | Modified | Filtro en subfamilias de `/api/familia/{id}` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Migración altera datos existentes | Low | Aditiva, con `server_default`; no toca ventas/registros |
| El filtro esconde familias por error | Low | Default `True`; tests backend del filtro |

## Rollback Plan

`alembic downgrade` de `0005` (drop column) + revertir los cambios de código. Sin impacto fiscal.

## Dependencies

- Ninguna.

## Open Questions (para design)

- Default del flag: se propone `True`; confirmar dirección.
- Alcance del filtro en `/tpv/api/familia/{id}`: solo subfamilias, o también validar botones
  de familia en `/api/botonera` que apunten a familia no visible (edge case).
- Si #2 exigirá un endpoint de familias raíz visibles, valorar exponer ya un método de
  repositorio reutilizable.

## Success Criteria

- [ ] Se puede marcar/desmarcar una familia como visible en táctil desde la consola (auditado).
- [ ] El TPV no ofrece familias no visibles en la navegación por familias.
- [ ] Cubierto por tests de backend (modelo/servicio/API y filtro del TPV).
