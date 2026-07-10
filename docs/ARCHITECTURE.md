# Arquitectura — TPV Bizkaitropik

> Estado: **en migración** hacia hexagonal pragmático (ADR-0001).
> Regla de oro del refactor: la lógica fiscal probada NO cambia; solo se reempaqueta,
> con los tests en verde en cada incremento.

## 1. Objetivo

TPV táctil monopuesto para acuariofilia, SIF sujeto al RRSIF (RD 1007/2023) y la Orden
HAC/1177/2024, operando en modalidad **VERI\*FACTU** (ADR-0008). Local-first: la venta se
cierra sin internet; la remisión a la AEAT es asíncrona con cola y reintentos.

Contexto de negocio y normativa: `docs/TPV_BIZKAITROPIK_consideraciones.md`,
`docs/VERIFACTU_ESQUEMAS_HAC1177.md`. Invariantes innegociables: `CLAUDE.md`.

## 2. Arquitectura objetivo (hexagonal pragmático)

Cuatro capas; las dependencias apuntan **hacia adentro**. El dominio no conoce ni el
framework web ni el ORM ni la AEAT.

```
  presentacion  ──►  aplicacion  ──►  dominio  ◄──  infraestructura
   (FastAPI)         (casos de uso)   (puro)        (ORM, SOAP, ESC/POS, XSD)
```

- **dominio** (puro, solo stdlib): valores (`Dinero`, `NIF`, `Huella`, `Porcentaje`),
  servicios (redondeo, composición de huella, validaciones de negocio, validación
  NIF/NIE/CIF) y **puertos** (interfaces): `RepositorioVentas`, `RepositorioRegistros`,
  `MotorFiscal`, `Remitente`, `Impresora`, `Reloj`.
- **aplicacion**: casos de uso que orquestan dominio + puertos: `EmitirVenta`,
  `RemitirLote`, `AbrirCajon`, `ConsultarEstadoFiscal`, `ConvertirEnFactura` (fase 2 del
  producto). No conocen HTTP ni SQL.
- **infraestructura**: adaptadores que implementan los puertos: modelos SQLAlchemy +
  repositorios, motor `VerifactuEngine`/`NullEngine`, serialización XML + validación XSD,
  QR, cliente SOAP, impresión ESC/POS, config, Alembic.
- **presentacion**: routers FastAPI (`/tpv`, `/admin`) — adaptadores de entrada que
  invocan casos de uso. Sin lógica de negocio.

### Decisión pragmática (ADR-0001)

Los **modelos SQLAlchemy siguen siendo las entidades**, accedidas tras los puertos de
repositorio. **No** duplicamos entidades de dominio puras con mapeadores ORM↔dominio: a
esta escala es boilerplate sin retorno. Se acepta que las entidades tocan el ORM; el
resto del dominio (valores + servicios) sí es puro.

## 3. Estado actual (honesto) y mapeo al objetivo

Hoy la lógica fiscal ya está mayormente aislada, pero la estructura de carpetas no refleja
las capas y hay lógica de negocio en los endpoints.

| Hoy | Objetivo | Nota |
|---|---|---|
| `app/core/redondeo`, `validadores` | `dominio/servicios`, `dominio/valores` | ya puro |
| `app/core/tipos` (`DecimalTexto`) | `infraestructura/persistencia` | tipo SQLAlchemy |
| `app/fiscal/huella`, `validaciones_negocio` | `dominio/servicios` | ya puro |
| `app/fiscal/engine` (`FiscalEngine`+`NullEngine`) | puerto en `dominio`, impl en `infra/fiscal` | ya es puerto |
| `app/fiscal/xml`, `validacion`, `qr`, `remitente` | `infraestructura/fiscal` | adaptadores |
| `app/fiscal/cola` (`ColaRemision`) | caso de uso `RemitirLote` + `RepositorioRegistros` | mezcla orquestación+query |
| `app/models` | `infraestructura/persistencia/modelos` | ORM |
| `app/api` | `presentacion` | lógica inline → mover a casos de uso |
| `app/printing` | `infra/impresion` + puerto `Impresora` | |

Costuras hexagonales que **ya existen**: `FiscalEngine` y `Remitente` (inversión de
dependencias). Dominio ya puro: redondeo, huella, validadores, validaciones de negocio.

## 4. Plan de migración por incrementos (tests verdes entre cada uno)

0. ✅ **Documentación**: `ARCHITECTURE.md` + ADRs.
1. ✅ **Capa de aplicación**: `EmitirVenta` como caso de uso; endpoints `/tpv` finos; puerto
   `MotorFiscal` en `dominio/puertos.py`.
2. ✅ **Repositorios**: `RepositorioArticulos`/`Ventas`/`Usuarios`/`Registros` + `UnidadDeTrabajo`
   (puertos) con adaptadores SQLAlchemy; `ColaRemision` → caso de uso `RemitirLote`.
3. ✅ **Reubicación de módulos** a `dominio/aplicacion/infraestructura/presentacion`
   (con `git mv`, imports reescritos por script, tests verdes en cada sub-paso):
   3a servicios puros → `dominio/servicios`; 3b modelos ORM → `infraestructura/persistencia`;
   3c fiscal → `infraestructura/fiscal`; 3d `core` (config/db/tipos/reloj/seguridad) →
   `infraestructura`; 3e `api` → `presentacion` y `printing` → `infraestructura/impresion`.
   La estructura de carpetas ya coincide con §2.
4. ✅ **Cierre**: regla de dependencias verificada con `import-linter` (contratos en
   `pyproject.toml` `[tool.importlinter]`) y comprobada en la suite (`tests/test_arquitectura.py`,
   `make arch`). Contratos: el dominio es puro en runtime; nadie depende de `presentacion`;
   `infraestructura` no depende de `aplicacion`/`presentacion`. Excepción documentada:
   `aplicacion` sí usa `infraestructura` (entidades ORM y serialización del sobre), por ADR-0001.

Cada incremento es un PR/commit propio, reversible, con `make test` en verde.

## 5. TDD, SOLID y Clean

- **TDD estricto de aquí en adelante**: test-first (rojo → verde → refactor) para el código
  nuevo. La base actual tiene 99 tests que cubren cada invariante; ese suelo no baja.
- **SOLID**: `FiscalEngine`/`Remitente` (DIP, OCP). Los casos de uso dan SRP a la
  aplicación (hoy la lógica está en los endpoints). Los puertos de repositorio invierten la
  dependencia del ORM.
- **Clean**: la regla de dependencias hacia adentro se documenta y (fase 4) se verifica
  automáticamente. Lo que NO haremos (y por qué): entidades de dominio puras separadas del
  ORM — ver ADR-0001.

## 6. Invariantes que el refactor NO puede tocar

Vienen de `CLAUDE.md` y la normativa; el refactor solo reempaqueta:

- Inmutabilidad de ventas emitidas y registros (triggers de BD) — ADR-0003.
- Numeración correlativa sin huecos (misma transacción) — ADR-0004.
- Importes en `Decimal`, jamás `float` — ADR-0002.
- Función única de redondeo — ADR-0005.
- Huella encadenada conforme al art. 13 — ADR-0006/0007.
