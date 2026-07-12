# tpv-venta Specification

## Purpose

Venta táctil monopuesto: cálculo de líneas, cobro OFFLINE, emisión con serie/número
correlativos y registro fiscal encadenado, impresión ESC/POS con QR y apertura de
cajón. Endpoints bajo `/tpv`, protegidos con PIN de operador.

## Requirements

### Requirement: Cálculo de líneas en servidor con precio e IVA congelados

El sistema MUST calcular cada línea en el servidor con `Decimal` y la función única de
redondeo (half-up por línea), congelando el PVP y el porcentaje de IVA vigente del
artículo en el momento del cálculo. El frontend MUST NOT hacer aritmética de importes.
Cuando el ítem incluye un `pvp` override, el sistema MUST usar ese PVP para la línea en
lugar del PVP de catálogo, independientemente del `modo_precio` del artículo. En
`modo_precio == "al_peso"`, el sistema MUST tratar la `cantidad` del ítem como el peso
ingresado (en kg) y el `pvp` de catálogo (o su override) como precio por kg; el total de
línea sigue siendo `cantidad x pvp_unitario` (misma fórmula, sin cambios).
(Previously: el override de `pvp` se describía en términos del booleano `precio_libre`;
ahora se describe en términos de `modo_precio`, y se añade el modo `al_peso`, que
reutiliza la misma fórmula con `cantidad` = peso.)

#### Scenario: Cálculo de totales vía API
- GIVEN un artículo con PVP 2,50 € y cantidad 2
- WHEN POST `/tpv/api/calcular`
- THEN el total es `"5.00"` (string decimal exacto)

#### Scenario: Artículo en modo libre
- GIVEN un artículo con `modo_precio = "libre"` y `pvp` explícito en el ítem
- WHEN se calcula la línea
- THEN se usa ese `pvp` (no el de catálogo) y se expone `requiere_cites`

#### Scenario: Override de precio en línea de artículo en modo fijo
- GIVEN un artículo con `modo_precio = "fijo"`, PVP de catálogo 3,00 € y cantidad 1
- WHEN se calcula la línea con un `pvp` override de 2,00 € en el ítem
- THEN la línea usa 2,00 € como PVP, no el de catálogo

#### Scenario: Sin override, la línea usa el PVP de catálogo
- GIVEN un artículo en modo fijo con PVP de catálogo 3,00 € y cantidad 1
- WHEN se calcula la línea sin `pvp` override
- THEN la línea usa 3,00 € (PVP de catálogo), igual que antes del cambio

#### Scenario: Cálculo en modo al_peso con peso decimal (NUEVO)
- GIVEN un artículo con `modo_precio = "al_peso"` y `pvp` (precio/kg) 4,50 €
- WHEN se calcula la línea con `cantidad` = 1,250 (peso en kg)
- THEN el total de línea es `"5.63"` (4,50 × 1,250, half-up)

**Tests**: `tests/test_tpv_api.py::test_calcular_totales_en_servidor`,
`::test_calcular_modo_libre`, `::test_calcular_override_pvp_articulo_modo_fijo`,
`::test_calcular_sin_override_usa_pvp_catalogo`,
`::test_calcular_modo_al_peso_con_peso_decimal` (NUEVO)

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

### Requirement: Congelado de línea editada y auditoría de precio manual al emitir

El sistema MUST congelar en `VentaLinea`, al emitir, los valores editados en el carrito
pre-emisión: si el ítem trae un `pvp` override, `VentaLinea.pvp_unitario` MUST ser ese
valor; si trae una `descripcion` override, `VentaLinea.descripcion` MUST ser ese texto
(si no, `articulo.nombre` como hoy, salvo en `modo_precio == "libre"`, ver requisito de
descripción obligatoria); `VentaLinea.cantidad` MUST ser la cantidad del ítem (en
`modo_precio == "al_peso"`, el peso ingresado). Si el `pvp_unitario` congelado de una
línea de un artículo con `modo_precio` en `{"fijo", "al_peso"}` difiere del PVP de
catálogo en ese momento, el sistema MUST registrar un evento en `LogAuditoria` con
`accion="precio_manual_venta"`. Los artículos con `modo_precio == "libre"` MUST NOT
generar evento de auditoría de precio. Si no hay diferencia (o el artículo está en modo
libre), el sistema MUST NOT registrar ningún evento. Un carrito editado que nunca se
emite MUST NOT generar ningún evento.
(Previously: la exclusión de auditoría se basaba en el booleano `precio_libre`; ahora se
basa en `modo_precio == "libre"`, y se aclara que `al_peso` audita igual que `fijo`.)

#### Scenario: Precio override se congela en pvp_unitario al emitir
- GIVEN un ítem con `pvp` override de 2,00 € sobre un artículo en modo fijo con PVP de
  catálogo 3,00 €
- WHEN se emite la venta
- THEN `VentaLinea.pvp_unitario` es 2,00 €

