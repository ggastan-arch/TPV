# ADR-0009: Perfil de arranque DEMO aislado

- Estado: Aceptado
- Fecha: 2026-07-11

## Contexto

El TPV necesita poder exhibirse (ferias, demostraciones comerciales, pruebas internas) sin
exponer datos reales de la persona titular ni remitir registros de facturación a la AEAT. El sistema
es un SIF sujeto al RD 1007/2023 (RRSIF): el invariante 5 (CLAUDE.md) prohíbe cualquier "modo
formación" que imprima tickets no contabilizados, y el invariante 7 exige que el certificado
electrónico de la persona titular nunca salga del servidor ni se cargue fuera de los flujos de
producción reales.

La demo no puede ser una vía paralela que "simule" facturación sin dejar rastro: eso sería
exactamente el "modo formación" prohibido. La solución debe generar documentos reales
(cadena de huella, triggers de inmutabilidad) pero en un proceso, base de datos y emisor
completamente aislados de la operación real, con cada documento marcado sin ambigüedad.

## Decisión

- Perfil de arranque `TPV_PROFILE` con dos valores válidos: `produccion` (por defecto,
  comportamiento actual sin cambios) y `demo`. Cualquier otro valor rechaza el arranque.
- En modo demo, `Settings` (resuelto en un `model_validator(mode="after")`, ANTES de que se
  creen los singletons `engine`/`SessionLocal`) fuerza de forma incondicional:
  - `db_path = tpv_demo.db` (nunca `tpv.db`; sin posibilidad de override por variable de
    entorno — el aislamiento no es negociable).
  - Emisor ficticio: NIF `00000000T`, nombre "AcuaTPV DEMO (documento de prueba)".
  - `certificado_cert_path` / `certificado_key_path` anulados a `None`: el certificado de la
    titular NUNCA se carga en modo demo (invariante 7).
- Salvaguarda de arranque independiente (`_verificar_aislamiento_demo` en `app/main.py`):
  compara la ruta ABSOLUTA resuelta de `db_path` contra la de `tpv.db` y aborta con
  `RuntimeError` si coinciden. Es defensa en profundidad: no confía únicamente en el
  validator de `Settings`, sino que blinda contra una regresión futura que dejara el perfil
  demo apuntando a la BD real.
- `get_motor()` cortocircuita a `NullEngine` como PRIMERA rama cuando el perfil es demo, antes
  de cualquier rama de producción futura. Hoy `NullEngine` es el único motor implementado, así
  que esto no cambia el comportamiento observable; blinda la garantía "no remite" para cuando
  exista un `VerifactuEngine` real (fuera de alcance de este cambio).
- `imprimir_ticket(..., demo: bool | None = None)`: si el perfil resuelto es demo, sustituye
  el bloque QR/leyenda VERI\*FACTU por un banner "DOCUMENTO DE PRUEBA" / "SIN VALIDEZ FISCAL",
  y NUNCA invoca la construcción de la URL de cotejo real ni el QR nativo de la impresora.
- Seed idempotente `sembrar_demo()` (extrae el catálogo base a un helper compartido con
  `sembrar()`) puebla `tpv_demo.db` con tipos de IVA, familias, artículos de acuariofilia y un
  cliente de prueba. La "empresa demo" es el emisor ya resuelto por `Settings` — no existe una
  tabla de empresa separada.
- Bootstrap real vía `make demo`: `alembic upgrade head` sobre `tpv_demo.db` (con la URL fijada
  explícitamente, igual que el patrón ya usado en los fixtures de test) seguido de
  `python -m app.seed --demo`. NUNCA `create_all`: la BD demo hereda los mismos triggers de
  inmutabilidad y el mismo esquema de cadena de huella que producción.
- La consola de administración (`admin.html`, HTML/JS estático sin motor de plantillas)
  consulta `GET /health` — que ahora expone `"perfil": settings.perfil` como fuente única de
  verdad — y pinta un banner "MODO DEMO" visible mientras el perfil activo sea demo.

## Alternativas rechazadas

| Alternativa | Motivo del rechazo |
|-------------|---------------------|
| Permitir `TPV_DB_PATH` como override en modo demo | El aislamiento de BD es un invariante no negociable de esta funcionalidad; un override abriría la puerta a apuntar accidentalmente a `tpv.db`. |
| Resolver el perfil con una función `bootstrap()` imperativa llamada después de crear `Settings` | `engine`/`SessionLocal` son singletons de módulo creados en cascada al importar `app/infraestructura/db.py`; resolver el perfil DESPUÉS dejaría el engine ya ligado a la BD equivocada. El `model_validator(mode="after")` resuelve el perfil ANTES de que exista el engine. |
| Confiar solo en la resolución de `Settings` para garantizar que `get_motor()` nunca remita en demo | No blinda contra un futuro `VerifactuEngine` de producción cuyo cableado dependa de la presencia de certificado en lugar del perfil. Se prefiere una comprobación explícita y redundante. |
| Exponer el perfil a la consola vía un motor de plantillas / contexto de render | `admin.html` es HTML/JS estático servido con `FileResponse` (sin Jinja ni contexto de servidor). Se expone el perfil por el contrato backend ya existente (`GET /health`) y se consulta por `fetch` en el arranque del JS, siguiendo el patrón ya usado por el resto de la consola. |
| Usar `create_all` para levantar `tpv_demo.db` | La demo debe demostrar el comportamiento fiscal real (cadena de huella, triggers de inmutabilidad); `create_all` no aplica los triggers definidos en las migraciones Alembic. |

## Consecuencias

- (+) La demo es indistinguible en profundidad técnica de producción (misma cadena de huella,
  mismos triggers), pero completamente aislada en datos, emisor y certificado.
- (+) Producción (perfil por defecto) queda byte a byte idéntica al comportamiento previo: cero
  regresión, sin necesidad de flags adicionales para el operador real.
- (+) La garantía "no remite" en demo depende del perfil, no de qué motor fiscal esté
  cableado en cada momento — se sostiene aunque en el futuro exista `VerifactuEngine`.
- (−) `tpv_demo.db` es un fichero desechable adicional a gestionar en el entorno de
  desarrollo/demo (documentado en `.gitignore`, nunca se versiona).
- (−) Introduce una segunda ruta de bootstrap (`make demo`) a mantener en paralelo a
  `make migrate` + `make seed`, aunque comparten la misma infraestructura de migraciones.

## Referencias

- Invariante 5 (CLAUDE.md): nada de "modo formación" ni tickets no contabilizados.
- Invariante 7 (CLAUDE.md): el certificado electrónico nunca sale del servidor ni se registra
  en logs — en demo, además, nunca se carga.
- ADR-0003: inmutabilidad en base de datos (triggers heredados también en `tpv_demo.db`).
- ADR-0006: motor fiscal intercambiable (`FiscalEngine` / `NullEngine`).
- ADR-0007: huella conforme Orden art. 13 (cadena heredada igual en demo).
