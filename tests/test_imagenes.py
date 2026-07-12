"""Util pura de validacion/gestion de imagenes de catalogo.

Sin dependencias HTTP: testeable en aislamiento. El tipo se detecta SIEMPRE por
los magic bytes reales del contenido, nunca por el content-type declarado por
el cliente (ver `tests/test_admin_api.py` para el rechazo con content-type
falseado a nivel de endpoint)."""
from __future__ import annotations

import re

import pytest

from app.infraestructura.imagenes import (
    ImagenInvalida,
    borrar_media,
    guardar_media,
    nombre_archivo,
    validar_imagen,
)

_JPEG = b"\xff\xd8\xff\xe0" + b"JFIF" + b"\x00" * 40
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
_WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 40
_GIF = b"GIF89a" + b"\x00" * 40
_TEXTO_PLANO = b"esto no es una imagen, es texto plano" * 5


# --- validar_imagen: tipos aceptados --------------------------------------------
def test_validar_imagen_acepta_jpeg_y_devuelve_extension_canonica():
    assert validar_imagen(_JPEG) == "jpg"


def test_validar_imagen_acepta_png_y_devuelve_extension_canonica():
    assert validar_imagen(_PNG) == "png"


def test_validar_imagen_acepta_webp_y_devuelve_extension_canonica():
    assert validar_imagen(_WEBP) == "webp"


# --- validar_imagen: rechazos ----------------------------------------------------
def test_validar_imagen_rechaza_gif():
    with pytest.raises(ImagenInvalida):
        validar_imagen(_GIF)


def test_validar_imagen_rechaza_texto_plano_aunque_declare_ser_imagen():
    # El content-type declarado por el cliente no llega a esta funcion: solo
    # importan los bytes reales. Un .txt renombrado a .jpg se rechaza igual.
    with pytest.raises(ImagenInvalida):
        validar_imagen(_TEXTO_PLANO)


def test_validar_imagen_rechaza_contenido_vacio():
    with pytest.raises(ImagenInvalida):
        validar_imagen(b"")


def test_validar_imagen_rechaza_tamano_excedido():
    contenido_grande = _JPEG + b"\x00" * (3 * 1024 * 1024)
    with pytest.raises(ImagenInvalida):
        validar_imagen(contenido_grande, tamano_max=3 * 1024 * 1024)


def test_validar_imagen_acepta_justo_en_el_limite_de_tamano():
    tamano_max = 1024
    contenido = _JPEG + b"\x00" * (tamano_max - len(_JPEG))
    assert len(contenido) == tamano_max
    assert validar_imagen(contenido, tamano_max=tamano_max) == "jpg"


# --- nombre_archivo ---------------------------------------------------------------
def test_nombre_archivo_tiene_la_forma_esperada():
    nombre = nombre_archivo("articulo", 5, "jpg")
    assert re.fullmatch(r"articulo-5-[0-9a-f]{8}\.jpg", nombre)


def test_nombre_archivo_ignora_cualquier_dato_de_cliente_y_es_unico_por_llamada():
    a = nombre_archivo("articulo", 5, "jpg")
    b = nombre_archivo("articulo", 5, "jpg")
    assert a != b


# --- guardar_media / borrar_media (E/S real, MEDIA_DIR monkeypatcheado) --------
def test_guardar_media_crea_el_directorio_si_no_existe_y_escribe_el_contenido(tmp_path, monkeypatch):
    import app.infraestructura.imagenes as imagenes_mod

    destino = tmp_path / "media_no_creada_aun"
    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", destino)

    guardar_media("archivo.jpg", b"contenido-binario")

    assert (destino / "archivo.jpg").read_bytes() == b"contenido-binario"


def test_borrar_media_elimina_el_archivo_existente(tmp_path, monkeypatch):
    import app.infraestructura.imagenes as imagenes_mod

    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", tmp_path)
    guardar_media("a-borrar.jpg", b"x")
    assert (tmp_path / "a-borrar.jpg").exists()

    borrar_media("a-borrar.jpg")
    assert not (tmp_path / "a-borrar.jpg").exists()


def test_borrar_media_ruta_inexistente_no_lanza(tmp_path, monkeypatch):
    import app.infraestructura.imagenes as imagenes_mod

    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", tmp_path)
    borrar_media("no-existe.jpg")  # no debe lanzar


def test_borrar_media_con_none_no_lanza(tmp_path, monkeypatch):
    import app.infraestructura.imagenes as imagenes_mod

    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", tmp_path)
    borrar_media(None)  # no debe lanzar (sin imagen anterior)


def test_borrar_media_usa_solo_basename_anti_traversal(tmp_path, monkeypatch):
    import app.infraestructura.imagenes as imagenes_mod

    subdir = tmp_path / "media"
    subdir.mkdir()
    monkeypatch.setattr(imagenes_mod, "MEDIA_DIR", subdir)

    fuera = tmp_path / "fuera_de_media.txt"
    fuera.write_text("secreto")

    # Aunque se pase una ruta con "..", solo se intenta borrar el basename
    # dentro de MEDIA_DIR: el archivo de fuera nunca se toca.
    borrar_media("../fuera_de_media.txt")

    assert fuera.exists()
