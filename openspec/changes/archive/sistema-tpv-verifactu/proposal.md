# Proposal: Sistema TPV AcuaTPV (VERI*FACTU) — marco global retrospectivo

> **Naturaleza**: SDD **retrospectivo**. El sistema ya está construido y verificado
> (161 tests en verde, `make arch` en verde). Este proposal NO finge que la especificación
> precedió al código: documenta con método SDD lo ya entregado, trazando problema, alcance
> y decisiones al código y los tests existentes, y delimitando el trabajo futuro.

## Intent

Una tienda física de acuariofilia debe, **por obligación legal** (RD 1007/2023 RRSIF +
Orden HAC/1177/2024, con art. 29.2.j LGT ya vigente), emitir sus tickets mediante un
Sistema Informático de Facturación (SIF). La persona titular tributa en IRPF por estimación
objetiva y en recargo de equivalencia de IVA. **Decisión fiscal cerrada**: todos los
tickets se expiden como facturas simplificadas, y el sistema opera en modalidad
**VERI\*FACTU** (remisión voluntaria anticipada a la AEAT; ADR-0008), que dispensa de firma
electrónica y registro de eventos formal. Éxito = un TPV que vende de forma fiable **offline**
y produce registros de facturación inalterables, correlativos y encadenados conforme a la
Orden, listos para remitir.

## Scope

### In Scope (entregado y verificado)

| # | Fase entregada | Contenido |
|---|---|---|
| 1 | Fundaciones de datos | Modelos SQLAlchemy, migraciones Alembic, `Decimal` como TEXT (ADR-0002), función única de redondeo half-up por línea (ADR-0005), validadores NIF/NIE/CIF |
| 2 | Motor fiscal VERI*FACTU | `Huella` SHA-256 encadenada (art. 13, verificada contra vectores oficiales AEAT; ADR-0006/0007), XML validado contra XSD, QR del ticket, cliente SOAP `Remitente`, cola de remisión FIFO con reintentos |
| 3 | TPV táctil | UI de venta, cobro **offline**, impresión ESC/POS con QR y apertura de cajón |
| 4 | Consola de administración | Auth sesión+rol, panel fiscal (cola, `verify_chain`, declaración responsable), informe del día, maestros |
| 5 | Arquitectura hexagonal pragmática | dominio/aplicacion/infraestructura/presentacion, verificada con import-linter (ADR-0001) |
| 6 | CRUD de maestros | Artículos, tipos de IVA, familias (árbol ilimitado) y clientes |

### Out of Scope (trabajo futuro, honesto)

- **Remisión REAL a la AEAT** (entorno de pruebas/producción): la lógica VERI*FACTU está
  implementada y verificada contra vectores oficiales, pero la remisión productiva **está
  pendiente de certificado electrónico**, que por diseño **nunca sale del servidor**.
- CRUD de usuarios; editor visual de botoneras; cierre Z / arqueo de caja; control de stock
  y mermas; backup/replicación con Litestream.

### Non-goals (excluidos por decisión)

Multiusuario / multipuesto; TPV en territorio foral (TicketBAI/Batuz); pasarela de pago
integrada; e-commerce.

## Capabilities

> Contrato con sdd-spec. `openspec/specs/` está vacío: todas son capacidades nuevas a documentar.

### New Capabilities
- `fundaciones-datos`: tipos monetarios, redondeo único, validadores fiscales, esquema e inmutabilidad de BD.
- `motor-fiscal-verifactu`: registro de alta/anulación, huella encadenada, XML+XSD, QR, cola de remisión FIFO.
- `tpv-venta`: venta táctil, cobro offline, series correlativas, impresión ESC/POS y cajón.
- `consola-administracion`: autenticación sesión+rol, panel fiscal, informe del día, declaración responsable.
- `maestros-crud`: artículos, tipos de IVA, familias (árbol) y clientes.

### Modified Capabilities
- None (no existían specs previas; este es el marco inaugural).

## Approach

Documentación por método SDD, sin tocar código. Las capacidades anteriores se especificarán
(sdd-spec) trazando cada requisito al código y al test que ya lo cubre. Los **invariantes
innegociables** (`invariants_do_not_weaken`) se presentan como **restricciones**, nunca se
proponen debilitar. Restricciones y tradeoffs asumidos: local-first (sin dependencias de red
en el cobro); `Decimal` jamás `float`; inmutabilidad **a nivel de BD** por triggers (ADR-0003);
numeración correlativa asignada en la **misma transacción** (ADR-0004); cadena de huellas
**secuencial**, nunca paralelizada; hexagonal **pragmático** — los modelos ORM son las
entidades (ADR-0001), tradeoff documentado frente a entidades de dominio puras.

## Affected Areas

| Área | Impacto | Descripción |
|------|--------|-------------|
| `openspec/changes/sistema-tpv-verifactu/` | New | Artefactos SDD (proposal, specs, design, tasks) |
| `openspec/specs/` | New (vía archive) | Specs de dominio consolidadas al cerrar el cambio |
| `app/`, `tests/` | None | Solo documentación; el código NO se modifica en este cambio |

## Risks

| Riesgo | Probabilidad | Mitigación |
|------|------------|-----------|
| La spec retrospectiva contradiga el código real | Media | Trazar cada requisito a test existente; el código es fuente de verdad |
| Documentar de menos el trabajo futuro y sugerir falso "completado" | Media | Out of Scope explícito: remisión productiva pendiente de certificado |
| Deriva respecto a la normativa (precedencia) | Baja | Precedencia normativa > consideraciones > CLAUDE.md; citar ADR/Orden en specs fiscales |

## Rollback Plan

Cambio **documentación-única**: no altera código, esquema ni datos. Rollback = descartar los
artefactos SDD del cambio (`openspec/changes/sistema-tpv-verifactu/`) y la entrada en engram.
Riesgo operativo nulo sobre el sistema en producción.

## Dependencies

- Docs autoritativos: `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/TPV_ACUATPV_consideraciones.md`,
  `docs/VERIFACTU_ESQUEMAS_HAC1177.md`, `docs/adr/0001..0008`.
- Para el trabajo futuro de remisión real: **certificado electrónico** de la persona titular (custodia en el servidor).

## Success Criteria

- [ ] Suite de **161 tests** en verde (incluye test por invariante y huella contra vectores oficiales).
- [ ] `make arch` (import-linter) en verde: dominio puro, nadie depende de `presentacion`.
- [ ] Cada capacidad documentada traza a código y test existentes, sin proponer debilitar ningún invariante.
- [ ] Out of Scope y non-goals explícitos, sin ambigüedad sobre lo entregado vs. lo pendiente.
