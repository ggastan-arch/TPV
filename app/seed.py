"""Datos de ejemplo para desarrollo (make seed).

Requiere el esquema aplicado (make migrate). Es idempotente: no duplica si ya existe.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.datos_demo import ARTICULOS as ARTICULOS_DEMO
from app.datos_demo import FAMILIAS as FAMILIAS_DEMO
from app.infraestructura.db import SessionLocal
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
    Cliente,
    CodigoBarras,
    ContadorSerie,
    Familia,
    PaginaBotonera,
    PerfilBotonera,
    Serie,
    TipoIVA,
    Usuario,
)

SERIES = [
    ("T", "Facturas simplificadas (tickets)", "F2"),
    ("F", "Facturas completas", "F1"),
    ("R", "Facturas rectificativas", "R5"),
]


def _hay_datos(s: Session) -> bool:
    return s.execute(select(TipoIVA.id).limit(1)).first() is not None


def _sembrar_catalogo_base(s: Session, ejercicio: int) -> None:
    """Catalogo base de ejemplo (IVA, series, familias, articulos, usuarios,
    botonera), compartido por `sembrar()` (produccion/desarrollo) y
    `sembrar_demo()` (perfil demo)."""
    iva_general = TipoIVA(nombre="General 21%", porcentaje=Decimal("21.00"))
    iva_reducido = TipoIVA(nombre="Reducido 10%", porcentaje=Decimal("10.00"))
    s.add_all([iva_general, iva_reducido])

    # La serie debe existir antes que su contador (FK sin relationship ORM ->
    # el flush no ordena solo; se fuerza flush intermedio).
    for codigo, desc, tipo in SERIES:
        s.add(Serie(codigo=codigo, descripcion=desc, tipo_factura_default=tipo))
    s.flush()
    for codigo, _desc, _tipo in SERIES:
        s.add(ContadorSerie(serie=codigo, ejercicio=ejercicio, ultimo_numero=0))

    peces = Familia(nombre="Peces tropicales", orden=1)
    plantas = Familia(nombre="Plantas vivas", orden=2)
    s.add_all([peces, plantas])
    s.flush()
    corales = Familia(nombre="Corales", orden=1, parent_id=peces.id)
    s.add(corales)
    s.flush()

    neon = Articulo(
        nombre="Neon cardenal", nombre_corto="Neon", familia_id=peces.id,
        tipo_iva_id=iva_general.id, pvp=Decimal("2.50"), control_stock=True,
    )
    anubias = Articulo(
        nombre="Anubias barteri", nombre_corto="Anubias", familia_id=plantas.id,
        tipo_iva_id=iva_reducido.id, pvp=Decimal("6.90"), control_stock=True,
    )
    tridacna = Articulo(
        nombre="Tridacna maxima", nombre_corto="Tridacna", familia_id=corales.id,
        tipo_iva_id=iva_general.id, pvp=Decimal("45.00"), precio_libre=True,
        requiere_cites=True, control_stock=True,
    )
    s.add_all([neon, anubias, tridacna])

    s.add(Usuario(nombre="admin", pin_hash=hash_pin("1234"), rol="administracion"))
    s.add(Usuario(nombre="dependiente", pin_hash=hash_pin("0000"), rol="venta"))

    perfil = PerfilBotonera(nombre="Principal")
    s.add(perfil)
    s.flush()
    pagina = PaginaBotonera(perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4)
    s.add(pagina)
    s.flush()  # asigna ids a articulos y familias pendientes

    # Fila 0: articulos directos.
    s.add(Boton(pagina_id=pagina.id, fila=0, columna=0, texto="Neon", articulo_id=neon.id))
    s.add(Boton(pagina_id=pagina.id, fila=0, columna=1, texto="Anubias", articulo_id=anubias.id))
    s.add(Boton(pagina_id=pagina.id, fila=0, columna=2, texto="Tridacna", articulo_id=tridacna.id))
    # Fila 1: navegacion por familias.
    s.add(Boton(pagina_id=pagina.id, fila=1, columna=0, texto="Peces", familia_id=peces.id))
    s.add(Boton(pagina_id=pagina.id, fila=1, columna=1, texto="Plantas", familia_id=plantas.id))
    # Fila 3: funciones.
    s.add(Boton(pagina_id=pagina.id, fila=3, columna=3, texto="Convertir en factura",
                funcion="convertir_factura"))
    s.add(Boton(pagina_id=pagina.id, fila=3, columna=4, texto="Abrir cajon",
                funcion="abrir_cajon"))


def _sembrar_iva_series_usuarios(
    s: Session, ejercicio: int
) -> tuple[TipoIVA, TipoIVA]:
    """Base fiscal comun: tipos de IVA, series con su contador y usuarios."""
    iva_general = TipoIVA(nombre="General 21%", porcentaje=Decimal("21.00"))
    iva_reducido = TipoIVA(nombre="Reducido 10%", porcentaje=Decimal("10.00"))
    s.add_all([iva_general, iva_reducido])

    for codigo, desc, tipo in SERIES:
        s.add(Serie(codigo=codigo, descripcion=desc, tipo_factura_default=tipo))
    s.flush()
    for codigo, _desc, _tipo in SERIES:
        s.add(ContadorSerie(serie=codigo, ejercicio=ejercicio, ultimo_numero=0))

    s.add(Usuario(nombre="admin", pin_hash=hash_pin("1234"), rol="administracion"))
    s.add(Usuario(nombre="dependiente", pin_hash=hash_pin("0000"), rol="venta"))
    s.flush()
    return iva_general, iva_reducido


def _construir_familias(s: Session, rutas: list[str]) -> dict[str, Familia]:
    """Crea el arbol de familias a partir de rutas "Padre/Hijo/Nieto".

    Devuelve un mapa ruta_completa -> Familia. El campo `orden` se asigna por
    orden de aparicion dentro de cada nivel (raiz o padre).
    """
    familias: dict[str, Familia] = {}
    ordenes: dict[int | None, int] = {}
    for ruta in rutas:
        partes = ruta.split("/")
        padre: Familia | None = None
        acumulada = ""
        for parte in partes:
            acumulada = f"{acumulada}/{parte}" if acumulada else parte
            if acumulada not in familias:
                parent_id = padre.id if padre is not None else None
                ordenes[parent_id] = ordenes.get(parent_id, 0) + 1
                fam = Familia(
                    nombre=parte, parent_id=parent_id, orden=ordenes[parent_id]
                )
                s.add(fam)
                s.flush()  # asigna id para que sirva de parent de sus hijos
                familias[acumulada] = fam
            padre = familias[acumulada]
    return familias


def _sembrar_catalogo_demo(s: Session, ejercicio: int) -> None:
    """Catalogo demo de agua dulce (sin acuario marino) reconstruido a partir
    del arbol de familias real de la tienda. Precios de demostracion."""
    iva_general, iva_reducido = _sembrar_iva_series_usuarios(s, ejercicio)
    ivas = {"general": iva_general, "reducido": iva_reducido}

    familias = _construir_familias(s, FAMILIAS_DEMO)

    articulos: dict[str, Articulo] = {}
    for datos in ARTICULOS_DEMO:
        flags = set(datos.get("flags", ()))
        articulo = Articulo(
            nombre=datos["nombre"],
            nombre_corto=datos["corto"],
            familia_id=familias[datos["familia"]].id,
            tipo_iva_id=ivas[datos["iva"]].id,
            pvp=Decimal(datos["pvp"]),
            control_stock="control_stock" in flags,
            precio_libre="precio_libre" in flags,
            requiere_cites="requiere_cites" in flags,
        )
        s.add(articulo)
        s.flush()
        ean = datos.get("ean")
        if ean:
            s.add(CodigoBarras(articulo_id=articulo.id, codigo=ean, principal=True))
        articulos[datos["corto"]] = articulo

    _sembrar_botonera_demo(s, familias, articulos)


def _sembrar_botonera_demo(
    s: Session,
    familias: dict[str, Familia],
    articulos: dict[str, Articulo],
) -> None:
    """Botonera demo: pagina con articulos frecuentes, navegacion por familias
    y funciones. Tolera que falte algun articulo del catalogo."""
    perfil = PerfilBotonera(nombre="Principal")
    s.add(perfil)
    s.flush()
    pagina = PaginaBotonera(
        perfil_id=perfil.id, nombre="Inicio", orden=0, columnas=5, filas=4
    )
    s.add(pagina)
    s.flush()

    # Fila 0: articulos directos frecuentes.
    directos = ["Neón cardenal", "Guppy macho", "Escalar velo", "Anubias", "Betta macho"]
    for col, corto in enumerate(directos):
        art = articulos.get(corto)
        if art is not None:
            s.add(Boton(pagina_id=pagina.id, fila=0, columna=col,
                        texto=art.nombre_corto, articulo_id=art.id))

    # Fila 1: navegacion por familias principales.
    fams = [
        ("Peces", "Peces por familias"),
        ("Plantas", "Plantas"),
        ("Alimento", "Alimento"),
        ("Trat. agua", "Tratamiento del agua"),
        ("Filtración", "Filtración"),
    ]
    for col, (texto, ruta) in enumerate(fams):
        fam = familias.get(ruta)
        if fam is not None:
            s.add(Boton(pagina_id=pagina.id, fila=1, columna=col,
                        texto=texto, familia_id=fam.id))

    # Fila 2: mas familias.
    fams2 = [
        ("Decoración", "Decoración"),
        ("Iluminación", "Iluminación"),
        ("Acuarios", "Acuarios"),
        ("Medicamentos", "Medicamentos"),
        ("Accesorios", "Accesorios"),
    ]
    for col, (texto, ruta) in enumerate(fams2):
        fam = familias.get(ruta)
        if fam is not None:
            s.add(Boton(pagina_id=pagina.id, fila=2, columna=col,
                        texto=texto, familia_id=fam.id))

    # Fila 3: funciones.
    s.add(Boton(pagina_id=pagina.id, fila=3, columna=3, texto="Convertir en factura",
                funcion="convertir_factura"))
    s.add(Boton(pagina_id=pagina.id, fila=3, columna=4, texto="Abrir cajón",
                funcion="abrir_cajon"))


def sembrar() -> None:
    ejercicio = datetime.now().astimezone().year
    with SessionLocal() as s, s.begin():
        if _hay_datos(s):
            print("Ya hay datos; no se siembra de nuevo.")
            return
        _sembrar_catalogo_base(s, ejercicio)

    print(f"Datos de ejemplo sembrados (ejercicio {ejercicio}).")


def sembrar_demo() -> None:
    """Seed idempotente de `tpv_demo.db`: catalogo demo de agua dulce (arbol de
    familias real de la tienda, SIN acuario marino, con precios de
    demostracion) mas un cliente de prueba. La "empresa demo" es el emisor de
    `settings` (NIF/nombre ya resueltos por el perfil,
    `Settings._resolver_perfil`); no existe una tabla de empresa separada."""
    ejercicio = datetime.now().astimezone().year
    with SessionLocal() as s, s.begin():
        if _hay_datos(s):
            print("Ya hay datos demo; no se siembra de nuevo.")
            return
        _sembrar_catalogo_demo(s, ejercicio)
        s.add(Cliente(
            nombre="Cliente de prueba (demo)", nif="00000000T",
            domicilio="Calle Demo 1, Bilbao", rgpd_consentimiento=True,
        ))

    print(f"Datos demo sembrados (ejercicio {ejercicio}).")


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        sembrar_demo()
    else:
        sembrar()
