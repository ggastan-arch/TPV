# ADR-0005: Función única de redondeo (base half-up, cuota como residuo)

- Estado: Aceptado
- Fecha: 2026-07-09

## Contexto

El TPV vende a PVP con IVA incluido; hay que derivar base y cuota por tipo impositivo y
que **cuadre** con el total, sin descuadres de céntimos. `CLAUDE.md` exige una única
función de redondeo (por línea, half-up, 2 decimales) con tests exhaustivos.

## Decisión

Por línea: `base = redondeo_half_up(total / (1 + tipo))` y `cuota = total - base`
(residuo). Así `base + cuota == total` es exacto por construcción en cada línea; al
agrupar por tipo, `Σ bases + Σ cuotas == importe_total`. Toda la aritmética en `Decimal`.
Implementación en un único módulo (`redondeo`), reutilizado por el cálculo del ticket, el
desglose fiscal y el formateo del XML/huella.

## Consecuencias

- (+) Cuadre garantizado; probado con tickets multi-tipo (21% + 10%).
- (+) Coherente con la tolerancia de ±10 € que valida la AEAT (nunca se necesita).
- Alternativa descartada: redondear base y cuota por separado (puede no sumar el total).
