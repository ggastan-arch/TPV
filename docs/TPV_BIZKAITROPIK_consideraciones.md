# TPV Bizkaitropik — Consideraciones previas al desarrollo (v2)

Documento de análisis previo, actualizado: la titular tiene su domicilio fiscal en **Cantabria (territorio común, AEAT)**. No aplica TicketBAI/Batuz; el sistema de referencia es **VeriFactu (RRSIF)**. Pensado para servir de contexto/requisitos a Claude Code.

---

## 1. Marco normativo (territorio común)

### 1.1. Calendario y normas de referencia

- **RD 1007/2023** (Reglamento de requisitos de los sistemas informáticos de facturación, RRSIF) y **Orden HAC/1177/2024** (especificaciones técnicas: registro de facturación, huella, QR, remisión).
- **Obligatoriedad aplazada por el RDL 15/2025**: 1/1/2027 para contribuyentes de IS; **1/7/2027 para autónomos y resto** (caso de la titular). El periodo anterior es, según nota de la AEAT, un periodo de pruebas.
- **Vigente YA, sin aplazamiento**: la prohibición de software de doble uso del **art. 29.2.j) LGT** y el régimen sancionador del **art. 201 bis LGT** (Ley 11/2021, en vigor desde 11/10/2021). Es decir: aunque VeriFactu no sea aún exigible, el TPV **no puede permitir** desde el primer día ocultar, borrar o alterar registros de ventas. Sanciones del 201 bis: 50.000 €/ejercicio para el usuario que tenga software no certificado cuando sea exigible; 150.000 €/ejercicio para fabricantes.

### 1.2. Régimen de la titular y decisión adoptada (DEFINITIVA)

La titular tributa en **IRPF por estimación objetiva (módulos)** y en **recargo de equivalencia** en IVA. Aunque el art. 3.1.b) del ROF (RD 1619/2012, redacción del RD 1073/2014) la exime de expedir factura por las ventas minoristas, **se opta deliberadamente por que todos los tickets sean facturas simplificadas**:

1. **Todos los tickets del TPV son facturas simplificadas** (arts. 4 y 7 ROF). El TPV es, por tanto, un **SIF sujeto al RRSIF**, con obligación de estar adaptado el 1/7/2027.
2. **Anticipación voluntaria en modalidad VERI*FACTU**: el art. 16 RRSIF permite remitir voluntariamente todos los registros de facturación a la AEAT ("Sistemas de emisión de facturas verificables"). Ventajas: se **presume que cumplen por diseño** los requisitos de inalterabilidad, quedan **dispensados de conservar copia de los registros** (obran en poder de la AEAT), y **no exigen firma electrónica de los registros ni registro de eventos** formal — las tres piezas técnicamente más costosas del modo NO VERI*FACTU. Las facturas llevan la leyenda "Factura verificable en la sede electrónica de la AEAT" / "VERI*FACTU".
3. **Reglas de calendario**: la opción VERI*FACTU es tácita (iniciar sistemáticamente la remisión) y vincula al menos hasta el fin del año natural del primer envío efectivo (art. 16.5 RRSIF). No obstante, hasta el 1/7/2027 rige un **periodo de pruebas** (nota AEAT tras el RDL 15/2025): se pueden remitir registros de prueba y dejar de hacerlo sin quedar vinculado, lo que da margen para desarrollar y probar contra los servicios reales de la AEAT antes de operar en firme.
4. **Declaración responsable** (art. 13 RRSIF): el productor del software —aquí el propio desarrollador— la emite y debe constar en el sistema (software, versión, productor). No hay homologación ni registro previo.
5. **Informe de vigilancia de módulos**: la consola debe mostrar el volumen anual de ingresos y las operaciones facturadas a empresarios, para controlar las **magnitudes excluyentes** de estimación objetiva y del RE. Si pasara a estimación directa, nada cambia en el TPV: ya estaría operando como SIF pleno.

### 1.3. Requisitos técnicos VeriFactu a los que preparar el software

