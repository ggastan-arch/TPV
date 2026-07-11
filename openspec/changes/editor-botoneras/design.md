# Design: Editor visual de botoneras (consola admin)

## Technical Approach

Cambio ADITIVO en tres capas siguiendo la arquitectura hexagonal ya presente:

- **Dominio (pura, sin BD)**: una función `validar_layout_botonera` en
  `app/dominio/servicios/botonera.py`. Es el corazón de la red de seguridad: recibe
  las dimensiones de la rejilla y la lista de botones (rectángulos + destino) y
  devuelve la lista de errores estructurales. Testeable en aislamiento total, igual
  que `redondeo.py` o `validadores.py`.
- **Aplicación**: `ServicioBotonera` en `app/aplicacion/botoneras.py`, con el mismo
  patrón que `ServicioFamilias` (constructor `(uow, *, usuario_id, origen)`, cada
  método valida → muta → audita → `commit`). Invoca la función pura Y valida contra
  BD (que artículo/familia referenciados existan). Lanza excepciones de dominio
  tipadas que la capa HTTP mapea.
- **Infraestructura**: `RepositorioBotoneraSQL` + puerto `RepositorioBotonera`
  (Protocol) cableado en la UoW como `uow.botoneras`. Lee el árbol completo para el
  editor y ejecuta el reemplazo atómico de botones.
- **Presentación**: endpoints `/admin/api/botonera/*` en `admin.py` (`require_admin`,
  `_origen`, Pydantic, mapeo excepción→HTTP) y una pestaña "Botoneras" en `admin.html`
  con el editor drag & drop vanilla JS.

El contrato `GET /tpv/api/botonera` NO se toca: el editor produce exactamente las
filas que ese endpoint ya lee (mismos modelos).

## Architecture Decisions

| Decisión | Alternativa rechazada | Motivo |
|----------|----------------------|--------|
| Validación de rejilla como función PURA en dominio | Validar dentro del servicio/endpoint con acceso a BD | Aislar la lógica geométrica (bounds/solape/destino/función) la hace testeable sin fixtures ni sesión; la red de seguridad se cubre con unit tests rápidos y deterministas |
| Guardado por LOTE del layout de una página (PUT completo) | Operaciones por botón (POST/PUT/DELETE por celda) | Un solo punto de validación y una sola transacción atómica; el editor JS ya tiene el estado completo en memoria; evita estados intermedios inválidos persistidos |
| Reemplazo atómico (clear + insert vía `delete-orphan`) | `UPDATE` diferencial por botón | Los botones NO son dato fiscal (tabla mutable, sin triggers de inmutabilidad); borrar+insertar es simple y correcto; si algo falla → rollback → nada cambia |
| Un solo perfil activo (activar uno desactiva los demás en la misma transacción) | Varios activos + heurística en el TPV | El TPV resuelve `activo == True` y toma el primero; múltiples activos lo harían ambiguo. Perfiles nuevos se crean `activo=False` |
| Refs a artículo/familia validadas en el SERVICIO (no en la función pura) | Meterlas en la función pura | La existencia depende de BD; la función pura debe permanecer sin I/O. Separación limpia dominio/aplicación |
| `ServicioBotonera` (una clase con métodos) | Casos de uso finos (una clase por acción) | Consistencia con `ServicioFamilias`/`ServicioArticulos`/`ServicioClientes` ya existentes |

