# VERIFACTU — Esquemas y especificación técnica (Orden HAC/1177/2024)

Guía de implementación del motor fiscal (`app/fiscal/`). Resume la Orden HAC/1177/2024
(BOE-A-2024-22138, 28/10/2024) y señala qué detalles se completan con la documentación
técnica de la sede de la AEAT.

## 0. Fuentes normativas y técnicas (por orden de autoridad)

1. **RD 1007/2023 (RRSIF)** — BOE-A-2023-24840. Requisitos de fondo (arts. 8, 15, 16).
2. **Orden HAC/1177/2024** — BOE-A-2024-22138. Especificaciones técnicas; el ANEXO
   contiene la estructura, campos, formatos y listas de valores de los registros.
3. **Sede AEAT → "Sistemas Informáticos de Facturación y VERI*FACTU" → Información
   técnica**: XSD oficiales, documento de "Detalle de las especificaciones técnicas
   para generación de la huella", especificación de la URL del QR, validaciones y
   errores, y direcciones de los servicios web (producción y PRUEBAS).
   ⚠️ TAREA PREVIA: descargar los XSD y documentos vigentes de la sede a `schemas/`
   y validar todo XML generado contra ellos en los tests. No programar "de memoria".

La DA 1ª de la Orden habilita a la AEAT a publicar en sede los detalles del algoritmo
de huella, la política de firma y las características de la URL del QR: esos detalles
concretos SIEMPRE se toman del documento de sede, no de terceros.

## 1. Reglas generales de formato (arts. 10-11 y anexo)

- XML con codificación **UTF-8**, estructura y contenido según el anexo de la Orden.
- Importes: decimales con punto, 2 decimales (`CuotaTotal`, `ImporteTotal`...).
- Fechas de factura: `dd-mm-aaaa`. Fecha-hora de generación del registro
  (`FechaHoraHusoGenRegistro`): ISO 8601 con huso horario (p. ej.
  `2027-07-01T10:15:30+02:00`). La fecha de expedición de la factura debe coincidir
  con la de generación del registro (las incidencias de envío no alteran esto).
- La remisión agrupa 1 a 1.000 registros por mensaje.

## 2. Estructura del mensaje de remisión (anexo, apdo. bloques)

```
RegFactuSistemaFacturacion
├── Cabecera
│   ├── ObligadoEmision { NombreRazon, NIF }
│   ├── Representante { ... }                (opcional)
│   └── RemisionVoluntaria                   (solo VERI*FACTU)
│       ├── FechaFinVeriFactu                (solo para renunciar; ver §7)
│       └── Incidencia (S/N)                 (S si hubo incidencia que retrasó envíos)
└── RegistroFactura (1..1000)
    ├── RegistroAlta        | o bien
    └── RegistroAnulacion
```

## 3. RegistroAlta — campos principales

(Estructura del anexo; nombres exactos, obligatoriedad y listas: validar contra XSD.)

| Campo | Contenido | Notas para este TPV |
|---|---|---|
| `IDVersion` | Versión del esquema | La vigente según sede |
| `IDFactura/IDEmisorFactura` | NIF del obligado a expedir | NIF de la titular |
| `IDFactura/NumSerieFactura` | Serie+número (hasta 60 chars) | p. ej. `T2027-000123` |
| `IDFactura/FechaExpedicionFactura` | dd-mm-aaaa | |
| `NombreRazonEmisor` | Nombre/razón social | |
| `TipoFactura` | Lista L2 | **F2** simplificada (tickets), **F1** completa, **F3** emitida en sustitución de simplificadas, **R1-R4** rectificativas, **R5** rectificativa de simplificadas |
| `TipoRectificativa` | S (sustitución) / I (diferencias) | Solo R1-R5 |
| `FacturasRectificadas` / `FacturasSustituidas` | IDs de las facturas afectadas | F3 → FacturasSustituidas; R* → FacturasRectificadas |
| `ImporteRectificacion` | Base/cuota rectificadas | Solo sustitución |
| `FechaOperacion` | Si difiere de expedición | Normalmente omitido en TPV |
| `DescripcionOperacion` | Texto libre (500) | p. ej. "Venta al por menor acuariofilia" |
| `FacturaSimplificadaArt7273` | S/N | Marcaje de simplificadas según art. 7.2/7.3 ROF |
| `Destinatarios/IDDestinatario` | NIF o IDOtro + nombre | Obligatorio en F1/F3; en F2 no se identifica destinatario |
| `Desglose/DetalleDesglose` | Por tipo impositivo | Ver §3.1 |
| `CuotaTotal` | Suma de cuotas | |
| `ImporteTotal` | Total factura | |
| `Encadenamiento` | `PrimerRegistro=S` o `RegistroAnterior{IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, Huella}` | Ver §5 |
| `SistemaInformatico` | Ver §3.2 | |
| `FechaHoraHusoGenRegistro` | ISO 8601 con huso | |
| `TipoHuella` | `01` = SHA-256 | |
| `Huella` | Hash del propio registro | Ver §4 |

