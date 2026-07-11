# Tasks: Editor visual de botoneras (consola admin)

## Resumen de entrega

Entrega en **2 tandas independientes**:

- **Tanda 1 — Backend (TDD estricto rojo → verde)**: tareas 1–6. Autocontenida y
  committeable por sí sola: al terminarla, la API `/admin/api/botonera/*` es
  completa, validada, auditada y con la suite en verde. El frontend previo
  (si existiera) no se toca.
- **Tanda 2 — Frontend (verificación manual)**: tareas 7–8. Depende por completo
  de la Tanda 1 (consume su API). Sin tests automáticos: checklist de
  verificación manual explícito.

Cada tarea de la Tanda 1 sigue el ciclo TDD: escribir el test que falla
(rojo) → implementar lo mínimo para que pase (verde) → refactor si aplica,
sin romper verde. No se escribe implementación antes que su test.

## Trazabilidad requisito (spec) → tarea

| Requisito (spec) | Tarea(s) |
|---|---|
| Gestión de perfiles con activación exclusiva | 3, 4 |
| Gestión de páginas dentro de un perfil | 3, 4 |
| Guardado atómico del layout de una página (bulk) | 1, 3, 4 |
| Validación de rejilla al guardar un layout | 1, 3 |
| Auditoría de cambios de botonera | 3, 4 |
| Compatibilidad del contrato de lectura del TPV | 5 |
| Borrado en cascada de páginas y botones | 2, 3 |

---

## Tanda 1 — Backend (TDD estricto)

### Tarea 1 — Función pura `validar_layout_botonera` (dominio)

Capa: `app/dominio/servicios/botonera.py` (nuevo). Sin BD, sin I/O.
**Paralelizable con la Tarea 2** (no comparten código; la Tarea 3 depende de
ambas).

- [x] Rojo: crear `tests/test_botonera_dominio.py` con casos que fallan porque
      `validar_layout_botonera` y `BotonSpec` aún no existen.
- [x] Rojo→Verde: `BotonSpec` (dataclass frozen: `ref, fila, columna, ancho,
      alto, articulo_id, familia_id, funcion`) y `validar_layout_botonera(filas,
      columnas, botones) -> list[str]` que devuelve `[]` en layout válido.
- [x] Rojo→Verde: regla **límites** — fila/columna negativos, ancho/alto < 1,
      `fila + alto > filas`, `columna + ancho > columnas` (casos exactamente en
      el borde deben pasar; un exceso de 1 debe rechazar).
- [x] Rojo→Verde: regla **solape AABB** — dos botones adyacentes (bordes que
      tocan sin intersección de área) deben ser válidos; dos botones cuyos
      rectángulos se intersectan (parcial o uno contenido en otro) deben
      rechazarse; verificar con al menos 3 botones donde solo dos se solapan
      (el resto del layout no debe generar falsos positivos).
- [x] Rojo→Verde: regla **destino único** — botón sin `articulo_id`,
      `familia_id` ni `funcion` (0 destinos) se rechaza; botón con más de uno
      de los tres no nulos (p. ej. `articulo_id` y `funcion` a la vez) se
      rechaza; exactamente uno de los tres es válido.
- [x] Rojo→Verde: regla **función válida** — `funcion` fuera del conjunto
      `FUNCIONES` soportado se rechaza; cada valor de `FUNCIONES` es aceptado.
- [x] Rojo→Verde: layout con varios errores simultáneos devuelve TODOS los
      errores encontrados (no corta en el primero), cada uno identificable por
      `ref` del botón.
- [x] Verde: `validar_layout_botonera` NO valida existencia de artículo/familia
      en BD (eso es responsabilidad de `ServicioBotonera`, Tarea 3) — test que
      lo confirma explícitamente (un `articulo_id` inexistente pasa esta
      función pura sin error).

### Tarea 2 — `RepositorioBotonera` (puerto + SQL) y cableado en la UoW

Capa: `app/dominio/puertos.py` (modificar), `app/infraestructura/persistencia/
repositorios.py` (modificar), `app/infraestructura/persistencia/
unidad_de_trabajo.py` (modificar, `self.botoneras = RepositorioBotoneraSQL
(session)` siguiendo el patrón de `self.familias`). Reutiliza los modelos
existentes en `app/infraestructura/persistencia/modelos/botonera.py` (sin
migración). **Paralelizable con la Tarea 1.**

