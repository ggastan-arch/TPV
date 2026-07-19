# Design: Cliente en venta + simplificada cualificada (art. 7.2/7.3 ROF)

## Technical Approach

Dos incrementos aditivos sobre la periferia del cobro, sin tocar el núcleo fiscal
(huella, cadena, numeración, redondeo). (A) fontanería cliente↔venta: búsqueda de
clientes y un `cliente_id` opcional enhebrado hasta `Venta.cliente_id`. (B) flag
`FacturaSimplificadaArt7273`: una columna booleana nueva en `venta`, serializada
CONDICIONALMENTE a un único elemento XML y reflejada en el ticket. La simplificada
normal queda byte-idéntica porque el elemento es `minOccurs=0` y se OMITE. El flag no
entra en la huella (confirmado en `huella.py:42-63`, subconjunto fijo sin el campo) ni
crea bloque `Destinatarios` (prohibido en F2, ya rechazado en `validaciones_negocio`).

## Architecture Decisions

### D1 — Representación: booleano en `venta`, serializado a "S"/omitido
**Choice**: columna `cualificada` (Boolean, nullable) en `venta` vía `op.add_column`
NATIVO (patrón `etiqueta_aparcada`, 0008). Serializa `True → <FacturaSimplificadaArt7273>S</>`;
`False/NULL → elemento ausente`.
**Alternatives**: (a) guardar el string "S"/"N"; (b) columna en `registro_fiscal`.
**Rationale**: nunca emitimos "N" — la ausencia (minOccurs=0) ES el "no cualificada" del
XSD y garantiza el byte-idéntico; un booleano evita estados inválidos. Ponerla en `venta`
(y no en `registro_fiscal`) mantiene intactos el esquema y el trigger del registro fiscal.

### D2 — Inmutabilidad: congelar `cualificada` recreando un único trigger
**Choice**: añadir `cualificada` a `_VENTA_CAMPOS_CONGELADOS` y RE-CREAR solo
`trg_venta_no_update` (DROP+CREATE nativo) en 0009.
**Alternatives**: no tocar el trigger (opción B, más ligera).
**Rationale**: `cualificada` es un atributo fiscal del documento emitido; se congela por
la MISMA razón que `cliente_id` (ddl.py:28): impedir su cambio durante la transición
controlada `cobrada→anulada/sustituida`. Un UPDATE plano a una venta emitida YA está
bloqueado por el trigger actual, así que esto solo cierra el hueco de la transición.
Recrear UN trigger por DDL nativo NO es `batch_alter_table` (no recrea la tabla): los
16 triggers y la huella sobreviven, verificado por test. Refuerza la inmutabilidad, no
la debilita. (Opción B es aceptable si se quiere minimizar DDL de trigger; el camino de
UPDATE plano ya queda protegido.)

### D3 — Flujo del flag hacia el XML (fuera de la huella)
**Choice**: nuevo kwarg `cualificada: bool = False` en `registro_alta_xml`; `RemitirLote`
resuelve `self.uow.ventas.buscar(reg.venta_id).cualificada` por cada alta y lo pasa. El
elemento se emite tras `DescripcionOperacion` y antes de `Desglose` (posición XSD
exacta, línea 144), solo si `True`.
**Alternatives**: denormalizar en `registro_fiscal` (toca esquema+trigger fiscal);
relación `viewonly`.
**Rationale**: el XML solo se serializa en remisión, no en emisión; un lookup por reg
(ya se hace `buscar(registro_anterior_id)`) mantiene `fiscal.py` sin cambios y el flag
fuera de la huella.

### D4 — Fontanería cliente: búsqueda + endpoints PIN-gated
**Choice**: `buscar_por_nif` (exacto normalizado) y `buscar_por_nombre` (subcadena ILIKE,
espejo de Artículo `repositorios.py:70-90`) en Protocol + SQL. `cliente_id` y `cualificada`
opcionales en `CobrarReq` → `EmitirVenta.ejecutar` (kwargs `None/False`; los 8 call-sites
de test intactos). Dos endpoints PIN-gated: `GET /tpv/api/clientes?q=` y
`POST /tpv/api/clientes` (alta inline, reusa `ServicioClientes.crear`, exige RGPD).
**Alternatives**: endpoint stateful "asignar cliente".
**Rationale**: el kiosco no persiste "venta actual" (carrito en frontend); la asignación
se materializa en el cobro. Reusar `ServicioClientes` conserva validación de NIF + auditoría.

### D5 — Regla cualificada: precondición NIF+domicilio en el caso de uso
**Choice**: acción explícita; `EmitirVenta.ejecutar` exige, si `cualificada`, `cliente_id`
con `cliente.nif` Y `cliente.domicilio`, o lanza `CualificadaSinDatos` (HTTP 422). Defensa
en profundidad: `validar_alta(..., es_cualificada=False)` acepta el flag solo en F2. Sigue
F2, nunca `Destinatarios` (rechazo `DESTINATARIO_NO_PERMITIDO` intacto).
**Rationale**: la precondición necesita la entidad `Cliente`, que `validaciones_negocio`
no ve; vive en el caso de uso. La comprobación F2 replica el patrón `tiene_destinatario`.

