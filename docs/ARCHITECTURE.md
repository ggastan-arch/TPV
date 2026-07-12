# Arquitectura — TPV AcuaTPV

TPV táctil monopuesto para acuariofilia, Sistema Informático de Facturación (SIF) sujeto
al RRSIF (RD 1007/2023) y a la Orden HAC/1177/2024, operando en modalidad **VERI\*FACTU**
(ADR-0008). Local-first: la venta se cierra sin internet; la remisión a la AEAT es
asíncrona, con cola y reintentos.

La arquitectura es **hexagonal pragmática** (ADR-0001), ya completada: cuatro capas con
dependencias hacia adentro, verificadas automáticamente por `import-linter` (`make arch`).
No es un objetivo a futuro — es la estructura actual del código.

Contexto de negocio y normativa: `docs/TPV_ACUATPV_consideraciones.md`,
`docs/VERIFACTU_ESQUEMAS_HAC1177.md`. Invariantes innegociables: `CLAUDE.md`.

## 1. Capas y dependencias

```
  presentacion  ──►  aplicacion  ──►  dominio  ◄──  infraestructura
   (FastAPI)         (casos de uso)   (puro)        (ORM, SOAP, ESC/POS, XSD)
```

| Capa | Contiene | No conoce |
|---|---|---|
| **dominio** (`app/dominio/`) | Servicios puros (redondeo, huella, validaciones de negocio, validadores NIF/NIE/CIF) y **puertos** (`Protocol`): `MotorFiscal`, `RepositorioArticulos`, `RepositorioVentas`, etc. Solo stdlib. | Framework web, ORM, AEAT |
| **aplicacion** (`app/aplicacion/`) | Casos de uso que orquestan dominio + puertos: `EmitirVenta`, `RemitirLote`, `ConsultarEstadoFiscal`, CRUD de artículos/familias/clientes/tipos IVA/usuarios/botoneras, `GenerarCierreZ`. | HTTP, SQL directo |
| **infraestructura** (`app/infraestructura/`) | Adaptadores: modelos SQLAlchemy + repositorios, `FiscalEngine`/`NullEngine`, XML+XSD, QR, cliente SOAP, impresión ESC/POS, config, Alembic. | Casos de uso, endpoints |
| **presentacion** (`app/presentacion/`) | Routers FastAPI: `/tpv` (PIN de operador), `/admin` (sesión + rol), `/health`. Sin lógica de negocio. | — |

La regla de dependencias se verifica en cada corrida de tests
(`tests/test_arquitectura.py` invoca `lint-imports`; contratos en `pyproject.toml
[tool.importlinter]`). Nadie depende de `presentacion`; `infraestructura` no depende de
`aplicacion` ni `presentacion`; el dominio no depende de ninguna otra capa **en runtime**
(los puertos referencian entidades ORM solo bajo `TYPE_CHECKING`, sin coste en ejecución).

### Decisión pragmática (ADR-0001)

Los **modelos SQLAlchemy son las entidades**, accedidas tras los puertos de repositorio.
No se duplican con entidades de dominio puras + mapeadores ORM↔dominio: a esta escala
(una tienda, un puesto) es boilerplate sin retorno. El resto del dominio (valores +
servicios) sí es puro.

## 2. Puertos y adaptadores

Todos los puertos viven en `app/dominio/puertos.py` (tipados como `Protocol`); las
implementaciones concretas están en `app/infraestructura/persistencia/repositorios.py`
salvo donde se indica.