- [x] Rojo: crear `tests/test_botonera_repositorio.py` (UoW sobre SQLite
      in-memory, mismo patrón que `tests/test_repositorios.py`) con casos que
      fallan porque el repositorio aún no existe.
- [x] Rojo→Verde: `Protocol RepositorioBotonera` en `puertos.py` con
      `arbol()`, `buscar_perfil(id)`, `agregar_perfil(perfil)`, `perfiles()`,
      `buscar_pagina(id)`, `agregar_pagina(pagina)`,
      `reemplazar_botones(pagina, botones)`; atributo `botoneras:
      RepositorioBotonera` en `UnidadDeTrabajo`.
- [x] Rojo→Verde: `RepositorioBotoneraSQL.arbol()` devuelve perfiles con sus
      páginas y botones (eager/relationship ya definida en el modelo).
- [x] Rojo→Verde: `reemplazar_botones` — `pagina.botones.clear(); flush();
      extend(nuevos)` apoyado en `cascade="all, delete-orphan"`; test que
      guarda un layout y verifica que los botones previos ya no existen en BD
      (no solo desasociados).
- [x] Rojo→Verde: borrar perfil (`session.delete`) elimina en cascada sus
      páginas y botones — test de conteo de filas en BD antes/después.
- [x] Rojo→Verde: borrar página elimina en cascada sus botones — mismo tipo de
      test.
- [x] Rojo→Verde: `perfiles()` devuelve todos los perfiles (usado por
      `activar_perfil` para desactivar los demás en la misma transacción).

### Tarea 3 — Casos de uso `ServicioBotonera` (aplicación)

Capa: `app/aplicacion/botoneras.py` (nuevo), mismo patrón que
`ServicioFamilias` (constructor `(uow, *, usuario_id=None, origen="local")`,
cada método valida → muta → audita → `commit`). **Depende de las Tareas 1 y
2.** Secuencial respecto a ellas.

- [x] Rojo: crear `tests/test_botonera_casos_uso.py` con casos que fallan
      porque `ServicioBotonera` y sus excepciones aún no existen.
- [x] Rojo→Verde: excepciones `LayoutInvalido` (expone `.errores: list[str]`),
      `PerfilNoEncontrado`, `PaginaNoEncontrada`, `DestinoNoExiste`.
- [x] Rojo→Verde: `crear_perfil(nombre) -> int` — se crea con `activo=False`;
      auditado.
- [x] Rojo→Verde: `renombrar_perfil(perfil_id, nombre)` — `PerfilNoEncontrado`
      si no existe; auditado.
- [x] Rojo→Verde: `activar_perfil(perfil_id)` — el perfil activado queda
      `activo=True` y CUALQUIER otro perfil que estuviera activo queda
      `activo=False`, todo en la misma transacción; auditado; test con 2+
      perfiles activos previos (estado inconsistente hipotético) para
      confirmar que todos quedan desactivados salvo el objetivo.
- [x] Rojo→Verde: `borrar_perfil(perfil_id)` — cascade de páginas/botones
      (delegado al repositorio de la Tarea 2); auditado; test explícito de que
      borrar el ÚLTIMO perfil (incluso si está activo) se permite sin error
      especial (el TPV degrada a 404 en su propio endpoint; ese
      comportamiento NO se valida aquí).
- [x] Rojo→Verde: `crear_pagina(perfil_id, datos)` — `PerfilNoEncontrado` si el
      perfil no existe; `filas` y `columnas` deben estar en el rango permitido
      **1–12** (rechazo fuera de rango); auditado.
- [x] Rojo→Verde: `actualizar_pagina(pagina_id, datos)` — nombre/orden/
      columnas/filas; `PaginaNoEncontrada` si no existe; mismo rango 1–12 para
      filas/columnas; auditado.
- [x] Rojo→Verde: `borrar_pagina(pagina_id)` — cascade de botones (Tarea 2);
      `PaginaNoEncontrada` si no existe; auditado.
