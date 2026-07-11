# Tasks: Perfil de arranque DEMO aislado

> STRICT TDD. Cada bloque de implementación se ordena RED (test que falla) → GREEN
> (implementación mínima) → REFACTOR si aplica. Ninguna tarea arranca marcada; `sdd-apply`
> las marca `[x]` al completarlas.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~400-460 (additions+deletions) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No (borderline, un solo slice cohesivo) |
| Suggested split | PR único; si el diff real supera ~450, usar `size:exception` en vez de encadenar |
| Delivery strategy | ask-on-risk (no se recibió override explícito) |
| Chain strategy | pending |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Todo el cambio (config → salvaguarda → motor → ticket → seed → bootstrap → consola → docs) | PR único | Archivos pequeños y desacoplados; si crece, dividir en "núcleo" (Fases 1-3) + "superficie" (Fases 4-9) como fallback |

**Corrección a la expectativa del usuario**: el estimado real ronda 400-460 líneas, no
claramente por debajo de 400 (config+tests nuevos ~60 líneas, seed+tests ~90, ADR ~50, resto
repartido en 6 ficheros pequeños). Es un caso límite: PR único es razonable si se mantiene el
ADR y los tests concisos; si el diff real supera el presupuesto, preferir `size:exception`
antes que trocear una funcionalidad aditiva y fuertemente acoplada por `settings.perfil`.

## Fase 1: Config — perfil de arranque (Requirement: Selección de perfil / Aislamiento BD)

- [x] 1.1 RED `tests/test_config.py` (nuevo): `TPV_PROFILE=demo` ⇒ `perfil=="demo"`, `db_path=="tpv_demo.db"`, `nif_emisor`/`nombre_emisor` demo, `certificado_cert_path is None` y `certificado_key_path is None` (escenarios: Perfil demo explícito; Demo usa tpv_demo.db; Emisión de ticket en modo demo)
- [x] 1.2 RED `tests/test_config.py`: sin `TPV_PROFILE` ⇒ `perfil=="produccion"`, `db_path=="tpv.db"`, emisor real intacto (escenarios: Sin TPV_PROFILE definida; Producción usa tpv.db; Arranque sin variables de perfil configuradas)
- [x] 1.3 RED `tests/test_config.py`: `TPV_PROFILE=staging` ⇒ `Settings()` lanza error de validación (escenario: Valor de perfil inválido)
- [x] 1.4 GREEN `app/infraestructura/config.py`: añadir `perfil: Literal["produccion","demo"]` (`Field(validation_alias="TPV_PROFILE")`), constantes `DB_PATH_PRODUCCION`, `DEMO_DB_PATH`, `DEMO_NIF="00000000T"`, `DEMO_NOMBRE`; `@model_validator(mode="after")` que en demo fija `db_path`/emisor y anula ambos campos de certificado

## Fase 2: Salvaguarda de arranque (Requirement: Salvaguarda contra colisión de rutas — dep. Fase 1)

- [x] 2.1 RED `tests/test_main.py` (nuevo): `Settings` demo forzado a resolver `tpv.db` ⇒ `crear_app()` lanza `RuntimeError` y no abre conexión (escenario: Configuración demo apunta a producción)
- [x] 2.2 RED `tests/test_main.py`: demo con `tpv_demo.db` ⇒ `crear_app()` no lanza (smoke, no-regresión)
- [x] 2.3 GREEN `app/main.py`: `_verificar_aislamiento_demo(settings)` compara `Path(db_path).resolve()` vs `Path(DB_PATH_PRODUCCION).resolve()`; invocar al inicio de `crear_app`

## Fase 3: Motor fiscal forzado (Requirement: NullEngine en demo — dep. Fase 1; invariante 7)

- [x] 3.1 RED `tests/test_deps.py` (nuevo): perfil demo + certificado configurado ⇒ `get_motor()` es `NullEngine` con emisor demo y el certificado NUNCA se lee (escenario: Certificado presente pero perfil demo)
- [x] 3.2 RED `tests/test_deps.py`: perfil producción ⇒ `get_motor()` sin cambios respecto al comportamiento actual (nota: `VerifactuEngine` real no existe aún — fuera de alcance de este proposal; cubre no-regresión, no el escenario aspiracional "Producción resuelve VerifactuEngine")
- [x] 3.3 GREEN `app/presentacion/deps.py`: `get_motor` — primera rama `if settings.perfil == "demo": return NullEngine(...)`

