# Design: Sistema TPV Bizkaitropik (VERI*FACTU) — arquitectura transversal

> **SDD retrospectivo.** Este documento DOCUMENTA la arquitectura ya construida y
> verificada (161 tests en verde, `make arch` en verde) y la traza a los ADR
> (`docs/adr/0001..0008`), que contienen la decisión completa. No reescribe los ADR: los
> resume y referencia (DRY). No modifica código.

## Enfoque técnico

Hexagonal **pragmático** (ADR-0001): cuatro capas con dependencias hacia adentro. El
dominio (valores + servicios + puertos) es puro (solo stdlib); la aplicación orquesta
casos de uso; la infraestructura implementa los puertos (ORM, SOAP, ESC/POS, XSD); la
presentación (FastAPI) es un adaptador de entrada fino. La regla de dependencias se
verifica en CI con import-linter (`make arch`; contratos en `pyproject.toml`
`[tool.importlinter]` y `tests/test_arquitectura.py`).

```
presentacion ──► aplicacion ──► dominio ◄── infraestructura
 (FastAPI)      (casos de uso)  (puro)      (ORM, SOAP, ESC/POS, XSD)
```

**Tradeoff clave (ADR-0001):** los modelos SQLAlchemy **SON las entidades**, accedidas
tras puertos de repositorio; no se duplican entidades de dominio puras con mapeadores
ORM↔dominio. A escala monopuesto ese boilerplate no aporta retorno; se acepta que las
entidades tocan el ORM y que `aplicacion` importe entidades ORM (excepción documentada del
contrato import-linter). El resto del dominio (valores, servicios) sí es puro y testeable
en aislamiento.

## Decisiones de arquitectura (resumen; decisión completa en cada ADR)

| Decisión | Elección | Alternativa descartada | ADR |
|---|---|---|---|
| Estilo arquitectónico | Hexagonal pragmático; ORM = entidades | Entidades puras + mapeadores (boilerplate sin retorno a esta escala) | 0001 |
| Tipo monetario | `Decimal` cuantizado, persistido como TEXT (`DecimalTexto` TypeDecorator); cálculo en servidor | `float`/`NUMERIC` (error de redondeo binario); enteros de céntimos (menos legible) | 0002 |
| Inmutabilidad | Triggers SQLite `BEFORE UPDATE/DELETE` → `RAISE(ABORT)`; fuente única en `persistencia/ddl.py` | Solo capa de aplicación (bugs/rutas alternativas la saltan) | 0003 |
| Numeración correlativa | Serie+número en la MISMA transacción; `BEGIN IMMEDIATE` + WAL + `busy_timeout` | Autobegin diferido (huecos bajo contienda) | 0004 |
| Redondeo | Función única: `base = half_up(total/(1+tipo))`, `cuota = total − base` (residuo) | Redondear base y cuota por separado (puede no cuadrar el total) | 0005 |
| Motor fiscal | Puerto `MotorFiscal`; impl. `NullEngine`/`VerifactuEngine` (DIP + OCP) | Motor único acoplado a la AEAT (cierra la puerta a TicketBAI) | 0006 |
| Huella | SHA-256 encadenada, cadena `campo=valor&…` según doc oficial; hex MAYÚS; anulación con sufijo `Anulada` | Formato compuesto "de memoria" (inaceptable en un SIF) | 0007 |
| Modalidad | VERI*FACTU: dispensa firma XAdES y registro de eventos formal; cola + reintentos | NO VERI*FACTU (firma + log de eventos: piezas más costosas) | 0008 |

## Puertos y adaptadores (reales)

Puertos formales en `app/dominio/puertos.py` (`Protocol`, tipado estructural → inversión de
dependencias, el dominio no importa implementaciones):

- `MotorFiscal` — el ABC `FiscalEngine` (infra) lo satisface; DIP + OCP (ADR-0006).
- Repositorios: `RepositorioArticulos / TiposIva / Familias / Clientes / Ventas / Usuarios
  / Registros / Auditoria`.