- [x] Rojo→Verde: `guardar_layout(pagina_id, datos)` paso 1 — invoca
      `validar_layout_botonera` (función pura, Tarea 1); si devuelve errores,
      lanza `LayoutInvalido(errores)` SIN tocar BD.
- [x] Rojo→Verde: `guardar_layout` paso 2 — por cada botón con
      `articulo_id`/`familia_id`, verifica existencia contra BD; si no existe,
      `DestinoNoExiste` SIN tocar BD (ni siquiera parcialmente).
- [x] Rojo→Verde: `guardar_layout` paso 3 — actualiza `filas/columnas` de la
      página y reemplaza los botones (Tarea 2) de forma atómica; auditado;
      `commit`.
- [x] Rojo→Verde: test de integración — **layout inválido (bounds, solape,
      destino, función o referencia inexistente) → NADA persiste**: se
      compara el estado de BD (página + botones) antes y después de la
      llamada fallida y debe ser IDÉNTICO (mismo test también con excepción
      forzada a mitad de transacción para confirmar rollback real, no solo
      validación previa).
- [x] Rojo→Verde: test de integración — layout válido reemplaza el anterior
      tal cual se envió (los botones previos ya no existen; los nuevos sí,
      con sus valores exactos).
- [x] Rojo→Verde: `cargar_arbol()` — devuelve la estructura perfil→página→
      botón lista para el editor (usa `RepositorioBotonera.arbol()`).
- [x] Verde: cada método que muta (crear/editar/borrar/activar/guardar_layout)
      tiene su test de auditoría — existe un nuevo `LogAuditoria` con acción y
      entidad afectada tras la operación (invariante 4).

### Tarea 4 — Endpoints `/admin/api/botonera/*` (presentación)

Capa: `app/presentacion/admin.py` (modificar) — `require_admin`, `get_uow`,
Pydantic, mapeo de excepciones a HTTP, `_origen` para auditoría, siguiendo el
patrón de los demás routers admin. **Depende de la Tarea 3.**

- [x] Rojo: crear `tests/test_botonera_admin_api.py` (TestClient, mismo
      patrón que `tests/test_admin_api.py`) con casos que fallan porque los
      endpoints aún no existen.
- [x] Rojo→Verde: `GET /admin/api/botonera` — árbol completo; `require_admin`
      (401 sin sesión válida, verificado con test explícito).
- [x] Rojo→Verde: `POST /admin/api/botonera/perfiles` — crear perfil (201/200
      con id); auditado.
- [x] Rojo→Verde: `PUT /admin/api/botonera/perfiles/{id}` — renombrar; 404 si
      `PerfilNoEncontrado`.
- [x] Rojo→Verde: `POST /admin/api/botonera/perfiles/{id}/activar` — activa y
      desactiva los demás; 404 si no existe.
- [x] Rojo→Verde: `DELETE /admin/api/botonera/perfiles/{id}` — borra con
      cascade; 404 si no existe.
- [x] Rojo→Verde: `POST /admin/api/botonera/perfiles/{id}/paginas` — crear
      página; 404 si el perfil no existe; 422 si filas/columnas fuera de
      rango 1–12.
- [x] Rojo→Verde: `PUT /admin/api/botonera/paginas/{id}` — actualizar
      nombre/orden/filas/columnas; 404 si no existe.
- [x] Rojo→Verde: `DELETE /admin/api/botonera/paginas/{id}` — borra con
      cascade; 404 si no existe.
- [x] Rojo→Verde: `PUT /admin/api/botonera/paginas/{id}/layout` — guarda
      layout completo; 404 si `PaginaNoEncontrada`; **422 con
      `{"detail": errores}`** si `LayoutInvalido`; 422 si `DestinoNoExiste`.
- [x] Verde: test explícito — todos los endpoints anteriores devuelven 401
      sin sesión de administrador (require_admin no se puede bypassear).
- [x] Verde: cada endpoint mutante deja rastro de auditoría con el `_origen`
      correcto (local/remoto, según patrón existente).

### Tarea 5 — Test de compatibilidad `GET /tpv/api/botonera`

