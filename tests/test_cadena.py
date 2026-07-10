"""La cadena de huellas queda lista para fase 2: encadenamiento y verificacion."""
from __future__ import annotations

from _helpers import construir_venta
from app.infraestructura.persistencia.modelos import RegistroFiscal


def _emitir_varias(crear_sesion, motor, usuario_id, n):
    for _ in range(n):
        with crear_sesion() as s, s.begin():
            venta = construir_venta(usuario_id, [("Neon", "2.50", "1", "21")])
            s.add(venta)
            motor.emit(s, venta)  # ejercicio por defecto = ano en curso (igual que el fixture)


def test_encadenamiento_y_verificacion(crear_sesion, motor, datos_base):
    _emitir_varias(crear_sesion, motor, datos_base["usuario_id"], 3)

    with crear_sesion() as s:
        registros = s.query(RegistroFiscal).order_by(RegistroFiscal.orden).all()
        assert [r.orden for r in registros] == [1, 2, 3]
        # El primero abre la cadena; el resto referencia la huella del anterior.
        assert registros[0].primer_registro is True
        assert registros[0].huella_anterior is None
        for anterior, actual in zip(registros, registros[1:]):
            assert actual.primer_registro is False
            assert actual.huella_anterior == anterior.huella
        # Huellas SHA-256 en hex mayusculas de 64 chars.
        for r in registros:
            assert len(r.huella) == 64
            assert r.huella == r.huella.upper()

        informe = motor.verify_chain(s)
        assert informe.ok, informe.errores
        assert informe.registros == 3
