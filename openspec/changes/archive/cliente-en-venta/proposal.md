# Proposal: Cliente en venta + simplificada cualificada (art. 7.2/7.3 ROF)

## Intent

Hoy el TPV no puede asignar un cliente a la venta ni expedir una **factura
simplificada cualificada** (art. 7.2/7.3 ROF): cuando el comprador pide NIF +
domicilio + cuota separada en el ticket, la única vía sería forzar factura completa
(F3 "Convertir en factura"), un flujo pesado e innecesario para el importe habitual de
la tienda. El botón "Cliente en venta" existe pero está `disabled`
(`app/ui/tpv.html:204-207`). Éxito = desde la pantalla táctil se busca/asigna/crea un
cliente y, opcionalmente, se marca la venta como cualificada; el ticket muestra
NIF+domicilio+cuota separada y el `RegistroAlta` lleva `FacturaSimplificadaArt7273=S`,
**sin dejar de ser F2** y sin tocar numeración, cadena ni triggers.

## Frontera fiscal (RECTORA — leer primero)

- **Verificado en el XSD oficial** (no se inventa el campo, per CLAUDE.md): el elemento
  `FacturaSimplificadaArt7273`, tipo `sf:SimplificadaCualificadaType` (`simpleType`
  restricción de `string`, enumeración **`S`/`N`**, NO booleano), `minOccurs="0"`,
  existe en `schemas/SuministroInformacion.xsd.xml:144` (secuencia de RegistroAlta,
  entre `DescripcionOperacion` y `FacturaSinIdentifDestinatarioArt61d`; definición del
  tipo en `:826-831`) y en `schemas/RespuestaConsultaLR.xsd.xml:124`. Al ser opcional,
  una simplificada NO cualificada se emite **byte-idéntica** (elemento omitido).
- Una cualificada **permanece TipoFactura=F2** y **NUNCA** lleva bloque `Destinatarios`
  (F1/F3 only, `schemas/...:153`). La regla ya está codificada como rechazo
  `DESTINATARIO_NO_PERMITIDO` en `validaciones_negocio.py:40-41,127-129`. El bloque
  `Destinatarios` es el cambio F3 aparcado, fuera de este alcance.
- **Huella**: `huella.py:42-63` hashea un subconjunto fijo (NIF emisor, num/serie, fecha
  exp, tipo factura, cuota total, importe total, huella anterior, fecha-hora-huso). El
  flag NO figura en él → cambio aditivo fuera de la huella. **Verificar en design.**
- `Venta.cliente_id` es FK nullable YA congelada en `_VENTA_CAMPOS_CONGELADOS`
  (`ddl.py:28`) → asignarla es aditivo, sin migración ni cambio de trigger.
- **Invariantes 1-7 intactos.** RGPD: capturar consentimiento en el alta inline.

## Scope

### In Scope — (A) fontanería cliente↔venta (bajo riesgo, aditivo)
- `RepositorioClientes.buscar_por_nombre` / `buscar_por_nif` + métodos de servicio
  (patrón existente en Artículo, `repositorios.py:55-90`).
- Endpoints `/tpv/api/*` **PIN-gated**: buscar clientes, crear cliente inline
  (NIF+nombre+domicilio+consentimiento RGPD) y asignar cliente a la venta actual.
- Enhebrar `cliente_id: int | None = None` **opcional** por `EmitirVenta.ejecutar`
  (`emitir_venta.py:48-62`) y `CobrarReq` (`tpv.py:85-89`) → fija `Venta.cliente_id` al
  emitir. No cambia nada cuando va ausente; los 8 call-sites de test son kwargs/JSON.
- UI TPV: cablear el botón "Cliente en venta" → panel buscar/asignar/crear inline.

### In Scope — (B) cualificada fiscal (crítico)
- Columna nueva nullable para `FacturaSimplificadaArt7273` en `venta`, con
  `op.add_column` **NATIVO** (como `etiqueta_aparcada`; NUNCA batch). Formato `S`/`N`
  según XSD.
- Elemento XML condicional en `registro_alta_xml` solo si cualificada; simplificada
  normal emite idéntica. Confirmar que NO entra en la huella.
- Ticket (`ticket.py`): NIF + domicilio del destinatario + cuota separada, solo en
  cualificadas.
- Regla de negocio: una venta es cualificada por **acción explícita** que EXIGE cliente
  asignado con NIF **y** domicilio (bloquea si falta alguno). No se auto-marca por el
  mero hecho de asignar cliente.

### Out of Scope / Non-Goals
- Bloque `Destinatarios` F1/F3 (cambio F3 aparcado; prohibido en F2).
- "Convertir en factura" F3.
- Que asignar cliente a una venta NO cualificada tenga efecto fiscal alguno (es solo
  CRM/registro; únicamente la cualificada altera el `RegistroAlta`).

## Capabilities

### New Capabilities
- `cliente-en-venta`: buscar/asignar/crear-inline cliente desde el TPV y marcar la
  venta como simplificada cualificada (art. 7.2/7.3) con sus reglas de bloqueo.

