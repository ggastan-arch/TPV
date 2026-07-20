"""Preparacion de go-live: fija el secreto de sesion y resetea el PIN del admin.

Ejecutar en la maquina de la tienda (perfil produccion), con el servidor detenido:

    .venv/Scripts/python scripts/preparar_produccion.py           # ambas cosas
    .venv/Scripts/python scripts/preparar_produccion.py --solo-secret
    .venv/Scripts/python scripts/preparar_produccion.py --solo-pin
    .venv/Scripts/python scripts/preparar_produccion.py --rotar    # renueva el secreto

Qué hace:
- TPV_SESSION_SECRET: lo agrega al .env si falta o si sigue en su valor por
  defecto (con `--rotar` lo renueva aunque ya sea fuerte, invalidando las sesiones
  de admin abiertas). NUNCA imprime el valor y no toca el resto de variables.
- PIN del admin: lo pide con getpass (no se muestra ni queda en el historial) y lo
  cambia via `ServicioUsuarios.cambiar_pin`, que valida la longitud minima del rol
  (administracion >= 8) y registra el cambio en el log de auditoria.

No imprime secretos ni la contraseña.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
if str(_RAIZ) not in sys.path:  # permitir ejecutar como script suelto (python scripts/...)
    sys.path.insert(0, str(_RAIZ))

from app.infraestructura.config import SESSION_SECRET_DEFAULT  # noqa: E402

_ENV = _RAIZ / ".env"
_CLAVE = "TPV_SESSION_SECRET"


def _valor_actual_secret(lineas: list[str]) -> str | None:
    """Valor actual de TPV_SESSION_SECRET en las lineas del .env, o None si no esta."""
    for linea in lineas:
        if linea.startswith(f"{_CLAVE}="):
            return linea.split("=", 1)[1].strip()
    return None


def _plan_secret(lineas: list[str], nuevo_valor: str, *, rotar: bool) -> tuple[list[str], str]:
    """Decide como quedan las lineas del .env y que accion se tomo.

    accion in {'sin-cambios', 'agregado', 'reemplazado', 'rotado'}. Solo se toca la
    linea de TPV_SESSION_SECRET; el resto del .env queda intacto. Un secreto fuerte
    ya presente NO se pisa salvo `rotar=True`."""
    actual = _valor_actual_secret(lineas)
    es_fuerte = actual not in (None, "", SESSION_SECRET_DEFAULT)
    if es_fuerte and not rotar:
        return lineas, "sin-cambios"
    linea_nueva = f"{_CLAVE}={nuevo_valor}"
    if actual is None:
        return [*lineas, linea_nueva], "agregado"
    resultantes = [linea_nueva if ln.startswith(f"{_CLAVE}=") else ln for ln in lineas]
    return resultantes, ("rotado" if es_fuerte else "reemplazado")


def preparar_session_secret(*, rotar: bool) -> None:
    lineas = _ENV.read_text(encoding="utf-8").splitlines() if _ENV.exists() else []
    resultantes, accion = _plan_secret(lineas, secrets.token_urlsafe(48), rotar=rotar)
    if accion == "sin-cambios":
        print(f"[session_secret] Ya configurado (no es el valor por defecto). Sin cambios. "
              f"Usá --rotar para renovarlo.")
        return
    _ENV.write_text("\n".join(resultantes) + "\n", encoding="utf-8")
    print(f"[session_secret] {accion.capitalize()} en {_ENV} (valor no mostrado).")


def resetear_pin_admin() -> None:
    from getpass import getpass

    from sqlalchemy import select

    from app.aplicacion.usuarios import PinInvalido, ServicioUsuarios
    from app.infraestructura.config import settings
    from app.infraestructura.db import SessionLocal
    from app.infraestructura.persistencia.modelos import Usuario
    from app.infraestructura.persistencia.unidad_de_trabajo import UnidadDeTrabajoSQL

    if settings.perfil != "produccion":
        print(f"[pin_admin] Perfil actual: {settings.perfil}. Este script es para produccion. Omitido.")
        return

    sesion = SessionLocal()
    try:
        admins = sesion.execute(
            select(Usuario)
            .where(Usuario.rol == "administracion", Usuario.activo.is_(True))
            .order_by(Usuario.id)
        ).scalars().all()
        if not admins:
            print("[pin_admin] No hay administrador activo en la BD. Omitido.")
            return
        if len(admins) == 1:
            admin = admins[0]
        else:
            print("[pin_admin] Hay varios administradores activos:")
            for a in admins:
                print(f"    {a.id}: {a.nombre}")
            objetivo = input("Nombre del admin a modificar: ").strip()
            admin = next((a for a in admins if a.nombre == objetivo), None)
            if admin is None:
                print("[pin_admin] Nombre no encontrado. Omitido.")
                return

        print(f"[pin_admin] Cambiando el PIN de: {admin.nombre} (id {admin.id}).")
        nuevo = getpass("Nuevo PIN (>= 8 caracteres): ")
        if nuevo != getpass("Repetir PIN: "):
            print("[pin_admin] Los PIN no coinciden. Cancelado.")
            return
        uow = UnidadDeTrabajoSQL(sesion)
        try:
            ServicioUsuarios(uow, usuario_id=admin.id, origen="local").cambiar_pin(admin.id, nuevo)
        except PinInvalido as exc:
            print(f"[pin_admin] {exc}. Cancelado.")
            return
        print(f"[pin_admin] PIN actualizado para {admin.nombre}.")
    finally:
        sesion.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preparacion de go-live: secreto de sesion + PIN del admin.")
    parser.add_argument("--rotar", action="store_true",
                        help="Renovar TPV_SESSION_SECRET aunque ya sea fuerte (invalida sesiones abiertas).")
    parser.add_argument("--solo-secret", action="store_true", help="Solo fijar el secreto de sesion.")
    parser.add_argument("--solo-pin", action="store_true", help="Solo resetear el PIN del admin.")
    args = parser.parse_args(argv)

    if not args.solo_pin:
        preparar_session_secret(rotar=args.rotar)
    if not args.solo_secret:
        resetear_pin_admin()


if __name__ == "__main__":
    main()
