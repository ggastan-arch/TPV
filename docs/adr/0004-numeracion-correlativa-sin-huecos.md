# ADR-0004: Numeración correlativa sin huecos (BEGIN IMMEDIATE)

- Estado: Aceptado
- Fecha: 2026-07-09

## Contexto

La numeración de series debe ser correlativa, sin huecos ni reutilización, asignada en la
**misma transacción** que emite el documento (invariante 2). Aunque el escenario es
monopuesto, hay concurrencia real (venta + administrador remoto) y hay que garantizarlo
bajo contienda.

## Decisión

SQLite en modo WAL. El engine desactiva el autobegin de pysqlite (`isolation_level=None`)
y emite `BEGIN IMMEDIATE` en el evento `begin` de SQLAlchemy, adquiriendo el lock de
escritura al inicio de la transacción. La emisión (incremento de `contador_serie` + alta de
venta + registro fiscal) ocurre en una única transacción serializada; `busy_timeout` hace
esperar a los escritores en contienda en vez de fallar.

## Consecuencias

- (+) Correlatividad garantizada; test de 20 hilos concurrentes da `{1..N}` exacto.
- (−) `BEGIN IMMEDIATE` global toma lock de escritura también en lecturas: reduce
  concurrencia de lectura, aceptable para un monopuesto.
- (−) Gotcha recurrente: con FastAPI, `s.get()`/`select` hacen autobegin; usar
  `s.commit()` al final (no `with s.begin()` tras una operación previa).
