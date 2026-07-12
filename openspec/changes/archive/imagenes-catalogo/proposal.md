# Proposal: Imágenes de catálogo en botones del TPV

## Intent

En la botonera táctil, peces y plantas se distinguen mal por texto/color y hoy no
hay forma de subir una foto. La persona titular necesita reconocerlos visualmente al vender.
Objetivo: subir una imagen a cada artículo y familia desde la consola y que el botón
del TPV la muestre. La imagen se sube UNA vez al artículo/familia y la reutiliza
cualquier botón que lo apunte.

## Scope

### In Scope
- Campo `Articulo.imagen` (ruta/nombre de archivo); migración Alembic `0006` aditiva y
  nullable. `Familia.imagen` ya existe.
- Endpoint de subida multipart en la consola para imagen de artículo y de familia:
  guarda el archivo en `media/` y persiste solo la ruta en BD.
- Servir `media/` como estático (`StaticFiles`).
- El DTO de botón del TPV (`/tpv/api/botonera`, `/tpv/api/familia`) expone la imagen
  efectiva del destino (precedencia: botón propio > artículo/familia).
- UI de consola: subir y previsualizar la imagen en las fichas de artículo y familia.
- Añadir `media/` a `.gitignore`.

### Out of Scope
- Edición/recorte de imágenes; optimización, CDN o thumbnails.
- Múltiples imágenes por artículo.
- Tests automáticos del JS de subida (sin infra de test frontend).

## Non-goals
- No tocar la cadena de huellas ni las tablas de ventas/registros fiscales.
- No guardar imágenes ni base64 en la BD.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `maestros-crud`: artículo gana `imagen`; subida multipart de imagen para artículo y
  familia; servir `media/` estático; subir/previsualizar en las fichas de la consola.
- `tpv-venta`: la botonera y la vista de familia exponen la imagen efectiva del destino
  para que el TPV la muestre.
- `editor-botoneras`: el árbol/preview del editor muestra la imagen efectiva del destino
  y aplica la precedencia botón propio > destino.

## Approach

Ruta en BD + archivo en disco servido estático; jamás binarios en la BD. Upload
multipart validado en backend (tipo y tamaño), con nombre de archivo saneado. Una
función única resuelve la "imagen efectiva" de un botón/destino, reutilizada por TPV y
editor. Backend con TDD estricto; frontend (subida + render) verificado a mano.

## To Resolve in Design
- Validación del archivo: tipos permitidos (p.ej. JPEG/PNG/WebP) y tamaño máximo.
- Nombres de archivo: evitar colisiones y path traversal (¿id + uuid/hash?).
- Cómo resuelve el botón la imagen efectiva (botón propio > artículo/familia).
- Limpieza del archivo anterior al reemplazar la imagen.
- Ubicación de `media/` y montaje del `StaticFiles`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/infraestructura/persistencia/modelos/maestros.py` | Modified | Campo `Articulo.imagen` |
| `migrations/versions/0006_*.py` | New | Añade `articulo.imagen` (aditiva) |
| `app/presentacion/admin.py` | Modified | Endpoint de subida multipart (artículo/familia) |
| `app/main.py` | Modified | Montar `StaticFiles` para `media/` |
| `app/presentacion/tpv.py` | Modified | DTO de botón expone imagen efectiva |
| `app/ui/*.html` | Modified | Subir/previsualizar y render de imagen |
| `.gitignore` | Modified | Ignorar `media/` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Subida de archivos = superficie de seguridad (path traversal, tipo/tamaño) | Med | Validar tipo y tamaño en backend; sanear nombre; guardar fuera de rutas de código |
| Imágenes subidas se cuelan al repo público | Med | `media/` en `.gitignore` |
| Archivos huérfanos al reemplazar imagen | Low | Limpieza del anterior (design) |

## Rollback Plan

Migración `0006` reversible (downgrade elimina `articulo.imagen`). Revertir el montaje
de `StaticFiles` y los endpoints. Los archivos de `media/` son descartables y no
versionados; borrarlos no afecta la cadena fiscal.

## Dependencies
- Ninguna librería nueva obligatoria (FastAPI aporta `UploadFile` y `StaticFiles`).

## Success Criteria
- [ ] Se sube una foto a un artículo y a una familia desde la consola.
- [ ] El botón del TPV muestra la imagen efectiva del destino.
- [ ] El archivo vive en `media/` (no en BD ni en git); la BD guarda solo la ruta.
- [ ] Backend cubierto por tests: el upload valida (tipo/tamaño) y guarda; el DTO expone la imagen efectiva.
