# interfaz-nocturne Specification

## Purpose

La app (TPV, consola, portada) adopta el sistema de diseño Nocturne (oscuro,
Inter, tokens CSS, componentes `.btn`/`.card`/`.field`/`.input`/`.tag`/
`.table`/`.dialog`) como reskin visual servido desde un asset propio, sin
alterar el comportamiento existente: mismos IDs, mismos handlers, mismas
llamadas a `/tpv/api/*`, `/admin/api/*` y `/health`.

## Requirements

### Requirement: Asset del sistema de diseño servido sin dependencia de red

El sistema MUST servir `styles.css` (y las fuentes/iconos que use) desde un
mount estático propio de la aplicación. El sistema MUST NOT depender de
ningún recurso de red (CDN, `@import` de Google Fonts, `unpkg.com` u origen
equivalente) para renderizar ninguna de las tres superficies; fuentes e
iconos MUST estar auto-alojados o embebidos (p. ej. SVG inline).

#### Scenario: HTML servido sin dependencias externas
- GIVEN que se sirve `tpv.html`, `admin.html` o `landing.html`
- WHEN se inspecciona el HTML devuelto
- THEN no contiene `fonts.googleapis.com`, `unpkg.com` ni otro origen externo
  para hoja de estilos, fuente o icono

#### Scenario: Hoja Nocturne enlazada desde origen propio
- GIVEN cualquiera de las tres superficies servidas
- WHEN se inspecciona el `<link rel="stylesheet">` de Nocturne
- THEN su `href` apunta a una ruta del propio origen, no a una URL externa

### Requirement: Reskin visual preserva IDs, handlers y llamadas a la API

El sistema MUST reescribir el markup de las tres superficies con clases y
tokens Nocturne SIN eliminar ni renombrar los IDs que referencia el
`<script>` inline, SIN cambiar los listeners existentes, y SIN alterar las
rutas de `fetch` a `/tpv/api/*`, `/admin/api/*` o `/health`.

#### Scenario: IDs de TPV preservados tras el reskin
- GIVEN el `tpv.html` reskineado
- WHEN se inspecciona el HTML
- THEN siguen presentes `#grid`, `#carrito`, `#total`, `#buscarInput`,
  `#demoBanner` y `#usuario`

#### Scenario: Rutas de API intactas
- GIVEN cualquiera de las tres superficies reskineadas
- WHEN se inspecciona el código embebido
- THEN las cadenas `/tpv/api/`, `/admin/api/` y `/health` siguen presentes
  literalmente

### Requirement: Pantalla de venta con el layout del diseño de referencia

La pantalla de venta MUST presentar: buscador de artículo, píldoras de
categoría, rejilla de artículos con foto (icono de familia como fallback),
nombre y precio por tarjeta; panel de carrito con controles +/- de cantidad,
botón de quitar línea, Total y COBRAR; y una barra de funciones inferior.

#### Scenario: Tarjeta de artículo con clase Nocturne
- GIVEN la pantalla de venta reskineada
- WHEN se inspecciona una tarjeta de artículo de la rejilla
- THEN usa una clase de tarjeta Nocturne (p. ej. `.pos-tile`) y muestra
  nombre y precio

#### Scenario: Carrito con controles Nocturne
- GIVEN una línea de carrito
- WHEN se inspecciona su marcado
- THEN expone controles +/- de cantidad y un botón de quitar línea con
  clases del sistema Nocturne

### Requirement: Entradas de funciones sin backend deshabilitadas

Las entradas "Convertir en factura", "Aparcar ticket", "Desaparcar" y
"Cliente en venta" MUST aparecer en la barra de funciones con rótulo e
icono, pero MUST estar deshabilitadas (`disabled` o equivalente accesible) y
MUST NOT ejecutar ninguna llamada a endpoint ni simular éxito.

#### Scenario: Botón presente pero deshabilitado
- GIVEN la barra de funciones reskineada
- WHEN se inspecciona el botón "Convertir en factura"
- THEN está presente en el HTML y tiene el atributo `disabled`

#### Scenario: Sin comportamiento simulado
- GIVEN cualquiera de las entradas sin backend
- WHEN se revisa su handler asociado
- THEN no existe llamada a `fetch` ni mensaje de éxito falso

### Requirement: Áreas táctiles mínimas en el TPV

Los controles interactivos de venta (tarjetas de artículo, controles de
cantidad, COBRAR) MUST tener una altura mínima de 48px, ajustando la
densidad 0.7× de Nocturne donde haga falta.

#### Scenario: Altura mínima declarada
- GIVEN la hoja de estilos aplicada a la pantalla de venta
- WHEN se inspeccionan las reglas de tarjeta, botón de cantidad y COBRAR
- THEN cada una declara `min-height` de al menos 48px

### Requirement: Portada y login de consola preservan el acceso por perfil

`landing.html` y la pantalla de login de la consola MUST reskinearse
preservando: enlaces a `/tpv/` y `/admin/`; el bloque de credenciales demo
condicionado a `perfil == "demo"`; el formulario usuario/contraseña en
producción; y el acceso directo sin login en demo (ya definido por
`consola-administracion`).

#### Scenario: Portada conserva enlaces y credenciales demo
- GIVEN `landing.html` reskineada
- WHEN se inspecciona su HTML
- THEN conserva `href="/tpv/"` y `href="/admin/"`, y el bloque de
  credenciales solo se activa con perfil `demo`

#### Scenario: Banner y "Salir" conservan su lógica de perfil
- GIVEN el TPV o la consola reskineados
- WHEN el perfil activo es `demo`
- THEN se muestra el banner `esDemo` y "Salir" no se muestra en la consola;
  en `produccion` ocurre lo contrario, sin cambio de comportamiento

## Constraints (no debilitar)

- El cobro sigue funcionando sin conexión a red (offline-first).
- Ningún cambio al motor fiscal, huella/cadena/numeración ni triggers de
  inmutabilidad.

## Out of Scope

Backend de Convertir en factura F3, Aparcar/desaparcar y Cliente-en-venta:
solo se maqueta la entrada deshabilitada de esta capacidad; su
implementación es trabajo futuro propio.