#### Scenario: Descripción override se congela en la línea
- GIVEN un ítem con `descripcion` override `"Guppy macho - promo"`
- WHEN se emite la venta
- THEN `VentaLinea.descripcion` es `"Guppy macho - promo"`

#### Scenario: Cantidad editada se refleja en la línea emitida
- GIVEN un ítem con `cantidad` editada a 3
- WHEN se emite la venta
- THEN `VentaLinea.cantidad` es 3

#### Scenario: Precio manual distinto del catálogo genera auditoría (modo fijo)
- GIVEN un ítem con `pvp` override de 2,00 € sobre un artículo en modo fijo con PVP de
  catálogo 3,00 €
- WHEN se emite la venta
- THEN existe 1 registro `LogAuditoria` con `accion="precio_manual_venta"`,
  catálogo 3,00 € -> cobrado 2,00 €

#### Scenario: Precio manual distinto del catálogo genera auditoría (modo al_peso) (NUEVO)
- GIVEN un ítem de un artículo `al_peso` con `pvp` override de 5,00 €/kg sobre un precio
  de catálogo de 4,50 €/kg
- WHEN se emite la venta
- THEN existe 1 registro `LogAuditoria` con `accion="precio_manual_venta"` para esa línea

#### Scenario: Precio sin diferencia no genera evento de auditoría
- GIVEN un ítem sin override de `pvp` (o igual al de catálogo)
- WHEN se emite la venta
- THEN no existe ningún registro `precio_manual_venta` para esa línea

#### Scenario: Artículo en modo libre no genera evento de auditoría de precio
- GIVEN un ítem `modo_precio = "libre"` con `pvp` override de 5,00 € (catálogo nominal
  0,00 €) y descripción
- WHEN se emite la venta
- THEN no existe ningún registro `precio_manual_venta` para esa línea

#### Scenario: No-regresión — artículo migrado de precio_libre a modo libre (NUEVO)
- GIVEN un artículo migrado (antes `precio_libre = True`, ahora `modo_precio = "libre"`)
  con `pvp` override y descripción
- WHEN se emite la venta
- THEN se emite igual que antes de la migración; no genera evento de auditoría de precio

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_congela_pvp_override_modo_fijo`,
`::test_emitir_venta_congela_descripcion_override`,
`::test_emitir_venta_congela_cantidad_editada`,
`::test_emitir_venta_registra_auditoria_precio_manual_modo_fijo`,
`::test_emitir_venta_registra_auditoria_precio_manual_modo_al_peso` (NUEVO),
`::test_emitir_venta_sin_diferencia_precio_no_registra_auditoria`,
`::test_emitir_venta_modo_libre_no_registra_auditoria`,
`::test_emitir_venta_articulo_migrado_modo_libre_no_regresion` (NUEVO)

### Requirement: Descripción obligatoria en modo libre al emitir

El sistema MUST rechazar la emisión completa de la venta (sin persistir nada) cuando una
línea de un artículo con `modo_precio == "libre"` resuelve una descripción vacía (sin
override, o un override compuesto solo de espacios). El sistema MUST lanzar
`DescripcionRequerida` (422 vía API) en ese caso. Esta validación solo aplica al emitir;
el cálculo/preview (`POST /tpv/api/calcular`) MUST NOT bloquearse por descripción vacía.

#### Scenario: Línea libre sin descripción se rechaza al emitir
- GIVEN un ítem de un artículo `modo_precio = "libre"` sin `descripcion` en el payload
- WHEN se ejecuta `EmitirVenta` / POST `/tpv/api/cobrar`
- THEN se lanza `DescripcionRequerida`; no se persiste venta ni registro fiscal

#### Scenario: Línea libre con descripción se emite correctamente
- GIVEN un ítem `modo_precio = "libre"` con `descripcion = "Roca decorativa 2kg"`
- WHEN se emite la venta
- THEN la venta se emite con éxito y `VentaLinea.descripcion` es `"Roca decorativa 2kg"`

#### Scenario: El cálculo/preview no bloquea por descripción vacía
- GIVEN un ítem de un artículo `modo_precio = "libre"` sin `descripcion`
- WHEN POST `/tpv/api/calcular`
- THEN la línea se calcula igual; la validación solo se aplica al emitir

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_modo_libre_sin_descripcion_rechaza`
(NUEVO), `::test_emitir_venta_modo_libre_con_descripcion_ok` (NUEVO);
`tests/test_tpv_api.py::test_calcular_modo_libre_sin_descripcion_no_bloquea` (NUEVO),
`::test_cobrar_modo_libre_sin_descripcion_devuelve_422` (NUEVO)

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

### Requirement: El DTO de botón/familia/artículo expone la imagen efectiva del destino

El sistema MUST incluir un campo `imagen` (ruta relativa bajo `media/`, o `null` si no
tiene) en:
- el objeto `articulo` de cada botón de tipo `articulo` en `GET /api/botonera`,
- el objeto `familia` de cada botón de tipo `familia` en `GET /api/botonera`,
- cada elemento de `subfamilias` y de `articulos` en `GET /tpv/api/familia/{familia_id}`.

