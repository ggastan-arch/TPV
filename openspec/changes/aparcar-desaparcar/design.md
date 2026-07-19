# Design: Aparcar / Desaparcar tickets

## Technical Approach

Cambio ADITIVO en tres capas hexagonales, sin tocar la frontera fiscal. Se reutiliza el
estado `aparcada` (ya en modelo/triggers/tests, hoy dormido): un ticket aparcado es una
`Venta(estado='aparcada')` + `VentaLinea` (+ `etiqueta_aparcada` opcional). Tres casos de
uso finos en `app/aplicacion` (sin `MotorFiscal`, sin HTTP) operan solo por `uow`; endpoints
finos en `tpv.py`; un método de listado nuevo en el repositorio. El cobro de un recuperado
NO cambia: `RecuperarAparcada` CONSUME el borrador (delete) y el cliente re-emite por el
camino INTACTO `EmitirVenta`/`/tpv/api/cobrar` ("delete-and-emit-fresh"). `EmitirVenta`,
numeración, registro, huella y triggers quedan BYTE A BYTE iguales; los 161+ tests actuales
siguen verdes.

## Architecture Decisions

| Decisión | Alternativa rechazada | Motivo |
|----------|-----------------------|--------|
| Migración con `op.add_column("venta", ...)` NATIVO (no `batch_alter_table`) | `batch_alter_table` (como 0007) | `batch` en SQLite RECREA la tabla y PERDERÍA los triggers `trg_venta_no_update/no_delete`. `ADD COLUMN` nativo nunca recrea: triggers e invariantes intactos |
| `etiqueta_aparcada TEXT NULL` sin default ni backfill | Reusar `descripcion`/campo fiscal | Columna NO fiscal, ajena a la huella y a `_VENTA_CAMPOS_CONGELADOS`; filas emitidas ya existentes quedan `NULL`, sin efecto |
| Sin columna `aparcada_en` (timestamp) | Añadir timestamp de aparcado | Minimiza el toque al esquema de `venta` (CLAUDE.md); el orden por `id` DESC da recencia implícita; `fecha_hora_huso` es fiscal, no se toca |
| Delete-and-emit-fresh | Mutar `EmitirVenta` para emitir el borrador in situ | Mantiene `EmitirVenta` como ÚNICO punto de identidad fiscal, sin refactor de riesgo; evita cobro doble (el borrador se consume) |
| Casos `AparcarVenta`/`ListarAparcadas`/`RecuperarAparcada` SIN parámetro `motor` | Inyectar `MotorFiscal` "por si acaso" | Frontera fiscal por CONSTRUCCIÓN: sin `motor` no hay `emit` posible |
| Helper compartido `construir_lineas(resueltas)` en `lineas.py` | Duplicar el bucle de `VentaLinea` | DRY; `EmitirVenta` puede adoptarlo sin cambiar su semántica (mismos objetos), con los tests de emisión como guardia de regresión |
| Renombrar `FUNCIONES` `recuperar`→`desaparcar` | Mapear label UI a `recuperar` | `recuperar` solo aparece en `FUNCIONES` + un docstring (sin botones/seed): rename seguro y coherente end-to-end |
| Aparcar NO exige descripción de `modo_precio=='libre'` | `exigir_descripcion_libre=True` | Un borrador no se emite; la exigencia se aplica al cobrar (fresh emit). Usa `resolver_items(..., exigir_descripcion_libre=False)` |

## Data Flow

```
APARCAR:   carrito(JS) ─POST /tpv/api/aparcar─► AparcarVenta ─► Venta(estado='aparcada')
                                                     │             +lineas +etiqueta  ──► commit
           carrito se vacía (cliente)               └─ NUNCA serie/numero/registro/huella/emit

DESAPARCAR: GET /tpv/api/aparcadas ─► ListarAparcadas ─► [{venta_id,etiqueta,total,n_lineas}]
           DELETE /tpv/api/aparcadas/{id} ─► RecuperarAparcada ─► lee lineas ─► delete draft
                                                     │                          (cascade lineas)
           lineas ──► repuebla carrito ──► recalcular()

COBRO recuperado:  carrito ─POST /tpv/api/cobrar─► EmitirVenta ─► motor.emit  [INTACTO]
```

## File Changes

