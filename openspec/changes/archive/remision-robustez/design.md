# Design: Robustez de la remisión VERI*FACTU (duplicados y rechazo de cabecera)

## Technical Approach

Cambio fiscal-ADYACENTE: no toca huella, cadena, numeración, redondeo ni los triggers de
inmutabilidad del núcleo. Todo el trabajo vive en la periferia de la cola de remisión: el
parseo de la respuesta AEAT (`remitente.py`), la orquestación del lote (`remitir_lote.py`),
el predicado de pendientes (`repositorios.py`), el metadato mutable `estado_remision` y el
panel fiscal. Se introduce un único estado nuevo, `requiere_intervencion`, y se corrige el
bucle del código 3000 mapeando el duplicado a su estado ORIGINAL terminal.

## Architecture Decisions

### Decision: SIN migración Alembic (clave del diseño)

**Choice**: Añadir `requiere_intervencion` SOLO a la tupla Python `ESTADOS_REMISION`. NO
añadir ningún valor nuevo a `remision_intento.resultado`; el rechazo de cabecera se anota
como `resultado="rechazado"` (ya válido en el CHECK) y la semántica "requiere intervención"
vive exclusivamente en `registro_fiscal.estado_remision`.
**Alternatives considered**: (A) nuevo valor `requiere_intervencion` en `resultado` +
migración batch de `ck_remision_resultado` (patrón de 0007).
**Rationale**: `estado_remision` NO tiene CHECK en BD (migración 0001, columna `String`
plana; el modelo no declara CheckConstraint) y el trigger `trg_registro_fiscal_no_update`
ya admite cualquier valor. La alternativa A obliga a rebuild batch de una tabla append-only:
sus triggers `no_update`/`no_delete` + un downgrade que reintrodujera el CHECK antiguo
harían IRREVERSIBLE la reversión si ya existieran filas con el valor nuevo. Reusar
`rechazado` evita el rebuild, respeta el append-only y hace el downgrade trivial (revertir
el commit; sin CHECK, las filas `requiere_intervencion` no corrompen nada). El precedente
del asimetría resultado≠estado ya existe (incidencia→pendiente).

### Decision: Mapa de duplicado DEDICADO (género femenino)

**Choice**: Tabla nueva `_DUPLICADO_A_RESULTADO = {"Correcta":"aceptado",
"AceptadaConErrores":"aceptado_con_errores"}`. `Anulada` y cualquier valor no mapeado →
`estado_final="requiere_intervencion"` (terminal anómalo, no reintentable).
**Alternatives considered**: reutilizar `_ESTADO_A_RESULTADO`.
**Rationale**: `EstadoRegistroDuplicado` usa formas FEMENINAS (`Correcta`/`AceptadaConErrores`/
`Anulada`, XSD `EstadoRegistroSFType`) vs. las masculinas de la línea normal
(`Correcto`/`AceptadoConErrores`, `EstadoRegistroType`). Mezclar tablas volvería a mapear a
`rechazado` y reactivaría el bucle 3000. `Anulada` es un tercer valor real que la propuesta
no contemplaba: se aísla en `requiere_intervencion` para no silenciarlo.

### Decision: Persistir el rechazo de cabecera por CADA registro del lote

**Choice**: En `RemitirLote.ejecutar`, si `estado_envio=="Incorrecto"` y `not lineas`,
recorrer TODO el lote y `registrar_resultado(reg, "rechazado",
codigo_error=<cabecera>, descripcion=<cabecera>, estado_remision_final="requiere_intervencion")`.
Sin marca de incidencia (no es conectividad).
**Alternatives considered**: un único intento "de lote" sin FK a registro.
**Rationale**: invariante "nunca se descarta un registro en silencio": cada registro debe
quedar con rastro propio y estado terminal no-reintentable.

