# TPV Bizkaitropik

TPV táctil monopuesto para tienda de acuariofilia. Sistema Informático de Facturación
(SIF) sujeto al RD 1007/2023 (RRSIF) y la Orden HAC/1177/2024, preparado para operar en
modalidad **VERI\*FACTU**. Todos los tickets se expiden como **facturas simplificadas**.

> Contexto y decisiones: `docs/TPV_BIZKAITROPIK_consideraciones.md`,
> `docs/VERIFACTU_ESQUEMAS_HAC1177.md` y `CLAUDE.md`.

## ⚠️ Seguridad (repositorio público)

Este repositorio es **público**. NUNCA se debe subir:

- **El certificado electrónico** de la titular (`*.pfx`, `*.p12`, `*.pem`, `*.key`, …).
  El certificado **nunca sale del servidor de la tienda** (invariante 7). Está cubierto
  por `.gitignore`, pero verificá `git status` antes de cada push.
- **La base de datos** (`tpv.db*`): contiene la cadena de registros fiscales y datos
  personales de clientes (RGPD + secreto tributario). Ignorada por `.gitignore`.
- **El fichero `.env`** con configuración/secretos locales. Ignorado.

Los XSD/WSDL oficiales de la AEAT (`schemas/`) y las specs de sede (`docs/Verifactu/`)
sí se versionan: son públicos y los tests los necesitan.

## Stack

Python 3.12+ · FastAPI · SQLAlchemy 2 + SQLite (WAL) · Alembic · lxml · segno ·
python-escpos · pytest.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
make migrate      # o: python -m alembic upgrade head
make seed         # datos de ejemplo (familias, artículos, botonera)
make dev PORT=8123   # servidor: http://127.0.0.1:8123/tpv/  (health: /health)
make test         # pytest
```

### Configuración (variables de entorno, prefijo `TPV_`)

Copiar a un `.env` local (no se versiona). Principales:

| Variable | Por defecto | Descripción |
|---|---|---|
| `TPV_DB_PATH` | `tpv.db` | Ruta de la BD SQLite |
| `TPV_NIF_EMISOR` / `TPV_NOMBRE_EMISOR` | `00000000T` / `Bizkaitropik` | Obligado a expedir |
| `TPV_NIF_PRODUCTOR` / `TPV_NOMBRE_PRODUCTOR` | — | Productor del software (SistemaInformatico) |
| `TPV_ID_SISTEMA` | `BZ` | IdSistemaInformatico (máx. 2 chars) |
| `TPV_ENTORNO_AEAT` | `pruebas` | `pruebas` \| `produccion` |
| `TPV_CERTIFICADO_CERT_PATH` / `_KEY_PATH` | — | Certificado (rutas locales, **fuera del repo**) |
| `TPV_IMPRESORA_TIPO` | `dummy` | `dummy` \| `network` |

## Estado

- **Fase 1 — núcleo**: modelo de datos con inmutabilidad a nivel de BD (triggers),
  numeración correlativa sin huecos, redondeo fiscal único, cadena de huellas. ✅
- **Fase 2 — motor VERI\*FACTU**: huella (validada contra vectores oficiales), XML de
  alta/anulación (validado contra XSD), QR, sobre de remisión, cola con reintentos,
  validaciones de negocio y cliente SOAP (listo para certificado). ✅
- **UI TPV táctil**: pantalla de venta con botonera, cobro y ticket con QR. 🚧 (en curso)
- Pendiente: consola de administración, import/export Excel, informes/cierre Z,
  Litestream (backup), y la primera remisión real contra el entorno de pruebas AEAT.

Los importes usan `Decimal` (nunca `float`). Ninguna venta emitida se edita o borra:
correcciones vía anulación o factura rectificativa. Sin `make test` verde de los
invariantes, una feature no está terminada.
