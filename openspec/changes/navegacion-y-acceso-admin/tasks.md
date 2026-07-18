# Tasks: Navegación TPV↔Administración y demo sin fricción

> STRICT TDD. Cada bloque de implementación se ordena RED (test que falla) → GREEN
> (implementación mínima) → REFACTOR si aplica. Ninguna tarea arranca marcada;
> `sdd-apply` las marca `[x]` al completarlas.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~480-620 (additions+deletions) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (nav) → PR 2 (reset demo) → PR 3 (acceso libre + Salir) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (a decidir con el usuario) |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Navegación TPV↔Admin (botones, Fase 4) | PR 1 | Independiente; base = tracker/main; ~100-130 líneas |
| 2 | Reset de arranque demo (Fase 2: `_resetear_demo`, seed, `crear_app`) | PR 2 | Base = PR 1; toca `app/main.py`/`app/seed.py`/`tests/test_seed.py`; el bloque más grande y de mayor riesgo operativo (Alembic + engine local + borrado de ficheros) |
| 3 | Acceso libre demo + ajuste "Salir" (Fases 1, 3, 5) | PR 3 | Base = PR 2; reutiliza `crear_app` ya tocado por PR 2 y el header de `admin.html` ya tocado por PR 1 |

El orden de implementación por Fases (1→6, abajo) sigue dependencias TDD dentro de
una sola rama; si se encadenan PRs, la agrupación por Unit de trabajo prevalece
sobre el número de Fase.

**Riesgo detectado (gotcha de Python, no opcional)**: `sembrar_demo(session_factory:
sessionmaker = SessionLocal)` fija el valor por defecto en tiempo de IMPORTACIÓN del
módulo. El `monkeypatch.setattr(seed_module, "SessionLocal", Sesion)` que usan las
10 llamadas existentes en `tests/test_seed.py` deja de alcanzar ese default una vez
se declara explícito. Sin actualizar esas 10 llamadas a `session_factory=Sesion`,
`make test` fallaría (o, peor, `sembrar_demo()` tocaría el `SessionLocal` real de
`app/infraestructura/db.py`, ligado a `tpv.db`). Fase 2 lo cubre como RED explícito.

## Fase 1: Identidad admin en demo (Requirement: Autenticación con sesión y rol de administración según perfil — dep: ninguna)

- [x] 1.1 RED `tests/test_admin_api.py`: `test_require_admin_demo_devuelve_primer_administrador_activo` — llamada directa a `require_admin_demo(s)` sobre una sesión con `datos_base`/admin sembrado (sin `Request`); assert devuelve el `id` del primer `Usuario` `rol="administracion"` activo
- [x] 1.2 GREEN `app/presentacion/admin.py`: añadir `require_admin_demo(s: Session = Depends(get_session)) -> int`
- [x] 1.3 GREEN/REFACTOR `app/presentacion/admin.py`: migrar `me()` a `usuario_id: int = Depends(require_admin)` (elimina la llamada directa `require_admin(request)` en la línea 258); `tests/test_admin_api.py::test_endpoint_protegido_exige_sesion` y `::test_flujo_completo` deben seguir en verde (no-regresión, sin cambios en esos tests)

## Fase 2: Reset de arranque demo (Requirement: Reset de arranque en modo demo — dep: ninguna, independiente de Fase 1)

