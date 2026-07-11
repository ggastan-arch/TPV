# Design: Cierre Z (informe Z inmutable)

## Technical Approach

Capability hexagonal (ADR-0001): un modelo ORM `CierreZ` con dos tablas hijas de
desglose, un caso de uso fino `GenerarCierreZ` en `app/aplicacion/`, un repositorio en
infraestructura y tres endpoints `/admin` auditados. El Z es un **snapshot inmutable**:
persiste los totales y desgloses CONGELADOS en la transacción de cierre; nunca se
recomputan al leer. Inmutabilidad por triggers de BD (patrón `ddl.py`, ADR-0003) vía
migración Alembic (nunca `create_all`). Numeración correlativa propia (Z global monótona)
asignada en la misma transacción bajo `BEGIN IMMEDIATE` (ADR-0004). Importes en `Decimal`;
los totales son sumas de valores ya redondeados por línea (ADR-0005), sin nuevo redondeo.

El Z **solo lee** sobre `venta`/`registro_fiscal`: jamás los muta (invariante 1). Las
ventas no se marcan "cerradas"; la pertenencia al Z se deriva por rango sobre el **orden
de emisión** del registro fiscal de alta (`registro_fiscal.orden`), no por `venta.id`.

## Architecture Decisions

| Decisión | Alternativas rechazadas | Motivo |
|----------|-------------------------|--------|
| **Desglose IVA y medio de pago en tablas hija** (`cierre_z_desglose_iva`, `cierre_z_desglose_pago`) con triggers de inmutabilidad | (a) columnas JSON; (b) recomputar en lectura | Recomputar viola "snapshot inmutable" (una anulación posterior alteraría el pasado). JSON pierde el tipado `Dinero`/`Porcentaje` (ADR-0002) y es un outlier: el precedente del proyecto para desglose es una tabla (`registro_fiscal_desglose`). Se replica ese patrón exacto. |
| **Contador Z derivado** `numero = (último CierreZ.numero)+1` dentro de `BEGIN IMMEDIATE` | (a) reusar `ContadorSerie` con serie 'Z'; (b) tabla contador dedicada | `serie`/`ContadorSerie` modela las SERIES FISCALES (T/F/R), y `venta.serie` es FK a `serie.codigo`: meter 'Z' ahí contamina el dominio fiscal y haría un Z aparecer como serie de factura válida. El Z **no es factura**. Derivar `MAX+1` bajo `BEGIN IMMEDIATE` da la misma garantía sin huecos que el `orden` de la cadena fiscal, sin tabla mutable extra. |
| **Z a cero permitido** (rango vacío → totales 0) | Rechazar con error | Un cierre sin ventas es un documento contable válido ("cero ventas en el período") y evita huecos en la serie Z. Comportamiento por defecto y definitivo (la spec lo fija en permitir). |

Ninguna decisión modifica un ADR existente (reutiliza 0001/0002/0003/0004/0005); no se
crea ADR nuevo.

### Mecanismo de rango (por orden de emisión: `registro_fiscal.orden`)

Se usa el **orden de emisión** de la cadena fiscal, no `venta.id`, porque `venta.id` se
asigna al aparcar (no al emitir): un ticket aparcado emitido tras un cierre podría caer
fuera de rango. El `orden` del registro de alta es monótono EN EL MOMENTO DE LA EMISIÓN,
lo que elimina ese hueco.

- `M` = `max(registro_fiscal.orden)` de registros de **alta** al cierre; `0` si no hay.
- `desde_orden` = `último_Z.hasta_orden + 1`, o `1` en el primer Z.
- `hasta_orden` = `M`.
- Totales = ventas con `estado == 'cobrada'` cuyo **registro de alta** tiene
  `desde_orden <= orden <= hasta_orden` (join `venta` ↔ `registro_fiscal` por `venta_id`,
  `tipo_registro == 'alta'`; estado leído al cierre y congelado).
- Contigüidad por construcción (`desde_n = hasta_{n-1}+1`) → sin huecos ni solapes.
- Rango vacío ⇔ `hasta_orden < desde_orden` (no hubo altas nuevas). Ventas anuladas/
  sustituidas cuyo alta cae en el rango consumen posición de `orden` pero se excluyen de
  los totales (filtro `estado == 'cobrada'`). Un evento posterior al cierre no reabre el
  Z (inmutable); su rastro vive en la cadena fiscal (RegistroAnulacion).