El RRSIF exige que el SIF garantice **integridad, inalterabilidad, trazabilidad, conservación, accesibilidad y legibilidad** de los registros. En concreto:

1. **Registro de facturación de alta** generado en el momento de expedir cada factura (incluidas las simplificadas), y **registro de anulación** cuando proceda. Formato y campos según la Orden HAC/1177/2024.
2. **Huella (hash SHA-256) encadenada** con el registro anterior.
3. **Código QR** en toda factura/ticket, con la URL de cotejo de la AEAT; si se opera en modalidad VERI*FACTU, la leyenda "Factura verificable en la sede electrónica de la AEAT / VERI*FACTU".
4. **Dos modalidades de funcionamiento** — decisión de diseño nº 2:
   - **VERI*FACTU**: remisión de cada registro a la AEAT en el momento de la expedición. A cambio, **no exige firma electrónica de los registros ni registro de eventos**. Más simple de implementar; requiere conectividad (con cola y reintento ante incidencias).
   - **NO VERI*FACTU**: todo local, pero exige **firma electrónica de los registros**, **registro de eventos** del sistema y plena disposición ante requerimientos de la AEAT.
   - Para una tienda con internet estable, la modalidad VERI*FACTU es la recomendable: elimina la firma (el punto técnicamente más delicado) y da imagen de transparencia.
5. **Declaración responsable del SIF** (art. 13 RRSIF): el productor del software (aquí, el propio desarrollador) declara que cumple el reglamento; debe constar en el propio sistema, identificando software, versión y productor. **No hay homologación ni registro previo** (a diferencia de TBAI): más sencillo, pero la responsabilidad recae en quien declara.
6. Nada de "modo formación" que imprima tickets reales, ni borrado/edición de ventas: anulación = **registro de anulación** + en su caso factura rectificativa.
7. **Log de eventos** y auditoría interna: aunque en modalidad VERI*FACTU no es exigible el registro de eventos formal, conviene implementarlo (descuentos, anulaciones, aperturas de cajón sin venta, cambios de precio) — es barato ahora y necesario si algún día se opera en modalidad NO VERI*FACTU.

### 1.4. Arquitectura: motor fiscal intercambiable

Aislar el cumplimiento tras una interfaz **`FiscalEngine`** con tres implementaciones posibles: `NullEngine` (fase inicial, sin remisión, pero ya con inalterabilidad, series y encadenamiento interno), `VerifactuEngine` (alta/anulación, hash, QR, remisión AEAT) y, si algún día volviera a territorio foral, `TicketBaiEngine`. VeriFactu y TBAI comparten conceptos (registro inalterable, encadenamiento, QR), así que el coste marginal de esta abstracción es bajo y protege la inversión ante mudanzas de domicilio fiscal o cambios normativos.

> Importante: "prepararlo para VeriFactu" no es solo dejar un hueco. Las restricciones estructurales (tickets inmutables, series correlativas, anulación por registro específico, datos del registro de alta capturados en el momento de la venta) deben estar en el **modelo de datos desde la fase 1**, porque son casi imposibles de retro-encajar.

---

## 2. Reglas de facturación que el TPV debe implementar

