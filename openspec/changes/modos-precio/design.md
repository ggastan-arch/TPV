# Design: Modo de precio por artículo (fijo | libre | al_peso)

## Enfoque técnico

Refactor mecánico fiscal-ADYACENTE: se sustituye el flag booleano `Articulo.precio_libre`
por un enum excluyente `modo_precio` (`fijo | libre | al_peso`) y se propaga por sus ~8
usos actuales. NO se toca la cadena de huellas, la inmutabilidad, los triggers ni la
función única de redondeo (invariantes 1-3). "Al peso" REUTILIZA la matemática de línea
existente (`cantidad × pvp_unitario`): `pvp` pasa a interpretarse como €/kg y la venta
envía `cantidad = peso`. La descripción obligatoria en modo `libre` se valida en el
servidor solo al EMITIR (no en el preview `/calcular`). Migración Alembic `0007` mapea el
dato y elimina la columna vieja.

## Decisiones de arquitectura

| Decisión | Alternativa rechazada | Motivo |
|----------|----------------------|--------|
| Enum `modo_precio` (`String` + `CheckConstraint`) | Añadir flag `al_peso` junto a `precio_libre` | Un único valor excluyente hace IMPOSIBLES los estados ilegales (libre+al_peso). Dos flags solapados dejan el modelo ambiguo y complican la auditoría. |
| Reutilizar `pvp` como €/kg en `al_peso` | Columna nueva `precio_kg` nullable | Evita una columna con sentido en un solo modo; NO cambia la matemática de línea. `cantidad` (`DecimalTexto(3)`) ya soporta el peso. |
| Validar descripción de `libre` solo al emitir | Validar también en `resolver_items`/`/calcular` | `/calcular` es un preview que corre en cada cambio del carrito; rechazar ahí rompería la vista antes de que el operador escriba la descripción. |
| `String` + `CheckConstraint` | SQLAlchemy `Enum` nativo | Coherente con los enums del proyecto (`ck_venta_estado`, `ck_pago_medio`); portable en SQLite batch mode. |

## Flujo de datos (al_peso)

    UI TPV (pide peso) ─→ ItemVenta{cantidad=peso, pvp=None}
         │
         ▼
    resolver_items ─→ pvp_unitario = articulo.pvp (€/kg); calcular_linea(pvp, cantidad=peso, iva)
         │
         ▼
    VentaLinea{cantidad=peso, pvp_unitario=€/kg}  (total = redondeo(€/kg × peso))

## Cambios por fichero

| Fichero | Acción | Descripción |
|---------|--------|-------------|
| `migrations/versions/0007_modo_precio_articulo.py` | Create | `down_revision="0006_articulo_imagen"`. Batch: add `modo_precio`; UPDATE mapeo; NOT NULL + CheckConstraint; drop `precio_libre`. Downgrade inverso. |
| `app/infraestructura/persistencia/modelos/maestros.py` | Modify | Quitar `precio_libre`; añadir `modo_precio: Mapped[str]` (`String`, `default="fijo"`) + `CheckConstraint("modo_precio IN ('fijo','libre','al_peso')", name="ck_articulo_modo_precio")`. |
| `app/aplicacion/lineas.py` | Modify | `resolver_items(..., exigir_descripcion_libre=False)`; si `True` y `articulo.modo_precio=='libre'` y `it.descripcion` vacía → `raise DescripcionRequerida`. Sin cambio en la aritmética (al_peso ya funciona). |
| `app/aplicacion/emitir_venta.py` | Modify | `_auditar_precios_manuales`: `lr.articulo.precio_libre` → `lr.articulo.modo_precio == 'libre'`. Llamar `resolver_items(..., exigir_descripcion_libre=True)`. Actualizar docstring. |
| `app/aplicacion/articulos.py` | Modify | `DatosArticulo.precio_libre: bool` → `modo_precio: str = "fijo"`; mapear en `crear`/`actualizar`. |
| `app/presentacion/admin.py` | Modify | `ArticuloReq.precio_libre` → `modo_precio: Literal["fijo","libre","al_peso"] = "fijo"`; `maestros_articulos` (DTO lectura) añade `"modo_precio"`. |
| `app/presentacion/tpv.py` | Modify | `_articulo_dto`: `precio_libre` → `modo_precio`. `/api/cobrar`: capturar `DescripcionRequerida` → `HTTPException(422)`. |
| `app/ui/tpv.html` | Modify | `anadir()`: rama por `modo_precio` — `libre` pide precio + descripción; `al_peso` pide peso (→ `cantidad`); `fijo` sin cambios. CRUD: etiqueta `pvp` como €/kg cuando `al_peso`. |
| `app/seed.py` | Modify | `tridacna.precio_libre=True` → `modo_precio="libre"`. Añadir genéricos (peces/plantas/material) `modo_precio="libre"`, `pvp=0`; y un material `al_peso` (madera/roca) de ejemplo. |
| `tests/test_emitir_venta.py`, `tests/test_tpv_api.py` | Modify | Actualizar helpers (`precio_libre` → `modo_precio`) y añadir casos nuevos. |

