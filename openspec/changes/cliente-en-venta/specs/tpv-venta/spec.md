# Delta for tpv-venta

## ADDED Requirements

### Requirement: Cliente opcional asociado a la venta al cobrar

El sistema MUST admitir un `cliente_id` opcional (`int | None`) en
`EmitirVenta.ejecutar` y en `CobrarReq`; cuando se indica, MUST persistir ese
`cliente_id` en `Venta` al emitir. Cuando está ausente, el sistema MUST
comportarse exactamente igual que antes de este cambio (no-regresión).

#### Scenario: Cobro con cliente asignado
- GIVEN una venta en curso con un cliente ya asignado
- WHEN se cobra
- THEN `Venta.cliente_id` persiste con el id de ese cliente

#### Scenario: Cobro sin cliente asignado (no-regresión)
- GIVEN una venta en curso sin cliente asignado
- WHEN se cobra
- THEN `Venta.cliente_id` es `None`; el resto del flujo de emisión no cambia

#### Scenario: Llamadas existentes sin `cliente_id` siguen funcionando
- GIVEN una llamada a `EmitirVenta.ejecutar(usuario_id=, items=, pagos=)` sin
  `cliente_id`
- WHEN se ejecuta
- THEN emite correctamente, igual que antes de este cambio

### Requirement: Impresión de ticket cualificado con NIF, domicilio y cuota separada

El sistema MUST imprimir, solo cuando la venta es simplificada cualificada, el
NIF y el domicilio del cliente destinatario y la cuota de IVA separada por tipo.
Una venta NO cualificada MUST imprimirse exactamente igual que hoy.

#### Scenario: Ticket cualificado incluye NIF, domicilio y cuota separada
- GIVEN una venta cualificada con cliente NIF+domicilio completos
- WHEN se imprime el ticket
- THEN incluye el NIF, el domicilio del destinatario y la cuota desglosada por
  tipo

#### Scenario: Ticket no cualificado sin cambios
- GIVEN una venta no cualificada
- WHEN se imprime el ticket
- THEN el contenido es idéntico al de antes de este cambio

**Tests**: `tests/test_emitir_venta.py::test_emitir_venta_persiste_cliente_id_opcional`
(NUEVO), `::test_emitir_venta_sin_cliente_id_no_regresion` (NUEVO);
`tests/test_tpv_api.py::test_cobrar_con_cliente_asignado` (NUEVO);
`tests/test_ticket.py::test_ticket_cualificado_incluye_nif_domicilio_cuota_separada`
(NUEVO), `::test_ticket_no_cualificado_sin_cambios` (NUEVO)
