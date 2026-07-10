"""Datos de ejemplo para desarrollo (make seed).

Requiere el esquema aplicado (make migrate). Es idempotente: no duplica si ya existe.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.seguridad import hash_pin
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
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


def sembrar() -> None:
    ejercicio = datetime.now().astimezone().year
    with SessionLocal() as s, s.begin():
        if s.execute(select(TipoIVA.id).limit(1)).first():
            print("Ya hay datos; no se siembra de nuevo.")
            return

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

    print(f"Datos de ejemplo sembrados (ejercicio {ejercicio}).")


if __name__ == "__main__":
    sembrar()
