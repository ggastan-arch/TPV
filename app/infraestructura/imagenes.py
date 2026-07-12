"""Validacion y almacenamiento de imagenes de catalogo (articulo/familia).

La imagen es un ARCHIVO en `media/`; la BD guarda solo su ruta publica (nunca
binarios ni base64). El tipo real se detecta por magic bytes (nunca por el
`content-type` declarado por el cliente, que se falsea trivialmente) y el
nombre de archivo lo genera SIEMPRE el servidor (nunca el filename del
cliente), evitando path traversal y colisiones.

`MEDIA_DIR` se lee como GLOBAL de modulo (no como default de parametro) para
que los tests puedan monkeypatchearlo a un `tmp_path` sin tocar el `media/`
real del proyecto.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

# Raiz del proyecto: este fichero vive en app/infraestructura/imagenes.py.
MEDIA_DIR = Path(__file__).resolve().parents[2] / "media"

TAMANO_MAX_BYTES = 3 * 1024 * 1024

# Tipo detectado (magic bytes) -> extension canonica de archivo.
EXTENSIONES = {"jpeg": "jpg", "png": "png", "webp": "webp"}


class ImagenInvalida(Exception):
    """Tipo de archivo no permitido, contenido vacio o tamano excedido."""


def _detectar_tipo(contenido: bytes) -> str | None:
    """Detecta el tipo real por magic bytes. Devuelve la clave de `EXTENSIONES`
    o `None` si no coincide con ningun formato soportado."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    return None


def validar_imagen(contenido: bytes, *, tamano_max: int = TAMANO_MAX_BYTES) -> str:
    """Valida el contenido de una imagen subida y devuelve su extension canonica.

    Rechaza (levanta `ImagenInvalida`): contenido vacio, tamano > `tamano_max`
    o tipo real distinto de JPEG/PNG/WebP (el `content-type` del cliente se
    ignora por completo: solo cuentan los bytes)."""
    if not contenido:
        raise ImagenInvalida("El archivo esta vacio")
    if len(contenido) > tamano_max:
        raise ImagenInvalida(
            f"El archivo supera el tamano maximo permitido ({tamano_max} bytes)"
        )
    tipo = _detectar_tipo(contenido)
    if tipo is None:
        raise ImagenInvalida("Tipo de archivo no permitido (solo JPEG, PNG o WebP)")
    return EXTENSIONES[tipo]


def nombre_archivo(entidad: str, entidad_id: int, extension: str) -> str:
    """Genera un nombre de archivo server-side; nunca reutiliza el nombre del
    cliente (evita path traversal y colisiones)."""
    return f"{entidad}-{entidad_id}-{uuid4().hex[:8]}.{extension}"


def guardar_media(nombre: str, contenido: bytes) -> None:
    """Crea `MEDIA_DIR` si hace falta y escribe el contenido en `nombre`."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / nombre).write_bytes(contenido)


def borrar_media(ruta_o_nombre: str | None) -> None:
    """Borra un archivo de `MEDIA_DIR` (best-effort: no lanza si no existe).

    Solo usa el `basename` de `ruta_o_nombre` (anti path traversal): aunque se
    reciba una ruta con "..", nunca se borra nada fuera de `MEDIA_DIR`."""
    if not ruta_o_nombre:
        return
    nombre = Path(ruta_o_nombre).name
    try:
        (MEDIA_DIR / nombre).unlink()
    except FileNotFoundError:
        pass
