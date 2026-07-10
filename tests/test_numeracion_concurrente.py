"""(b) Dos (o mas) emisiones concurrentes no producen huecos ni duplicados."""
from __future__ import annotations

import threading
from decimal import Decimal

from _helpers import construir_venta
from app.models import ContadorSerie, RegistroFiscal, Venta

N_HILOS = 20


def test_emisiones_concurrentes_sin_huecos_ni_duplicados(crear_sesion, motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ejercicio = datos_base["ejercicio"]

    barrera = threading.Barrier(N_HILOS)
    numeros: list[int] = []
    errores: list[Exception] = []
    lock = threading.Lock()

    def trabajo():
        try:
            barrera.wait()  # maximizar la contienda: todos arrancan a la vez
            with crear_sesion() as s, s.begin():
                venta = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
                s.add(venta)
                motor.emit(s, venta, ejercicio=ejercicio)
                numero = venta.numero
            with lock:
                numeros.append(numero)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errores.append(exc)

    hilos = [threading.Thread(target=trabajo) for _ in range(N_HILOS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f"Errores en emision concurrente: {errores}"
    # Correlativos, sin huecos y sin duplicados: exactamente {1..N}.
    assert sorted(numeros) == list(range(1, N_HILOS + 1))
    assert len(set(numeros)) == N_HILOS

    with crear_sesion() as s:
        contador = s.get(ContadorSerie, ("T", ejercicio))
        assert contador.ultimo_numero == N_HILOS
        assert s.query(Venta).count() == N_HILOS
        # Un registro fiscal por venta, con ordenes correlativos 1..N.
        ordenes = sorted(r.orden for r in s.query(RegistroFiscal).all())
        assert ordenes == list(range(1, N_HILOS + 1))
