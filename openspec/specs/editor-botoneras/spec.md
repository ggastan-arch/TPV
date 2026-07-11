# editor-botoneras Specification

## Purpose

API bajo `/admin` para configurar la botonera del TPV (perfil → página → botón).
El backend es la ÚNICA fuente de verdad: valida todo layout antes de persistir;
ningún cliente puede dejar la botonera en estado inválido. El editor visual
drag & drop (frontend) consume esta API pero no se especifica aquí (ver Out of
Scope).

## Requirements

### Requirement: Gestión de perfiles con activación exclusiva

El sistema MUST permitir crear, editar y borrar perfiles de botonera. El
sistema MUST garantizar a lo sumo un perfil activo: activar un perfil MUST
desactivar automáticamente, en la misma operación, cualquier otro perfil que
estuviera activo.

#### Scenario: Activar un perfil desactiva los demás
- GIVEN el perfil A está activo y el perfil B existe inactivo
- WHEN se activa el perfil B
- THEN el perfil B queda activo y el perfil A queda inactivo

### Requirement: Gestión de páginas dentro de un perfil

El sistema MUST permitir crear, editar (nombre, orden, columnas, filas) y
borrar páginas de un perfil existente.

#### Scenario: Crear página con columnas y filas válidas
- GIVEN un perfil existente
- WHEN se crea una página con nombre, orden, columnas y filas válidos
- THEN la página queda asociada al perfil con esos valores

### Requirement: Guardado atómico del layout de una página (bulk)

El sistema MUST aceptar el conjunto completo de botones de una página en una
sola operación y MUST reemplazarlo de forma atómica. Si el conjunto es
inválido, el sistema MUST rechazar la operación completa y MUST NOT persistir
ningún cambio parcial.

#### Scenario: Guardar layout válido reemplaza el anterior
- GIVEN una página con un layout previo
- WHEN se guarda un nuevo conjunto de botones válido
- THEN el layout anterior desaparece y el nuevo queda persistido tal cual se envió

#### Scenario: Guardar layout inválido no persiste nada
- GIVEN una página con un layout previo
- WHEN se intenta guardar un conjunto que incumple alguna validación de rejilla
- THEN la operación se rechaza y el layout previo permanece exactamente igual

### Requirement: Validación de rejilla al guardar un layout

El sistema MUST rechazar el layout completo si algún botón incumple alguna de
estas reglas:

| Regla | Condición de rechazo |
|---|---|
| Límites | `fila + alto > filas` de la página, o `columna + ancho > columnas` |
| Solape | Dos botones cuyos rectángulos (fila, columna, alto, ancho) se intersectan (AABB) |
| Destino único | El botón no referencia exactamente uno de artículo, familia o función |
| Función válida | El valor de función no pertenece al conjunto `FUNCIONES` soportado |
| Referencia existente | El `articulo_id` o `familia_id` referenciado no existe |

#### Scenario: Botón fuera de los límites de la rejilla
- GIVEN una página de 5 columnas y 4 filas
- WHEN se guarda un botón cuyo `columna + ancho` supera 5
- THEN el layout se rechaza

#### Scenario: Dos botones se solapan
- WHEN se guarda un layout con dos botones cuyos rectángulos se intersectan
- THEN el layout se rechaza

#### Scenario: Destino no único
- WHEN se guarda un layout con un botón sin destino, o con más de uno de
  artículo/familia/función a la vez
- THEN el layout se rechaza

#### Scenario: Función fuera del conjunto soportado
- WHEN se guarda un layout con un botón de función cuyo valor no está en `FUNCIONES`
- THEN el layout se rechaza

#### Scenario: Artículo o familia inexistente
- WHEN se guarda un layout con un botón que referencia un `articulo_id` o
  `familia_id` inexistente
- THEN el layout se rechaza

### Requirement: Auditoría de cambios de botonera

El sistema MUST registrar en el log de auditoría append-only cada creación,
edición, borrado y activación sobre perfiles, páginas y layouts de botones
(invariante 4).

#### Scenario: Guardar un layout queda auditado
- WHEN se guarda un layout de página válido
- THEN existe un nuevo `LogAuditoria` con la acción y la entidad afectada

### Requirement: Compatibilidad del contrato de lectura del TPV

El sistema MUST mantener sin cambios de forma la respuesta de `GET
/tpv/api/botonera` (perfil activo, página de menor orden, botones con tipo y
destino) tras cualquier edición realizada desde el editor.

#### Scenario: El TPV lee lo editado con el mismo contrato
- GIVEN se edita y guarda un nuevo layout en el perfil activo
- WHEN se consulta `GET /tpv/api/botonera`
- THEN la respuesta conserva su forma actual y refleja el layout recién guardado

### Requirement: Borrado en cascada de páginas y botones

El sistema MUST eliminar automáticamente las páginas y botones de un perfil al
borrarlo, y los botones de una página al borrarla, sin dejar registros huérfanos.

#### Scenario: Borrar un perfil elimina sus páginas y botones
- GIVEN un perfil con páginas y botones
- WHEN se borra el perfil
- THEN el perfil, sus páginas y sus botones dejan de existir

#### Scenario: Borrar una página elimina sus botones
- GIVEN una página con botones colocados
- WHEN se borra la página
- THEN la página y sus botones dejan de existir

## Constraints (no debilitar)

- El backend es la única fuente de verdad: ningún cliente puede persistir un
  layout inválido, sin importar el estado del frontend.
- Toda acción de edición de botonera queda en el log de auditoría append-only
  (invariante 4).
- `GET /tpv/api/botonera` no cambia de forma.

## Out of Scope

Editor visual drag & drop (frontend, sin infraestructura de test JS — se
verifica a mano); undo/redo; gestos táctiles avanzados/multitouch; i18n de
textos de botón.