- [x] 2.1 RED `tests/test_seed.py`: actualizar las 10 llamadas existentes a `seed_module.sembrar_demo()` (9 funciones; `test_sembrar_demo_dos_veces_no_duplica` llama dos veces) para pasar `session_factory=Sesion` explícito → falla con `TypeError` (el parámetro aún no existe)
- [x] 2.2 GREEN `app/seed.py`: `sembrar_demo(session_factory: sessionmaker = SessionLocal) -> None`; sustituir `with SessionLocal() as s` por `with session_factory() as s`; importar `sessionmaker` de `sqlalchemy.orm`
- [x] 2.3 RED `tests/test_modo_demo.py` (NUEVO): `test_primer_arranque_siembra` — `_resetear_demo(s)` con `s.db_path` en `tmp_path` (perfil demo, fichero inexistente) ⇒ tras ejecutar, un engine local con Alembic `head` contiene el catálogo + clientes sembrados
- [x] 2.4 RED `tests/test_modo_demo.py`: `test_resetear_demo_rechaza_ruta_produccion` — `_resetear_demo(s)` con `s.db_path == DB_PATH_PRODUCCION` ⇒ `RuntimeError` (cobertura adicional exigida por design.md, sin nombre propio en el spec)
- [x] 2.5 RED `tests/test_modo_demo.py`: `test_produccion_sin_cambios` — con perfil producción (datos ya registrados en `tmp_path`), `crear_app()` NO invoca `_resetear_demo` (spy/monkeypatch) y los datos previos persisten
- [x] 2.6 RED `tests/test_navegacion.py` (NUEVO): `test_rearranque_demo_descarta_cambios` — sembrar, insertar una fila extra directamente, ejecutar `_resetear_demo` de nuevo ⇒ el extra desaparece y el conteo vuelve al estado sembrado limpio
- [x] 2.7 RED `tests/test_navegacion.py`: `test_reset_no_ocurre_sin_reiniciar` — dentro de una misma instancia de `crear_app()` (perfil demo), varias peticiones no disparan un segundo reset (spy en `_resetear_demo`, invocado exactamente una vez)
- [x] 2.8 RED `tests/test_navegacion.py`: `test_produccion_no_resetea_en_reinicio` — dos llamadas a `crear_app()` con perfil producción (datos ya presentes en `tmp_path`) conservan los datos sin wipe ni reseed
- [x] 2.9 GREEN `app/main.py`: `_resetear_demo(s: Settings) -> None` — valida `Path(s.db_path).resolve() != Path(DB_PATH_PRODUCCION).resolve()` (si no, `RuntimeError`), borra `tpv_demo.db*`, `alembic.command.upgrade` contra `s.database_url` (Config con `script_location=migrations`, mismo patrón que `tests/conftest.py` y el target `demo` del Makefile — nunca `create_all`/`DELETE`), engine local + `sessionmaker`, `sembrar_demo(factory)`
- [x] 2.10 GREEN `app/main.py`: en `crear_app`, tras la salvaguarda existente (`_verificar_aislamiento_demo`), `if settings.perfil == "demo": _resetear_demo(settings)`

## Fase 3: Override de acceso libre (Requirement: Autenticación... — Acceso libre sin login en demo — dep: Fase 1)

- [x] 3.1 RED `tests/test_navegacion.py`: `test_demo_acceso_libre_sin_login` — `crear_app()` con perfil demo (BD propia en `tmp_path`, ya sembrada) ⇒ GET `/admin/api/me` y una ruta protegida (`/admin/api/informes/dia`) devuelven 200 SIN sesión
- [x] 3.2 RED `tests/test_navegacion.py`: `test_produccion_sigue_exigiendo_login` — `crear_app()` con perfil producción (override NO registrado) ⇒ `/admin/api/me` sigue devolviendo 401 sin sesión
- [x] 3.3 GREEN `app/main.py`: en `crear_app`, si `settings.perfil == "demo"`, `app.dependency_overrides[require_admin] = require_admin_demo` (importar ambos de `app.presentacion.admin`)

## Fase 4: Navegación TPV ↔ Administración (Requirement: Botón de navegación TPV→Admin / Admin→TPV — dep: ninguna)

- [x] 4.1 RED `tests/test_navegacion.py`: `test_boton_tpv_a_admin` — GET `/tpv/` contiene `href="/admin/"` visible en la cabecera
- [x] 4.2 GREEN `app/ui/tpv.html`: botón "Administración" en la cabecera, junto a `#usuario`
- [x] 4.3 RED `tests/test_navegacion.py`: `test_boton_admin_a_tpv` — GET `/admin/` contiene `href="/tpv/"` y el texto "Ir al TPV"
- [x] 4.4 GREEN `app/ui/admin.html`: botón "Ir al TPV" en la cabecera de `dashboard()`

## Fase 5: Ajuste de "Salir" según perfil (Requirement: Ajuste de "Salir" según perfil — dep: Fase 4, reutiliza `/health` existente)

- [x] 5.1 RED `tests/test_navegacion.py`: `test_salir_oculto_en_demo` — comprobación estructural del HTML/JS servido en `/admin/`: el render/`.onclick` de `#salir` queda condicionado a `!esDemo` (sin motor de plantillas ni navegador; mismo patrón que el banner de modo-demo, `tests/test_health.py`)
- [x] 5.2 RED `tests/test_navegacion.py`: `test_salir_presente_en_produccion` — comprobación estructural equivalente para el caso no condicionado
- [x] 5.3 GREEN `app/ui/admin.html`: `dashboard()` consulta `/health` (mismo contrato que `tpv.html`), guarda `esDemo`, oculta o repropone "Salir" y protege su `.onclick` con null-check cuando `esDemo`

## Fase 6: Verificación final (dep: todas las anteriores)

- [x] 6.1 `make test`: suite completa verde — previos sin regresión + nuevos de Fases 1-5 (incluye no-regresión de `tests/test_admin_api.py::test_endpoint_protegido_exige_sesion` / `::test_login_solo_admin` / `::test_flujo_completo`)
- [x] 6.2 `make arch`: import-linter sin romper contratos (cambios en `app.main`, `app.presentacion.admin`, `app.seed` y HTML estático; ningún import nuevo cruza capas prohibidas)
