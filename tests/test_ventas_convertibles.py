"""Fase 1 (convertir-en-factura-f3): elegibilidad de simplificadas convertibles.

`RepositorioVentas.convertibles()` MUST devolver solo T cobradas que aun no
hayan sido sustituidas por una F3 (spec conversion-factura-f3, Requirement
"Elegibilidad de simplificadas convertibles")."""
from __future__ import annotations

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import Venta, VentaSustitucion
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL


def test_convertibles_excluye_no_cobradas_o_ya_sustituidas(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    with crear_sesion() as s, s.begin():
        # T1: cobrada, elegible.
        t1 = construir_venta(usuario_id, [("Neon", "2.50", "2", "21")])
        s.add(t1)
        motor.emit(s, t1, serie="T", ejercicio=ejercicio, tipo_factura="F2")
        t1_id = t1.id

        # T2: cobrada, pero ya convertida en una F3 (sustituida).
        t2 = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
        s.add(t2)
        motor.emit(s, t2, serie="T", ejercicio=ejercicio, tipo_factura="F2")
        t2_id = t2.id
        f3 = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
        s.add(f3)
        motor.emit(s, f3, serie="F", ejercicio=ejercicio, tipo_factura="F3")
        s.add(VentaSustitucion(venta_sustituta_id=f3.id, venta_sustituida_id=t2_id))
        s.get(Venta, t2_id).estado = "sustituida"

        # T3: aparcada, nunca emitida.
        t3 = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
        s.add(t3)

    with crear_sesion() as s:
        convertibles = UnidadDeTrabajoSQL(s).ventas.convertibles()
        assert [v.id for v in convertibles] == [t1_id]