- **Ticket = factura simplificada** (ver §1.2), válida hasta 400 €, o hasta **3.000 € IVA incluido en ventas al por menor** (art. 4 ROF). Si una venta supera el límite, el TPV debe forzar factura completa.
- **Contenido mínimo del art. 7 ROF** en la plantilla: número y serie correlativos, fecha de expedición, NIF y nombre del emisor, descripción de las operaciones, tipo impositivo (u opcionalmente "IVA incluido"), contraprestación total. Más el **QR tributario** y, en modalidad VERI*FACTU, la leyenda correspondiente.
- **Factura simplificada "cualificada"** (art. 7.2 ROF): si el cliente empresario quiere deducir, basta añadir NIF y domicilio del destinatario y la cuota repercutida consignada por separado — función rápida en el TPV que evita muchas conversiones a factura completa.
- **"Convertir en factura"**: factura completa expedida **en sustitución** de la simplificada, referenciando la sustituida (tratamiento específico en el registro de facturación; nunca "reimprimir con NIF").
- **Series de numeración** separadas y correlativas: simplificadas, completas, rectificativas. Sin huecos ni reutilización.
- **Devoluciones**: siempre mediante **factura rectificativa** (arts. 15 ROF; claves R1–R5 del registro), también de simplificadas; prever devolución parcial de líneas.
- **Tipos de IVA por artículo** (tabla configurable, nunca hardcodeado):
  - Peces y animales ornamentales: **21%**.
  - Plantas vivas de carácter ornamental: **10%** (art. 91.Uno.1.8º LIVA).
  - Alimentos para animales de compañía: **21%** (excluidos del reducido).
  - Acuarios, equipamiento y complementos: **21%**.
  - Desglose de base y cuota por tipo en el ticket. Nota: en RE la titular no liquida IVA de sus ventas, pero el ticket/factura debe repercutir el IVA normalmente.
- Precios **con IVA incluido** (PVP): almacenar PVP y derivar la base con una regla de redondeo única y testeada (los descuadres de céntimos son el bug clásico de TPV).

---

## 3. Arquitectura técnica

### 3.1. Principios

- **Local-first**: la tienda debe poder vender sin internet. Venta, impresión y generación del registro son locales; la remisión VERI*FACTU se gestiona con **cola persistente y reintentos** (diseñar el flujo de incidencia de conectividad conforme a la Orden HAC/1177/2024 cuando se active el motor).
- **Una sola fuente de verdad**: BD local transaccional. Escenario confirmado: **un único puesto de venta + un administrador remoto** → **SQLite en modo WAL** (concurrencia trivial, cero administración). Complemento recomendado: **Litestream** para replicación continua de la BD a almacenamiento externo (S3/Backblaze) = backup en tiempo real + recuperación ante desastre.
- **Tres capas**: TPV táctil (frontend) / servidor local (API + lógica + motor fiscal) / consola de administración (web sobre la misma API).
- Stack sugerido (perfil Python): **FastAPI + SQLite** en un mini-PC; el TPV es una web a pantalla completa en el equipo táctil; la consola se abre desde cualquier navegador de la red local **o en remoto vía VPN**.

### 3.1 bis. Acceso remoto a la consola de administración

- **Nunca abrir puertos del router** hacia internet: el equipo contiene los registros de facturación, datos personales de clientes y el certificado electrónico.
- Solución: **VPN de malla (Tailscale/WireGuard)** o, alternativamente, Cloudflare Tunnel. Sin puertos abiertos, sin IP fija, funciona tras CGNAT. El administrador accede a la consola (`http://tpv:puerto/admin`) desde portátil o móvil como si estuviera en la red local.
- El servidor **permanece en la tienda** (local-first): sin internet la tienda sigue vendiendo; solo se pierde temporalmente el acceso remoto y se encola la remisión VERI*FACTU.
- Autenticación en dos niveles: dependiente con PIN solo en el puesto físico; administrador con contraseña fuerte (además de la barrera de la VPN). Las acciones remotas se registran en el log de auditoría igual que las locales.
- **El certificado electrónico no sale del servidor de la tienda**: la remisión a la AEAT la hace siempre el servidor; en remoto solo se consulta estado de la cola y rechazos.

### 3.2. Hardware y periféricos

- **Impresora de tickets 80 mm ESC/POS** (Epson TM-T20 o compatible): `python-escpos` o impresión vía servidor. Debe imprimir **QR** con calidad legible (lo exigirá VeriFactu).
- **Cajón portamonedas** por RJ11 de la impresora (pulso ESC/POS). Registrar cada apertura sin venta.
- **Lector de código de barras** modo teclado (keyboard wedge): captura global en el TPV; configurar prefijo/sufijo o detectar por velocidad de tecleo para distinguirlo del teclado en pantalla.
- **Pantalla táctil** ≥ 15", resolución fija conocida.
- **Datáfono**: empezar independiente (el TPV solo registra "pago con tarjeta"); la integración es proyecto aparte.
- **Certificado electrónico**: para la remisión VERI*FACTU a la AEAT hará falta certificado de la titular (o apoderamiento); decidir custodia. No se necesita firmar cada registro en esta modalidad.

