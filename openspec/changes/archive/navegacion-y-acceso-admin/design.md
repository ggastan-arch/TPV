# Design: Navegación TPV↔Administración y demo sin fricción

## Technical Approach

Cambio ADITIVO y *profile-gated*, cableado en el composition-root (`crear_app` en
`app/main.py`), sobre la costura existente `settings.perfil`. Dos dimensiones nuevas
cuelgan del perfil, JAMÁS con un `if demo` en el hot path:

1. **Acceso libre (AUTH)**: en `perfil=="demo"`, `crear_app` registra
   `app.dependency_overrides[require_admin] = require_admin_demo`. Las ~40 rutas que
   declaran `Depends(require_admin)` se voltean de una vez; producción NUNCA registra el
   override y su login por sesión queda BYTE A BYTE idéntico.
2. **Reset de arranque**: en `perfil=="demo"`, tras la salvaguarda existente, `crear_app`
   recrea la BD demo desde cero (esquema real Alembic + `sembrar_demo`). Producción no
   resetea nunca (invariante 1).

Refuerza invariante 1 (ningún reset en el SIF real: vive aislado en demo), invariante 5
(no "modo formación") y deja intacto el camino fiscal (huella/registro/numeración/cadena).

## Architecture Decisions

| Decisión | Alternativa rechazada | Motivo |
|----------|-----------------------|--------|
| `dependency_overrides[require_admin]=require_admin_demo` en `crear_app` cuando demo | `if settings.perfil=="demo"` dentro de `require_admin` | El guard corre en cada request; ramificar por perfil ahí es hot-path. El override voltea las ~40 rutas a la vez y producción no carga el código |
| `require_admin_demo(s=Depends(get_session))` devuelve el id del primer admin sembrado | Devolver un id sentinela constante | `/api/me` hace `s.get(Usuario, id)`; un id real resuelve nombre/rol como en producción sin `None` |
| Migrar `/api/me` a `Depends(require_admin)` | Dejar la llamada directa `require_admin(request)` (línea 258) | `dependency_overrides` solo afecta a `Depends(...)`; la llamada directa ignoraría el override y seguiría dando 401 en demo |
| Reset = borrar `tpv_demo.db*` + Alembic `upgrade head` + `sembrar_demo` | `drop_all`/`create_all`; `TRUNCATE`/`DELETE` | `create_all` no crea los triggers de inmutabilidad (drift vs producción); `DELETE` sobre ventas emitidas lo RECHAZAN esos triggers. Fichero fresco + migración real = esquema idéntico a producción y sin depender de `downgrade` completos |
| `_resetear_demo(s)` construye engine local desde `s.database_url` (no el singleton) | Reutilizar `SessionLocal` global | El singleton se liga al importar; un engine local hace la función autocontenida y testeable contra un `tpv_demo.db` en `tmp_path` sin tocar globals ni `tpv.db` |
| Orden en `crear_app`: salvaguarda → reset → seed → montar rutas | Reset antes de la salvaguarda | La salvaguarda garantiza que jamás se borre `tpv.db`; debe correr ANTES de cualquier borrado |
| Botones de navegación como HTML estático en ambas cabeceras | Inyectarlos por JS/perfil | Navegar TPV↔admin es válido en los dos perfiles; en producción `/admin/` muestra login. Mínimo, sin framework |

## Data Flow

```
crear_app()
  ├─ _verificar_aislamiento_demo(settings)        [salvaguarda modo-demo: aborta si demo→tpv.db]
  ├─ if perfil=="demo":
  │     _resetear_demo(settings)                   [borra tpv_demo.db*, Alembic upgrade head, sembrar_demo]
  │     app.dependency_overrides[require_admin] = require_admin_demo
  └─ include_router(...) / mounts

REQUEST /admin/api/*  (demo)
  Depends(require_admin) ──► require_admin_demo(get_session) ──► id primer admin  [sin sesión]
REQUEST /admin/api/*  (produccion)
  Depends(require_admin) ──► sesión["usuario_id"] o 401                           [intacto]
```

## File Changes

| File | Action | Integración exacta |
|------|--------|--------------------|
| `app/presentacion/admin.py` | Modify | Añadir `require_admin_demo(s=Depends(get_session))->int` (primer `Usuario` rol `administracion`); migrar `/api/me` a `usuario_id: int = Depends(require_admin)` |
| `app/main.py` | Modify | En `crear_app`, tras salvaguarda: si demo, `_resetear_demo(settings)` y `app.dependency_overrides[require_admin]=require_admin_demo`. Nuevo helper `_resetear_demo(s: Settings)` (engine local desde `s.database_url`, borra ficheros, Alembic `upgrade head`, `sembrar_demo(factory)`, valida `!= DB_PATH_PRODUCCION`) |
| `app/seed.py` | Modify | `sembrar_demo(session_factory: sessionmaker = SessionLocal)`: parámetro opcional para inyectar factory en tests y en `_resetear_demo` |
| `app/ui/tpv.html` | Modify | Cabecera junto a `#usuario`: `<a href="/admin/">Administración</a>` |
| `app/ui/admin.html` | Modify | `dashboard()`: añadir `<a href="/tpv/">Ir al TPV</a>`; render de "Salir" condicionado a `!window.esDemo` y guardar el `.onclick` con null-check |
| `tests/` | New | Ver Testing Strategy |

## Interfaces / Contracts

```python
# admin.py
def require_admin_demo(s: Session = Depends(get_session)) -> int: ...  # id primer admin
# me(): usuario_id: int = Depends(require_admin), s: Session = Depends(get_session)

# main.py
def _resetear_demo(s: Settings) -> None: ...  # RuntimeError si s.db_path resuelve a produccion

# seed.py
def sembrar_demo(session_factory: sessionmaker = SessionLocal) -> None: ...
```

## Testing Strategy (TDD — test primero)

| Layer | Qué testear | Enfoque |
|-------|-------------|---------|
| Integración auth | demo ⇒ `/admin/api/me` y una ruta protegida devuelven 200 SIN sesión | `crear_app` con `Settings(TPV_PROFILE="demo")` (db en `tmp_path`); override `get_session`/`get_uow` al engine demo sembrado; `TestClient` |
| Integración auth (no-regresión) | produccion ⇒ `/admin/api/me` da 401 sin sesión (override NO registrado) | `crear_app()` default + override DB con admin |
| Unit reset | `_resetear_demo(s)` deja estado sembrado limpio; datos previos descartados | `s` demo→`tmp_path/tpv_demo.db`; escribir basura; ejecutar; contar filas sembradas |
| Unit reset (guardarraíl) | `_resetear_demo` con `db_path==tpv.db` ⇒ `RuntimeError`; produccion no llama a reset | `pytest.raises`; espiar `_resetear_demo` y `crear_app()` produccion ⇒ no invocado |
| Integración UI | `/tpv/` contiene enlace a `/admin/`; `/admin/` contiene "Ir al TPV" | `TestClient`, `assert` substring en el HTML servido |

## Migration / Rollout

Sin migración de esquema ni datos productivos. `tpv_demo.db*` es desechable (ya gitignorado
por `modo-demo`). Rollback = quitar override, `_resetear_demo` y los enlaces; producción es
el default e intacto.

## Open Questions

- [ ] Si el catálogo real (`img_demo`/`datos_demo`) crece, el reset por arranque encarece el
      boot demo; aceptable para el TFM (proceso desechable, no concurrente).
