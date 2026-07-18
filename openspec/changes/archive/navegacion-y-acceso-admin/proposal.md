# Proposal: Navegación TPV↔Administración y demo sin fricción (acceso libre + reset)

## Intent

Hoy solo `app/ui/landing.html` (ruta `/`) enlaza TPV y consola: no hay botón para ir
del TPV a Administración ni viceversa. Para la demo del TFM, además, quien evalúa NO
debe toparse con ningún login: entrar a Administración tiene que ser directo, sin PIN.

**Restricción rectora (seguridad por aislamiento):** la demo y producción deben ser
sistemas TOTALMENTE separados. En la demo la seguridad no se da con un gate (login/PIN),
sino con la **desechabilidad**: acceso libre + estado que se resetea. Reutilizamos la
costura ya existente `settings.perfil` (`app/infraestructura/config.py`), la misma que
`modo-demo` usa para aislar BD/emisor/motor. Este cambio añade a esa costura la dimensión
AUTH (acceso libre en demo) y el reset de arranque, sin inventar una costura nueva.

**Frontera INNEGOCIABLE:** el acceso libre y el reset SOLO existen en `perfil=="demo"`,
cableados en el composition-root (nunca un `if demo` en un hot path). En producción, JAMÁS.
El invariante 1 (ninguna venta emitida se borra) PROHÍBE cualquier reset en el SIF real;
por eso vive aislado en la demo. El invariante 5 (nada de "modo formación") y el camino
fiscal (huella/registro/numeración/cadena) quedan intactos.

## Scope

### In Scope
- Botón "Administración" en la cabecera del TPV (`tpv.html`) → `/admin/`; botón "Ir al TPV"
  en la cabecera admin (`admin.html`) → `/tpv/`. Paths separados bajo un mismo dominio.
- **Acceso admin libre en demo:** con `perfil=="demo"`, la consola de administración se
  resuelve autenticada sin login ni PIN (guard de acceso libre cableado en el
  composition-root). `/admin/api/me` responde OK → dashboard directo, sin pantalla de login.
- **Reset de arranque en demo:** al iniciar la app con `perfil=="demo"`, la BD demo parte de
  un estado sembrado limpio (se descartan los cambios acumulados y se re-siembra). Sin botón;
  no ocurre a mitad de una demo, solo al (re)arrancar el proceso.
- Ajustes de UI en `admin.html` para demo: ocultar/repurposar "Salir" (sin sesión que cerrar).

### Out of Scope
- Login estricto de producción (usuario + credencial + sesión reforzada) — cambio futuro.
  El login de producción actual queda INTACTO y sigue siendo obligatorio en `produccion`.
- Login por PIN, PIN de admin nuevo y lockout: descartados (innecesarios con acceso libre).
- Permisos granulares más allá de los dos roles existentes (`venta`/`administracion`).
- Cualquier cambio en motor fiscal, cadena, numeración o aislamiento ya entregado de `modo-demo`.

## Non-Goals
- Que el acceso libre o el reset sean alcanzables en producción.
- Resetear datos durante una demo en curso (solo al (re)arrancar).

## Capabilities

### New Capabilities
- `navegacion-tpv-admin`: navegación bidireccional TPV↔Administración desde la UI.

### Modified Capabilities
- `consola-administracion`: en `perfil=="demo"` el acceso es libre (guard de acceso libre
  cableado en composition-root, sin login/PIN); en `produccion` el login sigue siendo
  obligatorio, sin cambios.
- `modo-demo`: el arranque en demo parte de un estado sembrado limpio (reset), reemplazando
  para ese perfil el seed "idempotente-preserva" por un "wipe + reseed".

## Approach

En `produccion`, el guard `require_admin` (sesión) queda intacto. En `demo`, se cablea en
el composition-root (`app/main.py` / dependencias) una variante de guard que resuelve un
identity de admin demo sin exigir sesión, de modo que producción nunca carga ese código.
El arranque en demo (`app/main.py` + `app/seed.py`) descarta el estado previo de la BD demo
y re-siembra limpio. Los botones se insertan en las cabeceras (`tpv.html` junto a `#usuario`;
`admin.html` junto a `#salir`, ajustando "Salir" para demo).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/presentacion/admin.py` | Modified | Guard de acceso libre para demo (require_admin real en producción) |
| `app/main.py` / cableado | Modified | Cableado condicional del guard según `perfil`; reset de arranque demo |
| `app/seed.py` | Modified | Wipe + reseed limpio del estado demo al arrancar |
| `app/ui/tpv.html` | Modified | Botón "Administración" en cabecera |
| `app/ui/admin.html` | Modified | Botón "Ir al TPV"; sin pantalla de login en demo; "Salir" ajustado |
| `tests/` | New | Cobertura acceso libre demo / login sigue en producción / reset / navegación |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Acceso libre alcanzable en producción | Low | Cableado condicional en composition-root; test que verifica que producción sigue exigiendo login |
| Reset alcanzable en producción (viola inv. 1) | Low | Reset gated por `perfil`; test que verifica que producción no resetea |
| Vandalismo de la demo pública entre reinicios | Med (aceptado) | Desechabilidad: datos demo aislados y sin validez; reset al reiniciar |
| Reinicio a mitad de demo borra el trabajo mostrado | Low | Aceptado: el reset es por diseño solo al (re)arrancar |

## Rollback Plan

Revertir = quitar el cableado del guard de acceso libre, el reset de arranque y los botones
de navegación. No hay migración de esquema ni datos productivos: producción usa el login
existente y queda intacta.

## Dependencies

- Costura `settings.perfil` (`config.py`) y aislamiento `modo-demo` ya entregados.
- `SessionMiddleware`, `require_admin` y el seed demo existentes.

## Success Criteria

- [ ] En demo, abrir `/admin/` entra al dashboard sin login ni PIN.
- [ ] En producción, `/admin/` sigue exigiendo login (comportamiento actual, sin cambios).
- [ ] En demo, (re)arrancar la app deja la BD demo en el estado sembrado limpio.
- [ ] En producción, el arranque NO resetea datos.
- [ ] Botones TPV→admin y admin→TPV navegan correctamente.
- [ ] Todo cubierto por tests nuevos (TDD estricto).