- `UnidadDeTrabajo` — agrupa los repositorios y controla la transacción (`session`,
  `flush`, `commit`, `rollback`).

Adaptadores en `app/infraestructura/`: repositorios + `UnidadDeTrabajo` SQLAlchemy
(`persistencia/`), `NullEngine`/`VerifactuEngine` (`fiscal/engine.py`), XML + validación
XSD (`fiscal/xml.py`, `fiscal/validacion.py`), QR (`fiscal/qr.py`), impresión ESC/POS
(`impresion/ticket.py`), reloj con huso (`reloj.py`), config y `db` (`BEGIN IMMEDIATE`).

**Precisión honesta:** `Remitente` (transporte SOAP mTLS, `fiscal/remitente.py`) NO es hoy
un `Protocol` en `puertos.py`, sino un adaptador **colaborador** de `VerifactuEngine` /
`RemitirLote`; aplica DIP en su propia frontera vía `cert` y `poster` inyectables (en tests
no hace falta red ni certificado). Igual que `Reloj` e `Impresora`, `docs/ARCHITECTURE.md`
los lista como costuras objetivo; el conjunto formal de puertos es el de `puertos.py`.

## Flujo de datos

Emisión de venta (cobro **offline**, sin dependencias de red):

```
/tpv ─► EmitirVenta ─► UnidadDeTrabajo (BEGIN IMMEDIATE, ADR-0004)
                        ├─ contador_serie++            (misma txn)
                        ├─ alta venta + líneas + pagos (Decimal→TEXT, ADR-0002)
                        └─ MotorFiscal.emit → RegistroFiscal
                              (huella encadenada al anterior, ADR-0007)
                        commit ─► impresión ESC/POS + QR + apertura de cajón
```

Remisión a la AEAT (asíncrona, VERI*FACTU):

```
RemitirLote ─► RepositorioRegistros.pendientes()  (FIFO, orden de generación)
            ─► Remitente (SOAP mTLS) ──────────► AEAT
            ─► registrar_resultado(aceptado | con_errores | rechazado)
                reintento ≥ 1/h; marca incidencia en el siguiente envío
```

La cadena de huella es **secuencial por definición**: nunca se paraleliza (rompería el
encadenamiento único por sistema). **Local-first**: la venta se cierra sin internet; la
remisión es un proceso aparte.

## Cambios de código

Ninguno. SDD retrospectivo: solo documentación. `app/` y `tests/` no se tocan (ver
proposal, §Affected Areas).

## Estrategia de test (existente)

| Capa | Qué se prueba | Cómo |
|---|---|---|
| Dominio | Redondeo (multi-tipo 21%+10%), huella (3 vectores oficiales AEAT), validadores NIF/NIE/CIF | pytest unitario, aislado |
| BD | Rechazo de UPDATE/DELETE sobre emitidos; correlatividad con 20 hilos concurrentes | pytest + SQLite real |
| Aplicación | `EmitirVenta`, `RemitirLote` | pytest sin HTTP |
| Presentación | `/tpv`, `/admin` | httpx TestClient |
| Arquitectura | Regla de dependencias hexagonal | import-linter (`make arch`) |

## Migración / rollout

No aplica: cambio documentación-única sobre sistema en producción; sin migración de datos
ni feature flags.

## Preguntas abiertas

- [ ] **Remisión productiva a la AEAT**: pendiente del certificado electrónico de la
      titular (custodia en el servidor, nunca sale ni se loguea). Bloquea `VerifactuEngine`
      en producción, no la cadena de huellas local.
- [ ] Flujo "Convertir en factura" (F3, sustitución de simplificadas): ADR pendiente si se
      detalla (ADR-0008).
- [ ] ¿Formalizar `Remitente` / `Reloj` / `Impresora` como `Protocol` en
      `dominio/puertos.py`? Hoy son adaptadores; decisión coste/beneficio a escala monopuesto.
