# Guion de presentación — TFM · TPV AcuaTPV

Material de apoyo para las **slides** y el **vídeo** de defensa. No son las slides en sí:
es el contenido y el hilo narrativo para que las montes en Canva / Google Slides y grabes.

> **Hilo conductor (la idea que tiene que quedar):** no es un CRUD de tienda. Es un
> **sistema de facturación real conforme a la normativa antifraude española** (VERI\*FACTU),
> con integridad garantizada a nivel de base de datos y **remisión real a la AEAT ya
> probada en vivo**. Ese es el diferenciador.

---

## Parte 1 · Slides (12 diapositivas, ~12 min)

### 1. Portada
- **TPV AcuaTPV** — Sistema de facturación VERI\*FACTU
- Subtítulo: *TPV táctil para comercio minorista conforme al RD 1007/2023 (RRSIF)*
- Tu nombre · Máster · Fecha · logo/imagen de la tienda (acuario)
- 🎤 *"Voy a presentar un TPV para una tienda real que cumple con la nueva normativa antifraude."*

### 2. El problema
- Ley antifraude 11/2021 → **RD 1007/2023 (RRSIF)** + **Orden HAC/1177/2024**.
- Todo sistema de facturación (SIF) debe garantizar: **integridad, conservación,
  trazabilidad e inalterabilidad** de los registros.
- **VERI\*FACTU**: modalidad en la que el TPV remite cada factura a la AEAT en el momento.
- 🎤 *"A partir de 2026 un comercio no puede facturar con cualquier programa: el software tiene obligaciones legales. Ahí nace el proyecto."*

### 3. Objetivo
- Construir un TPV **real, no un prototipo**: que emita facturas simplificadas conformes,
  con registro fiscal encadenado y **remisión real** a la AEAT.
- Restricciones reales: monopuesto, táctil, **el cobro se cierra offline** (local-first).
- 🎤 *"El objetivo no era 'que se vea bien', era que un inspector no pudiera tumbarlo."*

### 4. Qué hace (funcionalidades)
- Venta táctil con **botonera configurable**, búsqueda, escáner, precio libre / al peso.
- **Motor fiscal VERI\*FACTU**: registro, huella, QR, cola de remisión.
- **Consola de administración**: catálogo, clientes, cierre Z, panel fiscal.
- Impresión de ticket ESC/POS con QR + **modo demo** para pruebas.
- *(captura del TPV con la botonera)*

### 5. El corazón: los invariantes fiscales
- **Ninguna venta se borra ni se edita** → inmutabilidad con **triggers en la base de datos**.
- **Numeración correlativa sin huecos** (misma transacción que emite).
- **Cadena de huellas SHA-256** encadenada entre registros.
- Log de auditoría **append-only**; el **certificado nunca sale del servidor**.
- 🎤 *"Esto no son decisiones de diseño: son requisitos legales. Y por eso los puse en el sitio donde no se pueden saltar: la propia base de datos."*

### 6. Arquitectura
- **Hexagonal**: `dominio` (puro) · `aplicación` (casos de uso) · `infraestructura` · `presentación`.
- Stack: Python 3.12 · FastAPI · SQLite (WAL) + SQLAlchemy · Alembic · lxml.
- *(diagrama de las 4 capas; flecha: presentación → aplicación → dominio, infraestructura a un lado)*
- 🎤 *"El dominio fiscal no sabe que existe FastAPI ni SQLite. Puedo cambiar la impresora o la web sin tocar la lógica fiscal."*

### 7. La cadena de huellas (deep dive)
- Cada registro incluye la **huella del anterior** → cualquier cambio rompe la cadena.
- Huella **validada contra los vectores oficiales** de la AEAT.
- *(esquema: Registro N-1 → SHA-256 → Registro N → …)*
- 🎤 *"Si alguien edita una factura antigua, todas las huellas siguientes dejan de cuadrar. Es inalterabilidad demostrable, no una promesa."*

### 8. Integración REAL con la AEAT ⭐
- Cliente **SOAP con certificado** (mutual-TLS), cola FIFO con reintentos, QR de cotejo.
- **Primer contacto real con el entorno de pruebas de la AEAT: correcto, con CSV asignado.**
- **Golden test** sobre una respuesta real capturada (no fixtures inventados).
- 🎤 *"Esto es lo que lo separa de un ejercicio: no simula la AEAT, habla con la AEAT. Y ya respondió que sí."*

