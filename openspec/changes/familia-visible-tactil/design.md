# Design: Familia visible en táctil

## Technical Approach

Añadir una columna booleana `visible_en_tactil` a `Familia` y honrarla en la única
consulta del TPV que hoy lista familias (drill-down de subfamilias). El cambio es
aditivo y atraviesa las capas ya existentes sin introducir componentes nuevos:
modelo SQLAlchemy → migración Alembic `0005` → `DatosFamilia` → `ServicioFamilias`
→ `FamiliaReq`/admin → DTO de lectura del CRUD → filtro en `tpv.py`.

La propagación por el CRUD es casi automática: admin construye el servicio con
`DatosFamilia(**req.model_dump())`, de modo que basta con que el nombre del campo
coincida en `FamiliaReq` y `DatosFamilia` para que fluya hasta el servicio. Ninguna
capa fiscal (ventas, registros, cadena de huellas, triggers de inmutabilidad) se toca.

## Architecture Decisions

### Decision: Columna booleana con `server_default` en la migración

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Columna `visible_en_tactil` con `server_default='1'` | Filas existentes quedan visibles sin backfill manual; una sola migración | **Elegida** |
| Columna nullable sin default | Requiere backfill posterior y lógica de `None` en consultas | Rechazada |
| Tabla/relación aparte de visibilidad | Sobreingeniería para un flag por fila | Rechazada |

**Rationale**: `default=True` en el modelo cubre el ORM, pero las filas ya insertadas
necesitan `server_default` a nivel de BD. El default "visible" es intencional: la dueña
**apaga** las familias que se venden por escaneo; nunca debe quedar una familia oculta
por accidente tras migrar.

### Decision: Filtro combinado `activo` + `visible_en_tactil` en el drill-down

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Añadir `Familia.visible_en_tactil.is_(True)` a la query de subfamilias | Mínimo, localizado, testeable | **Elegida** |
| Filtrar también botones de familia en `/api/botonera` | Amplía alcance; rompe botones explícitos configurados a mano | Rechazada (out of scope) |

**Rationale**: Un botón explícito a una familia no visible es una decisión deliberada
del editor de botonera y se respeta. El flag gobierna solo la **navegación por familias**,
no el render de botones. Esto resuelve la Open Question del proposal.

## Data Flow

    Admin (FamiliaReq) ──> DatosFamilia ──> ServicioFamilias.crear/actualizar ──> Familia (BD)
                                                      │
                                                      └──> LogAuditoria (invariante 4)

    TPV GET /api/familia/{id} ──> query subfamilias WHERE activo AND visible_en_tactil ──> DTO

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/infraestructura/persistencia/modelos/maestros.py` | Modify | Columna `visible_en_tactil: Mapped[bool]`, `nullable=False, default=True` en `Familia` |
| `migrations/versions/0005_familia_visible_tactil.py` | Create | `add_column` con `server_default=sa.true()`; `down_revision="0004_configuracion_empresa"` |
| `app/aplicacion/familias.py` | Modify | Campo `visible_en_tactil: bool = True` en `DatosFamilia`; `crear` y `actualizar` lo asignan a `familia.visible_en_tactil` |
| `app/presentacion/admin.py` | Modify | Campo `visible_en_tactil: bool = True` en `FamiliaReq`; añadir el campo al DTO de `GET /api/maestros/familias` |
| `app/presentacion/tpv.py` | Modify | Query de subfamilias (~línea 155): sumar `Familia.visible_en_tactil.is_(True)` |

## Interfaces / Contracts

Nota de nombres: los métodos del servicio son `crear` / `actualizar` (no
`crear_familia` / `actualizar_familia`). La auditoría interna sí usa las acciones
`"crear_familia"` / `"actualizar_familia"` y queda intacta.

```python
# maestros.py (Familia)
visible_en_tactil: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

# migración 0005
op.add_column("familia", sa.Column(
    "visible_en_tactil", sa.Boolean, nullable=False, server_default=sa.true()))
# downgrade: op.drop_column("familia", "visible_en_tactil")
```

## Testing Strategy

TDD estricto (backend). Cada test primero en rojo.

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Servicio | `crear` persiste `visible_en_tactil`; default `True` cuando no se envía; `actualizar` lo alterna | pytest sobre `ServicioFamilias` con UoW/BD de test |
| API admin | `POST`/`PUT /api/maestros/familias` aceptan el flag; el listado lo devuelve; el cambio queda auditado | cliente FastAPI de test con sesión admin |
| API TPV | `GET /api/familia/{id}`: el drill-down oculta subfamilias con `visible_en_tactil=False`; muestra las visibles | cliente FastAPI de test |
| No-regresión | Filas existentes (migración) quedan visibles; una familia visible pero `activo=False` sigue oculta | fixtures + assert sobre la query combinada |

## Migration / Rollout

Migración `0005` aditiva y reversible: `alembic upgrade head` añade la columna con
`server_default` (todas las familias existentes → visibles). Rollback:
`alembic downgrade 0004_configuracion_empresa` (drop column) + revertir el código.
Sin impacto en ventas, registros ni cadena de huellas.

## Open Questions

- [ ] Ninguna que bloquee. El endpoint de familias raíz visibles para el TPV y el
      posible método de repositorio reutilizable se difieren al cambio #2 (fuera de alcance).