### 3.1. Desglose (por cada tipo de IVA presente en el ticket)

- `Impuesto` = 01 (IVA) · `ClaveRegimen` = 01 (régimen general) para este TPV.
- `CalificacionOperacion` = **S1** (sujeta y no exenta, sin inversión del sujeto pasivo)
  en la operativa normal de la tienda.
- `TipoImpositivo` (21.00 / 10.00), `BaseImponibleOimporteNoSujeto`, `CuotaRepercutida`.
- El TPV vende PVP con IVA incluido: derivar base y cuota por tipo con la función única
  de redondeo y cuadrar: Σ bases + Σ cuotas = `ImporteTotal` (las validaciones de la
  AEAT admiten tolerancias mínimas de céntimos; comprobar documento de validaciones).
- Nota: la titular está en recargo de equivalencia como VENDEDORA minorista; el RE no se
  repercute en sus ventas (solo lo soportan sus compras), así que los campos de recargo
  del desglose NO se usan en este TPV.

### 3.2. Bloque `SistemaInformatico` (en cada registro)

`NombreRazon` y `NIF` del productor del software (el desarrollador),
`NombreSistemaInformatico`, `IdSistemaInformatico` (código corto asignado por el
productor), `Version`, `NumeroInstalacion`, e indicadores
`TipoUsoPosibleSoloVerifactu`, `TipoUsoPosibleMultiOT`, `IndicadorMultiplesOT`.
Debe ser coherente con la **declaración responsable** (art. 15 de la Orden): mismo
nombre, id y versión. Cambiar de versión ⇒ actualizar ambos.

## 4. Huella (art. 13 de la Orden)

Composición VERIFICADA en la Orden — la huella se calcula sobre este subconjunto, en
este orden:

- **Registro de alta**: NIF del emisor + Número y serie de factura + Fecha de
  expedición + Tipo de factura + Cuota total + Importe total + **Huella del registro
  anterior** + Fecha, hora y huso de generación del registro.
- **Registro de anulación**: NIF del emisor + Número y serie + Fecha de expedición +
  Huella del registro anterior + Fecha, hora y huso de generación.

Detalles de cómputo (documento de sede "generación de la huella" — confirmar allí):
cadena de entrada tipo `campo1=valor1&campo2=valor2&...` con los valores sin espacios
sobrantes, UTF-8, algoritmo **SHA-256**, salida en hexadecimal MAYÚSCULAS (64 chars).
En el primer registro del sistema, el término "huella anterior" va vacío y el bloque
`Encadenamiento` lleva `PrimerRegistro=S` (art. 7 de la Orden: la excepción del primer
registro tras la instalación).

Implementación exigida por la Orden (arts. 6-7): el sistema debe poder **verificar** la
huella de cualquier registro y recorrer la cadena hacia delante y hacia atrás indicando
si el encadenamiento y el orden temporal son correctos (⇒ implementar
`verify_chain()` y exponerlo en la consola); si se detecta una vulneración de la
integridad, mostrar **alarma persistente** en todos los terminales y generar el evento.

## 5. Encadenamiento