### Modified Capabilities
- `motor-fiscal-verifactu`: nuevo elemento condicional `FacturaSimplificadaArt7273=S`
  en `RegistroAlta` (fuera de huella; F2 sin `Destinatarios`).
- `tpv-venta`: `cliente_id` opcional en el cobro; acción "cualificada" con precondición
  NIF+domicilio.

## Approach

Dos incrementos independientemente entregables: (A) fontanería aditiva sin impacto
fiscal, (B) el flag cualificada fiscal-crítico. Reutilizar el patrón de búsqueda de
Artículo para Cliente; endpoints propios PIN-gated (el CRUD admin es cookie/rol y no es
alcanzable desde el kiosco). El flag se persiste en `venta`, se serializa condicional en
el XML y se imprime en el ticket; la simplificada normal queda inalterada.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `app/dominio/puertos.py` | Modified | Puerto `buscar_por_nombre`/`buscar_por_nif` |
| `app/infraestructura/persistencia/repositorios.py` | Modified | Impl. de búsqueda de clientes |
| `app/aplicacion/clientes.py` | Modified | Métodos de servicio de búsqueda |
| `app/aplicacion/emitir_venta.py` | Modified | `cliente_id` opcional → `Venta.cliente_id` |
| `app/presentacion/tpv.py` | Modified | `CobrarReq.cliente_id` + endpoints `/tpv/api/*` |
| `app/infraestructura/persistencia/modelos/venta.py` | Modified | Columna `FacturaSimplificadaArt7273` |
| `migrations/` | New | `add_column` nativo del flag |
| `app/infraestructura/fiscal/xml.py` | Modified | Elemento condicional en `registro_alta_xml` |
| `app/infraestructura/impresion/ticket.py` | Modified | NIF+domicilio+cuota separada (cualificada) |
| `app/ui/tpv.html` | Modified | Cablear botón + panel cliente |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|------------|
| Nombre/posición/formato del campo XSD incorrecto | Baja | Verificado en `schemas/`: `S`/`N`, `minOccurs=0`; validar XML contra XSD en design |
| El flag alterase la huella | Baja | `huella.py:42-63` no lo incluye; test de invariancia de huella |
| Construir `Destinatarios` en F2 (rechazo AEAT) | Baja | Prohibido explícito; `validaciones_negocio` ya rechaza |
| Simplificada normal cambie su XML | Baja | Elemento condicional; test byte-idéntico |
| Cualificada sin NIF/domicilio | Media | Bloqueo en la acción explícita, no auto-marcado |
| RGPD sin consentimiento en alta inline | Media | Capturar `rgpd_consentimiento` en creación TPV |

## Rollback Plan

(A) es aditivo: revertir métodos/endpoints/UI y el `cliente_id` opcional deja el cobro
como hoy. (B): al ser el flag `minOccurs=0` y condicional, retirar la rama de emisión
restaura XML byte-idéntico; la columna nullable puede quedar sin uso o revertirse con
migración `down`. Sin impacto en numeración, cadena ni triggers.

## Dependencies

- XSD oficiales en `schemas/` (ya presentes; campo verificado).
- Patrón de búsqueda de Artículo (`repositorios.py:55-90`) como referencia.

## Success Criteria

- [ ] Desde el TPV se busca/asigna/crea (inline, con RGPD) un cliente en la venta.
- [ ] Marcar cualificada exige NIF+domicilio; bloquea si faltan.
- [ ] Cualificada emite `FacturaSimplificadaArt7273=S` (F2, sin `Destinatarios`),
      validado contra el XSD, y NO altera la huella.
- [ ] Simplificada normal emite XML byte-idéntico al actual.
- [ ] Ticket cualificado imprime NIF+domicilio+cuota separada.
- [ ] Invariantes 1-7 intactos; cubierto por tests (TDD estricto).

## Ronda de preguntas de propuesta

No se pudo preguntar en vivo (ejecución sub-agente). Preguntas con default recomendado
para revisión del usuario antes de spec/design:

1. **Cualificada = acción explícita** que exige cliente con NIF+domicilio, bloqueando si
   faltan [REC] — vs. auto-marcar por cualquier asignación de cliente.
2. **RGPD en alta inline desde TPV**: capturar consentimiento reutilizando
   `rgpd_consentimiento` [REC: sí].
3. **Asignar cliente a venta NO cualificada** no tiene efecto fiscal; es solo
   CRM/registro [REC: sí — solo la cualificada altera el `RegistroAlta`].
4. **Entrega**: ¿un cambio o dos slices (A fontanería / B flag fiscal)? [Nota: el
   dimensionamiento lo decide el orquestador; A y B son independientemente entregables].
5. **Cuota separada**: ¿basta el desglose por tipo existente (`ticket.py:100-104`) o se
   requiere una línea nueva específica? [a resolver en design].

**Supuestos asumidos** (corregir si procede): endpoints cliente propios PIN-gated (no se
reutiliza el admin cookie/rol); creación inline permitida para walk-ins; el flag y su
migración van en ESTE cambio (fiscal-crítico, ya con XSD verificado).
