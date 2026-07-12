# Design: Imágenes de catálogo en botones del TPV

## Technical Approach

La imagen es un ARCHIVO en disco servido estático; la BD guarda solo su ruta pública
(nunca binarios ni base64). El backend valida cada subida por tipo REAL (magic bytes) y
tamaño, y genera un nombre server-side (jamás el filename del cliente). El flujo respeta
la arquitectura por capas existente: endpoint (adaptador HTTP + E/S de fichero) → util de
infraestructura (`app/infraestructura/imagenes.py`, pura y testeable) → servicio de
aplicación (muta campo + audita + commit). El DTO de botón/familia del TPV expone la ruta
del destino para que el `<img src>` la use verbatim. Frontend (subir/preview) verificado a
mano; todo lo demás bajo TDD estricto.

## Architecture Decisions

| Decisión | Alternativa rechazada | Motivo |
|----------|-----------------------|--------|
| Archivo en `media/` + ruta en BD | Blob/base64 en columna | Invariante `docs`: nada de binarios en BD; `media/` es desechable y no altera la cadena fiscal |
| Validar por magic bytes (util pura que recibe `bytes`) | Confiar en `Content-Type`/extensión del cliente | Superficie de seguridad: el header y la extensión se falsifican; testeable sin HTTP |
| Nombre `{entidad}-{id}-{uuid8}.{ext}` server-side | Reusar el filename del cliente | Elimina path traversal y colisiones; extensión canónica del tipo detectado |
| BD guarda la ruta pública `/media/{archivo}` | Guardar filename desnudo / ruta absoluta | El DTO la entrega lista para `<img src>`; sin prefijos duplicados en Python+JS |
| SIN `Boton.imagen`; imagen efectiva = imagen del destino | Columna propia en botón + resolver de precedencia | Un botón apunta a UN destino (artículo O familia); no hay precedencia real que resolver → un resolver sobra |
| `MEDIA_DIR` como global de módulo leído en tiempo de llamada | Parámetro por defecto `media_dir=MEDIA_DIR` | Permite monkeypatch a `tmp_path` en tests (los defaults se fijan en `def`) |

## Data Flow

    Consola (ficha)                     TPV (venta)
        │ multipart                         │ GET /tpv/api/botonera
        ▼                                   ▼
    POST /admin/api/maestros/{e}/{id}/imagen   _articulo_dto / familia dto
        │ await file.read()                 │  "imagen": a.imagen | fam.imagen
        ▼                                   ▼
    validar_imagen(bytes) ──► ext        <img src="/media/...">
        │                                   ▲
        ▼                                   │ StaticFiles("/media")
    nombre_archivo() + guardar_media() ──► media/{archivo}
        │                                   ▲
        ▼                                   │
    Servicio.fijar_imagen(id,"/media/..") ─┴─► BD (articulo.imagen / familia.imagen)
        │ (audita + commit)
        ▼
    borrar_media(anterior)  # best-effort tras commit

## File Changes

| Fichero | Acción | Descripción |
|---------|--------|-------------|
| `migrations/versions/0006_articulo_imagen.py` | Crear | `add_column articulo.imagen` (String, nullable); `down_revision = "0005_familia_visible_tactil"` |
| `app/infraestructura/persistencia/modelos/maestros.py` | Modificar | `Articulo.imagen: Mapped[str \| None]` (`Familia.imagen` ya existe) |
| `app/infraestructura/imagenes.py` | Crear | Util pura de validación + helpers de E/S y `MEDIA_DIR` |
| `app/main.py` | Modificar | `MEDIA_DIR.mkdir(...)` + `app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")` |
| `app/aplicacion/articulos.py` | Modificar | `ServicioArticulos.fijar_imagen(id, ruta) -> str \| None` (devuelve la anterior) |
| `app/aplicacion/familias.py` | Modificar | `ServicioFamilias.fijar_imagen(id, ruta) -> str \| None` |
| `app/presentacion/admin.py` | Modificar | 2 endpoints multipart de subida + `imagen` en DTOs read-only de maestros |
| `app/presentacion/tpv.py` | Modificar | `_articulo_dto` y ramas familia/subfamilia exponen `imagen` |
| `.gitignore` | Modificar | Añadir `media/` (el dir se crea en runtime) |
| `app/ui/admin.html` | Modificar | Subir + previsualizar imagen en fichas de artículo y familia (verificado a mano) |

## Interfaces / Contracts