Cadena ÚNICA por sistema informático (no por serie): cada registro (alta o anulación)
referencia al inmediatamente anterior generado por el sistema mediante
`RegistroAnterior{IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, Huella}`.
Consecuencia de diseño: la generación de registros es **secuencial y serializada**
(lock/single-writer); jamás en paralelo.

## 6. QR y leyenda (arts. 20-21 de la Orden)

- QR conforme a ISO/IEC 18004, tamaño entre **30x30 y 40x40 mm** en el ticket, con la
  URL de cotejo de la sede de la AEAT llevando NIF emisor, número/serie, fecha e
  importe total (formato exacto de la URL: especificación de sede; usar la URL de
  PRUEBAS en el entorno de pruebas).
- Encima/junto al QR, el texto que indique la especificación de sede; y al operar como
  VERI*FACTU, la leyenda **"Factura verificable en la sede electrónica de la AEAT"** o
  **"VERI*FACTU"**.
- La impresora térmica de 80 mm imprime ~72 mm útiles: reservar zona del QR en la
  plantilla y verificar legibilidad real con el documento de sede (nivel de corrección
  de errores incluido).

## 7. Flujo de remisión VERI*FACTU (arts. 16-17 de la Orden)

- Envío de registros al servicio web de la AEAT (SOAP, autenticación con certificado
  electrónico; endpoints de PRODUCCIÓN y PRUEBAS publicados en sede — el entorno de
  pruebas está operativo desde el 29/7/2025).
- **Control de flujo**: la respuesta de la AEAT indica un tiempo de espera entre
  envíos; respetarlo y agrupar los registros generados en ese intervalo (máx. 1.000).
- **Incidencias** (texto de la Orden): si algo impide la remisión, remitir en cuanto
  sea posible respetando el orden temporal de generación, marcando la incidencia en el
  campo habilitado de los mensajes afectados; **reintentar al menos una vez cada
  hora**; y avisar al usuario de que hay registros pendientes indicando cuántos faltan.
- **Respuestas**: estados por registro (aceptado / aceptado con errores / rechazado).
  Los rechazados se corrigen y reenvían (subsanación) sin romper la cadena local: el
  registro local no se modifica jamás; la subsanación es un nuevo envío conforme al
  mecanismo previsto en las validaciones de sede.
- **Renuncia a VERI*FACTU**: cumplimentando `FechaFinVeriFactu` en la cabecera de un
  envío antes de fin del año natural (art. 16.5 RRSIF: la opción vincula al menos
  hasta fin del año natural del primer envío efectivo). Antes del 1/7/2027 rige el
  periodo de pruebas (nota AEAT): los envíos de prueba no vinculan.

## 8. Registro de eventos (art. 9) y firma (art. 14) — SOLO modo NO VERI*FACTU

Operando como VERI*FACTU no se exige ni la firma de los registros ni el registro de
eventos formal. Si algún día se operase en modo NO VERI*FACTU: firma **XAdES Enveloped**
(ETSI EN 319 132) de cada registro, y registro de eventos con su propia cadena de
huellas (campos del hash de evento: id. productor + id. sistema + versión + nº
instalación + NIF obligado + tipo de evento + huella del evento anterior + fecha-hora-huso).
El diseño del TPV mantiene un log de auditoría propio en todo caso (invariante 4 de
CLAUDE.md), lo que dejaría este modo a un paso.

## 9. Checklist de tests mínimos del motor

1. Huella: vectores de prueba calculados a mano contra el documento de sede
   (alta, anulación, primer registro con huella anterior vacía).
2. Cadena: alta → alta → anulación → alta; `verify_chain()` detecta cualquier
   alteración de un campo intermedio.
3. Serialización XML válida contra los XSD oficiales de `schemas/` (F1, F2, F3, R5).
4. Cuadre de desglose multi-tipo (21 % + 10 % en el mismo ticket) con PVP IVA incluido.
5. Cola: caída de red simulada → marca de incidencia en el siguiente envío, reintento
   horario, orden temporal preservado, contador de pendientes visible.
6. Inmutabilidad: UPDATE/DELETE sobre venta emitida o registro → rechazado por la BD.
7. Reloj: desviación temporal del sistema detectada al arrancar.
