# tpv-venta Specification

## Purpose

Venta táctil monopuesto: cálculo de líneas, cobro OFFLINE, emisión con serie/número
correlativos y registro fiscal encadenado, impresión ESC/POS con QR y apertura de
cajón. Endpoints bajo `/tpv`, protegidos con PIN de operador.

## Requirements

### Requirement: Cálculo de líneas en servidor con precio e IVA congelados

El sistema MUST calcular cada línea en el servidor con `Decimal` y la función única
de redondeo (half-up por línea), congelando el PVP y el porcentaje de IVA vigente
del artículo en el momento del cálculo. El frontend MUST NOT hacer aritmética de
importes.

#### Scenario: Cálculo de totales vía API
- GIVEN un artículo con PVP 2,50 € y cantidad 2
- WHEN POST `/tpv/api/calcular`
- THEN el total es `"5.00"` (string decimal exacto)

#### Scenario: Artículo de precio libre
- GIVEN un artículo `precio_libre` con `pvp` explícito en el ítem
- WHEN se calcula la línea
- THEN se usa ese PVP (no el de catálogo) y se expone `requiere_cites`

**Tests**: `tests/test_tpv_api.py::test_calcular_totales_en_servidor`,
`::test_calcular_precio_libre`

### Requirement: Autenticación por PIN del operador

El sistema MUST autenticar al operador por PIN verificado contra hash antes de
habilitar el cobro, sin exponer el PIN en claro.

#### Scenario: Login correcto
- GIVEN un usuario activo con PIN configurado
- WHEN POST `/tpv/api/login` con el PIN correcto
- THEN responde 200 con `usuario_id`, `nombre`, `rol`

#### Scenario: PIN incorrecto
- WHEN POST `/tpv/api/login` con un PIN que no coincide con ningún usuario activo
- THEN responde 401

**Tests**: `tests/test_tpv_api.py::test_login_ok_y_ko`

### Requirement: Emisión de venta atómica y offline

El sistema MUST cerrar la venta y generar su registro fiscal encadenado en un único
commit atómico, sin dependencias de red en el flujo de cobro; MUST asignar
serie/número correlativo en esa misma transacción (ADR-0004); MUST rechazar
tickets vacíos y usuarios/artículos inválidos sin persistir nada.

#### Scenario: Cobro con cambio
- GIVEN 2 uds a 2,50 € y pago efectivo de 10,00 €
- WHEN se ejecuta `EmitirVenta` / POST `/tpv/api/cobrar`
- THEN venta queda `estado="cobrada"`, existe 1 `RegistroFiscal`, `num_serie`
  empieza por `"T"` (serie simplificada), total `"5.00"`, cambio `"5.00"`

#### Scenario: Ticket vacío
- WHEN se invoca con `items=[]`
- THEN se lanza `TicketVacio` (400 en la API); no se persiste venta

#### Scenario: Usuario o artículo inválido
- WHEN el `usuario_id` o `articulo_id` no existen
- THEN se lanza `UsuarioNoValido` (401) o `ArticuloNoExiste` (404) sin persistir

**Tests**: `tests/test_emitir_venta.py` (todos), `tests/test_tpv_api.py::test_cobrar_emite_venta`,
`::test_cobrar_ticket_vacio_rechaza`

### Requirement: Medios de pago y cambio

El sistema MUST admitir varios pagos por venta (efectivo, tarjeta) y MUST calcular
el cambio como el exceso del efectivo sobre el total, nunca negativo.

