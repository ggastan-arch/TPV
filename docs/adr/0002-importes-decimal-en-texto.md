# ADR-0002: Importes como `Decimal` almacenados en TEXT

- Estado: Aceptado
- Fecha: 2026-07-09

## Contexto

`CLAUDE.md` exige `Decimal`, jamás `float`, para importes (los descuadres de céntimos son
el bug clásico de TPV y, en un SIF, un problema de conformidad). SQLite no tiene tipo
`Decimal` nativo y degrada `NUMERIC`/`REAL` a coma flotante binaria.

## Decisión

Almacenar los importes como **TEXT** (cadena canónica, p. ej. `"12.34"`) mediante un
`TypeDecorator` propio (`DecimalTexto`) que devuelve siempre `Decimal` cuantizado. En el
frontend del TPV el dinero **se calcula en el servidor**; el JS solo muestra cadenas.

## Consecuencias

- (+) Exactitud garantizada de extremo a extremo; valores legibles en la BD.
- (+) Coherente con el formato de importes de la Orden (punto decimal, 2 decimales).
- (−) Comparaciones/ordenación numérica en SQL requieren cuidado (no se ordenan importes
  como número en la BD; no es necesario en este dominio).
- Alternativa descartada: enteros de céntimos (menos legible, fricción con bases derivadas).
