# Motor Fiscal VERI*FACTU — Especificación

## Purpose

Motor fiscal intercambiable (ADR-0006): genera, encadena, serializa y remite registros de
facturación del art. 13 (Orden HAC/1177/2024), modalidad VERI*FACTU (ADR-0008). Verificado:
generación, encadenamiento, XML/XSD, QR y cola con transporte inyectado. Remisión productiva:
ver Out of Scope.

## Requirements

### Requirement: Puerto MotorFiscal (emit/cancel/verify_chain)

El sistema MUST exponer `MotorFiscal.emit/cancel/verify_chain`, implementado por
`NullEngine` y `VerifactuEngine` (ADR-0006); `cancel` MUST rechazar un registro ya anulado.

#### Scenario: La cadena verifica tras varias emisiones
- GIVEN 3 ventas emitidas
- WHEN se invoca `verify_chain`
- THEN reporta `ok=True` y 3 registros

**Trazabilidad**: `tests/test_cadena.py::test_encadenamiento_y_verificacion`;
`tests/test_anulacion.py` (incluye rechazo de doble anulación).

### Requirement: Huella SHA-256 encadenada conforme al art. 13

El sistema MUST componer la huella (`campo=valor&...`, huella anterior vacía en el primer
registro, SHA-256 hex mayúsculas 64 caracteres) y reproducir los vectores oficiales AEAT;
anulación con sufijo `Anulada` (ADR-0007).

#### Scenario: Los tres vectores oficiales coinciden
- GIVEN los valores de los tres casos del documento de sede
- WHEN se calcula la huella de alta y de anulación
- THEN el resultado coincide con la huella oficial esperada

**Trazabilidad**: `tests/test_huella_vectores.py` (los tres casos).

### Requirement: Sustitución de simplificada por factura completa (F3)

El sistema MUST soportar la conversión de una F2 en F3 en sustitución: bloque
`FacturasSustituidas`, enlace `VentaSustitucion` y transición de la F2 a `sustituida`,
inmutable tras su creación.

#### Scenario: F3 sustituye a una F2 previa
- GIVEN una venta F2 ya emitida
- WHEN se emite una F3 referenciando la F2
- THEN la F2 pasa a `sustituida` y el enlace queda registrado

**Trazabilidad**: `tests/test_sustitucion.py` (todas).

### Requirement: Serialización XML validada contra los XSD oficiales

El sistema MUST serializar cada registro de alta y de anulación (incluidas altas F3) a XML
que valide sin errores contra los XSD oficiales de la AEAT.

#### Scenario: Alta encadenada válida contra el XSD
- GIVEN un segundo registro de alta encadenado al primero
- WHEN se serializa a XML
- THEN la validación no devuelve errores

**Trazabilidad**: `tests/test_xml_validacion.py` (todas).

### Requirement: QR tributario del ticket

El sistema MUST generar la URL de cotejo (arts. 20-21): NIF, serie, fecha e importe (2
decimales), con caracteres especiales codificados; y producir el QR en nivel M y PNG.

#### Scenario: Número de serie con carácter especial
- GIVEN un número de serie que contiene `&`
- WHEN se genera la URL de cotejo
- THEN se codifica (`%26`) y el QR usa nivel `M`

**Trazabilidad**: `tests/test_qr.py` (todas).

### Requirement: Transporte SOAP de remisión (sobre + cliente)

El sistema MUST envolver registros en un sobre `RegFactuSistemaFacturacion` válido contra
el XSD SuministroLR (máx. 1000) y enviarlo por SOAP con un cliente que parsea CSV, tiempo
de espera y resultado por línea, traduciendo incidencias de red/SOAP Fault en excepciones,
con transporte inyectable. El parseo MUST clasificar además:

| Caso AEAT | Detección | Resultado |
|---|---|---|
| Duplicado (`CodigoErrorRegistro=3000` + `RegistroDuplicado`) | `EstadoRegistroDuplicado` (`Correcta`/`AceptadaConErrores`, vocabulario propio, distinto de `Correcto`/`AceptadoConErrores` de línea) | `aceptado` / `aceptado_con_errores` — nunca rechazado |
| Rechazo de cabecera (`EstadoEnvio=Incorrecto` sin `RespuestaLinea`) | Código + descripción de cabecera | Aplica a todos los registros del lote enviado |

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

**Trazabilidad**: `tests/test_envelope.py` (todas); `tests/test_remitente.py` (todas).

### Requirement: Cola de remisión FIFO con reintentos

El sistema MUST mantener pendientes en orden FIFO de generación, marcar incidencia y
reintentar según el intervalo de la AEAT, registrando cada intento de forma append-only. Estos
resultados MUST ser terminales (excluidos de reintento automático):

| Resultado terminal | Origen | Reintento |
|---|---|---|
| `aceptado` / `aceptado_con_errores` | Línea normal o duplicado | No |
| `requiere_intervencion` | Rechazo de cabecera (motivo AEAT persistido por registro, sin incidencia de conectividad) | No |
| `rechazado` (código ≠ 3000, sin duplicado) | Existente | Sin cambios (fuera de alcance) |

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

**Trazabilidad**: `tests/test_remision.py` (todas).

### Requirement: Validaciones de negocio previas a la remisión

El sistema MUST validar cada registro antes de remitir: límite 3.000 € (F2), tipos
permitidos, NIF emisor coherente, formato de serie, fecha no futura, formato de sistema y
destinatario según tipo.

#### Scenario: F2 supera el límite de 3.000 €
- GIVEN un registro F2 con importe total de 3.630 €
- WHEN se valida antes de remitir
- THEN se reporta `F2_LIMITE_3000` como rechazo

**Trazabilidad**: `tests/test_validaciones_negocio.py` (todas).

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

**Trazabilidad**: `tests/test_remision.py::test_reencolar_devuelve_a_pendiente_y_audita`; `tests/test_admin_api.py::test_reencolar_devuelve_a_pendiente_via_endpoint`.

### Requirement: Visibilidad persistente de incidencias de remisión

El panel fiscal (`fiscal_estado`) MUST exponer, de forma persistente entre
refrescos (no efímera), el conteo de registros en `requiere_intervencion` y el
último error de la AEAT (código + descripción).

#### Scenario: Conteo y último error visibles
- GIVEN registros en `requiere_intervencion` y un rechazo de cabecera ya procesado
- WHEN se consulta el panel fiscal en momentos distintos, sin nueva remisión
- THEN el conteo y el último código/descripción de error siguen visibles

**Trazabilidad**: `tests/test_admin_api.py::test_fiscal_estado_expone_ultimo_error`.

## Out of Scope

Remisión PRODUCTIVA a la AEAT pendiente del certificado electrónico de la persona titular (nunca
sale del servidor). Verificado: generación, encadenamiento, XML/XSD, QR, sobre SOAP y
cliente, con transporte inyectado.
