# Delta for maestros-crud

## ADDED Requirements

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

## Constraints (no debilitar)

- El nuevo campo no exime a `ServicioFamilias` de las reglas ya existentes
  (validación de padre, prevención de ciclos, bloqueo de baja con hijos
  activos, borrado lógico) ni de la obligación de auditar cada alta/edición.
