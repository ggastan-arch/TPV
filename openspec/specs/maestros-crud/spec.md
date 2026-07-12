# maestros-crud Specification

## Purpose

CRUD de artículos, tipos de IVA, familias (árbol ilimitado) y clientes, vía
servicios de aplicación (`ServicioArticulos`, `ServicioTiposIva`, `ServicioFamilias`,
`ServicioClientes`), expuestos bajo `/admin/api/maestros/*`. Reglas comunes: nunca
hard-delete, y toda alta/edición/baja queda auditada.

## Requirements

### Requirement: Modo de precio del artículo (fijo | libre | al peso)

El sistema MUST exponer un campo `modo_precio` en `Articulo`, con valores excluyentes
`fijo`, `libre` o `al_peso`, que sustituye al booleano `precio_libre`. El sistema MUST
rechazar cualquier valor fuera de ese conjunto (422 vía API) sin persistir el artículo.
Si no se indica `modo_precio` al crear, el sistema MUST persistir `fijo` por defecto.
El campo MUST ser editable tanto al crear (`ServicioArticulos.crear` / `ArticuloReq`)
como al actualizar (`ServicioArticulos.actualizar`), y su edición MUST auditarse igual
que el resto de campos (`crear_articulo` / `actualizar_articulo`). En modo `al_peso` el
artículo MUST reutilizar `pvp` como precio por kg (sin columna nueva).

#### Scenario: Crear artículo sin indicar modo_precio usa el default
- GIVEN una petición de alta sin `modo_precio` en el payload
- WHEN se ejecuta `ServicioArticulos.crear`
- THEN el artículo persiste con `modo_precio = "fijo"`

#### Scenario: Crear artículo en modo al_peso
- GIVEN una petición de alta con `modo_precio = "al_peso"` y `pvp` como precio/kg
- WHEN se ejecuta `ServicioArticulos.crear`
- THEN el artículo persiste con ese `modo_precio` y ese `pvp`

#### Scenario: Actualizar el modo de precio de un artículo existente
- GIVEN un artículo existente con `modo_precio = "fijo"`
- WHEN se ejecuta `ServicioArticulos.actualizar` con `modo_precio = "libre"`
- THEN el artículo queda con `modo_precio = "libre"`
- AND existe 1 log `actualizar_articulo` con el `entidad_id` del artículo

#### Scenario: Valor de modo_precio inválido se rechaza
- WHEN se crea o actualiza un artículo con `modo_precio = "otro"` (fuera del enum)
- THEN se lanza `ModoPrecioInvalido` (422 vía API); no se persiste el cambio

#### Scenario: Migración de artículos existentes (precio_libre → modo_precio)
- GIVEN artículos previos a la migración, unos con `precio_libre = True` y otros con
  `precio_libre = False`
- WHEN se aplica la migración Alembic de este cambio
- THEN los primeros quedan con `modo_precio = "libre"` y los segundos con
  `modo_precio = "fijo"`

**Tests**: `tests/test_articulos.py::test_crear_articulo_sin_modo_precio_usa_default_fijo`,
`::test_crear_articulo_modo_al_peso`, `::test_actualizar_modo_precio_y_audita`,
`::test_modo_precio_invalido_falla_y_no_persiste`,
`::test_migracion_precio_libre_a_modo_precio` (NUEVO);
`tests/test_admin_api.py::test_crear_articulo_modo_precio_invalido` (NUEVO)

Nota: `modo_precio` es un valor único excluyente — nunca coexisten "libre" y "al_peso"
para el mismo artículo (evita estados ilegales de precio).

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

### Requirement: Visibilidad de familia en el táctil del TPV

El sistema MUST exponer un campo `visible_en_tactil` (booleano) en `Familia`,
editable al crear y al actualizar una familia desde la consola
(`FamiliaReq`/`DatosFamilia`/`ServicioFamilias.crear`/`actualizar`). Si no se
indica valor al crear, el sistema MUST persistir `visible_en_tactil = True`
por defecto. El cambio de valor MUST auditarse igual que el resto de campos
de familia (evento `crear_familia`/`actualizar_familia` ya existente).

#### Scenario: Crear familia sin indicar el flag usa el default

- GIVEN una petición de alta de familia sin `visible_en_tactil` en el payload
- WHEN se ejecuta `ServicioFamilias.crear`
- THEN la familia persiste con `visible_en_tactil = True`

#### Scenario: Crear familia marcándola como no visible

- GIVEN una petición de alta de familia con `visible_en_tactil = False`
- WHEN se ejecuta `ServicioFamilias.crear`
- THEN la familia persiste con `visible_en_tactil = False`
- AND queda 1 log `crear_familia` con `entidad_id` de la familia creada

#### Scenario: Actualizar el flag de una familia existente

- GIVEN una familia existente con `visible_en_tactil = True`
- WHEN se ejecuta `ServicioFamilias.actualizar` con `visible_en_tactil = False`
- THEN la familia queda con `visible_en_tactil = False`
- AND existe 1 log `actualizar_familia` con `entidad_id` de la familia

#### Scenario: El listado de maestros expone el flag

