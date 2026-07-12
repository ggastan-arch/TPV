# Tasks: Familia visible en táctil

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~120-160 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (una sola tanda de apply) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Modelo + migración 0005 + propagación CRUD + filtro TPV + suite verde | PR único | Cambio chico, aditivo, sin capa fiscal; una sola tanda |

## Phase 1: Modelo y migración (Foundation)

- [x] 1.1 RED: en `tests/test_familias.py`, test que instancia `Familia(nombre=...)` sin pasar `visible_en_tactil` y espera `visible_en_tactil is True` (default a nivel modelo).
- [x] 1.2 GREEN: en `app/infraestructura/persistencia/modelos/maestros.py`, añadir `visible_en_tactil: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)` a `Familia` (tras `activo`, línea ~39).
- [x] 1.3 Crear `migrations/versions/0005_familia_visible_tactil.py`: `revision = "0005_familia_visible_tactil"`, `down_revision = "0004_configuracion_empresa"`; `upgrade()` con `op.add_column("familia", sa.Column("visible_en_tactil", sa.Boolean, nullable=False, server_default=sa.true()))`; `downgrade()` con `op.drop_column("familia", "visible_en_tactil")`.
- [x] 1.4 Verificación: `make migrate` aplica `0005` sin error; columna existe con `server_default` (filas previas → `True`).

## Phase 2: Propagación CRUD (Core Implementation)

- [x] 2.1 RED: en `tests/test_familias.py`, `test_crear_familia_sin_flag_usa_default_true` — `ServicioFamilias.crear` con `DatosFamilia` sin `visible_en_tactil` persiste `True`.
- [x] 2.2 RED: `test_crear_familia_no_visible_en_tactil_y_audita` — `DatosFamilia(visible_en_tactil=False)` persiste `False` y genera 1 log `crear_familia`.
- [x] 2.3 RED: `test_actualizar_flag_visible_en_tactil_y_audita` — `ServicioFamilias.actualizar` cambia `visible_en_tactil` de `True` a `False` y genera 1 log `actualizar_familia`.
- [x] 2.4 GREEN: en `app/aplicacion/familias.py`, añadir `visible_en_tactil: bool = True` a `DatosFamilia`; en `ServicioFamilias.crear` pasar `visible_en_tactil=datos.visible_en_tactil` al construir `Familia`; en `ServicioFamilias.actualizar` asignar `familia.visible_en_tactil = datos.visible_en_tactil`.
- [x] 2.5 RED: en `tests/test_admin_api.py`, `test_listado_maestros_familias_expone_visible_en_tactil` — GET `/admin/api/maestros/familias` incluye `visible_en_tactil` por elemento.
- [x] 2.6 GREEN: en `app/presentacion/admin.py`, añadir `visible_en_tactil: bool = True` a `FamiliaReq` (línea ~121-126); añadir `"visible_en_tactil": f.visible_en_tactil` al dict de `maestros_familias` (línea ~327).

## Phase 3: Filtro TPV (Integration)

- [x] 3.1 RED: en `tests/test_tpv_api.py`, `test_familia_excluye_subfamilias_no_visibles_en_tactil` — familia con dos subfamilias activas (una `visible_en_tactil=True`, otra `False`); GET `/tpv/api/familia/{id}` solo devuelve la visible en `subfamilias`.
- [x] 3.2 RED: `test_familia_incluye_subfamilias_visibles_y_activas` — no-regresión, subfamilias con `visible_en_tactil=True` y `activo=True` siguen apareciendo.
- [x] 3.3 RED: reutilizar/confirmar caso existente de subfamilia inactiva (comportamiento previo intacto: `activo=False` sigue excluida aunque `visible_en_tactil=True`).
- [x] 3.4 GREEN: en `app/presentacion/tpv.py` (`familia`, línea ~155-158), sumar `Familia.visible_en_tactil.is_(True)` al `where(...)` de la query de `subs`.
- [x] 3.5 RED: en `tests/test_tpv_api.py`, `test_botonera_respeta_boton_explicito_a_familia_no_visible` — botón de botonera apuntando a familia con `visible_en_tactil=False` sigue apareciendo en GET `/api/botonera`.
- [x] 3.6 GREEN: sin cambio de código en `/api/botonera` (verificar que el render de botones no referencia el nuevo filtro); test 3.5 debe pasar solo con los cambios de 1.x-2.x.

## Phase 4: Verificación (Cleanup)

- [x] 4.1 Ejecutar `make test`: suite completa verde, incluidos los tests nuevos de las Fases 1-3. (359/359 passed; baseline 350 + 9 tests nuevos)
- [x] 4.2 Ejecutar `make arch`: import-linter sin violaciones (capas hexagonales intactas). (3 kept, 0 broken)
- [x] 4.3 Revisar que ninguna capa fiscal (ventas, registros, cadena de huellas, triggers de inmutabilidad) fue tocada — confirmar diff limitado a los 5 ficheros de `design.md`. (confirmado: maestros.py, migración 0005, familias.py, admin.py, tpv.py + tests)
