# Delta for Cierre Z

## MODIFIED Requirements

### Requirement: Cuadre de totales y desgloses

El sistema MUST calcular nº de tickets, base total, cuota total, total y
desglose por tipo de IVA y por medio de pago exclusivamente a partir de las
ventas cuyo registro de alta tenga `orden` en `[desde_orden, hasta_orden]` Y
cuyo `estado` sea `cobrada` **o** `sustituida`, EXCLUYENDO toda venta que sea
la factura F3 sustituta de una conversión (`Venta.id` presente como
`venta_sustituta_id` en `venta_sustitucion`), en el momento de la generación.
Base + cuota MUST igualar el total (ADR-0005).

(Previously: solo incluía `estado == 'cobrada'`; una conversión F3 dejaba el
`desglose_pago` corto por el importe del origen convertido en todo Z cuyo
rango incluyera el alta de la F3, porque la simplificada origen pasaba a
`sustituida` — fuera del filtro — y la F3 no genera filas `Pago` propias.)

(Nota: la corrección depende de la inmutabilidad de la simplificada origen —
al pasar a `sustituida` solo cambia `Venta.estado`; `base_total`,
`cuota_total`, `total_con_iva` y sus filas `Pago` permanecen congelados. Por
eso incluir `sustituida` en el cómputo sigue sumando el efectivo REAL, no un
valor mutado.)

#### Scenario: Los totales cuadran con las ventas del rango

- GIVEN ventas cobradas cuyos registros de alta tienen orden dentro del rango,
  con pagos en efectivo y tarjeta y dos tipos de IVA distintos
- WHEN se genera el Cierre Z
- THEN `base_total + cuota_total == total_con_iva`, y la suma del desglose por
  IVA y por medio de pago coincide exactamente con esos totales

#### Scenario: Una anulación posterior no reabre un Z ya cerrado

- GIVEN una venta del rango de un Cierre Z ya cerrado pasa a estado
  `anulada_con_rastro` después del cierre
- WHEN se consulta ese Cierre Z
- THEN sus totales permanecen sin cambios; el efecto de la anulación se refleja
  únicamente en el Cierre Z del rango donde caiga el `orden` del documento
  generado por la anulación

#### Scenario: Conversión F3 del mismo periodo no rompe el cuadre

- GIVEN una simplificada T se cobra y, dentro del mismo rango de `orden` aún
  no cerrado, se convierte en una F3 (la T pasa a `sustituida`; la F3 queda
  `cobrada` sin filas `Pago` propias)
- WHEN se genera el Cierre Z cuyo rango incluye tanto el alta de la T como el
  alta de la F3
- THEN el efectivo real de la T se cuenta exactamente una vez en
  `desglose_pago`, la F3 no aporta importe a ningún total ni desglose, y
  `base_total + cuota_total == total_con_iva`

#### Scenario: Conversión F3 cross-period no duplica el efectivo

- GIVEN una simplificada T fue cobrada y quedó incluida en un Cierre Z ya
  cerrado en un periodo anterior; más tarde se convierte en una F3 cuyo alta
  cae en el rango de un Cierre Z posterior
- WHEN se genera ese Cierre Z posterior
- THEN la F3 queda excluida de sus totales y desgloses — el importe de la T ya
  fue contado, congelado, en el Z anterior — y ningún Z cuenta ese efectivo
  dos veces

#### Scenario: `num_tickets` refleja ventas reales, no facturas en papel

- GIVEN el rango de un Cierre Z incluye el alta de una T convertida en F3 y el
  alta de esa F3
- WHEN se genera el Cierre Z
- THEN `num_tickets` cuenta la T (venta real cobrada) y no suma la F3 como un
  ticket adicional
