# ADR-0001: Arquitectura hexagonal pragmática

- Estado: Aceptado
- Fecha: 2026-07-10

## Contexto

El proyecto empezó como capas pragmáticas (`core`, `models`, `fiscal`, `api`, `printing`)
con la lógica fiscal ya aislada pero con reglas de negocio dentro de los endpoints y
acceso directo al ORM. Se busca trazabilidad, testabilidad y proteger el núcleo fiscal
ante cambios de infraestructura (AEAT, impresora, BD), sin caer en sobre-ingeniería para
un TPV monopuesto.

## Decisión

Adoptar **hexagonal (puertos y adaptadores) en su versión pragmática**: capas
`dominio` (puro) → `aplicacion` (casos de uso) ← `infraestructura` (adaptadores) y
`presentacion` (FastAPI). Dependencias hacia adentro; el dominio no importa framework,
ORM ni clientes externos.

Variante pragmática: **los modelos SQLAlchemy siguen siendo las entidades**, accedidas
tras puertos de repositorio. NO se crean entidades de dominio puras con mapeadores
ORM↔dominio.

## Consecuencias

- (+) Núcleo fiscal (valores + servicios) puro y testeable en aislamiento; adaptadores
  externos (SOAP, ESC/POS, XSD) intercambiables tras puertos.
- (+) Casos de uso testeables sin HTTP; endpoints finos (SRP).
- (−) No es hexagonal "de libro": las entidades tocan el ORM.
- Alternativa descartada: hexagonal dogmático (entidades puras + mapeadores). Se descarta
  por boilerplate desproporcionado a la escala (una tienda, un puesto).
- Migración incremental con los tests en verde (ver `docs/ARCHITECTURE.md` §4).