```python
# app/infraestructura/imagenes.py
MEDIA_DIR = Path(__file__).resolve().parents[2] / "media"   # raíz del proyecto
TAMANO_MAX_BYTES = 3 * 1024 * 1024
EXTENSIONES = {"jpeg": "jpg", "png": "png", "webp": "webp"}  # tipo detectado -> ext canónica

class ImagenInvalida(Exception): ...

def validar_imagen(contenido: bytes, *, tamano_max: int = TAMANO_MAX_BYTES) -> str:
    """Detecta el tipo REAL por magic bytes (JPEG FF D8 FF / PNG 89504E47.. /
    WebP 'RIFF'....'WEBP'). Rechaza tipo no permitido, vacío o > tamano_max.
    Devuelve la extensión canónica o lanza ImagenInvalida."""

def nombre_archivo(entidad: str, entidad_id: int, extension: str) -> str:
    return f"{entidad}-{entidad_id}-{uuid4().hex[:8]}.{extension}"

def guardar_media(nombre: str, contenido: bytes) -> None:   # crea MEDIA_DIR, escribe bytes
def borrar_media(ruta_o_nombre: str | None) -> None:        # best-effort; usa solo basename (anti-traversal)
```

```python
# app/presentacion/admin.py — mismo patrón para familia
@router.post("/api/maestros/articulos/{articulo_id}/imagen")
async def subir_imagen_articulo(articulo_id: int, request: Request,
        archivo: UploadFile = File(...),
        usuario_id: int = Depends(require_admin), uow=Depends(get_uow)) -> dict:
    if uow.articulos.buscar(articulo_id) is None:      # 404 antes de escribir disco
        raise HTTPException(404, "Articulo no encontrado")
    try:
        ext = validar_imagen(await archivo.read())     # el body ya está en memoria
    except ImagenInvalida as exc:
        raise HTTPException(422, str(exc))              # nada escrito, nada persistido
    nombre = nombre_archivo("articulo", articulo_id, ext)
    guardar_media(nombre, contenido)
    anterior = _servicio_articulos(request, usuario_id, uow).fijar_imagen(
        articulo_id, f"/media/{nombre}")               # audita "cambiar_imagen_articulo" + commit
    borrar_media(anterior)                              # best-effort, tras commit OK
    return {"imagen": f"/media/{nombre}"}
```

Orden de fallo: validar (sin disco) → verificar existencia (sin disco) → escribir → commit →
borrar anterior. Si el commit falla, el `try` del endpoint borra el archivo nuevo (huérfano).

## Testing Strategy

| Capa | Qué probar | Cómo |
|------|-----------|------|
| Unit | `validar_imagen` acepta JPEG/PNG/WebP → ext canónica | bytes con magic real por tipo |
| Unit | rechaza tipo no permitido (GIF/PDF/texto), vacío y > 3 MB | assertRaises `ImagenInvalida` |
| Unit | `nombre_archivo` → forma `articulo-5-<8hex>.jpg`; ignora filename cliente; único por llamada | regex + dos llamadas distintas |
| Integration | subida válida → 200, archivo en `tmp_path`, `articulo.imagen == /media/...`, fila de auditoría | `TestClient` + sesión admin; monkeypatch `imagenes.MEDIA_DIR` a `tmp_path` |
| Integration | subida inválida (tipo/tamaño) → 422, sin archivo, `imagen` sin cambios | idem |
| Integration | reemplazo: sube A luego B → A borrado, `imagen` apunta a B | idem |
| Integration | id inexistente → 404 (sin escribir); sin sesión admin → 401 | idem |
| Integration | familia: subida válida simétrica | idem |
| DTO | `/tpv/api/botonera`: botón→artículo y botón→familia exponen `imagen`; botón→función sin imagen | fixture de botonera |
| DTO | `/tpv/api/familia/{id}`: artículos y subfamilias exponen `imagen` | fixture de familia |

Testabilidad: `guardar_media`/`borrar_media` leen `MEDIA_DIR` como global del módulo (no como
default de parámetro), de modo que los tests lo monkeypatchean a un `tmp_path` sin tocar `media/`.

## Migration / Rollout

`0006` es aditiva y reversible: `upgrade` añade `articulo.imagen` nullable (filas existentes →
NULL); `downgrade` la elimina. Los archivos de `media/` son descartables y no versionados;
borrarlos no afecta la cadena fiscal ni ventas/registros. Sin backfill.

## Open Questions

- [ ] `FamiliaReq.imagen` (campo string en el PUT JSON) queda como está; la ficha gestiona la
      imagen SOLO por el endpoint de subida. ¿Se elimina del contrato JSON para forzar rutas
      validadas y evitar que un admin inyecte una ruta arbitraria? (riesgo bajo: admin confiable).
- [ ] ¿`MEDIA_DIR` debe moverse a `Settings` para diferenciar perfil demo/producción? No exigido
      (las imágenes no son datos fiscales); por ahora un directorio compartido es aceptable.
- [ ] Límite de 3 MB y set JPEG/PNG/WebP: confirmar con la persona titular si alguna cámara/formato de la
      tienda queda fuera.
