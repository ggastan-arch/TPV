# Proposal: Perfil de arranque DEMO aislado

## Intent

Necesitamos mostrar el TPV en la defensa del máster sin exponer datos reales de la
titular (RGPD, identidad fiscal) ni remitir registros a la AEAT (no existe certificado
demo). Hoy no hay forma segura de hacerlo: arrancar el sistema usa `tpv.db`, el emisor
real y la cadena de huellas de producción.

**Restricción de compliance (rectora):** el invariante 5 (RRSIF, RD 1007/2023) PROHÍBE
"modo formación" o cualquier vía que imprima tickets no contabilizados DENTRO del SIF de
producción. Por eso la demo NO puede ser un toggle sobre la misma BD/caja: se diseña como
**perfil de arranque aislado**. Este proposal respeta el invariante 5 porque (a) aísla la
BD y el emisor, (b) fuerza `NullEngine` (no remite), y (c) marca cada documento como
prueba, de modo que jamás se presenta un ticket demo como factura del SIF real.

## Scope

### In Scope
- Ajuste `TPV_PROFILE` (`produccion` | `demo`), **default `produccion`**: la demo se pide a propósito.
- BD demo aislada `tpv_demo.db`; jamás la real `tpv.db`.
- `NullEngine` forzado en demo (genera cadena, no remite), aun cuando exista `VerifactuEngine`.
- Empresa demo: emisor ficticio (NIF de prueba + nombre "Demo"), nunca la titular real.
- Seed demo idempotente (empresa + clientes + artículos), reutilizando `app/seed.py`.
- Marca inequívoca en ticket y consola: "DOCUMENTO DE PRUEBA — SIN VALIDEZ FISCAL", sin QR de cotejo real de la AEAT.
- Salvaguarda de arranque: rechazar si el perfil demo resolviera hacia la BD de producción.

### Out of Scope
- Remisión real a la AEAT (certificado, cola VERI*FACTU).
- Cualquier toggle dentro del sistema de producción.
- Ejecutar en la máquina real de la tienda (la demo va en portátil aparte).

## Non-Goals
- Que el perfil demo emita documentos con validez fiscal.

## Capabilities

### New Capabilities
- `modo-demo`: perfil de arranque aislado (config, BD demo, NullEngine forzado, empresa demo, seed demo, marcado "SIN VALIDEZ FISCAL", salvaguarda de arranque).

### Modified Capabilities
- None (comportamiento aditivo y gated por perfil; no debilita specs ni invariantes existentes).

## Approach

Extender `Settings` con `perfil`; resolver `db_path`/emisor según perfil en el bootstrap;
`get_motor` fuerza `NullEngine` en demo; parametrizar el seed para sembrar empresa demo;
condicionar `imprimir_ticket` y la UI a la marca demo (suprimiendo cotejo real);
validar en `crear_app` que demo nunca apunte a `tpv.db`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/infraestructura/config.py` | Modified | Campo `perfil` + resolución db/emisor demo |
| `app/infraestructura/db.py` | Modified | Engine ligado a la BD del perfil |
| `app/presentacion/deps.py` | Modified | `get_motor` fuerza NullEngine en demo |
| `app/seed.py` | Modified | Seed demo (empresa+clientes+artículos) |
| `app/infraestructura/impresion/ticket.py` | Modified | Marca demo, sin QR cotejo real |
| `app/main.py` | Modified | Salvaguarda de arranque del perfil demo |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Confundir demo con producción (compliance) | Med | Aislamiento BD + default producción + marcado + salvaguarda |
| Demo apunte a `tpv.db` | Low | Rechazo de arranque si resuelve a BD real |
| `VerifactuEngine` futuro remita en demo | Low | NullEngine forzado por perfil, no por wiring |

## Rollback Plan

Revertir es quitar el campo `perfil` y las ramas demo; producción es el default y queda
intacta. No hay migración de esquema ni datos productivos afectados.

## Dependencies

- `NullEngine` existente (ya arma cadena sin remitir).

## Success Criteria

- [ ] Arrancar con `TPV_PROFILE=demo` levanta datos demo sobre `tpv_demo.db` con marca visible.
- [ ] Producción (default) intacta: usa `tpv.db`, emisor real, sin marca demo.
- [ ] El arranque demo se rechaza si resolviera hacia `tpv.db`.
- [ ] Cubierto por tests nuevos (TDD estricto).