### 3.3. Copias de seguridad

- Backup automático diario de la BD, cifrado, con copia fuera del local (contiene la cadena de registros: perderla es un problema fiscal, no solo operativo).
- Conservación: prescripción tributaria (4 años, art. 66 LGT) y 6 años mercantiles (art. 30 CCom). En la práctica: no borrar nunca.

---

## 4. Modelo de datos (núcleo)

- **Artículo**: `id` interno estable (nunca se reutiliza), nombre completo, nombre corto para botón, familia (FK), tipo de IVA, PVP (IVA incluido), coste, flag control de stock, flag "precio libre" (vivos con precio según talla), imagen/color de botón, activo/inactivo (nunca borrar artículos con ventas), **N códigos de barras por artículo** (tabla aparte).
- **Familia**: árbol de **niveles ilimitados** (`parent_id`), orden, color, imagen. Estructura de catálogo y a la vez navegación del táctil.
- **Botonera**: entidad propia, no derivada automáticamente de las familias. Un **perfil de botonera** contiene páginas; cada página, una rejilla; cada botón apunta a: (a) un **artículo**, (b) una **familia** (navega a sus hijos), o (c) una **función** (cobrar, convertir en factura, devolución, aparcar/recuperar ticket, abrir cajón, descuento, cierre de caja…). Propiedades: posición, tamaño (1x1, 2x1…), color, icono, texto. Editable desde la consola sin tocar código.
- **Cliente**: NIF validado, nombre, domicilio (para factura completa), email, teléfono, flags RGPD.
- **Venta**: cabecera (serie, número, fecha-hora, empleado, estado: aparcada / cobrada / facturada / anulada-con-rastro), líneas (artículo, descripción congelada, cantidad, PVP, IVA, descuento), pagos (efectivo, tarjeta, mixto), y hueco para el **registro de facturación** (hash, hash anterior, QR, estado de remisión) aunque el motor esté inactivo.
- **Usuario**: PIN rápido, roles (venta / administración), trazabilidad por empleado.
- **Movimientos de stock**: entradas, ventas, y **mermas con motivo** (§7).

---

## 5. Importación/exportación por Excel

- Plantilla `.xlsx` fija, una hoja por entidad (Artículos, Familias, Clientes, Precios). Exportar = plantilla ya rellena; editar y reimportar.
- **Clave estable**: código interno (no nombre ni EAN). Import = *upsert*.
- **Nunca borrar por omisión** (baja solo con columna explícita).
- **Dry-run obligatorio**: informe de errores/avisos (IVA inexistente, familia no encontrada, precio 0, EAN duplicado…) antes de confirmar. Log de cada importación.
- Trampas de Excel: **EAN convertidos a número** (ceros perdidos, notación científica → forzar texto, validar dígito de control EAN-13), decimales con coma, espacios.
- Histórico de cambios de precio (auditoría y margen).
- Librerías: `openpyxl` (o `pandas` + `openpyxl`).

---

## 6. UX del módulo táctil (vendedor)

- Venta normal en **2-3 toques o un escaneo**; escáner siempre activo en pantalla de venta.
- Botones grandes (≥ 80 px), alto contraste, respuesta visual inmediata, sin dobles confirmaciones en lo frecuente.
- Navegación por familias con **breadcrumb** y botón "Inicio" siempre visible (imprescindible con varios niveles).
- Búsqueda por texto con teclado en pantalla como red de seguridad.
- **Tickets aparcados**.
- Cobro: importes rápidos (5/10/20/50 €, exacto), cambio grande y visible, pago mixto.
- Precio libre / variantes S-M-L para vivos.
- Funciones sensibles (devolución, descuento > X%, arqueo) protegidas por PIN de administrador.