## Data Flow

    Editor (admin.html)                 Backend
    ───────────────────                 ───────
    GET /admin/api/botonera  ─────────▶  árbol perfil→páginas→botones
    (edita en memoria: drag&drop,
     resize, paleta, color/texto)
    PUT .../paginas/{id}/layout ──────▶  ServicioBotonera.guardar_layout
                                          │ 1. validar_layout_botonera (PURA)
                                          │ 2. validar refs en BD (art/familia)
                                          │ 3. reemplazo atómico botones + dims
                                          │ 4. auditar (invariante 4)
                                          │ 5. commit  (falla → rollback)
                                          ▼
                                         perfil_botonera / pagina_botonera / boton
                                          ▲
    TPV  GET /tpv/api/botonera  ─────────┘  (contrato SIN cambios)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/dominio/servicios/botonera.py` | Create | Función pura `validar_layout_botonera` + dataclass `BotonSpec` |
| `app/aplicacion/botoneras.py` | Create | `ServicioBotonera` + DTOs + excepciones |
| `app/dominio/puertos.py` | Modify | Añadir Protocol `RepositorioBotonera` y atributo `botoneras` en `UnidadDeTrabajo` |
| `app/infraestructura/persistencia/repositorios.py` | Modify | `RepositorioBotoneraSQL` |
| `app/infraestructura/persistencia/unidad_de_trabajo.py` | Modify | Cablear `self.botoneras` |
| `app/presentacion/admin.py` | Modify | Endpoints `/admin/api/botonera/*` (auditados, `require_admin`) |
| `app/ui/admin.html` | Modify | Pestaña "Botoneras" con editor drag & drop |
| `tests/` | Create | Unit de la función pura + servicio/repo + contrato TPV |

Sin migración: las tablas `perfil_botonera`, `pagina_botonera`, `boton` (con
`ck_boton_destino_unico`) ya existen en `migrations/versions/0001_inicial.py` y son
mutables (config, no dato fiscal).

## Interfaces / Contracts

### Función pura de dominio

```python
# app/dominio/servicios/botonera.py
@dataclass(frozen=True)
class BotonSpec:
    ref: str                      # id de cliente/JS para localizar el error
    fila: int
    columna: int
    ancho: int
    alto: int
    articulo_id: int | None = None
    familia_id: int | None = None
    funcion: str | None = None

def validar_layout_botonera(
    filas: int, columnas: int, botones: list[BotonSpec]
) -> list[str]:
    """Devuelve la lista de errores (vacía == layout válido). PURA, sin I/O.
    Detecta:
      - fuera de límites: fila/columna < 0, ancho/alto < 1,
        fila+alto > filas, columna+ancho > columnas
      - solape AABB entre dos botones (rectángulos [columna,columna+ancho) ×
        [fila,fila+alto) que se intersectan)
      - destino no único: nº de {articulo_id, familia_id, funcion} no nulos != 1
      - función inválida: funcion not in FUNCIONES
    NO valida existencia de artículo/familia (eso depende de BD → servicio).
    """
```

### Puerto de repositorio

```python
class RepositorioBotonera(Protocol):
    def arbol(self) -> list["PerfilBotonera"]: ...          # perfiles→páginas→botones
    def buscar_perfil(self, perfil_id: int) -> "PerfilBotonera | None": ...
    def agregar_perfil(self, perfil: "PerfilBotonera") -> None: ...
    def perfiles(self) -> list["PerfilBotonera"]: ...        # para "activar uno desactiva otros"
    def buscar_pagina(self, pagina_id: int) -> "PaginaBotonera | None": ...
    def agregar_pagina(self, pagina: "PaginaBotonera") -> None: ...
    def reemplazar_botones(self, pagina: "PaginaBotonera", botones: list["Boton"]) -> None: ...
```

`reemplazar_botones` hace `pagina.botones.clear(); flush(); extend(nuevos)` apoyándose
en `cascade="all, delete-orphan"`. Borrado de perfil/página vía `session.delete` (cascade).

### Servicio de aplicación

```python
# app/aplicacion/botoneras.py
class LayoutInvalido(Exception):            # expone .errores: list[str]
class PerfilNoEncontrado(Exception): ...
class PaginaNoEncontrada(Exception): ...
class DestinoNoExiste(Exception): ...       # artículo o familia referenciada inexistente

class ServicioBotonera:
    def __init__(self, uow, *, usuario_id=None, origen="local"): ...
    def cargar_arbol(self) -> list[dict]: ...
    def crear_perfil(self, nombre: str) -> int: ...                 # activo=False
    def renombrar_perfil(self, perfil_id: int, nombre: str) -> None: ...
    def activar_perfil(self, perfil_id: int) -> None: ...           # desactiva los demás (misma tx)
    def borrar_perfil(self, perfil_id: int) -> None: ...
    def crear_pagina(self, perfil_id: int, datos: DatosPagina) -> int: ...
    def actualizar_pagina(self, pagina_id: int, datos: DatosPagina) -> None: ...
    def borrar_pagina(self, pagina_id: int) -> None: ...
    def guardar_layout(self, pagina_id: int, datos: LayoutPagina) -> None: ...
```

`guardar_layout`: (1) `validar_layout_botonera(...)` → si hay errores, `LayoutInvalido`;
(2) por cada botón con destino artículo/familia, comprobar existencia → `DestinoNoExiste`;
(3) actualizar `filas/columnas` de la página y reemplazar botones; (4) auditar; (5) commit.
Cualquier fallo antes del commit deja la transacción sin efecto (rollback).

### Endpoints (todos `require_admin`, todos auditados)

| Método | Ruta | Acción |
|--------|------|--------|
| GET | `/admin/api/botonera` | Árbol completo para el editor |
| POST | `/admin/api/botonera/perfiles` | Crear perfil |
| PUT | `/admin/api/botonera/perfiles/{id}` | Renombrar |
| POST | `/admin/api/botonera/perfiles/{id}/activar` | Activar (desactiva los demás) |
| DELETE | `/admin/api/botonera/perfiles/{id}` | Borrar perfil (cascade) |
| POST | `/admin/api/botonera/perfiles/{id}/paginas` | Crear página |
| PUT | `/admin/api/botonera/paginas/{id}` | Nombre/orden/filas/columnas |
| DELETE | `/admin/api/botonera/paginas/{id}` | Borrar página |
| PUT | `/admin/api/botonera/paginas/{id}/layout` | Guardar layout completo (atómico) |

Mapeo de excepciones: `PerfilNoEncontrado`/`PaginaNoEncontrada` → 404;
`LayoutInvalido` → 422 con `{"detail": errores}`; `DestinoNoExiste` → 422.

## Frontend drag & drop (verificación MANUAL, sin tests)

No hay infraestructura de test JS: el editor se verifica A MANO. Sigue el patrón de
`admin.html` (helper `api()`, render por `innerHTML`, sin framework). Nueva pestaña
`data-t="botoneras"` que añade su botón en `dashboard()` y su rama en `pintarPestana()`.

- **Carga**: `GET /admin/api/botonera` pinta selector de perfil y de página, y la
  rejilla `filas × columnas` con CSS `display:grid`.
- **Rejilla**: cada celda es un `dropzone`; cada botón un `div` `draggable=true`
  posicionado con `grid-row`/`grid-column` (`span alto/ancho`).
- **Arrastrar/soltar**: `dragstart` guarda el id del botón; `drop` en una celda
  actualiza fila/columna EN MEMORIA (no persiste hasta "Guardar").
- **Redimensionar**: tiradores en el botón que ajustan `ancho`/`alto` en memoria.
- **Paleta de destinos**: lista lateral de artículos, familias y funciones
  (`FUNCIONES`); arrastrar desde la paleta crea un botón nuevo con ese destino.
- **Edición**: panel para `color`/`icono`/`texto` del botón seleccionado.
- **Gestión**: crear/renombrar/activar/borrar perfil; crear/editar/borrar página.
- **Guardar**: envía `PUT .../paginas/{id}/layout` con `{filas, columnas, botones:[...]}`
  completo. Si el backend responde 422, muestra los `errores` (resaltando por `ref`).

El backend es la autoridad: un editor con bugs NO puede persistir un layout inválido.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (dominio) | `validar_layout_botonera`: bounds (negativos, exceso, ancho/alto<1), solape AABB (adyacente OK vs. solapado KO), destino no único (0 y >1), función inválida | pytest puro, sin BD; TDD estricto |
| Unit (aplicación) | CRUD perfiles/páginas; `activar_perfil` desactiva los demás; `DestinoNoExiste` con artículo/familia inexistente | UoW sobre SQLite in-memory |
| Integración | `guardar_layout` con layout inválido → NADA persiste (atómico, rollback); layout válido → botones reemplazados; auditoría registrada (invariante 4) | fixtures de perfil/página |
| Contrato | `GET /tpv/api/botonera` sigue devolviendo la misma forma tras editar por el editor | test que edita vía servicio y lee vía endpoint TPV |

TDD estricto en TODO el backend. El frontend se excluye de tests automáticos.

## Migration / Rollout

No migration required — las tablas ya existen (`0001_inicial.py`). Cambio aditivo:
revertir = quitar endpoints, servicio, repositorio y la pestaña del editor; modelos y
contrato del TPV quedan intactos. La configuración por seed/SQL sigue funcionando.

## Open Questions

- [ ] ¿Debe el editor impedir borrar el ÚLTIMO perfil activo (para no dejar el TPV en
      404), o basta con avisar? Propuesta: avisar y permitir; el TPV ya maneja el 404.
- [ ] Límite superior de `filas`/`columnas` para la rejilla (evitar layouts absurdos).
      Propuesta: validar rango razonable (p. ej. 1–12) dentro de la función pura.