### D6 — Ticket: reutilizar desglose + bloque destinatario
**Choice**: el desglose por tipo (`ticket.py:100-104`) YA imprime base+cuota separadas =
"cuota separada". Solo se añade, si `venta.cualificada`, un bloque destinatario
(nombre + NIF + domicilio). `imprimir_ticket` recibe `cliente: Cliente | None`; lo carga
`_imprimir_ticket_seguro`.

## Data Flow

    TPV UI (busca/crea/asigna cliente + marca "cualificada")
      │  GET/POST /tpv/api/clientes           cliente_id + cualificada en CobrarReq
      ▼
    EmitirVenta.ejecutar  ── si cualificada → exige nif+domicilio (o 422)
      │  Venta(cliente_id, cualificada)  → INSERT único (estado='cobrada', sin trigger UPDATE)
      ▼
    motor.emit → RegistroFiscal + huella (SIN el flag)   ── ticket: desglose + destinatario
      ▼
    RemitirLote → registro_alta_xml(reg, cualificada=venta.cualificada)
                    └─ True → <FacturaSimplificadaArt7273>S</>  | False → omitido (byte-idéntico)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `migrations/versions/0009_venta_cualificada.py` | Create | `add_column` nativo `cualificada`; DROP+CREATE `trg_venta_no_update` con el campo congelado (D2) |
| `app/infraestructura/persistencia/modelos/venta.py` | Modify | Columna `cualificada` (Boolean nullable) |
| `app/infraestructura/persistencia/ddl.py` | Modify | Añadir `cualificada` a `_VENTA_CAMPOS_CONGELADOS` |
| `app/infraestructura/fiscal/xml.py` | Modify | Kwarg `cualificada`; elemento condicional en posición XSD |
| `app/aplicacion/remitir_lote.py` | Modify | Resolver venta y pasar `cualificada` a `registro_alta_xml` |
| `app/aplicacion/emitir_venta.py` | Modify | `cliente_id`/`cualificada` opcionales; precondición; set en `Venta` |
| `app/dominio/servicios/validaciones_negocio.py` | Modify | `es_cualificada` en `validar_alta`: flag solo en F2 |
| `app/dominio/puertos.py` | Modify | `buscar_por_nif`/`buscar_por_nombre` en `RepositorioClientes` |
| `app/infraestructura/persistencia/repositorios.py` | Modify | Impl. búsqueda de clientes |
| `app/aplicacion/clientes.py` | Modify | Métodos de servicio de búsqueda (opcional) |
| `app/presentacion/tpv.py` | Modify | `CobrarReq.cliente_id/cualificada` + endpoints `/tpv/api/clientes` |
| `app/infraestructura/impresion/ticket.py` | Modify | Bloque destinatario en cualificadas |
| `app/ui/tpv.html` | Modify | Cablear botón + panel buscar/crear/asignar + marcar cualificada |

## Interfaces / Contracts

```python
# puertos.py — RepositorioClientes (add)
def buscar_por_nif(self, nif: str) -> "Cliente | None": ...
def buscar_por_nombre(self, q: str, limite: int = 20) -> list["Cliente"]: ...

# emitir_venta.py
def ejecutar(self, *, usuario_id, items, pagos,
             cliente_id: int | None = None, cualificada: bool = False) -> ResultadoVenta
class CualificadaSinDatos(Exception): ...  # cliente sin NIF y/o domicilio → HTTP 422

# xml.py
def registro_alta_xml(reg, *, nombre_emisor, sistema, anterior=None,
                      cualificada: bool = False) -> etree._Element
```

## Testing Strategy (TDD estricto, `python -m pytest`)

| Test | Qué valida |
|------|-----------|
| `test_buscar_cliente_por_nif_nombre` | Repo: exacto por NIF; subcadena por nombre |
| `test_endpoint_clientes_pin` | GET/POST PIN-gated; alta inline exige RGPD |
| `test_cobro_con_cliente_fija_cliente_id` | `Venta.cliente_id` seteado; sin cliente = como hoy |
| `test_cobro_sin_cliente_noregresion` | 8 call-sites siguen verdes |
| `test_migracion_0009_triggers_y_huella` | tras `upgrade head`: 16 triggers vivos; UPDATE ilegal rechazado; huella de venta emitida inalterada |
| `test_xml_cualificada_valida_xsd` | F2 cualificada emite `...Art7273=S` y valida contra XSD |
| `test_xml_normal_byte_identico` | Sin flag → XML byte-idéntico al actual (golden) |
| `test_huella_independiente_del_flag` | Huella igual con y sin flag |
| `test_cualificada_sin_nif_o_domicilio_rechaza` | `CualificadaSinDatos` |
| `test_f2_con_destinatario_sigue_rechazado` | `DESTINATARIO_NO_PERMITIDO` intacto |
| `test_ticket_cualificada_imprime_destinatario` | NIF+domicilio+cuota separada |

## Migration / Rollout

0009: `op.add_column("venta", Column("cualificada", Boolean, nullable=True))`; luego
DROP+CREATE `trg_venta_no_update` con `cualificada` en el set congelado. `downgrade`:
restaurar el trigger original y `drop_column`. Nunca `batch_alter_table`. Rollback (B):
retirar la rama de emisión restaura XML byte-idéntico; la columna nullable puede quedar sin uso.

## Open Questions

- [ ] D2: ¿congelar `cualificada` recreando el trigger (recomendado, A) o dejarlo al
  bloqueo de UPDATE plano ya existente (B)? Resuelto a favor de A; confirmar si se
  prefiere minimizar DDL de trigger.
