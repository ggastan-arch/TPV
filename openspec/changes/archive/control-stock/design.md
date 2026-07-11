# Design: Control de stock (informativo, no bloqueante)

## Enfoque técnico

Retrofit aditivo sobre el modelo existente (`Articulo.control_stock`, `MovimientoStock`
append-only con triggers en `ddl.py`). No se toca el contrato fiscal de `tpv-venta`
(ADR-0006) ni el esquema de `venta`/`registro_fiscal` (invariante 1). Se añaden:

1. Tabla de configuración singleton `configuracion_empresa` (ajuste global, mutable).
2. Dos puertos/repositorios nuevos: `RepositorioStock` y `RepositorioConfiguracion`.
3. Casos de uso finos `RegistrarEntrada`, `RegistrarMerma` y consulta de stock.
4. Efecto de stock **no bloqueante** dentro de `EmitirVenta`, aislado en SAVEPOINT.
5. Endpoints admin (toggle, entrada, merma, listado) + estado/alarma consumible por TPV.

Capas respetadas (ADR-0001): dominio expone Protocols; aplicación orquesta; infraestructura
implementa SQL; presentación cablea. El dominio no importa ORM/FastAPI (`make arch`).

## Decisiones de arquitectura

| Decisión | Alternativa rechazada | Motivo |
|---|---|---|
| Ajuste en tabla singleton `configuracion_empresa` (fila id=1, `control_stock_activo` bool, default `false`) | Variable de entorno / `settings` | Debe editarse en remoto desde la consola (Tailscale) sin reinicio ni acceso al FS del servidor; la fila viaja en el backup Litestream. La tabla es mutable (sin triggers): NO es fiscal. |
| Efecto `venta` en **SAVEPOINT anidado** dentro del commit de la venta | Efecto best-effort POST-commit en transacción aparte | Honra "efecto secundario en la MISMA transacción local" (proposal): venta y stock comparten el mismo instante de durabilidad, sin ventana de crash "venta sí / stock no"; sin segundo `BEGIN IMMEDIATE` (cero contención extra en WAL monoescritor). El SAVEPOINT aísla el fallo. Viable porque `db.py` ya usa `isolation_level=None` + `BEGIN IMMEDIATE` explícito (prerrequisito de SAVEPOINT en pysqlite). |
| Stock = agregación on-the-fly en **Python/Decimal** | `SUM()` en SQL / saldo materializado | Los importes/cantidades se guardan como TEXT (`DecimalTexto`, ADR-0002); `SUM` SQL degradaría a float y descuadraría. Volumen de tienda modesto → sin caché. Sigue el patrón de `cobradas_por_rango_orden`. |
| `cantidad` almacenada como **magnitud positiva**; el signo lo aporta `tipo` (`entrada` +, `venta`/`merma` −) | Guardar `cantidad` con signo | `tipo` es única fuente de verdad de la dirección; imposible una fila incoherente. La "cantidad negativa" de la spec se lee como *efecto* sobre el stock, no como valor persistido. |
| Anulación NO revierte stock (fuera de alcance) | Encadenar la reversión al camino fiscal | El stock es informativo; acoplarlo a `cancel()` arriesgaría el camino fiscal. Ver "Fuera de alcance". |

## Punto crítico: efecto de stock en `EmitirVenta`

`ejecutar` se mantiene: `buscar usuario → resolver_items → Venta → motor.emit → commit`.
Se inserta `_efecto_stock(venta, usuario_id)` **tras `motor.emit` y antes de `commit`**.
El registro fiscal ya está flusheado (la venta tiene `id`).

```
ejecutar()  [BEGIN IMMEDIATE]
  ├─ ventas.agregar(venta); motor.emit(session, venta)   # venta+registro flusheados
  ├─ _efecto_stock(venta, usuario_id)
  │     if not configuracion.control_stock_activo(): return
  │     try:
  │        with session.begin_nested():            # SAVEPOINT sp_stock
  │            for linea in venta.lineas:
  │               art = articulos.buscar(linea.articulo_id)
  │               if art and art.control_stock:
  │                  stock.agregar(MovimientoStock(tipo="venta",
  │                     articulo_id=art.id, cantidad=linea.cantidad,
  │                     venta_id=venta.id, usuario_id=usuario_id,
  │                     fecha_hora_huso=ahora_huso()))
  │            # flush al salir; si falla -> ROLLBACK TO sp_stock
  │     except Exception as exc:                    # el stock JAMÁS aborta la venta
  │        logger.warning("stock venta %s: %s", venta.id, exc)
  └─ commit()                                       # venta + registro (+ stock si ok)
```

Un fallo del INSERT de stock (o del repo) hace `ROLLBACK TO SAVEPOINT`, la excepción se
captura y **no** se propaga; el `commit()` posterior persiste venta + registro con
normalidad. La sobreventa (stock negativo) NO es un fallo: se persiste y solo alimenta la
alarma.

## Modelo de datos y migración

Nuevo modelo `ConfiguracionEmpresa` (`modelos/configuracion.py`):
`id:int pk`, `control_stock_activo:bool nonnull default False`.

