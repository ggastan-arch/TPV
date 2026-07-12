# Delta for maestros-crud

## ADDED Requirements

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

**Tests**: (a definir en diseño/tareas) — deben cubrir subida válida a artículo,
subida válida a familia, rechazo por tipo real no permitido (con content-type
falseado) y rechazo por tamaño excedido.

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

**Tests**: (a definir en diseño/tareas) — deben cubrir reemplazo con borrado del
archivo anterior y reemplazo cuando el archivo anterior ya no existe en disco.