- GIVEN familias con distintos valores de `visible_en_tactil`
- WHEN GET `/admin/api/maestros/familias`
- THEN cada elemento del listado incluye `visible_en_tactil` con su valor persistido

**Tests**: `tests/test_familias.py::test_crear_familia_sin_flag_usa_default_true`,
`::test_crear_familia_no_visible_en_tactil_y_audita`,
`::test_actualizar_flag_visible_en_tactil_y_audita`;
`tests/test_admin_api.py::test_listado_maestros_familias_expone_visible_en_tactil`

### Requirement: Subida de imagen para artículo y familia con validación de tipo y tamaño

El sistema MUST permitir subir una imagen (JPEG, PNG o WebP) para un artículo o una
familia desde la consola, mediante un endpoint de subida multipart. El sistema MUST
verificar el tipo real del archivo (no el `content-type` declarado por el cliente) y
MUST rechazar cualquier tipo distinto a los permitidos. El sistema MUST rechazar
archivos que superen el tamaño máximo (~3 MB). En ambos rechazos, el sistema MUST NOT
guardar el archivo ni modificar el campo `imagen` del artículo/familia.

Cuando la subida es válida, el sistema MUST generar el nombre de archivo en el
servidor (nunca reutilizar el nombre enviado por el cliente, para evitar path
traversal), MUST guardar el archivo en `media/` y MUST persistir en BD solo la
ruta/nombre generado (`Articulo.imagen` o `Familia.imagen`); nunca el binario ni un
base64.

#### Scenario: Subida válida a un artículo
- GIVEN un artículo existente sin imagen
- WHEN se sube un archivo JPEG válido de 500 KB al endpoint de imagen de ese artículo
- THEN el archivo queda guardado en `media/` con un nombre generado por el servidor
- AND `Articulo.imagen` persiste la ruta/nombre de ese archivo (no el nombre original ni base64)

#### Scenario: Subida válida a una familia
- GIVEN una familia existente sin imagen
- WHEN se sube un archivo PNG válido de 1 MB al endpoint de imagen de esa familia
- THEN el archivo queda guardado en `media/` con un nombre generado por el servidor
- AND `Familia.imagen` persiste la ruta/nombre de ese archivo

#### Scenario: Tipo de archivo no permitido
- GIVEN un artículo existente
- WHEN se sube un archivo cuyo contenido real no es JPEG/PNG/WebP (p.ej. un `.txt`
  renombrado a `.jpg`, o un GIF, incluso si el cliente declara `content-type:
  image/jpeg`)
- THEN se rechaza la subida (422 vía API); no se guarda ningún archivo en `media/`
- AND `Articulo.imagen` no cambia

#### Scenario: Tamaño de archivo excede el máximo
- GIVEN una familia existente
- WHEN se sube una imagen válida en formato pero de más de 3 MB
- THEN se rechaza la subida (422 vía API); no se guarda ningún archivo en `media/`
- AND `Familia.imagen` no cambia

**Tests**: `tests/test_imagenes.py` (15 casos), `tests/test_admin_api.py` (subida válida, tipo inválido, tamaño excedido), `tests/test_esquema.py` (campo existe)

### Requirement: Reemplazo de imagen borra el archivo anterior

Cuando un artículo o familia ya tiene una imagen y se sube una nueva, el sistema MUST
borrar el archivo anterior de `media/` (best-effort: un fallo de borrado MUST NOT
impedir que la nueva imagen quede persistida), evitando archivos huérfanos.

#### Scenario: Reemplazar la imagen de un artículo
- GIVEN un artículo con una imagen ya subida (archivo A en `media/`)
- WHEN se sube una nueva imagen válida (archivo B) para ese artículo
- THEN `Articulo.imagen` pasa a apuntar al archivo B
- AND el archivo A ya no existe en `media/`

#### Scenario: Fallo al borrar el archivo anterior no bloquea el reemplazo
- GIVEN un artículo cuya imagen anterior ya no existe físicamente en disco
- WHEN se sube una nueva imagen válida para ese artículo
- THEN `Articulo.imagen` pasa a apuntar al nuevo archivo igualmente (el intento de
  borrado fallido no interrumpe la operación)

**Tests**: `tests/test_admin_api.py::test_reemplazar_imagen_articulo_borra_la_anterior`, `::test_reemplazar_imagen_familia_cuando_la_anterior_ya_no_existe_en_disco_no_bloquea`

## Constraints (no debilitar)

- Nunca `DELETE`/hard-delete sobre artículos, familias, tipos de IVA, clientes ni usuarios.
- Log de auditoría append-only para todo cambio de maestro (invariante 4).
- El porcentaje de IVA congelado en línea de venta nunca se reescribe.
- El PIN de usuario nunca se almacena ni se registra en claro; el sistema nunca queda sin administrador activo.

## Out of Scope

Ninguno pendiente en esta capacidad: el CRUD de usuarios quedó entregado (ver requisito
"Gestión de usuarios/operadores"). La remisión real a la AEAT sigue siendo trabajo futuro
del motor fiscal, no de los maestros.
