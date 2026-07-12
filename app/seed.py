"""Datos de ejemplo para desarrollo (make seed).

Requiere el esquema aplicado (make migrate). Es idempotente: no duplica si ya existe.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infraestructura.db import SessionLocal
from app.infraestructura.seguridad import hash_pin
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
    Cliente,
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
    material = Familia(nombre="Material", orden=3)
    s.add_all([peces, plantas, material])
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
        tipo_iva_id=iva_general.id, pvp=Decimal("45.00"), modo_precio="libre",
        requiere_cites=True, control_stock=True,
    )
    # Genericos (modo libre, PVP 0): fuerzan precio + descripcion al vender
    # (un ejemplar sin ficha propia en catalogo, ver spec "Descripcion obligatoria
    # en modo libre al emitir").
    generico_pez = Articulo(
        nombre="Generico pez", nombre_corto="Gen.pez", familia_id=peces.id,
        tipo_iva_id=iva_general.id, pvp=Decimal("0.00"), modo_precio="libre",
    )
    generico_planta = Articulo(
        nombre="Generico planta", nombre_corto="Gen.planta", familia_id=plantas.id,
        tipo_iva_id=iva_reducido.id, pvp=Decimal("0.00"), modo_precio="libre",
    )
    generico_material = Articulo(
        nombre="Generico material", nombre_corto="Gen.material", familia_id=material.id,
        tipo_iva_id=iva_general.id, pvp=Decimal("0.00"), modo_precio="libre",
    )
    # Material al peso de ejemplo: pvp = precio/kg de catalogo.
    madera_al_peso = Articulo(
        nombre="Madera flotante (al peso)", nombre_corto="Madera", familia_id=material.id,
        tipo_iva_id=iva_general.id, pvp=Decimal("18.00"), modo_precio="al_peso",
    )
    s.add_all([
        neon, anubias, tridacna,
        generico_pez, generico_planta, generico_material, madera_al_peso,
    ])

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


def sembrar() -> None:
    ejercicio = datetime.now().astimezone().year
    with SessionLocal() as s, s.begin():
        if _hay_datos(s):
            print("Ya hay datos; no se siembra de nuevo.")
            return
        _sembrar_catalogo_base(s, ejercicio)

    print(f"Datos de ejemplo sembrados (ejercicio {ejercicio}).")


def sembrar_demo() -> None:
    """Seed idempotente de `tpv_demo.db`: mismo catalogo base que `sembrar()`
    mas un cliente de prueba. La "empresa demo" es el emisor de `settings`
    (NIF/nombre ya resueltos por el perfil, `Settings._resolver_perfil`); no
    existe una tabla de empresa separada."""
    ejercicio = datetime.now().astimezone().year
    with SessionLocal() as s, s.begin():
        if _hay_datos(s):
            print("Ya hay datos demo; no se siembra de nuevo.")
            return
        _sembrar_catalogo_base(s, ejercicio)
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