#### Scenario: Cambio en efectivo
- GIVEN total 5,00 € y pago efectivo 10,00 €
- THEN cambio `"5.00"`

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_emite_y_encadena`,
`tests/test_tpv_api.py::test_cobrar_emite_venta`

### Requirement: Impresión ESC/POS con QR y cajón

El sistema MUST imprimir el ticket de factura simplificada (art. 7 ROF) con
serie/número, fecha de expedición, NIF, líneas, total con coma decimal, leyenda
VERI*FACTU y QR tributario de cotejo embebido (comando `GS ( k`); MUST permitir
abrir el cajón por pulso con o sin venta asociada, dejando log de auditoría cuando
no hay venta; un fallo de impresora MUST NOT revertir una venta ya cerrada.

#### Scenario: Ticket con datos obligatorios y QR
- GIVEN una venta emitida con líneas a distinto tipo de IVA
- WHEN se imprime en una impresora Dummy
- THEN la salida contiene num_serie, fecha, `"NIF:"`, total con coma, la leyenda
  corta VERI*FACTU, la URL de cotejo con el NIF del emisor y el corte de papel

#### Scenario: Apertura de cajón sin venta
- WHEN POST `/tpv/api/cajon` sin venta asociada
- THEN se emite el pulso ESC/POS y queda un registro `accion="apertura_cajon_sin_venta"`
  en el log de auditoría

#### Scenario: Fallo de impresora no revierte la venta
- GIVEN una venta ya cobrada
- WHEN la impresión lanza una excepción de hardware
- THEN la venta permanece `"cobrada"`; el error solo se registra en log

**Tests**: `tests/test_ticket.py` (ambos), `app/presentacion/tpv.py::_imprimir_ticket_seguro`

### Requirement: QR tributario descargable

El sistema MUST exponer el QR de cotejo de cada venta emitida como imagen PNG.

#### Scenario: Descarga del QR
- WHEN GET `/tpv/api/venta/{venta_id}/qr.png`
- THEN responde 200, `content-type` PNG, cabecera PNG válida

**Tests**: `tests/test_tpv_api.py::test_cobrar_emite_venta` (bloque QR)

### Requirement: Drill-down de subfamilias filtra por visibilidad táctil

El sistema MUST listar, en `GET /tpv/api/familia/{familia_id}`, únicamente las
subfamilias con `visible_en_tactil = True` y `activo = True`. Una subfamilia
con `visible_en_tactil = False` MUST NOT aparecer en el listado de
`subfamilias`, aunque esté activa. Este filtro gobierna solo el listado de
navegación por familias; MUST NOT afectar al render de botones explícitos de
la botonera (`GET /api/botonera`) que apunten a una familia no visible: un
botón que referencia directamente una familia no visible se sigue mostrando
y funcionando con normalidad, porque el flag controla el drill-down, no el
botón.

#### Scenario: Subfamilia no visible queda excluida

- GIVEN una familia con dos subfamilias activas, una con
  `visible_en_tactil = True` y otra con `visible_en_tactil = False`
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN `subfamilias` incluye solo la que tiene `visible_en_tactil = True`

#### Scenario: Familias existentes (default True) no sufren regresión

- GIVEN subfamilias activas creadas antes de este cambio, todas con
  `visible_en_tactil = True` por el `server_default` de la migración
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN todas siguen apareciendo en `subfamilias`, igual que antes del cambio

#### Scenario: Subfamilia inactiva sigue excluida (comportamiento previo)

- GIVEN una subfamilia con `visible_en_tactil = True` pero `activo = False`
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN no aparece en `subfamilias`

#### Scenario: Botón explícito a familia no visible se respeta

- GIVEN un botón de botonera que apunta a una familia con
  `visible_en_tactil = False`
- WHEN GET `/api/botonera`
- THEN el botón aparece igual que si la familia fuera visible; el flag no
  afecta el render de botones, solo el listado de `subfamilias`

**Tests**: `tests/test_tpv_api.py::test_familia_excluye_subfamilias_no_visibles_en_tactil`,
`::test_familia_incluye_subfamilias_visibles_y_activas`,
`::test_botonera_respeta_boton_explicito_a_familia_no_visible`

## Constraints (no debilitar)

- Cobro sin dependencias de red (local-first).
- Numeración correlativa en la misma transacción (ADR-0004); nunca UPDATE/DELETE
  sobre ventas o registros emitidos (ADR-0003).
- Importes en `Decimal`; redondeo half-up por línea en una única función (ADR-0002/0005).

## Out of Scope

Límite de 3.000 € con forzado a factura completa, simplificada cualificada
(art. 7.2 ROF), conversión a F3 y devolución rectificativa: verificadas en la
capacidad `motor-fiscal-verifactu` (`tests/test_validaciones_negocio.py`,
`tests/test_sustitucion.py`), fuera del alcance de `tpv-venta`.
