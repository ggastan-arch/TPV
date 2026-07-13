# Proposal: Robustez de la remisión VERI*FACTU (duplicados y rechazo de cabecera)

## Intent

La infraestructura de remisión funciona end-to-end contra AEAT preproducción (cert, TLS,
SOAP, sobre, cadena; un registro fresco obtuvo `EstadoRegistro=Correcta` con CSV). Pero el
manejo de DOS respuestas reales de la AEAT está roto y viola invariantes fiscales. Este
cambio los corrige sin tocar el núcleo fiscal (huella, numeración, inmutabilidad, redondeo).

## Problema (evidencia AEAT, sesión de pruebas reales)

1. **Duplicado (código 3000) → bucle infinito.** La AEAT responde `EstadoRegistro=Incorrecto`
   + `CodigoErrorRegistro=3000` con un bloque `RegistroDuplicado`/`EstadoRegistroDuplicado`
   (`Correcta` | `AceptadaConErrores`): el registro YA está aceptado. Hoy
   `_ESTADO_A_RESULTADO` mapea todo `Incorrecto`→`rechazado`; como `rechazado` no está en
   `ESTADOS_ACEPTADOS`, `pendientes()` lo reenvía para siempre. Escenario real: corte de red
   tras el procesado en AEAT → el reintento recibe 3000 de forma permanente.

2. **Rechazo de CABECERA (`EstadoEnvio=Incorrecto` sin `RespuestaLinea`) → descarte silencioso.**
   `RemitirLote.ejecutar` solo llama a `registrar_resultado` si hay líneas. Un rechazo de
   cabecera (p. ej. código 4109, NIF de `SistemaInformatico` inválido — defecto PERMANENTE de
   config) deja los registros en `no_remitido`, 0 intentos; el error parpadea en la UI y
   desaparece. Contradice el invariante "nunca se descarta un registro en silencio".

## Scope

### In Scope
- Parsear `RegistroDuplicado` y mapear al estado ORIGINAL (terminal) → corta el bucle 3000.
- Tratar el rechazo de cabecera como **"rechazado: requiere intervención"**: persistir motivo
  AEAT, NO reintentar en bucle, dejar rastro en cada registro del lote.
- Persistir y **hacer visible el último error de la AEAT** en el panel fiscal (no efímero).
- Alarma de consola diferenciada para "requiere intervención".
- Tests (strict TDD) por caso, sin romper el flujo aceptado/incidencia existente.

### Out of Scope
- Núcleo fiscal: huella/cadena, triggers de inmutabilidad, numeración, redondeo.
- Remisión productiva definitiva (sigue pendiente del certificado; ya cubierta por la spec).
- Flujo de corrección de config que resuelve el 4109 (solo se expone la alarma, no se autorepara).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `motor-fiscal-verifactu`: refina "Transporte SOAP de remisión" (parseo de `RegistroDuplicado`
  y rechazo de cabecera) y "Cola de remisión FIFO con reintentos" (estados terminales
  no-reintentables + visibilidad persistente del último error).

## Approach

- **Duplicado**: en `_parsear_respuesta`, detectar el bloque duplicado y mapear
  `EstadoRegistroDuplicado`→resultado terminal (`aceptado`/`aceptado_con_errores`) mediante una
  tabla dedicada (ojo al desajuste de género vs. `EstadoRegistro`).
- **Rechazo de cabecera**: en `RemitirLote.ejecutar`, ante `EstadoEnvio=Incorrecto` sin líneas,
  registrar resultado para TODO el lote con el código/descripción de cabecera, en un estado
  no-reintentable y SIN marcar incidencia.
- **Cola**: excluir el nuevo estado terminal de `pendientes()`/`contar_pendientes()`.
- **Visibilidad**: exponer último `codigo_error`/`descripcion` en `fiscal_estado` y renderizarlo
  de forma persistente en `admin.html`, con alarma propia.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `app/infraestructura/fiscal/remitente.py` | Modified | Parseo de `RegistroDuplicado`; mapeo terminal de estados. |
| `app/aplicacion/remitir_lote.py` | Modified | Rama de rechazo de cabecera sin líneas. |
| `app/infraestructura/persistencia/repositorios.py` | Modified | Estados terminales en `pendientes`/`registrar_resultado`. |
| `app/infraestructura/persistencia/modelos/fiscal.py` | Modified | Posible nuevo valor en `ESTADOS_REMISION` (ver diseño). |
| `app/presentacion/admin.py` + `app/ui/admin.html` | Modified | Panel fiscal: último error persistente + alarma. |
| `migrations/` | New (posible) | Migración si se añade valor de estado (ver diseño). |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|-----------|
| Debilitar un invariante fiscal | Baja | Solo `estado_remision` (mutable por trigger) cambia; núcleo intacto. |
| Mapeo incorrecto del duplicado reactiva el bucle | Media | Tabla de mapeo explícita + test del caso 3000 con estado terminal. |
| Migración de estado con datos existentes | Media | Sin CHECK BD sobre `estado_remision`; rollback no corrompe filas previas. |

## Rollback Plan

Cambio aditivo/lógico. Revertir el commit restaura el comportamiento previo. Si se introduce
migración de estados, debe ser reversible; como `estado_remision` no tiene CHECK en BD, el
downgrade no rompe filas existentes (documentar en design cualquier normalización necesaria).

## Cuestiones abiertas (a resolver en fase design)

1. **Esquema/migración**: ¿nuevo valor `requiere_intervencion` en `estado_remision`? La tupla
   `ESTADOS_REMISION` es solo Python (sin CHECK BD), pero si el rechazo de cabecera necesita un
   nuevo `resultado` en `remision_intento`, ese CHECK (`ck_remision_resultado`) SÍ obliga a
   rebuild Alembic (batch). El trigger de inmutabilidad ya admite cualquier `estado_remision`.
2. **Dónde persistir el error de cabecera**: hoy sin líneas no se anota nada. ¿Un
   `RemisionIntento` por cada registro del lote con el código/descripción de cabecera? Definir el
   mapeo cabecera→registros.
3. **Mapeo de estados de duplicado**: parsear `RegistroDuplicado`/`EstadoRegistroDuplicado`;
   resolver el desajuste `Correcta/AceptadaConErrores` (duplicado) vs.
   `Correcto/AceptadoConErrores` (línea normal). ¿CSV del duplicado disponible/persistido?
4. **Alarma en consola**: hoy solo distingue incidencia/pendientes/al día. Definir el contrato
   de `fiscal_estado` y el render del último error (código + descripción), no efímero.
5. **Estados terminales de la cola**: nuevo predicado de `pendientes()` (aceptados +
   requiere_intervención) para no reenviar lo no-reintentable.
6. **Salida de `requiere_intervencion`**: ¿acción manual de admin tras corregir la config? Definir
   si hay un "re-habilitar" explícito o queda fuera de scope.

## Success Criteria

- [ ] Duplicado 3000 termina en `aceptado`/`aceptado_con_errores`, sale de la cola, no se reenvía.
- [ ] Rechazo de cabecera deja rastro por registro, estado no-reintentable y alarma visible.
- [ ] Último error de la AEAT queda persistido y visible en el panel fiscal.
- [ ] El flujo aceptado/incidencia existente sigue verde (tests).