### 9. Calidad y testing
- **456 tests** verdes · TDD · tests dedicados de los **invariantes fiscales**.
- Regla del proyecto: *"sin el test del invariante, una feature no está terminada"*.
- 🎤 *"En un sistema fiscal el testing no es opcional; cada invariante legal tiene su test."*

### 10. Modo demo y despliegue
- Perfil **demo aislado**: BD propia, sin certificado, **sin validez fiscal** (todo marcado).
- Desplegado en **Render** con Docker; se reinicia limpio en cada arranque.
- **URL del demo:** `https://…` *(rellenar)*
- 🎤 *"Para que lo podáis probar sin datos reales, hay un modo demo desplegado. Vamos a verlo."*

### 11. Demo en vivo → *(pasar a pantalla / vídeo, ver Parte 2)*

### 12. Cierre
- **Retos**: la densidad normativa, la cadena secuencial (no paralelizable), la integración real.
- **Aprendizajes**: llevar requisitos legales a invariantes de software; arquitectura para aislar el dominio.
- **Próximos pasos**: import/export Excel, Litestream (backup continuo).
- Enlaces: **GitHub** (github.com/ggastan-arch/TPV) · **Demo** (URL).
- 🎤 *"Gracias. Repo y demo en pantalla."*

---

## Parte 2 · Guion del vídeo (captura de pantalla, ~8-10 min)

> Grabá con la URL del demo abierta. Antes de grabar, **abrí el demo una vez** para que
> Render "despierte" (el plan free se duerme y tarda ~40s la primera visita).

**[0:00–1:00] Intro (sobre las slides 1-3)**
- Presentate y presentá el problema en 3 frases: normativa antifraude → obligación del SIF → tu TPV.

**[1:00–3:00] Lo técnico (slides 5-9)**
- Enseñá el diferenciador: invariantes en la BD, cadena de huellas, integración real AEAT, 456 tests.
- No te alargues: la chicha es el demo.

**[3:00–8:00] Demo en vivo (captura de pantalla)** — orden sugerido:
1. **Portada `/`**: mostrá la página de inicio, el badge "MODO DEMO" y las credenciales.
2. **TPV `/tpv`**: logueá con PIN `0000`. Tocá 2-3 artículos de la botonera (Neon, Anubias…), mostrá el carrito y el total calculado en el servidor.
3. **Cobro**: cobrá en efectivo → mostrá el ticket con **"DOCUMENTO DE PRUEBA · SIN VALIDEZ FISCAL"** y el número de serie `T2026-…`. 🎤 *"Fijaos: en demo no hay QR de la AEAT, está marcado como prueba."*
4. **Admin `/admin`**: entrá como `admin` / `1234`. Mostrá el **catálogo** y la **botonera editable**.
5. **Panel fiscal**: mostrá la **cadena íntegra** (✔) y explicá la nota del modo demo (no se remite, es NullEngine).
6. **Cierre Z** (opcional): generá o mostrá un cierre para enseñar los totales del día.

**[8:00–9:00] Cierre (slide 12)**
- Retos + aprendizajes + próximos pasos. Enseñá el repo en GitHub y la URL del demo.

---

## Parte 3 · Checklist antes de grabar
- [ ] Demo "despierto" (visitá la URL 1 min antes).
- [ ] Ventana del navegador limpia (sin pestañas ni marcadores personales).
- [ ] Zoom del navegador al 110-125 % para que se lea en el vídeo.
- [ ] Audio probado; guion a mano (no leas palabra por palabra, hablá).
- [ ] Si vas a mostrar `make test`, corré `.venv\Scripts\python -m pytest` (verde: 456).
- [ ] URL del demo y del repo pegadas en la última slide.

## Enlaces para el formulario de entrega
- Repo: https://github.com/ggastan-arch/TPV
- Demo: `https://…` *(rellenar tras el deploy)*
- Slides: `https://…` *(pegar el enlace público de Canva/Google Slides)*
- Vídeo: `https://…` *(YouTube/Drive, acceso público)*
- Credenciales de prueba: admin `1234` · dependiente `0000`