Añadir caso a `tests/test_tpv_api.py` (fichero existente, junto a
`test_botonera_incluye_articulo`). **Depende de la Tarea 3** (y opcionalmente
de la 4; se puede ejercitar editando vía `ServicioBotonera` directamente,
sin pasar por HTTP, si eso adelanta la tarea).

- [x] Rojo: nuevo test que edita un layout del perfil activo vía
      `ServicioBotonera.guardar_layout` (o vía el endpoint de la Tarea 4) y
      luego consulta `GET /tpv/api/botonera`; falla porque aún no hay forma
      de editar.
- [x] Verde: la respuesta de `GET /tpv/api/botonera` conserva EXACTAMENTE la
      misma forma (mismos campos: perfil activo, página de menor orden,
      botones con tipo y destino) y refleja el layout recién guardado.
- [x] Verde: test de regresión explícito — comparar el shape (claves) de la
      respuesta contra un snapshot/estructura esperada fija, para detectar
      cualquier cambio de forma introducido por accidente en tareas
      anteriores.

### Tarea 6 — Checkpoint Tanda 1

- [ ] Suite completa en verde: `make test` sin fallos ni tests saltados.
- [ ] `make arch` (o `pytest tests/test_arquitectura.py`) en verde — el nuevo
      código respeta las fronteras hexagonales (dominio sin imports de
      infraestructura/presentación, etc.).
- [ ] Revisar que ningún test de la Tanda 1 depende de estado dejado por otro
      test (aislamiento, orden-independiente).
- [ ] Confirmar que este punto es COMMITTEABLE por sí solo: la API admin de
      botoneras es completa, validada, auditada, y `GET /tpv/api/botonera`
      sigue funcionando sin cambios de forma. El frontend aún no tiene UI para
      esta API (se añade en la Tanda 2).

---

## Tanda 2 — Frontend (verificación manual, SIN tests automáticos)

El proyecto no tiene infraestructura de test JS. Esta tanda se valida
ÚNICAMENTE con el checklist manual de la Tarea 7. El backend (Tanda 1) es la
autoridad: un bug del editor no puede persistir un layout inválido, así que
el riesgo de esta tanda es de usabilidad, no de integridad de datos.

### Tarea 7 — Editor drag & drop en `app/ui/admin.html`

**Depende por completo de la Tanda 1** (consume `/admin/api/botonera/*`).
Secuencial, un solo desarrollador (no paraleliza con nada de esta tanda).

- [x] Nueva pestaña `data-t="botoneras"`: botón en `dashboard()` y rama en
      `pintarPestana()`, siguiendo el patrón de las demás pestañas de
      `admin.html`.
- [x] Carga inicial: `GET /admin/api/botonera` pinta selector de perfil,
      selector de página, y la rejilla `filas × columnas` con
      `display:grid`.
- [x] Render de rejilla: cada celda es un `dropzone`; cada botón existente se
      posiciona con `grid-row`/`grid-column` (`span alto/ancho`).
- [x] Arrastrar/soltar: `dragstart` guarda el id del botón arrastrado;
      `drop` sobre una celda actualiza fila/columna EN MEMORIA (no persiste
      hasta pulsar "Guardar").
- [x] Redimensionar: tiradores en el botón que ajustan `ancho`/`alto` en
      memoria (arrastre desde una esquina/borde).
- [x] Paleta de destinos: lista lateral con artículos, familias y las
      `FUNCIONES` soportadas; arrastrar un ítem de la paleta a la rejilla
      crea un botón nuevo con ese destino.
- [x] Panel de edición: color, icono y texto del botón actualmente
      seleccionado.
- [x] Gestión de perfiles: crear, renombrar, activar y borrar perfil desde
      la UI (llama a los endpoints de perfiles).
- [x] Gestión de páginas: crear, editar (nombre/orden/filas/columnas) y
      borrar página desde la UI.
- [x] Botón "Guardar": envía `PUT .../paginas/{id}/layout` con el layout
      completo en memoria (`{filas, columnas, botones: [...]}`).
- [x] Manejo de error 422: si el backend rechaza el layout, se muestran los
      `errores` devueltos, resaltando el botón afectado por su `ref`
      (ningún estado se pierde en memoria; el usuario puede corregir y
      reintentar).