| File | Action | Integración |
|------|--------|-------------|
| `migrations/versions/0008_venta_etiqueta_aparcada.py` | Create | `op.add_column("venta", sa.Column("etiqueta_aparcada", sa.String(), nullable=True))`; `down_revision="0007_modo_precio_articulo"`; downgrade = `op.drop_column` |
| `app/infraestructura/persistencia/modelos/venta.py` | Modify | `etiqueta_aparcada: Mapped[str \| None] = mapped_column(String, nullable=True)` |
| `app/aplicacion/aparcar_venta.py` | Create | 3 casos de uso (abajo) |
| `app/aplicacion/lineas.py` | Modify | Extraer helper `construir_lineas(resueltas) -> list[VentaLinea]` |
| `app/dominio/puertos.py` | Modify | `RepositorioVentas`: `+listar_por_estado`, `+eliminar` |
| `app/infraestructura/persistencia/repositorios.py` | Modify | Impl SQL de ambos métodos |
| `app/presentacion/tpv.py` | Modify | `AparcarReq`; endpoints aparcar/aparcadas/desaparcar |
| `app/dominio/servicios/botonera.py` | Modify | `FUNCIONES`: `recuperar`→`desaparcar` (+ docstring en modelos/botonera.py) |
| `app/ui/tpv.html` | Modify | Cablear botones pie + `ejecutarFuncion` + overlay + repoblar `carrito` |

## Interfaces / Contracts

```python
# app/aplicacion/aparcar_venta.py  (uow-driven, sin motor, sin HTTP)
class AparcarVenta:                       # __init__(self, uow)
    def ejecutar(self, *, usuario_id: int, items: list[ItemVenta],
                 etiqueta: str | None = None) -> int: ...      # -> venta_id
class ListarAparcadas:                     # __init__(self, uow)
    def ejecutar(self) -> list[AparcadaDTO]: ...  # venta_id, etiqueta, total, n_lineas
class RecuperarAparcada:                   # __init__(self, uow)
    def ejecutar(self, venta_id: int) -> list[LineaCarritoDTO]: ...  # lee, borra, devuelve

# puertos.py  RepositorioVentas
def listar_por_estado(self, estado: str) -> list["Venta"]: ...
def eliminar(self, venta: "Venta") -> None: ...   # solo aparcada (triggers eximen)

# tpv.py  (kiosco; aparcar lleva usuario_id por el FK NOT NULL)
class AparcarReq(BaseModel): usuario_id: int; items: list[ItemVenta]; etiqueta: str | None = None
# POST /tpv/api/aparcar  -> {venta_id, etiqueta, total, n_lineas}
# GET  /tpv/api/aparcadas -> [{venta_id, etiqueta, total, n_lineas}]  (orden id DESC)
# DELETE /tpv/api/aparcadas/{venta_id} -> {lineas:[{articulo_id,cantidad,pvp,descripcion,modo_precio,nombre_corto}]}
```

La línea recuperada se enriquece con `modo_precio`/`nombre_corto` (join `Articulo`) y se marca
`editado:true` en `carrito` para que `render()` (usa `carrito[i].modo_precio`) y la no-fusión
de `anadir()` funcionen igual que hoy.

## Testing Strategy (TDD estricto — test primero)

| Layer | Qué testear | Enfoque |
|-------|-------------|---------|
| Unit caso | Aparcar crea `Venta(estado='aparcada')`+líneas+etiqueta; sin serie/numero/registro | uow + sqlite tmp |
| Unit caso | Listar devuelve solo aparcadas; Recuperar devuelve líneas y BORRA el borrador (+cascade) | uow + tmp |
| Frontera fiscal | Tras aparcar: `RegistroFiscal` vacío, `ContadorSerie` intacto, `venta.serie/numero is None`; `AparcarVenta.__init__` sin `motor` | Assert BD + firma |
| Migración | Post-upgrade: columna existe y es NULL-able; triggers `trg_venta_no_update/no_delete` presentes; huella de una venta emitida IDÉNTICA (columna no entra en el hash) | migrar tmp + recomputar `huella_alta` |
| API | POST aparcar→200; GET lista; DELETE devuelve líneas y borra; cobrar tras recuperar EMITE fresh (nuevo `RegistroFiscal`+serie) | TestClient |

## Migration / Rollout

Alembic 0008 (`add_column` nativo). Rollback: `downgrade` (drop_column) + revertir casos/endpoints/UI;
los botones vuelven a `disabled`; `aparcada` vuelve a dormir. Producción intacta.

## Open Questions

- [ ] ¿Confirmar que no se requiere `aparcada_en`? (asunción: orden por `id` basta para la UX).
- [ ] ¿Aparcar debe capturar `cliente_id`? (Out of scope actual; el modelo lo soporta si se reabre).
