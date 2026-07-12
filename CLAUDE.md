# CLAUDE.md — TPV AcuaTPV

Contexto operativo para Claude Code. Leer también `docs/TPV_ACUATPV_consideraciones.md`
(decisiones de negocio y marco normativo) y `docs/VERIFACTU_ESQUEMAS_HAC1177.md`
(especificación técnica del motor fiscal). Ante conflicto, ese orden de prevalencia:
normativa > consideraciones > este fichero.

## Qué es este proyecto

TPV táctil monousuario para una tienda de acuariofilia (peces tropicales, plantas,
complementos) en territorio común (AEAT). Un puesto de venta físico + consola de
administración web accesible en remoto vía Tailscale. La persona titular tributa en IRPF por
estimación objetiva y en recargo de equivalencia de IVA.

**Decisión fiscal cerrada (no reabrir):** todos los tickets se expiden como FACTURAS
SIMPLIFICADAS. El TPV es un Sistema Informático de Facturación (SIF) sujeto al
RD 1007/2023 (RRSIF) y a la Orden HAC/1177/2024, y operará en modalidad VERI*FACTU
(remisión voluntaria anticipada de registros a la AEAT).

## Stack

- Python 3.12+, FastAPI, SQLite (modo WAL) + SQLAlchemy, Alembic para migraciones.
- Frontend TPV y consola: web (HTML/JS servidos por FastAPI; el TPV corre a pantalla
  completa en el equipo táctil de la tienda).
- Impresión: `python-escpos` (Epson 80 mm, cajón por pulso RJ11, QR en ticket).
- Excel: `openpyxl`.
- Replicación/backup: Litestream hacia almacenamiento S3-compatible.
- Tests: `pytest`. Sin test del invariante correspondiente, una feature no está terminada.

## Estructura del proyecto

```
app/
  core/          # config, seguridad, auditoría
  models/        # SQLAlchemy: articulo, familia, boton, cliente, venta, registro_fiscal...
  api/           # routers FastAPI (tpv, admin, fiscal)
  fiscal/        # motor fiscal — ver "FiscalEngine" abajo
  printing/      # ESC/POS, plantillas de ticket, QR
  importer/      # import/export Excel con dry-run
  ui/            # frontend TPV y consola
migrations/      # Alembic
tests/
docs/            # los .md de contexto
```

## Invariantes INNEGOCIABLES (art. 29.2.j LGT + RRSIF)

Estos invariantes existen por obligación legal. Cualquier PR que los debilite es un error,
aunque "simplifique" el código:

1. **Ninguna venta emitida se borra ni se edita.** No existe `DELETE` ni `UPDATE` sobre
   ventas emitidas ni sobre registros de facturación. Corregir = factura rectificativa
   (nueva alta vinculada) o registro de anulación. Implementar a nivel de BD (triggers
   que rechacen UPDATE/DELETE sobre filas emitidas), no solo en la capa de aplicación.
2. **Series correlativas sin huecos ni reutilización.** La numeración se asigna en la
   misma transacción que emite el documento. Series separadas: simplificadas (T),
   completas (F), rectificativas (R).
3. **Registro de facturación por cada factura**, generado en el momento de la expedición,
   con huella SHA-256 encadenada al anterior conforme a
   `docs/VERIFACTU_ESQUEMAS_HAC1177.md`. La fecha de expedición coincide con la de
   generación del registro.
4. **Log de auditoría append-only**: descuentos, anulaciones, aperturas de cajón sin
   venta, cambios de precio, importaciones, accesos de administración (locales y remotos).
5. **Nada de "modo formación"** ni ninguna vía que imprima tickets no contabilizados.
6. **El reloj importa**: las horas se almacenan con huso (`FechaHoraHusoGenRegistro`
   ISO 8601 con offset). Verificar desviación del reloj del sistema al arrancar.
7. **El certificado electrónico nunca sale del servidor** de la tienda ni se registra en
   logs. La remisión a la AEAT la hace solo el servidor.

## FiscalEngine

Interfaz única en `app/fiscal/engine.py`:

- `emit(venta) -> RegistroAlta`   # genera registro, huella, QR; encola remisión
- `cancel(registro) -> RegistroAnulacion`
- `verify_chain(desde, hasta) -> informe`  # exigido por la Orden (trazabilidad)

Implementaciones: `VerifactuEngine` (objetivo) y `NullEngine` solo para desarrollo local
(genera registros y cadena igualmente, pero no remite). La estructura del registro y la
huella se implementan SIEMPRE, incluso con NullEngine: el encadenamiento no es opcional.

Reglas de remisión (modalidad VERI*FACTU): cola persistente FIFO respetando orden de
generación; respetar el tiempo de espera que devuelva la AEAT en la respuesta; ante
incidencia de conectividad, marcar el campo de incidencia en el siguiente envío y
reintentar al menos una vez por hora; alarma visible en TPV y consola con nº de
registros pendientes.

## Reglas de negocio clave

- Precios PVP con IVA incluido. Regla de redondeo única (por línea, half-up a 2
  decimales) implementada en UNA función con tests exhaustivos. `Decimal`, jamás `float`,
  para importes.
- Tipos de IVA por artículo (tabla, no hardcode): peces 21 %, plantas vivas ornamentales
  10 %, alimentación animal 21 %, complementos 21 %.
- Factura simplificada: contenido del art. 7 ROF; límite 3.000 € IVA incluido en venta
  minorista → por encima, forzar factura completa (F1).
- Simplificada "cualificada" (art. 7.2 ROF): botón rápido que añade NIF + domicilio del
  destinatario y cuota separada.
- "Convertir en factura": factura completa en sustitución de simplificada(s) →
  TipoFactura F3 con bloque FacturasSustituidas.
- Devolución: rectificativa R5 (de simplificada) o R1-R4 según caso.
- Artículos: id interno estable, N códigos de barras por artículo, familia en árbol
  ilimitado, flag CITES, flag precio libre. Artículos con ventas nunca se borran
  (solo `activo=false`).
- Botonera: entidad propia (perfiles → páginas → rejilla de botones); botón = artículo |
  familia | función. Editable desde la consola.
- Import Excel: upsert por código interno, dry-run obligatorio con informe, nunca dar de
  baja por omisión, EAN siempre como texto (validar dígito de control).

## Convenciones

- Código y comentarios en español (dominio fiscal español; los nombres de campos fiscales
  deben coincidir con el anexo de la Orden: `NumSerieFactura`, `CuotaTotal`, etc.).
- Migraciones Alembic siempre; nunca `create_all` en producción.
- Endpoints admin bajo `/admin`, protegidos con sesión + rol; TPV bajo `/tpv` con PIN.
- Toda excepción en la cola fiscal se registra y se reintenta; nunca se descarta un
  registro en silencio.

## Comandos

```
make dev        # servidor local con recarga
make test       # pytest (incluye tests de invariantes y de huella)
make migrate    # alembic upgrade head
make seed       # datos de ejemplo (familias/artículos acuariofilia)
```

## Qué NO hacer

- No introducir dependencias de red en el flujo de cobro (la venta debe cerrarse offline).
- No "optimizar" la cadena de huellas con procesamiento en paralelo: es secuencial por
  definición.
- No inventar campos ni valores de listas del anexo de la Orden: ante duda, consultar
  `docs/VERIFACTU_ESQUEMAS_HAC1177.md` y los XSD oficiales descargados en `schemas/`.
- No tocar el esquema de las tablas de ventas/registros sin revisar el impacto en la
  cadena de huellas y en los triggers de inmutabilidad.