## Fase 4: Ticket demo (Requirement: Marcado inequívoco — dep. Fase 1; invariante 5)

- [x] 4.1 RED `tests/test_ticket.py`: `imprimir_ticket(demo=True)` ⇒ salida contiene "DOCUMENTO DE PRUEBA" y "SIN VALIDEZ FISCAL", no contiene URL de cotejo ni `qr_mod.LEYENDA_CORTA` (escenario: Ticket impreso en modo demo)
- [x] 4.2 RED `tests/test_ticket.py`: `demo=False` (no-regresión) ⇒ salida con QR + leyenda VERI*FACTU intactos (escenario: Ticket de producción sin marca demo)
- [x] 4.3 GREEN `app/infraestructura/impresion/ticket.py`: kw-only `demo: bool | None = None`; si demo, sustituir el bloque QR (líneas 61-67) por banner centrado/negrita; nunca invocar `qr_mod.url_cotejo_registro` ni `printer.qr` en esa rama

## Fase 5: Seed demo idempotente (Requirement: Seed demo — dep. Fase 1)

- [x] 5.1 RED `tests/test_seed.py` (nuevo): `sembrar_demo()` sobre BD vacía crea empresa demo (emisor de settings), clientes y artículos de acuariofilia (escenario: Primer arranque en modo demo)
- [x] 5.2 RED `tests/test_seed.py`: ejecutar `sembrar_demo()` dos veces ⇒ mismo número de filas (escenario: Reinicio no duplica datos)
- [x] 5.3 GREEN `app/seed.py`: extraer catálogo base a helper reutilizable; añadir `sembrar_demo()` idempotente (guard `select(TipoIVA)` existente) que además siembra `Cliente` de prueba

## Fase 6: Bootstrap BD demo — decisión cerrada 1 (dep. Fases 1, 5)

- [x] 6.1 `app/seed.py`: añadir flag `--demo` al bloque `if __name__ == "__main__"` que invoca `sembrar_demo()`
- [x] 6.2 `Makefile`: target `demo` que ejecuta `TPV_PROFILE=demo` + `alembic upgrade head` sobre `tpv_demo.db` y luego `python -m app.seed --demo` (arrastra triggers de inmutabilidad y esquema real, no `create_all`)
- [x] 6.3 Smoke manual: `make demo` de punta a punta sobre `tpv_demo.db`; confirmar triggers y cadena de huella heredados del esquema real

## Fase 7: Banner consola web — decisión cerrada 2 (Requirement: Marcado inequívoco/consola — dep. Fase 1)

- [x] 7.1 RED `tests/test_health.py` (nuevo): `GET /health` expone `perfil` igual a `settings.perfil` (fuente única de verdad; escenario: Consola en modo demo, contrato backend)
- [x] 7.2 GREEN `app/presentacion/health.py`: añadir `"perfil": settings.perfil` a la respuesta
- [x] 7.3 GREEN `app/ui/admin.html`: al cargar, consultar `/health` y renderizar banner visible "MODO DEMO" cuando `perfil=="demo"` (admin.html es HTML/JS estático sin motor de plantillas — no hay test automatizado de render, solo del contrato backend en 7.1)

## Fase 8: Documentación y config — decisiones cerradas 3 y 4

- [x] 8.1 Redactar `docs/adr/0009-perfil-de-arranque-demo.md` (contexto, decisión, alternativas rechazadas de la tabla de design.md, consecuencias, referencia a invariantes 5 y 7)
- [x] 8.2 `.gitignore`: confirmar/añadir entrada explícita `tpv_demo.db*` con comentario (ya cubierto por el patrón `*.db` existente, pero se documenta la intención)

## Fase 9: Verificación final (dep. todas las anteriores)

- [x] 9.1 `make test`: suite completa verde — 161 tests previos sin regresión + todos los nuevos de Fases 1-7 (cubre Requirement: No regresión del comportamiento de producción). Resultado real: **174 passed** (161 previos + 13 nuevos: 3 config + 2 main + 2 deps + 2 ticket + 2 seed + 2 health).
- [x] 9.2 `make arch`: import-linter sin romper la regla de capas hexagonal (cambios solo en `infraestructura`/`presentacion`). Resultado real: **3 contracts kept, 0 broken** (50 files, 95 dependencies; antes 94).
