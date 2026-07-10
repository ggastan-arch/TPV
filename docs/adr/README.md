# Registro de Decisiones de Arquitectura (ADR)

Cada ADR documenta una decisión relevante: contexto, qué se decidió y consecuencias.
Formato ligero (Michael Nygard). Un ADR no se edita una vez aceptado; si se cambia, se
crea uno nuevo que lo **supersede**.

## Índice

| # | Decisión | Estado |
|---|---|---|
| [0001](0001-arquitectura-hexagonal-pragmatica.md) | Arquitectura hexagonal pragmática | Aceptado |
| [0002](0002-importes-decimal-en-texto.md) | Importes como `Decimal` almacenados en TEXT | Aceptado |
| [0003](0003-inmutabilidad-en-base-de-datos.md) | Inmutabilidad de ventas/registros con triggers | Aceptado |
| [0004](0004-numeracion-correlativa-sin-huecos.md) | Numeración correlativa sin huecos (BEGIN IMMEDIATE) | Aceptado |
| [0005](0005-funcion-unica-de-redondeo.md) | Función única de redondeo (base half-up, cuota residuo) | Aceptado |
| [0006](0006-motor-fiscal-intercambiable.md) | Motor fiscal intercambiable (`FiscalEngine`) | Aceptado |
| [0007](0007-huella-conforme-orden-art13.md) | Huella conforme a la Orden art. 13 (vectores oficiales) | Aceptado |
| [0008](0008-modalidad-verifactu.md) | Modalidad VERI\*FACTU y ticket = factura simplificada | Aceptado |

## Plantilla

```markdown
# ADR-NNNN: Título

- Estado: Propuesto | Aceptado | Superseded por ADR-XXXX
- Fecha: aaaa-mm-dd

## Contexto
Qué problema/fuerzas motivan la decisión.

## Decisión
Qué se decide.

## Consecuencias
Positivas, negativas y alternativas descartadas.
```
