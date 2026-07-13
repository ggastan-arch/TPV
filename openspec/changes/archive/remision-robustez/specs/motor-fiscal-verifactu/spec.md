# Delta for Motor Fiscal VERI*FACTU

## MODIFIED Requirements

### Requirement: Transporte SOAP de remisión (sobre + cliente)

El sistema MUST envolver registros en un sobre `RegFactuSistemaFacturacion` válido
contra el XSD SuministroLR (máx. 1000) y enviarlo por SOAP con un cliente que parsea
CSV, tiempo de espera y resultado por línea, traduciendo incidencias de red/SOAP Fault
en excepciones, con transporte inyectable. El parseo MUST clasificar además:

| Caso AEAT | Detección | Resultado |
|---|---|---|
| Duplicado (`CodigoErrorRegistro=3000` + `RegistroDuplicado`) | `EstadoRegistroDuplicado` (`Correcta`/`AceptadaConErrores`, vocabulario propio, distinto de `Correcto`/`AceptadoConErrores` de línea) | `aceptado` / `aceptado_con_errores` — nunca rechazado |
| Rechazo de cabecera (`EstadoEnvio=Incorrecto` sin `RespuestaLinea`) | Código + descripción de cabecera | Aplica a todos los registros del lote enviado |

(Previously: solo clasificaba por `EstadoRegistro` de línea; el duplicado caía en
rechazado y el rechazo de cabecera no se detectaba.)

#### Scenario: Resultados mixtos en la misma respuesta
- GIVEN una respuesta con líneas aceptada y rechazada
- WHEN se parsea la respuesta
- THEN cada línea queda clasificada como aceptado o rechazado

#### Scenario: Duplicado 3000 ya aceptado (con o sin errores)
- GIVEN una línea con `CodigoErrorRegistro=3000` y `EstadoRegistroDuplicado` en
  `Correcta` o `AceptadaConErrores`
- WHEN se parsea la respuesta
- THEN la línea se clasifica como aceptado o aceptado_con_errores, nunca rechazado

#### Scenario: Rechazo de cabecera sin líneas
- GIVEN una respuesta con `EstadoEnvio=Incorrecto` y sin elementos `RespuestaLinea`
- WHEN se parsea la respuesta
- THEN se extrae código y descripción de cabecera para todo el lote

### Requirement: Cola de remisión FIFO con reintentos

El sistema MUST mantener pendientes en orden FIFO, marcar incidencia y reintentar
según el intervalo de la AEAT, registrando cada intento append-only. Estos
resultados MUST ser terminales (excluidos de reintento automático):

| Resultado terminal | Origen | Reintento |
|---|---|---|
| `aceptado` / `aceptado_con_errores` | Línea normal o duplicado | No |
| `requiere_intervencion` | Rechazo de cabecera (motivo AEAT persistido por registro, sin incidencia de conectividad) | No |
| `rechazado` (código ≠ 3000, sin duplicado) | Existente | Sin cambios (fuera de alcance) |

(Previously: solo aceptado/aceptado_con_errores salían de la cola; el duplicado se
reenviaba indefinidamente; el rechazo de cabecera no dejaba rastro.)

#### Scenario: Incidencia de red deja los registros pendientes
- GIVEN un lote de registros pendientes
- WHEN la remisión falla por incidencia
- THEN siguen pendientes y queda marcada la incidencia

#### Scenario: Duplicado 3000 corta el bucle de reenvío
- GIVEN un registro cuya última respuesta fue un duplicado ya aceptado
- WHEN se recalcula la cola de pendientes
- THEN el registro no aparece entre los pendientes

#### Scenario: Rechazo de cabecera deja el lote en requiere_intervencion
- GIVEN un envío que recibe `EstadoEnvio=Incorrecto` sin líneas
- WHEN se procesa la respuesta
- THEN cada registro del lote queda en `requiere_intervencion` con el motivo
  persistido, sin reintento automático

#### Scenario: Rechazo de línea con código distinto de 3000 no cambia
- GIVEN una línea `Incorrecto` con código ≠ 3000, sin `RegistroDuplicado`
- WHEN se procesa la respuesta
- THEN el registro se clasifica como rechazado, igual que antes de este cambio

## ADDED Requirements

### Requirement: Recuperación manual de un registro en `requiere_intervencion`

Un administrador MUST poder reencolar un registro en `requiere_intervencion`,
devolviéndolo a pendientes para reintento; la acción MUST registrarse en el log de
auditoría append-only (invariante 4 de CLAUDE.md).

#### Scenario: Reencolar tras corregir la configuración
- GIVEN un registro en `requiere_intervencion` y la configuración ya corregida
- WHEN el administrador lo reencola
- THEN vuelve a pendientes y queda anotado en el log de auditoría

#### Scenario: Sin reencolado automático
- GIVEN un registro en `requiere_intervencion`
- WHEN se ejecuta el ciclo automático de reintentos
- THEN no se reenvía sin acción explícita de un administrador

### Requirement: Visibilidad persistente de incidencias de remisión

El panel fiscal (`fiscal_estado`) MUST exponer, de forma persistente entre
refrescos (no efímera), el conteo de registros en `requiere_intervencion` y el
último error de la AEAT (código + descripción).

#### Scenario: Conteo y último error visibles
- GIVEN registros en `requiere_intervencion` y un rechazo de cabecera ya procesado
- WHEN se consulta el panel fiscal en momentos distintos, sin nueva remisión
- THEN el conteo y el último código/descripción de error siguen visibles