| Puerto | Para qué |
|---|---|
| `MotorFiscal` | Emitir y anular registros fiscales, verificar la cadena de huellas |
| `RepositorioArticulos` / `RepositorioTiposIva` / `RepositorioFamilias` / `RepositorioClientes` | Maestros (CRUD, nunca hard-delete) |
| `RepositorioVentas` | Alta y consulta de ventas |
| `RepositorioUsuarios` | Operadores/administradores del TPV |
| `RepositorioAuditoria` | Log append-only (descuentos, anulaciones, accesos admin, etc.) |
| `RepositorioRegistros` | Cola de remisión: pendientes, reintentos, resultado por registro |
| `RepositorioCierresZ` | Snapshot inmutable del Cierre Z por rango de `orden` |
| `RepositorioConfiguracion` | Ajuste de empresa singleton (hoy: control de stock activo/inactivo) |
| `RepositorioBotonera` | Árbol perfil → página → botón de la botonera del TPV |
| `RepositorioStock` | Movimientos de stock informativo (entrada/venta/merma); agregación en `Decimal`, nunca `SUM` SQL |
| `UnidadDeTrabajo` | Agrupa todos los repositorios anteriores y controla la transacción (`commit`/`rollback`/`flush`) |

## 3. Capacidades entregadas (SDD / openspec)

El proyecto usa Spec-Driven Development: cada capacidad nace como propuesta → specs →
diseño → tareas en `openspec/changes/`, y al cerrarse se consolida en `openspec/specs/`.
`openspec/config.yaml` fija invariantes, convenciones y comandos de test/arquitectura para
ese flujo.

Specs consolidadas (`openspec/specs/`):

| Spec | Cubre |
|---|---|
| `fundaciones-datos` | Tipos monetarios exactos, redondeo único, validadores, inmutabilidad/numeración en BD, auditoría |
| `motor-fiscal-verifactu` | Generación, encadenamiento, XML/XSD, QR y cola de remisión con transporte inyectado |
| `tpv-venta` | Venta táctil, cobro offline, emisión con serie/número, ticket ESC/POS con QR |
| `consola-administracion` | Panel `/admin`: cola fiscal, verificación de cadena, informe del día, auditoría |
| `maestros-crud` | CRUD de artículos/tipos IVA/familias/clientes |
| `editor-botoneras` | API de configuración de la botonera (perfil → página → botón) |
| `control-stock` | Stock informativo; nunca bloquea el cobro |
| `cierre-z` | Cierre Z: snapshot inmutable por rango de `orden` |
| `modo-demo` | Perfil de arranque aislado (ver ADR-0009) |

Changes ya archivados en `openspec/changes/archive/` (histórico, no se editan): entre
otros, `sistema-tpv-verifactu` (marco global retrospectivo), `imagenes-catalogo`,
`familia-visible-tactil`, `edicion-linea-tpv`, `modos-precio`, `busqueda-tpv`.

## 4. Persistencia

### Migraciones (Alembic, hasta 0007)

| # | Migración |
|---|---|
| 0001 | Esquema inicial: maestros, ventas, registro fiscal, triggers de inmutabilidad |
| 0002 | Campos de remisión (estado, CSV, incidencia) |
| 0003 | Cierre Z |
| 0004 | `configuracion_empresa` (singleton) |
| 0005 | `familia.visible_tactil` |
| 0006 | `articulo.imagen` (ruta a `media/`) |
| 0007 | `articulo.modo_precio` (fijo \| libre \| al_peso) |

Nunca `create_all` en producción ni en el perfil demo: ambas BD nacen con `alembic
upgrade head`, heredando los mismos triggers de inmutabilidad y el mismo esquema de
cadena de huella.

`migrations/env.py` resuelve la URL con prioridad `-x sqlalchemy.url` (override del
runner) > `sqlalchemy.url` de `alembic.ini` > `settings.database_url`
(`resolver_url_migracion` en `app/infraestructura/db.py`). Esto permite migrar contra una
BD de scratch (tests, demo) sin depender de que el proceso ya tenga `TPV_PROFILE`
resuelto ni de tocar la URL por defecto.

### Perfil de arranque `demo` (ADR-0009)

