"""Numeracion del Cierre Z bajo concurrencia: sin huecos, sin duplicados, sin solapes.

Mismo mecanismo que la numeracion de ventas (BEGIN IMMEDIATE + secuencia derivada,
ADR-0004): dos cierres concurrentes se serializan en el candado de escritura, de modo
que los numeros Z salen correlativos y los rangos [desde_orden, hasta_orden] contiguos."""
from __future__ import annotations

import threading

from _helpers import construir_venta
from app.aplicacion.generar_cierre_z import GenerarCierreZ
from app.infraestructura.persistencia.modelos import CierreZ
from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

N_HILOS = 10
N_VENTAS = 3


def test_cierres_z_concurrentes_sin_huecos_ni_duplicados(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    # Emitir algunas ventas para que el primer Z tenga contenido real.
    with crear_sesion() as s, s.begin():
        for _ in range(N_VENTAS):
            venta = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
            s.add(venta)
            motor.emit(s, venta, ejercicio=ejercicio)

    barrera = threading.Barrier(N_HILOS)
    numeros: list[int] = []
    errores: list[Exception] = []
    lock = threading.Lock()

    def trabajo():
        try:
            barrera.wait()  # todos arrancan a la vez -> maxima contienda
            with crear_sesion() as s:
                resultado = GenerarCierreZ(UnidadDeTrabajoSQL(s)).ejecutar(
                    usuario_id=usuario_id, origen="local")
            with lock:
                numeros.append(resultado.numero)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errores.append(exc)

    hilos = [threading.Thread(target=trabajo) for _ in range(N_HILOS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f"Errores en cierre Z concurrente: {errores}"
    # Correlativos, sin huecos ni duplicados: exactamente {1..N}.
    assert sorted(numeros) == list(range(1, N_HILOS + 1))
    assert len(set(numeros)) == N_HILOS

    with crear_sesion() as s:
        cierres = list(s.query(CierreZ).order_by(CierreZ.numero).all())
        assert [c.numero for c in cierres] == list(range(1, N_HILOS + 1))
        # Rangos contiguos: cada Z arranca donde termino el anterior, sin hueco ni solape.
        for anterior, siguiente in zip(cierres, cierres[1:]):
            assert siguiente.desde_orden == anterior.hasta_orden + 1
        # Todas las ventas emitidas quedan contabilizadas exactamente una vez.
        assert sum(c.num_tickets for c in cierres) == N_VENTAS