- [ ] **Checklist de verificación manual** (a ejecutar por una persona, sin
      test automático; dejar constancia de que se ejecutó antes de dar la
      tarea por cerrada). **PENDIENTE DE EJECUCIÓN HUMANA**: el código
      implementado por el agente NO fue ejercitado en un navegador real
      (el agente no tiene esa capacidad); estos pasos deben ejecutarse
      manualmente antes de cerrar la tanda:
  - [ ] Crear un perfil nuevo, agregarle una página, colocar 3+ botones de
        distinto destino (artículo, familia, función) y guardar con éxito.
  - [ ] Arrastrar un botón fuera de los límites de la rejilla y guardar:
        el backend rechaza (422) y la UI muestra el error sin perder el
        estado en memoria.
  - [ ] Solapar dos botones y guardar: mismo comportamiento de rechazo con
        error legible.
  - [ ] Redimensionar un botón hasta hacerlo salir de la rejilla: guardar
        rechaza correctamente.
  - [ ] Crear dos perfiles, activar el segundo, confirmar en la propia UI
        (recargando el árbol) que el primero quedó inactivo.
  - [ ] Borrar una página con botones: confirmar que desaparecen sin dejar
        residuos visuales tras recargar.
  - [ ] Borrar el ÚLTIMO perfil (el activo): confirmar que la UI no rompe y
        que el TPV, al recargar, degrada según su comportamiento existente
        (404 ya manejado, fuera de esta tanda).
  - [ ] Verificar visualmente en el TPV (`/tpv`) que el layout recién
        guardado se refleja tal cual tras recargar la pantalla táctil.

### Tarea 8 — Checkpoint final

- [x] `make test` completo en verde — confirmar que el trabajo de frontend
      (solo HTML/JS) no rompió ningún test de backend. **348 passed, 0
      failed** (`.venv/Scripts/python -m pytest -q`).
- [x] `make arch` en verde. **3 contratos KEPT, 0 broken**
      (`.venv/Scripts/lint-imports.exe`).
- [ ] Checklist manual de la Tarea 7 ejecutado y sin pendientes abiertos.
      **PENDIENTE**: requiere ejecución humana en navegador (ver Tarea 7).
- [ ] Confirmar que `GET /tpv/api/botonera` sigue sin cambios de forma tras
      el uso real del editor (no solo en test, también inspección manual de
      la respuesta JSON). El test automático de contrato
      (`tests/test_tpv_api.py::test_botonera_refleja_layout_editado_por_el_editor`,
      Tanda 1) sigue en verde y ya cubre esto vía `ServicioBotonera`; la
      inspección manual del JSON tras uso real del editor en navegador
      **queda pendiente** junto con el checklist de la Tarea 7.

---

## Notas de ejecución

- **Paralelismo**: Tareas 1 y 2 pueden ejecutarse en paralelo (dominio puro
  vs. persistencia, sin dependencia de código entre sí). Tareas 3 → 4 → 5 son
  estrictamente secuenciales (cada una depende de que la anterior esté
  verde). Tarea 6 es el checkpoint de cierre de la Tanda 1. Tarea 7 depende
  de que la Tanda 1 completa esté cerrada (necesita la API real, no mocks).
- **TDD estricto**: ninguna línea de implementación en `app/dominio`,
  `app/aplicacion`, `app/infraestructura` o `app/presentacion` para esta
  feature se escribe sin un test que falle primero. El frontend (Tanda 2)
  queda explícitamente fuera de esta disciplina por ausencia de
  infraestructura de test JS (decisión ya cerrada en proposal/design).
- **Sin migración**: los modelos `perfil_botonera`, `pagina_botonera`,
  `boton` ya existen (`migrations/versions/0001_inicial.py`); ninguna tarea
  de esta lista debe tocar Alembic.
- **Contrato TPV intacto**: si cualquier tarea de la Tanda 1 requiere tocar
  `app/presentacion/tpv.py` o el modelo leído por `GET /tpv/api/botonera`,
  eso es señal de alerta — el diseño no lo contempla y debe revisarse antes
  de continuar.
