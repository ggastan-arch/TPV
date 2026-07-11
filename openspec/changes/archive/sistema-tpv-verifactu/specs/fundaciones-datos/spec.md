# Fundaciones de Datos — Especificación

## Purpose

Tipos monetarios exactos, redondeo único, validadores de documentos, esquema, inmutabilidad
y numeración a nivel de base de datos, y estructuras append-only de auditoría y catálogo.
Base del motor fiscal VERI*FACTU.

## Requirements

### Requirement: Importes exactos en Decimal

El sistema MUST almacenar y operar todo importe, porcentaje y cantidad como `Decimal`,
persistido en columnas TEXT (`DecimalTexto`), sin degradar nunca a `float` (ADR-0002).

#### Scenario: Ida y vuelta sin pérdida de precisión
- GIVEN un importe `Decimal` calculado por el dominio
- WHEN se persiste y se recupera de la base de datos
- THEN el valor devuelto sigue siendo `Decimal` e idéntico al original

**Trazabilidad**: `tests/test_redondeo.py::test_no_hay_float_en_el_camino`; columnas TEXT
verificadas en `tests/test_esquema.py`; implementación `app/infraestructura/tipos.py::DecimalTexto`.

### Requirement: Redondeo único half-up por línea

El sistema MUST calcular base y cuota por línea con una única función (`redondeo_half_up`):
`cuota = total - base` como residuo, garantizando `base + cuota == total` incluso con tipos
de IVA mezclados (ADR-0005).

#### Scenario: Ticket con dos tipos de IVA cuadra
- GIVEN un ticket con líneas al 21 % y al 10 %
- WHEN se agregan los totales por tipo
- THEN Σ bases + Σ cuotas == importe total, sin descuadre de céntimos

**Trazabilidad**: `tests/test_redondeo.py::test_ticket_multitipo_cuadra`,
`test_base_mas_cuota_igual_total`, `test_descuento_por_linea`.

### Requirement: Validación de NIF/NIE/CIF

El sistema MUST validar NIF, NIE y CIF por dígito/letra de control y MUST normalizar
espacios/guiones a mayúsculas sin separadores.

#### Scenario: Letra de control incorrecta se rechaza
- GIVEN un NIF con letra de control errónea
- WHEN se valida el documento
- THEN el validador devuelve `False`

**Trazabilidad**: `tests/test_nif.py::test_documentos_validos`, `test_documentos_invalidos`,
`test_normalizar_documento`.

### Requirement: Esquema de base de datos coherente con los modelos

El sistema MUST mantener las migraciones Alembic sincronizadas con los modelos: toda tabla
y columna del modelo MUST existir tras aplicarlas.

#### Scenario: La migración refleja el modelo
- GIVEN las migraciones aplicadas sobre una base limpia
- WHEN se inspecciona el esquema real
- THEN cada tabla y columna del modelo existe en la base de datos

**Trazabilidad**: `tests/test_esquema.py::test_todas_las_tablas_y_columnas_del_modelo_existen`.

### Requirement: Inmutabilidad de ventas y registros fiscales

El sistema MUST rechazar (triggers `BEFORE UPDATE/DELETE`) todo `UPDATE`/`DELETE` sobre una
venta emitida o un registro fiscal, salvo la transición controlada de estado y el metadato
`estado_remision`. Una venta aparcada MAY modificarse o borrarse (ADR-0003).

#### Scenario: Intento de alterar una venta emitida
- GIVEN una venta cobrada con registro fiscal
- WHEN se intenta modificar su importe o borrarla
- THEN la operación se rechaza y la transacción se revierte

#### Scenario: Venta aparcada sigue editable
- GIVEN una venta no emitida
- WHEN se modifica o borra
- THEN se permite

**Trazabilidad**: `tests/test_inmutabilidad.py` (todas); triggers en
`tests/test_esquema.py::test_triggers_de_inmutabilidad_instalados`.

### Requirement: Numeración correlativa sin huecos

El sistema MUST asignar el número de serie en la misma transacción de emisión
(`BEGIN IMMEDIATE`), garantizando correlatividad exacta sin huecos ni duplicados bajo
concurrencia real (ADR-0004).

#### Scenario: Veinte emisiones concurrentes
- GIVEN 20 hilos emitiendo ventas simultáneas contra la misma serie/ejercicio
- WHEN todas las emisiones concluyen
- THEN los números asignados son exactamente `{1..20}`, uno por registro fiscal

**Trazabilidad**: `tests/test_numeracion_concurrente.py::test_emisiones_concurrentes_sin_huecos_ni_duplicados`.

### Requirement: Log de auditoría append-only

El sistema MUST permitir solo `INSERT` sobre `log_auditoria`; todo `UPDATE`/`DELETE` MUST
rechazarse a nivel de base de datos.

#### Scenario: Intento de manipular una entrada del log
- GIVEN una entrada ya insertada en el log de auditoría
- WHEN se intenta modificarla o borrarla
- THEN la base de datos rechaza la operación

**Trazabilidad**: `tests/test_auditoria_append_only.py` (todas).

### Requirement: Árbol de familias de niveles ilimitados

El sistema MUST soportar jerarquías de familias de profundidad arbitraria por
auto-referencia (`parent_id`), consultables recursivamente en ambos sentidos.

#### Scenario: Árbol de 6 niveles se recorre completo
- GIVEN una cadena de 6 familias anidadas
- WHEN se consulta la descendencia desde la raíz y el ascenso desde la hoja
- THEN se obtienen exactamente los 6 niveles en ambos sentidos

**Trazabilidad**: `tests/test_familia_arbol.py::test_arbol_de_familias_n_niveles`.
