# Tasks: Imágenes de catálogo en botones del TPV

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~550–700 (modelo, migración, util nueva, 2 servicios, 2 endpoints, 2 DTOs, 2 ficheros de test, 2 ficheros frontend) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Fase 1 (backend, TDD) → PR 2 = Fase 2 (frontend, manual) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend completo (modelo, migración, util, endpoints, DTO) bajo TDD, suite verde | PR 1 | Autónomo: no requiere frontend para verificarse (tests de API) |
| 2 | UI de subida/preview en consola + render en TPV | PR 2 | Depende de PR 1 (endpoints y DTO ya expuestos); verificación manual |

## Fase 1: Backend (TDD estricto, rojo → verde)

### 1. Modelo `Articulo.imagen` + migración
- [x] 1.1 RED: `tests/test_esquema.py` — falla porque `Articulo.imagen` no existe.
- [x] 1.2 GREEN: `app/infraestructura/persistencia/modelos/maestros.py` — añadir `Articulo.imagen: Mapped[str | None]`.
- [x] 1.3 GREEN: `migrations/versions/0006_articulo_imagen.py` — `add_column` aditiva, `down_revision="0005_familia_visible_tactil"`.

### 2. Util de validación de imágenes
- [x] 2.1 RED: `tests/test_imagenes.py` — `validar_imagen` acepta JPEG/PNG/WebP (magic bytes) → ext canónica.
- [x] 2.2 RED: rechaza GIF/PDF/texto (con `content-type` falseado), vacío y >3 MB → `ImagenInvalida`.
- [x] 2.3 RED: `nombre_archivo("articulo", 5, "jpg")` → patrón `articulo-5-<8hex>.jpg`, único por llamada.
- [x] 2.4 RED: `guardar_media`/`borrar_media` (monkeypatch `MEDIA_DIR` a `tmp_path`); borrar ruta inexistente no lanza.
- [x] 2.5 GREEN: crear `app/infraestructura/imagenes.py` (`MEDIA_DIR`, `ImagenInvalida`, `validar_imagen`, `nombre_archivo`, `guardar_media`, `borrar_media`).

### 3. Servir `media/` como estático
- [x] 3.1 GREEN: `app/main.py` — `MEDIA_DIR.mkdir(exist_ok=True)` + `app.mount("/media", StaticFiles(...), name="media")`.
- [x] 3.2 GREEN: añadir `media/` a `.gitignore`.

### 4. Endpoints de subida + cierre de la ruta arbitraria
- [x] 4.1 RED: subida JPEG válida a artículo → 200, archivo en disco, `Articulo.imagen` persistida, auditoría registrada.
- [x] 4.2 RED: subida inválida (tipo/tamaño) → 422, sin archivo, `imagen` sin cambios.
- [x] 4.3 RED: reemplazo A→B borra A; borrado fallido no bloquea el reemplazo.
- [x] 4.4 RED: id inexistente → 404 sin escribir; sin sesión admin → 401.
- [x] 4.5 RED: simétrico para familia (válida, inválida, reemplazo, 404/401).
- [x] 4.6 RED: `PUT` JSON de artículo/familia con `"imagen"` en el body → se ignora, no persiste.
- [x] 4.7 GREEN: `app/aplicacion/articulos.py` / `familias.py` — `fijar_imagen(id, ruta) -> str | None` (audita + commit).
- [x] 4.8 GREEN: `app/presentacion/admin.py` — `POST /admin/api/maestros/{articulos|familias}/{id}/imagen` (multipart, `require_admin`); quitar `imagen` del payload del PUT JSON.

### 5. DTO del botón expone la imagen del destino
- [x] 5.1 RED: `tests/test_tpv_api.py` — botón→artículo y botón→familia exponen `imagen`; destino sin imagen → `null`; drill-down de familia expone `imagen` en subfamilias/artículos.
- [x] 5.2 GREEN: `app/presentacion/tpv.py` — `_articulo_dto` y ramas de familia/subfamilia añaden `imagen`.

### 6. Checkpoint backend
- [x] 6.1 `make test` en verde (suite completa): 392 passed (359 baseline + 33 nuevos).
- [x] 6.2 `make arch` en verde (import-linter): 3 kept, 0 broken.

## Fase 2: Frontend (verificación manual, sin tests automáticos)

### 7. Subida/preview en consola + render en TPV
- [ ] 7.1 `app/ui/admin.html` — input de archivo + preview en la ficha de artículo; sube al endpoint de 4.8 y refresca la imagen mostrada.
- [ ] 7.2 `app/ui/admin.html` — ídem en la ficha de familia.
- [ ] 7.3 `app/ui/tpv.html` — el botón renderiza `<img src>` con la imagen del destino cuando existe; conserva el aspecto actual cuando es `null`.
- [ ] 7.4 Ejecutar el checklist de verificación manual (abajo).

### 8. Checkpoint final
- [ ] 8.1 `make test` en verde (sin regresión).
- [ ] 8.2 `make arch` en verde.

### Checklist de verificación manual (Fase 2)
- Subir JPEG a un artículo → preview visible sin recargar.
- Subir PNG a una familia → preview visible.
- Subir un `.pdf` renombrado → error visible, ficha no se rompe.
- Reemplazar la imagen de un artículo → preview se actualiza (sin caché obsoleta).
- TPV: botón de artículo con imagen la muestra; botón sin imagen conserva su aspecto.
- Drill-down de familia en TPV muestra imagen de subfamilias/artículos.
- `media/` no aparece en `git status` tras subir imágenes.