---

## 7. Consola de administración

- **Maestros**: artículos, familias, clientes, usuarios, tipos de IVA, series, **editor visual de botoneras**, plantillas de ticket.
- **Informes**: ventas por día/franja/familia/artículo/empleado/forma de pago; margen; informe X y **cierre Z** diario.
- **Cierre y arqueo de caja**: fondo, recuento por denominaciones, retiradas, descuadres registrados (todo deja rastro, nada se "ajusta" en silencio).
- **Stock**: entradas por proveedor, regularizaciones y **mermas por mortalidad** de peces/plantas con motivo y fecha — importante para gestión y para **justificar fiscalmente la pérdida de existencias** en una eventual comprobación.
- **Etiquetado**: códigos de barras internos para artículos sin EAN (prefijos **20–29** de uso interno, con dígito de control EAN-13).
- **Fiscal**: estado de la cola de remisión, reenvíos, incidencias, declaración responsable visible, versión del software.
- Copias de seguridad y restauración desde la consola.

---

## 8. Particularidades del negocio (acuariofilia)

- **Vivos sin código de barras** → familias/subfamilias y botonera. Variantes por talla como sub-artículos para no multiplicar botones.
- **Garantías de vivos** (pez muerto en 24-48 h): flujo propio de devolución = rectificativa/devolución con rastro + merma.
- **CITES**: corales duros, *Tridacna* y otras especies requieren documentación en la compraventa. Flag "requiere doc. CITES" en el artículo, con aviso al vender y campo para nº de documento (trazabilidad ante Seprona).
- **Núcleo zoológico**: obligación administrativa del establecimiento (en Cantabria, registro autonómico), ajena al software; solo checklist de negocio.
- **Web bizkaitropik.com**: aunque no entre en v1, diseñar (a) API o export programado de artículos/precios/stock y (b) tener presente que las ventas online con factura también quedarán bajo VeriFactu cuando sea exigible.

---

## 9. RGPD y seguridad

- Ficha de cliente con minimización de datos, información básica RGPD (arts. 5 y 13 RGPD; LOPDGDD 3/2018), registro de actividades de tratamiento del negocio.
- No imprimir datos personales en tickets salvo factura completa.
- Backups cifrados, PIN por usuario, bloqueo automático de la sesión de administración.

---

## 10. Hoja de ruta sugerida

1. **Fase 0 — decisiones previas**: régimen confirmado (estimación objetiva + RE; tickets = facturas simplificadas, §1.2); hardware concreto; certificado electrónico para la remisión; alta en Tailscale (o equivalente) para el acceso remoto.
2. **Fase 1 — núcleo**: modelo de datos (con inmutabilidad, series y estructura del registro de facturación desde el inicio), TPV táctil, cobro, aparcar, impresión ESC/POS, cajón, escáner, maestros, botonera configurable, import/export Excel.
3. **Fase 2 — motor VeriFactu (adelantado)**: registros de alta/anulación conforme a la Orden HAC/1177/2024, hash SHA-256 encadenado, QR con URL de cotejo, leyenda VERI*FACTU, cola de remisión con reintentos, declaración responsable; desarrollo y pruebas contra el **entorno de pruebas de la AEAT** (periodo de pruebas hasta 1/7/2027, sin vinculación); cuando esté estable, inicio de la remisión sistemática en firme (opción tácita del art. 16.5 RRSIF, vinculante hasta fin del año natural).
4. **Fase 3 — administración avanzada**: informes, arqueos, stock/mermas, etiquetas, histórico de precios, informe de magnitudes de módulos.
5. **Fase 4 — integración web** y mejoras.

> El motor VeriFactu es ahora parte esencial del producto: el núcleo de la fase 1 debe construirse ya con sus reglas (inmutabilidad, series, estructura del registro), y la fase 2 lo activa.
