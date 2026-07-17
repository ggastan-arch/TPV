# TPV AcuaTPV

TPV táctil monopuesto para una tienda de acuariofilia (peces tropicales, plantas,
complementos). Sistema Informático de Facturación (SIF) sujeto al RD 1007/2023 (RRSIF) y
la Orden HAC/1177/2024, preparado para operar en modalidad **VERI\*FACTU**: cada venta
genera una **factura simplificada** con su registro fiscal encadenado por huella SHA-256 y
remisible a la AEAT. 

> Contexto y decisiones de negocio: `docs/TPV_ACUATPV_consideraciones.md` ·
> especificación fiscal: `docs/VERIFACTU_ESQUEMAS_HAC1177.md` ·
> arquitectura y ADR: `docs/ARCHITECTURE.md` y `docs/adr/`.

## 🚀 Demo en vivo

**URL:** https://tpv-acuatpv-demo.onrender.com/

> ⏳ La primera carga puede tardar ~50 s: el plan gratuito de Render duerme el
> servicio tras un rato de inactividad y lo despierta bajo demanda. Recarga si ves
> un error 503 momentáneo.

El despliegue corre en **modo demo**: base de datos aislada con datos ficticios, sin
certificado y sin remisión a la AEAT (nada tiene validez fiscal). Credenciales de prueba:

| Rol | Usuario | PIN / Contraseña |
|---|---|---|
| Administración | `admin` | `1234` |
| Venta (TPV) | — (solo PIN) | `0000` |

El TPV (`/tpv`) pide únicamente el PIN. En la consola (`/admin`) el usuario es `admin` y la
contraseña es su PIN (`1234`). La raíz `/` es la portada con accesos a ambos.

## Stack

Python 3.12+ · FastAPI · SQLAlchemy 2 + SQLite (WAL) · Alembic · lxml · segno ·
python-escpos · pytest. Frontend en HTML/JS servido por FastAPI. Despliegue con Docker.

## Puesta en marcha (local)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows (Linux/Mac: .venv/bin/…)
make migrate      # o: python -m alembic upgrade head
make seed         # datos de ejemplo (familias, artículos, botonera)
make dev PORT=8123   # servidor: http://127.0.0.1:8123/  (TPV en /tpv, admin en /admin)
make test         # pytest (invariantes fiscales, huella, redondeo, concurrencia)
```

### Modo demo (datos de prueba, sin validez fiscal)

Perfil aislado (ADR-0009): BD propia `tpv_demo.db`, certificado nunca cargado, motor
`NullEngine` (genera la cadena de huella pero no remite). Cada ticket queda marcado como
"DOCUMENTO DE PRUEBA · SIN VALIDEZ FISCAL".

```bash
make demo         # migra + siembra tpv_demo.db (aislada de tpv.db)
TPV_PROFILE=demo make dev PORT=8123
```

### Configuración (variables de entorno, prefijo `TPV_`)

Copiar a un `.env` local (no se versiona). Principales:

| Variable | Por defecto | Descripción |
|---|---|---|
| `TPV_PROFILE` | `produccion` | `produccion` \| `demo` (perfil aislado) |
| `TPV_DB_PATH` | `tpv.db` | Ruta de la BD SQLite |
| `TPV_SESSION_SECRET` | _(dev)_ | Secreto de la cookie de sesión admin. **Obligatorio en despliegue** |
| `TPV_NIF_EMISOR` / `TPV_NOMBRE_EMISOR` | `00000000T` / `AcuaTPV` | Obligado a expedir |
| `TPV_NIF_PRODUCTOR` / `TPV_NOMBRE_PRODUCTOR` | — | Productor del software (SistemaInformatico) |
| `TPV_ENTORNO_AEAT` | `pruebas` | `pruebas` \| `produccion` |
| `TPV_CERTIFICADO_CERT_PATH` / `_KEY_PATH` | — | Certificado (rutas locales, **fuera del repo**) |
| `TPV_IMPRESORA_TIPO` | `dummy` | `dummy` \| `network` |

## Despliegue (Render, Docker)

El repo incluye `Dockerfile`, `docker-entrypoint.sh` y `render.yaml` (Blueprint). En
Render: **New → Blueprint → conectar este repo**. Render construye la imagen, inyecta
`$PORT`, fija `TPV_PROFILE=demo` y **genera** un `TPV_SESSION_SECRET` aleatorio. El
contenedor migra y siembra `tpv_demo.db` en cada arranque; en el filesystem efímero del
plan gratuito, cada arranque en frío deja el demo limpio (reset automático).

## Estructura del proyecto

Arquitectura hexagonal (ver `docs/ARCHITECTURE.md`):

```
app/
  dominio/          # entidades y puertos; puro en runtime (sin dependencias de infra)
  aplicacion/       # casos de uso (emitir venta, remitir lote, cierre Z…)
  infraestructura/  # config, persistencia (SQLAlchemy), fiscal (huella/XML/QR/SOAP),
                    # impresión ESC/POS, seguridad, reloj
  presentacion/     # routers FastAPI: landing (/), tpv (/tpv), admin (/admin), health
  ui/               # frontend: landing.html, tpv.html, admin.html