El valor MUST ser el campo `imagen` del artículo o familia de destino (no existe un
campo `imagen` propio del botón); si el destino no tiene imagen asignada, el campo
MUST ser `null` y el sistema MUST NOT fallar al construir la respuesta para ese botón.

#### Scenario: Botón de artículo con imagen
- GIVEN un artículo con `imagen` asignada, referenciado por un botón de la botonera activa
- WHEN GET `/api/botonera`
- THEN el botón correspondiente incluye `articulo.imagen` con la ruta persistida

#### Scenario: Botón de familia con imagen
- GIVEN una familia con `imagen` asignada, referenciada por un botón de la botonera activa
- WHEN GET `/api/botonera`
- THEN el botón correspondiente incluye `familia.imagen` con la ruta persistida

#### Scenario: Destino sin imagen expone null
- GIVEN un artículo o una familia sin `imagen` asignada, referenciado por un botón
- WHEN GET `/api/botonera`
- THEN el campo `imagen` del destino es `null` y la respuesta no falla

#### Scenario: Drill-down de familia expone imagen de subfamilias y artículos
- GIVEN una familia con subfamilias y artículos, algunos con `imagen` asignada y otros sin ella
- WHEN GET `/tpv/api/familia/{familia_id}`
- THEN cada elemento de `subfamilias` y de `articulos` incluye su `imagen`
  (la persistida o `null`)

**Tests**: `tests/test_tpv_api.py::test_botonera_expone_imagen_de_articulo_y_familia_con_imagen_asignada`, `::test_botonera_destino_sin_imagen_expone_null_y_no_falla`, `::test_familia_drilldown_expone_imagen_en_subfamilias_y_articulos`

### Requirement: Búsqueda incremental de artículos por nombre

El sistema MUST exponer un endpoint de solo lectura `GET /tpv/api/buscar?q=...`
sin efectos secundarios (no modifica estado). El universo de búsqueda MUST ser
todos los artículos con `activo = True` (no se filtra por familia ni por
`visible_en_tactil`). El sistema MUST considerar coincidencia cuando `q`
aparece como subcadena, case-insensitive, dentro de `nombre` **o** de
`nombre_corto` del artículo. El sistema MUST NOT buscar por código de barras
(ese universo lo cubre `GET /tpv/api/articulo/por-codigo/{codigo}`). Cada
artículo devuelto MUST tener la misma forma que produce `_articulo_dto`
(`id`, `nombre`, `nombre_corto`, `pvp`, `tipo_iva`, `precio_libre`,
`requiere_cites`, `color`, `imagen`), para poder agregarse al carrito sin
transformación adicional.

#### Scenario: Coincidencia por nombre, case-insensitive

- GIVEN un artículo activo con `nombre = "Betta Splendens Macho"`
- WHEN GET `/tpv/api/buscar?q=BETTA`
- THEN la respuesta incluye ese artículo con la forma `_articulo_dto`

#### Scenario: Coincidencia por nombre_corto

- GIVEN un artículo activo cuyo `nombre` no contiene "xyz" pero cuyo
  `nombre_corto` sí lo contiene
- WHEN GET `/tpv/api/buscar?q=xyz`
- THEN la respuesta incluye ese artículo

#### Scenario: Artículo inactivo excluido

- GIVEN un artículo con `activo = False` cuyo `nombre` coincide con `q`, y
  otro artículo activo cuyo `nombre` también coincide
- WHEN GET `/tpv/api/buscar?q=guppy`
- THEN la respuesta incluye solo el artículo activo

**Tests**: `tests/test_tpv_api.py::test_buscar_coincide_por_nombre_case_insensitive`,
`::test_buscar_coincide_por_nombre_corto`,
`::test_buscar_excluye_articulos_inactivos`

### Requirement: Longitud mínima de consulta y límite de resultados

El sistema MUST NOT ejecutar ninguna coincidencia contra el catálogo cuando
`q` tiene menos de 2 caracteres (ausente, vacío o de 1 carácter), devolviendo
una lista de artículos vacía. El sistema MUST limitar el número de artículos
devueltos a un máximo de 20, aunque coincidan más artículos con `q`.

#### Scenario: Query por debajo del mínimo no ejecuta búsqueda

- WHEN GET `/tpv/api/buscar?q=a`
- THEN responde 200 con una lista de artículos vacía

#### Scenario: Query ausente no ejecuta búsqueda

- WHEN GET `/tpv/api/buscar` sin parámetro `q`
- THEN responde 200 con una lista de artículos vacía

#### Scenario: Más de 20 coincidencias se recortan al top 20

- GIVEN 25 artículos activos cuyo `nombre` contiene "pez"
- WHEN GET `/tpv/api/buscar?q=pez`
- THEN la respuesta contiene como máximo 20 artículos

**Tests**: `tests/test_tpv_api.py::test_buscar_query_corta_no_ejecuta_busqueda`,
`::test_buscar_limita_a_top_20`

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
