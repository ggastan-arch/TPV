# maestros-crud Specification

## Purpose

CRUD de artículos, tipos de IVA, familias (árbol ilimitado) y clientes, vía
servicios de aplicación (`ServicioArticulos`, `ServicioTiposIva`, `ServicioFamilias`,
`ServicioClientes`), expuestos bajo `/admin/api/maestros/*`. Reglas comunes: nunca
hard-delete, y toda alta/edición/baja queda auditada.

## Requirements

### Requirement: Validación de claves foráneas al crear/editar artículo

El sistema MUST validar que `tipo_iva_id` y, si se indica, `familia_id` existen
antes de persistir un artículo; MUST NOT persistir nada si la validación falla.

#### Scenario: Tipo de IVA inexistente
- WHEN se crea un artículo con `tipo_iva_id` inexistente
- THEN se lanza `TipoIvaNoExiste` (422 vía API) y no se crea el artículo

#### Scenario: Familia inexistente
- WHEN se crea un artículo con `familia_id` inexistente
- THEN se lanza `FamiliaNoExiste` (422 vía API)

**Tests**: `tests/test_articulos.py::test_crear_tipo_iva_inexistente_falla_y_no_persiste`,
`::test_crear_familia_inexistente_falla`, `::test_crear_con_familia_valida`;
`tests/test_admin_api.py::test_crear_articulo_tipo_iva_inexistente`

### Requirement: Auditoría del cambio de precio de artículo

El sistema MUST registrar un evento `cambio_precio` (con precio anterior y nuevo)
solo cuando el PVP cambia, además del evento genérico `actualizar_articulo` en
toda edición.

#### Scenario: Cambio de precio auditado
- WHEN se actualiza un artículo cambiando el PVP de 2,50 € a 3,00 €
- THEN existe 1 log `cambio_precio` con ambos valores

#### Scenario: Edición sin cambio de precio
- WHEN se actualiza un artículo sin tocar el PVP
- THEN no se genera log `cambio_precio` (sí `actualizar_articulo`)

**Tests**: `tests/test_articulos.py::test_actualizar_cambia_precio_y_audita_cambio_precio`,
`::test_actualizar_sin_cambio_de_precio_no_audita_cambio_precio`

### Requirement: Alta/edición de tipo de IVA con validación de porcentaje

El sistema MUST validar que el porcentaje esté en rango válido (≥ 0) al crear o
editar un tipo de IVA, y MUST auditar el cambio de porcentaje (`cambio_porcentaje_iva`)
solo cuando el valor difiere del anterior.

#### Scenario: Porcentaje inválido
- WHEN se crea/edita un tipo de IVA con porcentaje negativo
- THEN se lanza `PorcentajeInvalido` (422 vía API); no se persiste

#### Scenario: Cambio de porcentaje auditado
- WHEN se edita el porcentaje del 10,00 % al 8,00 %
- THEN existe 1 log `cambio_porcentaje_iva` con ambos valores

**Tests**: `tests/test_tipos_iva.py::test_crear_porcentaje_negativo_falla`,
`::test_actualizar_cambia_porcentaje_y_audita`,
`::test_actualizar_sin_cambio_de_porcentaje_no_audita_cambio`;
`tests/test_admin_api.py::test_crear_tipo_iva_porcentaje_invalido`

### Requirement: El porcentaje de IVA vigente no altera ventas ya emitidas

El sistema MUST preservar el porcentaje de IVA congelado en cada línea de venta
ya emitida; editar el tipo de IVA tras la emisión MUST NOT reescribir la cuota
histórica.

#### Scenario: IVA editado tras emitir
- GIVEN una venta emitida con línea al 21 %
- WHEN se cambia el tipo de IVA general al 5 %
- THEN la línea de la venta ya emitida sigue en `21.00` (congelado)

**Tests**: `tests/test_tipos_iva.py::test_cambiar_porcentaje_no_altera_ventas_ya_emitidas`

### Requirement: Árbol de familias sin ciclos

El sistema MUST rechazar la creación/reasignación de una familia cuyo padre sea
ella misma o uno de sus descendientes, para no romper el árbol recursivo.

#### Scenario: Auto-referencia o ciclo con descendiente
- WHEN se asigna como padre la propia familia, o un descendiente suyo
- THEN se lanza `CicloEnFamilia` (422 vía API); la reasignación no se aplica

#### Scenario: Reasignación válida
- WHEN se reasigna una familia a un padre válido no descendiente
- THEN se aplica y queda auditada (`actualizar_familia`)

**Tests**: `tests/test_familias.py::test_no_puede_ser_su_propio_padre`,
`::test_no_puede_colgar_de_un_descendiente`, `::test_reasignar_padre_valido_ok_y_audita`;
`tests/test_admin_api.py::test_reasignar_padre_ciclo_devuelve_422`

### Requirement: No desactivar familia con hijos activos

El sistema MUST impedir la baja lógica de una familia mientras tenga subfamilias
activas, para no dejar huérfanos en la navegación.

#### Scenario: Baja bloqueada
- GIVEN una familia con al menos una subfamilia activa
- WHEN se intenta desactivarla
- THEN se lanza `FamiliaConHijos` (409 vía API); permanece activa