## Data Flow

    POST /admin/api/cierres-z
      -> GenerarCierreZ.ejecutar(usuario_id, origen)
         [1a lectura dispara BEGIN IMMEDIATE]
         uow.cierres_z.ultimo()                        -> desde_orden, numero
         uow.registros.max_orden_alta()                -> hasta_orden
         uow.cierres_z.cobradas_por_rango_orden(d, h)  -> agregar totales + desgloses
         uow.cierres_z.agregar(CierreZ+hijas); flush()
         uow.auditoria.registrar("generar_cierre_z", entidad_id=id)
         uow.commit()                                  [triggers guardan UPDATE/DELETE]

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/infraestructura/persistencia/modelos/cierre_z.py` | Create | `CierreZ`, `CierreZDesgloseIva`, `CierreZDesglosePago` |
| `app/infraestructura/persistencia/modelos/__init__.py` | Modify | Exportar los nuevos modelos (registrar metadata) |
| `app/infraestructura/persistencia/ddl.py` | Modify | `TRIGGERS_CIERRE_Z` / `DROP_TRIGGERS_CIERRE_Z` (BEFORE UPDATE/DELETE incondicional en las 3 tablas) |
| `migrations/versions/0003_cierre_z.py` | Create | `create_table` x3 + índices + `op.execute(TRIGGERS_CIERRE_Z)`; downgrade inverso |
| `app/infraestructura/persistencia/repositorios.py` | Modify | `RepositorioCierresZSQL` (incl. `ultimo()`, `agregar()`, `buscar()`, `listar()`, `cobradas_por_rango_orden(desde, hasta)`); en `RepositorioRegistrosSQL` añadir `max_orden_alta()` |
| `app/infraestructura/persistencia/unidad_de_trabajo.py` | Modify | Cablear `self.cierres_z` |
| `app/dominio/puertos.py` | Modify | Puerto `RepositorioCierresZ`; ampliar `RepositorioRegistros` (`max_orden_alta()`) y `UnidadDeTrabajo` |
| `app/aplicacion/generar_cierre_z.py` | Create | Caso de uso + `ResultadoCierreZ` (Z a cero permitido: rango vacio -> totales 0, sin excepcion) |
| `app/presentacion/admin.py` | Modify | POST/GET/GET detalle de cierres Z (auditados, `require_admin`) |
| `tests/test_cierre_z_*.py` | Create | Invariantes + cuadre + API |

## Interfaces / Contracts

```python
# modelos/cierre_z.py
class CierreZ(Base):            # __tablename__ = "cierre_z"
    id: int (PK)
    numero: int                # UniqueConstraint uq_cierre_z_numero (global monótona)
    fecha_hora_huso: str       # ISO 8601 + offset (ahora_huso())
    usuario_id: FK usuario (RESTRICT)
    desde_orden: int           # rango sobre registro_fiscal.orden (alta)
    hasta_orden: int
    num_tickets: int
    base_total / cuota_total / total_con_iva: Dinero()
    desglose_iva:  list[CierreZDesgloseIva]    # cascade all, delete-orphan
    desglose_pago: list[CierreZDesglosePago]
# hijas: (tipo_impositivo Porcentaje, base_imponible, cuota_repercutida) / (medio ck efectivo|tarjeta, importe)

# aplicacion/generar_cierre_z.py
class GenerarCierreZ:
    def __init__(self, uow: UnidadDeTrabajo): ...
    def ejecutar(self, *, usuario_id: int, origen: str = "local") -> ResultadoCierreZ: ...
```

Ventas del rango vía `cobradas_por_rango_orden` (join `venta` ↔ `registro_fiscal` de alta
por `orden`). Agregación reutilizada de `admin.informe_dia` (por medio de pago) y de
`engine._desglose` (por `tipo_iva_porcentaje`), sumando `base_linea`/`cuota_linea`.

## Testing Strategy (TDD estricto)

| Layer | Qué se prueba | Cómo |
|-------|---------------|------|
| Inmutabilidad | UPDATE/DELETE sobre `cierre_z` y las 2 hijas → aborta | `pytest.raises(sa.exc.DatabaseError)` (patrón `test_inmutabilidad.py`) |
| Numeración | Z consecutivos 1,2,3 sin huecos; unique impide duplicado | Generar varios; `UniqueConstraint`; opcional concurrencia (`BEGIN IMMEDIATE`) |
| Rango | `desde_orden_2 = hasta_orden_1 + 1`; sin hueco ni solape; alta nueva solo en el Z posterior; **ticket aparcado emitido tras un cierre queda en el Z de su emisión** (no se pierde) | Emitir, cerrar, aparcar+emitir, cerrar; verificar por `registro_fiscal.orden` |
| Cuadre | `num_tickets`/`base`/`cuota`/`total` = suma del rango; desglose IVA y pago cuadran; anulada (alta en rango) excluida de totales | Assert contra sumas `Decimal` |
| Snapshot | Anular una venta del rango DESPUÉS del cierre → totales del Z inalterados | `motor.cancel` post-cierre, releer Z |
| Sin ventas | Z a cero (o error, según spec) | Cerrar sin emisiones nuevas |
| API | POST crea + fila de auditoría; GET listar/detalle; 401 sin admin | TestClient (patrón `test_admin_api.py`) |
| Arquitectura | `make arch` (import-linter) verde; caso de uso solo importa puertos + modelos | ejecutar `make arch` |

## Migration / Rollout

Migración `0003_cierre_z` (revises `0002_remision`). `downgrade`: drop triggers + tablas;
no toca `venta`/`registro_fiscal` (el Z solo lee) → rollback limpio, sin datos que migrar.

## Open Questions

- [x] **Ticket aparcado a través de un cierre** — RESUELTA: el rango usa
  `registro_fiscal.orden` (orden de emisión real), no `venta.id`; un ticket aparcado y
  emitido tras un cierre entra en el Z del período en que se emite, sin huecos.
- [x] **Numeración Z global vs por ejercicio** — RESUELTA: secuencia global monótona
  (Z-1, Z-2…), sin reinicio por ejercicio.
- [x] **Política de Z a cero** — RESUELTA: permitido por defecto (rango vacío → totales 0).

Sin preguntas abiertas pendientes.