migrations/         # Alembic (esquema con triggers de inmutabilidad + cadena de huella)
schemas/            # XSD/WSDL oficiales de la AEAT (públicos; los tests los usan)
tests/              # pytest — incluye tests de invariantes fiscales y golden de la AEAT
docs/               # contexto de negocio, especificación fiscal, ARCHITECTURE, ADR
```

## Funcionalidades principales

- **Venta táctil**: botonera configurable (perfiles → páginas → botones de artículo /
  familia / función), búsqueda, escáner (keyboard wedge), edición de línea, precio libre y
  venta al peso, aviso CITES. El dinero se calcula siempre en el servidor con `Decimal`.
- **Motor fiscal VERI\*FACTU**: registro de alta/anulación con huella SHA-256 encadenada,
  numeración correlativa sin huecos, QR tributario, sobre SOAP y cola de remisión con
  reintentos. Huella validada contra los vectores oficiales; XML contra los XSD.
- **Consola de administración**: catálogo (artículos, IVA, familias en árbol), clientes,
  usuarios, editor de botonera, control de stock, cierre Z y panel fiscal (estado de la
  cola, integridad de la cadena, reintento/reencolado).
- **Impresión**: ticket ESC/POS 80 mm con QR y apertura de cajón.
- **Modo demo** aislado para pruebas/despliegue público.

## Estado

- **Fase 1 — núcleo** ✅ — inmutabilidad a nivel de BD (triggers), numeración correlativa,
  redondeo fiscal único, cadena de huellas.
- **Fase 2 — motor VERI\*FACTU** ✅ — huella (vectores oficiales), XML alta/anulación (XSD),
  QR, sobre de remisión, cola con reintentos, cliente SOAP. **Primer contacto real con el
  entorno de pruebas de la AEAT: correcto (CSV asignado)**; parser de respuesta validado
  con un _golden test_ sobre una respuesta real.
- **UI TPV táctil** ✅ · **Consola de administración** ✅ · **Cierre Z** ✅ · **Modo demo** ✅.
- Pendiente: import/export Excel y Litestream (backup).

## Invariantes fiscales

Los importes usan `Decimal` (nunca `float`). Ninguna venta emitida se edita ni se borra
(inmutabilidad garantizada por triggers de BD): las correcciones van por anulación o
factura rectificativa. Series correlativas sin huecos. Log de auditoría append-only. El
certificado nunca sale del servidor. Sin `make test` verde de los invariantes, una feature
no está terminada.

## ⚠️ Seguridad (repositorio público)

Este repositorio es **público**. NUNCA se debe subir:

- **El certificado electrónico** de la persona titular (`*.pfx`, `*.p12`, `*.pem`, `*.key`…).
  Nunca sale del servidor de la tienda (invariante 7). Cubierto por `.gitignore`; verificá
  `git status` antes de cada push.
- **La base de datos** (`tpv.db*`): cadena de registros fiscales y datos personales de
  clientes (RGPD + secreto tributario). Ignorada.
- **El fichero `.env`** con configuración/secretos locales. Ignorado.

Los XSD/WSDL oficiales de la AEAT (`schemas/`) y las specs de sede (`docs/Verifactu/`) sí
se versionan: son públicos y los tests los necesitan.
