# Design: Perfil de arranque DEMO aislado

## Technical Approach

Cambio ADITIVO y *profile-gated* en dos capas hexagonales (ADR-0001): `infraestructura`
(config, db, seed, impresion) y `presentacion` (deps, main). Sin tocar `dominio` ni
`aplicacion`; `make arch` (import-linter) no se ve afectado. Toda conducta demo cuelga de
`settings.perfil`, cuyo default es `produccion`, de modo que el camino de produccion queda
BYTE A BYTE idéntico y los 161 tests actuales siguen verdes.

La pieza central es la RESOLUCION del perfil dentro de `Settings` (pydantic
`model_validator(mode="after")`). Como `settings = Settings()`, `engine = crear_engine()` y
`SessionLocal` son singletons de módulo creados en cascada al importar, resolver el perfil
DENTRO de `Settings` garantiza que `engine` ya nazca ligado a `tpv_demo.db` sin reordenar
imports. La salvaguarda de arranque en `crear_app` es un chequeo independiente (defensa en
profundidad) que aborta si la resolución regresara hacia la BD real.

Refuerza invariante 5 (no "modo formación" dentro del SIF: la demo es un proceso/BD/emisor
aislados, cada documento marcado) e invariante 7 (en demo el certificado ni se referencia
ni se carga).

## Architecture Decisions

| Decisión | Alternativa rechazada | Motivo |
|----------|-----------------------|--------|
| Campo `perfil: Literal["produccion","demo"]` con `Field(validation_alias="TPV_PROFILE")` | Campo `perfil` con env_prefix normal (daría `TPV_PERFIL`) | Nombre de código en español (convención) + nombre de env pedido `TPV_PROFILE`; `validation_alias` fija el env exacto y salta el prefijo `TPV_` |
| Resolver db/emisor en `Settings.model_validator(mode="after")` | Función `bootstrap()` imperativa post-import | El `engine` es singleton creado al importar `db.py`; mutar settings después dejaría el engine apuntando a `tpv.db`. El validator resuelve ANTES de crear el engine |
| En demo forzar `db_path=tpv_demo.db` incondicionalmente y `certificado_*=None` | Permitir override por `TPV_DB_PATH` | Aislamiento no negociable (proposal); el certificado nunca debe cargarse en demo (inv. 7) |
| `get_motor` cortocircuita a `NullEngine` si demo, ANTES de cualquier rama de producción futura | Confiar en el wiring actual (hoy ya devuelve NullEngine) | Blindar contra un futuro `VerifactuEngine`: la garantía "no remite" depende del PERFIL, no del cableado |
| `imprimir_ticket(..., demo: bool | None=None)` resuelto a `settings.perfil=="demo"` | Leer `settings` global dentro de la función sin parámetro | Testeable por inyección (patrón ya usado: `ancho`/`nombre_emisor`), sin monkeypatch del singleton |
| Salvaguarda como chequeo independiente en `crear_app` | Confiar solo en la resolución del validator | Falla RUIDOSA ante regresión/misconfig futura: compara rutas ABSOLUTAS resueltas |

## Data Flow

```
TPV_PROFILE=demo
      │
      ▼
Settings.__init__ ──(model_validator after)──► db_path=tpv_demo.db, emisor="…Demo", cert=None
      │
      ▼
crear_engine(settings.database_url) ─► engine ligado a tpv_demo.db ─► SessionLocal
      │
      ▼
crear_app() ─► _verificar_aislamiento_demo(settings)
                    │ abspath(db) == abspath(tpv.db)? ─► RuntimeError (abortar)
                    ▼ ok
get_motor() ─► perfil demo ─► NullEngine(emisor demo)   [cert nunca referenciado]
imprimir_ticket(demo=True) ─► banner "SIN VALIDEZ FISCAL", SUPRIME QR/leyenda cotejo
```

## File Changes

