# ADR-0007: Huella conforme a la Orden art. 13, verificada con vectores oficiales

- Estado: Aceptado
- Fecha: 2026-07-09

## Contexto

La huella SHA-256 encadenada es el núcleo de la inalterabilidad. Su formato exacto lo fija
el documento de sede de la AEAT; programarlo "de memoria" es inaceptable en un SIF.

## Decisión

Componer la cadena de entrada según el subconjunto y orden **verificados** en el documento
oficial (`docs/Verifactu/Veri-Factu_especificaciones_huella_hash_registros.pdf`, v0.1.2):
`campo=valor&...`, valores con espacios de inicio/fin recortados, huella anterior vacía en
el primer registro, SHA-256 en hex MAYÚSCULAS (64 chars), UTF-8. Los nombres de campo del
registro de **anulación** llevan sufijo `Anulada` (`IDEmisorFacturaAnulada`, …).

Se prueban los **tres vectores oficiales** del documento (`tests/test_huella_vectores.py`).

## Consecuencias

- (+) Conformidad demostrada contra la fuente, no contra la memoria.
- (+) Se detectó y corrigió un error propio: los nombres de campo de la anulación.
- Fechas de factura en `dd-mm-aaaa` (formato fiscal), almacenadas así para que XML y huella
  usen la misma representación.