## Firmas

```python
# app/aplicacion/lineas.py
class DescripcionRequerida(Exception):
    def __init__(self, articulo_id: int): ...

def resolver_items(
    articulos: "RepositorioArticulos", items, *, exigir_descripcion_libre: bool = False
) -> tuple[list[LineaResuelta], Totales]: ...

# app/aplicacion/articulos.py
@dataclass
class DatosArticulo:
    ...
    modo_precio: str = "fijo"        # sustituye a precio_libre

# app/infraestructura/persistencia/modelos/maestros.py
modo_precio: Mapped[str] = mapped_column(String, nullable=False, default="fijo")
```

Migración `0007` (esquema del up):

```python
with op.batch_alter_table("articulo") as b:
    b.add_column(sa.Column("modo_precio", sa.String, nullable=True))
op.execute("UPDATE articulo SET modo_precio = CASE precio_libre WHEN 1 THEN 'libre' ELSE 'fijo' END")
with op.batch_alter_table("articulo") as b:
    b.alter_column("modo_precio", nullable=False)
    b.create_check_constraint("ck_articulo_modo_precio", "modo_precio IN ('fijo','libre','al_peso')")
    b.drop_column("precio_libre")
# downgrade: recrear precio_libre, UPDATE precio_libre = (modo_precio=='libre'), drop modo_precio
```

## Estrategia de test (TDD estricto)

| Capa | Qué probar | Cómo |
|------|-----------|------|
| Migración | `up` mapea `precio_libre=True→'libre'`, `False→'fijo'`, elimina `precio_libre`; `down` inverso (`'libre'→True`, resto `False`) | `command.upgrade(cfg,"0006_articulo_imagen")` (harness `_aplicar_migraciones`), INSERT fila, `upgrade("0007")`, asserts; `downgrade("0006...")`, asserts |
| CRUD | `modo_precio` editable en crear/actualizar; DTO lectura lo expone; valor inválido → 422 | `ServicioArticulos` + endpoints `/api/maestros/articulos` |
| al_peso | `total == redondeo(pvp €/kg × peso)` con `Decimal` | `/api/calcular` con `cantidad=peso` (p.ej. 12.00 × 1.250 = 15.00) |
| libre sin descripción | Emitir → `DescripcionRequerida` → 422; `/calcular` NO rechaza | `EmitirVenta.ejecutar` y `/api/cobrar` vs `/api/calcular` |
| libre con descripción | Congela `descripcion` en `VentaLinea` | Emitir y leer la línea |
| Auditoría (inv. 4) | `libre` NO audita; `fijo`/`al_peso` con precio≠catálogo SÍ | `_auditorias("precio_manual_venta")` |
| No-regresión | `fijo` normal; artículos migrados (`libre`) igual que antes | Suite existente actualizada |

## Migración / Rollout

Tandas de apply (recomendado **2**):

1. **Backend + migración + seed (TDD estricto):** núcleo fiscal-adyacente, cohesivo y
   mecánico. Todo cubierto por tests antes de tocar la UI. Estimado < 300 líneas
   (dentro del presupuesto de 400).
2. **Frontend a mano (sin TDD):** `app/ui/tpv.html` (peso / precio+descripción) y el CRUD
   (selección de modo, etiqueta €/kg). Separado porque es manual y no lleva tests unitarios.

Rollback: revertir el diff + `alembic downgrade 0006_articulo_imagen`. Caveat: el downgrade
mapea `al_peso → precio_libre=False` (se pierde el matiz "al peso"); sin datos fiscales
afectados.

## Preguntas abiertas

- [ ] ¿El DTO admin de lectura debe exponer también `pvp` etiquetado (€/kg) o basta con
  `modo_precio` y que la UI decida la etiqueta? (Diseño actual: solo `modo_precio`; la UI
  formatea.)
- [ ] Genéricos con `pvp=0`: ¿algún test debe impedir emitir un `libre` con precio 0 y sin
  descripción, o el 0 es válido si trae descripción? (Diseño actual: solo se exige
  descripción; `pvp=0` no se bloquea.)