`TPV_PROFILE=demo` fuerza, de forma no configurable, una BD propia (`tpv_demo.db`),
emisor ficticio y certificado anulado — nunca se carga el certificado real de la persona
titular en este perfil (invariante 7). `get_motor()` cortocircuita a `NullEngine` como
primera rama cuando el perfil es demo. Bootstrap: `make demo`.

### Imágenes de catálogo

`app/infraestructura/imagenes.py` valida y guarda imágenes de artículo/familia en
`media/` (gitignored, nunca en BD): tipo real por magic bytes (ignora el `content-type`
del cliente), nombre de archivo generado siempre por el servidor (anti path-traversal),
límite de 3 MB, JPEG/PNG/WebP.

## 5. Estado honesto del motor fiscal

El puerto `MotorFiscal` (`app/dominio/puertos.py`) tiene **una sola implementación
real: `NullEngine`** (`app/infraestructura/fiscal/engine.py`). `NullEngine.emit`/`cancel`
generan el registro fiscal, la huella y el encadenamiento igual que lo haría un motor de
producción (no es un stub simplificado: numeración correlativa, huella SHA-256
encadenada, triggers de inmutabilidad, todo real) — pero **no remiten nada a la AEAT**.
El QR se construye aparte, a partir del registro ya generado, al imprimir el ticket
(`app/infraestructura/fiscal/qr.py`), así que el ticket con su QR sale igual en local.

No existe una clase `VerifactuEngine` que implemente `MotorFiscal` de punta a punta.
Lo que sí existe, ya construido y con tests, es la maquinaria de remisión como pieza
**separada**:

- `app/infraestructura/fiscal/xml.py` serializa el sobre `RegFactuSistemaFacturacion` y
  lo valida contra los XSD oficiales (`schemas/`).
- `app/infraestructura/fiscal/remitente.py` (`RemitenteVerifactu`) hace el transporte
  SOAP real (mutual-TLS) contra el WSDL de la AEAT.
- `app/aplicacion/remitir_lote.py` (`RemitirLote`) orquesta: toma pendientes en FIFO,
  construye el sobre, llama al `Remitente`, registra el resultado.
- Está cableada a un endpoint de administración
  (`POST /admin/api/fiscal/reintentar`), pero ese endpoint responde
  `"Certificado no configurado: la remision no esta disponible"` si no hay certificado
  cargado — que es el estado actual.

En corto: **la cadena de huellas y el ticket con QR funcionan hoy, en local, sin tocar la
red. La remisión real a la AEAT está construida y probada con transporte simulado, pero
nunca se ha ejecutado contra el entorno de la AEAT** porque falta el certificado
electrónico de la persona titular (ADR-0008, ADR-0009). Cuando llegue el certificado, la
pieza que falta es cablear `RemitirLote`/`RemitenteVerifactu` a un disparador automático
(hoy es manual, vía el botón de "reintentar" de la consola) — no reescribir el transporte.

## 6. Invariantes que esta arquitectura protege

Vienen de `CLAUDE.md` y la normativa; ningún cambio de arquitectura puede debilitarlos:

- [ ] Inmutabilidad de ventas emitidas y registros (triggers de BD) — ADR-0003.
- [ ] Numeración correlativa sin huecos, misma transacción — ADR-0004.
- [ ] Importes en `Decimal`, nunca `float` — ADR-0002.
- [ ] Función única de redondeo — ADR-0005.
- [ ] Huella encadenada conforme al art. 13 — ADR-0006/0007.
- [ ] Certificado electrónico: nunca sale del servidor ni se registra en logs — ADR-0009.

## 7. Referencias

- ADRs: `docs/adr/0001` a `docs/adr/0009`.
- Especificación técnica del motor fiscal: `docs/VERIFACTU_ESQUEMAS_HAC1177.md`.
- Contexto de negocio: `docs/TPV_ACUATPV_consideraciones.md`.
- Metodología SDD: `openspec/config.yaml`, `openspec/specs/`, `openspec/changes/archive/`.
