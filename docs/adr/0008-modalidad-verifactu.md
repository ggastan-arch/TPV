# ADR-0008: Modalidad VERI\*FACTU y ticket = factura simplificada

- Estado: Aceptado
- Fecha: 2026-07-09 (decisión de negocio previa, formalizada aquí)

## Contexto

La persona titular tributa en IRPF por estimación objetiva y en recargo de equivalencia, con
domicilio fiscal en territorio común (AEAT). El ROF la eximiría de expedir factura por las
ventas minoristas, pero se decide lo contrario por control y transparencia.

## Decisión

- **Todos los tickets del TPV son facturas simplificadas** (F2), art. 4 y 7 ROF. El TPV es
  un SIF sujeto al RRSIF.
- Operar en modalidad **VERI\*FACTU** (remisión voluntaria anticipada): se presume
  cumplimiento por diseño, dispensa de conservar copia y **no exige firma electrónica de
  los registros ni registro de eventos** (las piezas más costosas del modo NO VERI\*FACTU).
- "Convertir en factura" = **F3** en sustitución de simplificadas (ADR pendiente si se
  detalla el flujo), no una anulación.

## Consecuencias

- (+) Modelo técnico más simple (sin firma XAdES ni log de eventos formal).
- (−) Requiere conectividad para remitir (mitigado con cola + reintentos).
- (−) Requiere certificado de la persona titular para la remisión real (aún no aportado).
- Límite de la simplificada: 3.000 € IVA incl.; por encima, factura completa (validado).
