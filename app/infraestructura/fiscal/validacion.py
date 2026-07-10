"""Validacion de los registros y del sobre de remision contra los XSD de la AEAT.

- `esquema()`: valida RegistroAlta/RegistroAnulacion contra SuministroInformacion.xsd.
- `esquema_remision()`: valida el sobre RegFactuSistemaFacturacion contra SuministroLR.xsd
  (que a su vez importa SuministroInformacion.xsd).

Los XSD importan el esquema de firma XML (xmldsig) por URL; como en VERI*FACTU los
registros NO se firman (ds:Signature es opcional y no lo emitimos), se elimina ese
import antes de compilar, para validar sin conexion. Para el sobre, ambos esquemas se
materializan (sin firma) en un directorio temporal con los nombres que espera el
import relativo de SuministroLR.
"""
from __future__ import annotations

import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from lxml import etree

from app.core.config import settings

_XS = "{http://www.w3.org/2001/XMLSchema}"


def _dir_schemas() -> Path:
    return Path(settings.schemas_dir)


def _arbol_sin_firma(ruta: Path) -> etree._ElementTree:
    """Parsea un XSD y elimina el import de xmldsig y las referencias a ds:Signature."""
    doc = etree.parse(str(ruta))
    root = doc.getroot()
    a_borrar = []
    for imp in root.findall(f"{_XS}import"):
        referencia = (imp.get("schemaLocation") or "") + (imp.get("namespace") or "")
        if "xmldsig" in referencia:
            a_borrar.append(imp)
    for el in root.iter(f"{_XS}element"):
        if (el.get("ref") or "").endswith("Signature"):
            a_borrar.append(el)
    for el in a_borrar:
        el.getparent().remove(el)
    return doc


@lru_cache(maxsize=1)
def esquema() -> etree.XMLSchema:
    doc = _arbol_sin_firma(_dir_schemas() / "SuministroInformacion.xsd.xml")
    return etree.XMLSchema(doc)


@lru_cache(maxsize=1)
def _dir_remision() -> Path:
    """Materializa SuministroInformacion (sin firma) y SuministroLR con nombres que
    resuelven el import relativo, para compilar el esquema del sobre offline."""
    tmp = Path(tempfile.mkdtemp(prefix="tpv_xsd_"))
    info = _arbol_sin_firma(_dir_schemas() / "SuministroInformacion.xsd.xml")
    (tmp / "SuministroInformacion.xsd").write_bytes(etree.tostring(info))
    shutil.copy(_dir_schemas() / "SuministroLR.xsd.xml", tmp / "SuministroLR.xsd")
    return tmp


@lru_cache(maxsize=1)
def esquema_remision() -> etree.XMLSchema:
    doc = etree.parse(str(_dir_remision() / "SuministroLR.xsd"))
    return etree.XMLSchema(doc)


def _errores(schema: etree.XMLSchema, elemento: etree._Element) -> list[str]:
    if schema.validate(elemento):
        return []
    return [f"{e.line}: {e.message}" for e in schema.error_log]


def errores(elemento: etree._Element) -> list[str]:
    """Errores de validacion de un RegistroAlta/RegistroAnulacion (vacia si conforme)."""
    return _errores(esquema(), elemento)


def errores_remision(elemento: etree._Element) -> list[str]:
    """Errores de validacion del sobre RegFactuSistemaFacturacion (vacia si conforme)."""
    return _errores(esquema_remision(), elemento)


def es_valido(elemento: etree._Element) -> bool:
    return esquema().validate(elemento)