Migración `0004_configuracion_empresa` (`down_revision="0003_cierre_z"`):
- `create_table("configuracion_empresa", ...)`; `INSERT` de la fila singleton `id=1`.
- `create_index("ix_movimiento_stock_articulo", "movimiento_stock", ["articulo_id"])` (agiliza la agregación).
- Sin triggers de inmutabilidad: tabla de parámetros mutable.

## Puertos y repositorios

En `puertos.py` (Protocol) + `repositorios.py` (SQL) + cablear en `UnidadDeTrabajoSQL`:

```python
class RepositorioConfiguracion(Protocol):
    def control_stock_activo(self) -> bool: ...
    def fijar_control_stock(self, activo: bool) -> None: ...   # UPDATE fila id=1

class RepositorioStock(Protocol):
    def agregar(self, movimiento: MovimientoStock) -> None: ...          # session.add
    def stock_actual(self, articulo_id: int) -> Decimal: ...            # Σ Decimal en Python
    def movimientos(self, articulo_id: int) -> list[MovimientoStock]: ...
    def rastreados_en_negativo(self) -> list[tuple[int, Decimal]]: ...  # (articulo_id, stock)
```

`stock_actual`/`rastreados_en_negativo` cargan filas y reducen con `Decimal`
(`entrada` +, resto −); nunca `SUM` SQL.

## Casos de uso (`app/aplicacion/stock.py`)

```python
class RegistrarEntrada:                       # crea MovimientoStock tipo="entrada"
    def ejecutar(self, *, articulo_id: int, cantidad: Decimal,
                 usuario_id: int, origen: str = "local") -> int: ...
class RegistrarMerma:                          # tipo="merma", motivo obligatorio
    def ejecutar(self, *, articulo_id: int, cantidad: Decimal, motivo: str,
                 usuario_id: int, origen: str = "local") -> int: ...
class ConsultarStock:
    def stock_de(self, articulo_id: int) -> Decimal: ...
    def articulos_en_negativo(self) -> list[tuple[int, Decimal]]: ...
```

Excepciones: `ArticuloNoRastreado` (artículo inexistente o `control_stock=false`),
`CantidadInvalida` (≤0), `MotivoRequerido` (merma sin motivo). Ambos casos de uso
`flush()` para obtener id, auditan (`auditoria.registrar`, invariante 4) y `commit()`.
Manuales independientes del toggle global (el admin prepara stock antes de activarlo).

## Presentación

Bajo `/admin` (rol administración, `require_admin`, `_origen`, auditado):
- `POST /api/stock/ajuste {activo}` → `configuracion.fijar_control_stock`.
- `POST /api/stock/entrada {articulo_id, cantidad}` → `RegistrarEntrada`.
- `POST /api/stock/merma {articulo_id, cantidad, motivo}` → `RegistrarMerma`.
- `GET /api/stock` (listado rastreados+saldo), `GET /api/stock/{id}/movimientos`.
- `GET /api/stock/estado` → `{control_activo, articulos_en_negativo, detalle[...]}`
  (patrón de `/api/fiscal/estado`).

Señal TPV (bajo `/tpv`, PIN): `GET /api/stock/alarma` →
`{control_activo, articulos_en_negativo}`, informativa (mismo patrón que la alarma de
cola de remisión ya consumida por el TPV). No bloquea el cobro.

## Estrategia de test (TDD estricto)

| Capa | Qué | Cómo |
|---|---|---|
| Unit | `stock_actual` (entrada/venta/merma mixtos = 5) | movimientos in-memory, asserts `Decimal` |
| Unit | `RegistrarMerma` sin motivo lanza `MotivoRequerido` y no persiste | caso de uso + UoW test |
| Unit | Merma con motivo / entrada positiva auditan | verificar fila `log_auditoria` |
| Integr. | Toggle off ⇒ venta de artículo rastreado NO crea `MovimientoStock` | `EmitirVenta` + config off |
| Integr. | Toggle on ⇒ solo líneas rastreadas descuentan | venta mixta |
| Integr. | **Fallo de stock no aborta la venta** | `uow.stock.agregar` lanza dentro del SAVEPOINT; assert venta `cobrada` + registro encadenado; sin `MovimientoStock` |
| Integr. | Sobreventa deja saldo negativo y alarma cuenta el artículo | stock 1, vender 5 → −4 |
| Arch | `make arch` verde (dominio puro) | import-linter |

## Fuera de alcance: anulación y stock (futuro)

Hoy `cancel()` (camino fiscal) NO genera movimiento inverso. A futuro se abordaría con un
caso de uso INDEPENDIENTE (`RevertirStockAnulacion`) que, fuera de la transacción fiscal y
tras la anulación, añada movimientos `entrada` compensatorios append-only referenciando la
venta anulada — sin tocar `VerifactuEngine`/`NullEngine` ni el encadenamiento de huellas.

## Preguntas abiertas

- [ ] ¿`RegistrarEntrada`/`RegistrarMerma` deben exigir el toggle global activo, o basta con
      `Articulo.control_stock=true`? Diseño actual: solo exige `control_stock=true`.
- [ ] ¿Umbral de "stock bajo" (además de negativo) para la alarma? La spec solo pide negativo.
- [ ] Redacción de la spec ("cantidad negativa") ⇒ confirmar que se interpreta como *efecto*,
      no como valor persistido (design: magnitud positiva + signo por `tipo`).