#### Scenario: Baja permitida tras desactivar hijos
- GIVEN los hijos ya desactivados
- WHEN se desactiva el padre
- THEN se aplica correctamente

**Tests**: `tests/test_familias.py::test_no_desactivar_con_hijos_activos`,
`::test_desactivar_padre_tras_desactivar_hijos`;
`tests/test_admin_api.py::test_desactivar_familia_con_hijos_devuelve_409`

### Requirement: NIF de cliente opcional pero validado y normalizado

El sistema MUST permitir crear un cliente sin NIF (la simplificada no lo exige);
si se aporta, MUST validarlo (NIF/NIE/CIF) y MUST almacenarlo normalizado
(mayúsculas, sin espacios).

#### Scenario: Cliente sin NIF
- WHEN se crea un cliente sin NIF
- THEN se persiste con `nif=None`

#### Scenario: NIF válido normalizado
- WHEN se crea/edita con NIF `" a58818501 "`
- THEN se almacena como `"A58818501"`

#### Scenario: NIF inválido
- WHEN se crea/edita con un NIF que no supera la validación
- THEN se lanza `NifInvalido` (422 vía API); no se persiste el cambio

**Tests**: `tests/test_clientes.py::test_crear_cliente_sin_nif_ok`,
`::test_crear_cliente_con_nif_valido_se_normaliza`,
`::test_crear_cliente_nif_invalido_falla_y_no_persiste`, `::test_actualizar_nif_invalido_falla`;
`tests/test_admin_api.py::test_crear_cliente_nif_invalido`

### Requirement: Borrado lógico en todos los maestros (nunca hard-delete)

El sistema MUST NOT eliminar físicamente artículos, tipos de IVA, familias ni
clientes; la baja MUST marcar `activo=false`, preservando el registro y su
historial de auditoría; MUST permitir reactivar.

#### Scenario: Baja y reactivación de artículo
- WHEN se desactiva y luego se activa un artículo
- THEN sigue existiendo la fila; `activo` refleja el último estado

#### Scenario: Listado excluye inactivos por defecto
- WHEN se listan artículos sin pedir inactivos
- THEN los desactivados no aparecen, pero siguen en BD

**Tests**: `tests/test_articulos.py::test_desactivar_no_borra_marca_inactivo`,
`::test_activar_reactiva`, `::test_listar_puede_excluir_inactivos`;
`tests/test_tipos_iva.py::test_desactivar_no_borra`;
`tests/test_familias.py::test_desactivar_hoja_ok_no_borra`;
`tests/test_clientes.py::test_desactivar_no_borra`;
`tests/test_admin_api.py::test_desactivar_articulo`

### Requirement: Toda alta/edición/baja de maestro queda auditada

El sistema MUST registrar en el log de auditoría cada creación, edición y baja de
artículo, tipo de IVA, familia y cliente, con `entidad`, `entidad_id` y `usuario_id`.

#### Scenario: Alta de artículo auditada
- WHEN se crea un artículo
- THEN existe 1 log `crear_articulo` con `entidad="articulo"` y el `usuario_id` actor

**Tests**: `tests/test_articulos.py::test_crear_articulo_persiste_y_audita`;
`tests/test_familias.py::test_crear_familia_raiz_persiste_y_audita`;
`tests/test_clientes.py::test_actualizar_cliente_ok_y_audita`;
`tests/test_tipos_iva.py::test_crear_tipo_iva_persiste_y_audita`

### Requirement: Gestión de usuarios/operadores con salvaguarda de administrador

El sistema MUST permitir crear/editar/activar/desactivar operadores del TPV con rol
`venta` o `administracion`; MUST almacenar el PIN hasheado (nunca en claro ni en el log
de auditoría); MUST garantizar nombre único; y MUST NOT dejar el sistema sin ningún
administrador activo (ni por baja ni por degradación de rol).

#### Scenario: No se puede desactivar/degradar al último administrador activo
- GIVEN un único administrador activo en el sistema
- WHEN se intenta desactivarlo o cambiar su rol a `venta`
- THEN se lanza `UltimoAdministrador` (409 vía API) y el administrador permanece activo

#### Scenario: El cambio de PIN no expone el PIN
- WHEN se cambia el PIN de un usuario
- THEN el nuevo PIN queda hasheado y no aparece en ninguna entrada del log de auditoría

**Tests**: `tests/test_usuarios.py::test_crear_usuario_hashea_pin_y_audita`,
`::test_no_desactivar_ultimo_administrador`, `::test_no_degradar_a_venta_al_ultimo_administrador`,
`::test_cambiar_pin_no_expone_el_pin`; `tests/test_admin_api.py::test_desactivar_ultimo_admin_devuelve_409`

## Constraints (no debilitar)

- Nunca `DELETE`/hard-delete sobre artículos, familias, tipos de IVA, clientes ni usuarios.
- Log de auditoría append-only para todo cambio de maestro (invariante 4).
- El porcentaje de IVA congelado en línea de venta nunca se reescribe.
- El PIN de usuario nunca se almacena ni se registra en claro; el sistema nunca queda sin administrador activo.

## Out of Scope

Ninguno pendiente en esta capacidad: el CRUD de usuarios quedó entregado (ver requisito
"Gestión de usuarios/operadores"). La remisión real a la AEAT sigue siendo trabajo futuro
del motor fiscal, no de los maestros.