## Data Flow

    AEAT XML
      │  _parsear_respuesta (remitente.py)
      ├─ RespuestaLinea normal ─────► ResultadoLinea(resultado, estado_final=None)
      ├─ RegistroDuplicado (cod 3000) ─► _DUPLICADO_A_RESULTADO
      │      Correcta/AceptadaConErrores ► aceptado / aceptado_con_errores (terminal)
      │      Anulada / otro ─────────────► estado_final=requiere_intervencion
      └─ sin líneas + EstadoEnvio=Incorrecto ► RespuestaEnvio.codigo_error_cabecera
      │  RemitirLote.ejecutar (remitir_lote.py)
      ├─ por línea ► registrar_resultado(..., estado_remision_final)
      └─ cabecera ► por CADA reg del lote ► requiere_intervencion
      ▼
    estado_remision (mutable) + remision_intento (append-only)
      ▼  pendientes() excluye {aceptado, aceptado_con_errores, requiere_intervencion}
    admin.py fiscal_estado ► admin.html (alarma + último error persistente)
      ▲ fiscal_reencolar: requiere_intervencion ► pendiente + auditoría

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/infraestructura/fiscal/remitente.py` | Modify | `_DUPLICADO_A_RESULTADO`; parsear `RegistroDuplicado`/`EstadoRegistroDuplicado`; campos nuevos en `ResultadoLinea` (`estado_final`, `duplicado`) y `RespuestaEnvio` (`codigo_error_cabecera`, `descripcion_cabecera`). NO hay CSV de duplicado (XSD no lo incluye). |
| `app/aplicacion/remitir_lote.py` | Modify | Rama de rechazo de cabecera (sin líneas); pasar `estado_remision_final` por línea. |
| `app/infraestructura/persistencia/repositorios.py` | Modify | `ESTADOS_TERMINALES = ESTADOS_ACEPTADOS + ("requiere_intervencion",)` en `pendientes`/`contar_pendientes`/`hay_incidencia_pendiente`; `registrar_resultado(..., estado_remision_final=None)`; método `reencolar(reg)`; `ultimo_error()`. |
| `app/infraestructura/persistencia/modelos/fiscal.py` | Modify | Añadir `"requiere_intervencion"` a `ESTADOS_REMISION` (solo Python). `RESULTADOS_REMISION` y el CHECK NO cambian. |
| `app/presentacion/admin.py` | Modify | `fiscal_estado`: exponer `ultimo_error` + contador `requiere_intervencion`. Endpoint `POST /api/fiscal/reencolar` con auditoría. |
| `app/ui/admin.html` | Modify | Render persistente del último error; alarma diferenciada "REQUIERE INTERVENCIÓN"; botón "Reencolar y reintentar". |
| `tests/_helpers.py` | Modify | `respuesta_remision_xml` soporta bloque `RegistroDuplicado` y respuesta sin líneas. |

## Interfaces / Contracts

```python
@dataclass
class ResultadoLinea:
    num_serie_factura: str
    resultado: str                     # CHECK-valid: aceptado|aceptado_con_errores|rechazado
    codigo_error: str | None = None
    descripcion: str | None = None
    estado_final: str | None = None    # override de estado_remision (None = derivar)
    duplicado: bool = False

# registrar_resultado(reg, resultado, *, codigo_error=None, descripcion=None,
#   csv=None, estado_remision_final=None)  ->  estado = estado_remision_final or
#   ("pendiente" if incidencia else resultado)  # backward-compatible

# fiscal_estado añade: {"cola": {..., "requiere_intervencion": int},
#                       "ultimo_error": {"codigo": str|None, "descripcion": str|None,
#                                        "num_serie": str|None, "fecha": str}|None}
```

## Testing Strategy

Strict TDD (`python -m pytest`). Casos (rojo→verde):

| Test | Qué valida |
|------|-----------|
| `test_parsea_duplicado_correcta_es_aceptado` | 3000 + `Correcta` → resultado `aceptado`, `duplicado=True` |
| `test_parsea_duplicado_aceptada_con_errores` | 3000 + `AceptadaConErrores` → `aceptado_con_errores` |
| `test_parsea_duplicado_anulada_requiere_intervencion` | 3000 + `Anulada` → `estado_final=requiere_intervencion` |
| `test_remitir_duplicado_sale_de_la_cola` | Tras 3000, `contar_pendientes()==0`, NO se reenvía |
| `test_rechazo_cabecera_4109_marca_todo_el_lote` | sin líneas + Incorrecto → cada reg `requiere_intervencion`, motivo persistido, sin incidencia |
| `test_requiere_intervencion_no_esta_en_pendientes` | Predicado de cola excluye el estado |
| `test_reencolar_devuelve_a_pendiente_y_audita` | `requiere_intervencion`→`pendiente`, `LogAuditoria` creado, reaparece en `pendientes()` |
| `test_fiscal_estado_expone_ultimo_error` | Contrato de `fiscal_estado` (código+descr no efímero) |
| `test_noregresion_aceptado_incidencia_rechazo_linea` | Flujo existente intacto (rechazo de línea normal SIGUE reintentándose) |

Los tests de `test_remitente.py`/`test_remision.py` existentes deben seguir verdes (firma
retrocompatible).

## Migration / Rollout

No migration required. `ESTADOS_REMISION` es tupla Python sin CHECK en BD; el trigger ya
admite cualquier `estado_remision`. Downgrade = revertir el commit; las filas
`requiere_intervencion` no violan ninguna constraint (bajo el código antiguo volverían a
tratarse como pendientes, comportamiento previo, sin corrupción).

## Open Questions

- [ ] Confirmar contra una respuesta AEAT real capturada DÓNDE viaja el código de cabecera
  (4109): el XSD `RespuestaBaseType` no define campo de error a nivel envelope. Si no llega
  en el XML, `descripcion_cabecera` usa un mensaje fijo con `EstadoEnvio`. El mecanismo
  (persistir por registro + requiere_intervencion) es robusto a la ubicación exacta.