| File | Action | Integración exacta |
|------|--------|--------------------|
| `app/infraestructura/config.py` | Modify | Añadir `perfil` (alias `TPV_PROFILE`), constantes `DB_PATH_PRODUCCION="tpv.db"`, `DEMO_DB_PATH`, `DEMO_NIF`, `DEMO_NOMBRE`; `@model_validator(mode="after")` `_resolver_perfil` que en demo fija db/emisor y anula `certificado_cert_path`/`certificado_key_path` |
| `app/main.py` | Modify | `crear_app`: llamar `_verificar_aislamiento_demo(settings)` al inicio; helper compara `Path(db_path).resolve()` vs `Path(DB_PATH_PRODUCCION).resolve()` y lanza `RuntimeError` si coinciden |
| `app/presentacion/deps.py` | Modify | `get_motor`: `if settings.perfil == "demo": return NullEngine(...)` como PRIMERA rama |
| `app/infraestructura/impresion/ticket.py` | Modify | `imprimir_ticket`: nuevo kw-only `demo`; si demo, sustituir bloque QR (líneas 61-67) por banner centrado/negrita "DOCUMENTO DE PRUEBA" / "SIN VALIDEZ FISCAL"; NO invocar `qr_mod.url_cotejo_registro` ni `printer.qr` |
| `app/seed.py` | Modify | Extraer catálogo base a helper reutilizable; añadir `sembrar_demo()` idempotente (guard `select(TipoIVA)` existente) que además siembre `Cliente` de prueba; "empresa demo" = emisor de settings, NO tabla nueva |
| `app/infraestructura/db.py` | No change | `crear_engine()` ya lee `settings.database_url`; hereda el perfil sin tocar |

## Interfaces / Contracts

```python
# config.py
DB_PATH_PRODUCCION = "tpv.db"
perfil: Literal["produccion", "demo"] = Field("produccion", validation_alias="TPV_PROFILE")

# main.py
def _verificar_aislamiento_demo(s: Settings) -> None: ...  # RuntimeError si demo→tpv.db

# ticket.py  (firma extendida, retrocompatible)
def imprimir_ticket(printer, venta, registro, *, ancho=None, nombre_emisor=None,
                    nif_emisor=None, cortar=True, demo: bool | None = None) -> None: ...
```

## Testing Strategy (TDD — escribir el test primero)

| Layer | Qué testear | Enfoque |
|-------|-------------|---------|
| Unit config | `TPV_PROFILE=demo` ⇒ `db_path=="tpv_demo.db"`, emisor demo, `certificado_cert_path is None` | Instanciar `Settings(_env_file=None)` con env parcheado (monkeypatch) |
| Unit config (no-regresión) | default ⇒ `perfil=="produccion"`, `db_path=="tpv.db"`, emisor real intacto | `Settings()` sin env |
| Unit deps | demo ⇒ `isinstance(get_motor(), NullEngine)` y emisor demo | Parchear `settings.perfil` |
| Boot safeguard | demo con db resuelta == abspath(`tpv.db`) ⇒ `crear_app()` lanza `RuntimeError` | Settings forzado; `pytest.raises` |
| Boot happy-path | demo con `tpv_demo.db` ⇒ `crear_app()` no lanza | Smoke |
| Seed | `sembrar_demo()` dos veces ⇒ sin duplicados; crea `Cliente`+`Articulo` | BD en memoria (`create_all`), contar filas |
| Print demo | `imprimir_ticket(demo=True)` ⇒ salida contiene "SIN VALIDEZ FISCAL" y NO contiene URL cotejo ni `LEYENDA_CORTA` | `escpos.Dummy`, inspeccionar `printer.output` |
| Print prod (no-regresión) | `demo=False` ⇒ salida con QR + `VERI*FACTU`, sin banner | `Dummy` |

## Migration / Rollout

Sin migración de esquema ni datos productivos. Rollback = quitar `perfil` y las ramas demo;
producción es el default. La BD `tpv_demo.db` es un fichero desechable (portátil de la
demo). Añadir `tpv_demo.db*` a `.gitignore`.

## Open Questions

- [ ] Banner demo en la consola/UI web: ¿por *flag* de template inyectado en el contexto de
      render, o exponiendo `settings.perfil` a las vistas? (afecta a `presentacion`, no al
      motor). Recomendación provisional: exponer `perfil` al contexto de plantillas (una sola
      fuente de verdad, coherente con ticket y deps).
- [ ] ¿Formalizar la decisión como `docs/adr/0009-perfil-de-arranque-demo.md`? El cambio NO
      modifica ADRs existentes (es aditivo), pero introduce el concepto "perfil de arranque".
