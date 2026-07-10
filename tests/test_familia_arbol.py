"""(d) El arbol de familias soporta N niveles (parent_id, consulta recursiva)."""
from __future__ import annotations

from sqlalchemy import text

from app.models import Familia

PROFUNDIDAD = 6


def test_arbol_de_familias_n_niveles(crear_sesion):
    with crear_sesion() as s, s.begin():
        parent_id = None
        ids = []
        for nivel in range(PROFUNDIDAD):
            fam = Familia(nombre=f"Nivel {nivel}", parent_id=parent_id, orden=nivel)
            s.add(fam)
            s.flush()
            ids.append(fam.id)
            parent_id = fam.id
        raiz_id = ids[0]
        hoja_id = ids[-1]

    consulta = text(
        """
        WITH RECURSIVE arbol(id, nombre, parent_id, nivel) AS (
            SELECT id, nombre, parent_id, 0 FROM familia WHERE id = :raiz
            UNION ALL
            SELECT f.id, f.nombre, f.parent_id, a.nivel + 1
            FROM familia f JOIN arbol a ON f.parent_id = a.id
        )
        SELECT id, nivel FROM arbol ORDER BY nivel
        """
    )
    with crear_sesion() as s:
        filas = s.execute(consulta, {"raiz": raiz_id}).all()
        # Descendencia desde la raiz: PROFUNDIDAD nodos, niveles 0..PROFUNDIDAD-1.
        assert len(filas) == PROFUNDIDAD
        assert [nivel for _, nivel in filas] == list(range(PROFUNDIDAD))
        assert filas[-1][0] == hoja_id

        # Camino de ancestros de la hoja hasta la raiz.
        ancestros = text(
            """
            WITH RECURSIVE subir(id, parent_id, salto) AS (
                SELECT id, parent_id, 0 FROM familia WHERE id = :hoja
                UNION ALL
                SELECT f.id, f.parent_id, s.salto + 1
                FROM familia f JOIN subir s ON f.id = s.parent_id
            )
            SELECT COUNT(*) FROM subir
            """
        )
        total = s.execute(ancestros, {"hoja": hoja_id}).scalar_one()
        assert total == PROFUNDIDAD
