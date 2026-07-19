# Proposal: Aparcar / Desaparcar tickets

## Intent

En mostrador hace falta dejar un ticket a medias y retomarlo luego. Hoy el carrito
vive solo en memoria del navegador y se pierde al recargar; los botones "Aparcar
ticket"/"Desaparcar" del pie existen pero están deshabilitados. Queremos guardar el
carrito como borrador NO emitido y recuperarlo después.

## Frontera fiscal (rectora)

Aparcar toca SOLO `Venta(estado='aparcada')` + sus `VentaLinea`/`Pago`. NUNCA `serie`,
`ejercicio`, `numero`, `num_serie_factura`, `fecha_hora_huso`, `registro_fiscal`, huella,
`ContadorSerie` ni `motor.emit`. `EmitirVenta` sigue siendo el único punto que asigna
identidad fiscal. Las filas `aparcada` son mutables/borrables por diseño (ADR-0003):
borrador pre-emisión, no dato fiscal. Invariantes 1-7 intactos.

## Scope

### In Scope
- **Aparcar**: caso `AparcarVenta` (uow, sin `motor.emit`) persiste el carrito como `Venta(estado='aparcada')`+líneas; endpoint `/tpv/api/*`; vacía el carrito.
- **Listar**: `RepositorioVentas.listar_por_estado` + caso + endpoint; overlay con total, nº líneas y etiqueta/hora (ver preguntas).
- **Desaparcar**: caso que recarga las líneas al carrito; endpoint; cablear botones del pie + `ejecutarFuncion`.
- **Cobro de recuperado** (asunción): el borrador se elimina y se emite venta NUEVA por el camino INTACTO `EmitirVenta`/`/tpv/api/cobrar`.
- **Nomenclatura**: aparcar/desaparcar en UI y endpoints; reconciliar `FUNCIONES` (hoy `recuperar`) — detalle de diseño.

### Out of Scope
- Convertir en factura F3 y buscar/asignar cliente (aparte). Aparcar captura SOLO items (sin `cliente_id`).
- Cambios en `EmitirVenta`, motor fiscal, numeración, registro, huella o triggers.

## Capabilities

### New Capabilities
- `aparcar-ticket`: persistir/listar/recuperar borradores `estado='aparcada'` sin identidad fiscal.

### Modified Capabilities
- None (aditivo; el cobro/emisión de `tpv-venta` no cambia de requisito).

## Approach

Reutilizar el estado `aparcada` (ya en modelo/triggers/tests, hoy dormido). Casos de uso
finos sin `MotorFiscal`; endpoints finos en `tpv.py`; listado nuevo en repo. Estrategia
"delete-and-emit-fresh": recuperar consume el borrador y cobrar emite venta nueva por el
camino intacto. Alternativa rechazada (a diseño): mutar `EmitirVenta` para actualizar el
borrador in situ.

## Affected Areas

| Area | Impact |
|------|--------|
| `app/aplicacion/aparcar_venta.py` | New |
| `app/dominio/puertos.py` | Modified — `listar_por_estado` |
| `app/infraestructura/persistencia/repositorios.py` | Modified |
| `app/presentacion/tpv.py` | Modified — endpoints |
| `app/ui/tpv.html` | Modified — botones + overlay |
| `app/dominio/servicios/botonera.py` | Modified — `recuperar`→`desaparcar` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Aparcar toque identidad fiscal | Low | Sin `motor.emit`; triggers eximen aparcada |
| Cobrar dos veces un borrador | Med | Se consume al recuperar |
| Migración por timestamp | Med | Diseño decide `aparcada_en` |

## Rollback Plan

Quitar los casos de uso, endpoints y cableado UI; los botones vuelven a `disabled`. Sin
migración salvo columna nueva. `aparcada` vuelve a estar dormido; producción intacta.

## Success Criteria

- [ ] Aparcar guarda `Venta(estado='aparcada')`+líneas sin identidad fiscal y vacía el carrito.
- [ ] El TPV lista y recupera borradores al carrito.
- [ ] Cobrar un recuperado emite por el camino intacto y consume el borrador.
- [ ] Test de frontera: ningún borrador crea serie/numero/registro/huella.

## Preguntas abiertas

1. ¿Etiqueta opcional al aparcar (cliente/"mostrador 2")? (rec: texto libre opcional.)
2. ¿Hora de aparcado? Puede requerir columna nullable `aparcada_en` (migración). (rec: diseño decide.)
3. ¿Recuperar abierto a cualquiera (kiosco) o restringido al cajero? (rec: kiosco, PIN único.)
4. ¿Tope de borradores simultáneos? (rec: sin tope inicial.)
