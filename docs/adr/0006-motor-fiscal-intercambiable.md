# ADR-0006: Motor fiscal intercambiable (`FiscalEngine`)

- Estado: Aceptado
- Fecha: 2026-07-09

## Contexto

El cumplimiento fiscal (registro, huella, encadenamiento, QR, remisión) debe estar
aislado tras una interfaz para poder desarrollarlo por fases y protegerlo ante cambios
(p. ej. una mudanza a territorio foral → TicketBAI). Consideraciones §1.4.

## Decisión

Interfaz `FiscalEngine` con `emit` / `cancel` / `verify_chain`. Implementaciones:

- `NullEngine` (fase 1/desarrollo): genera registro + huella + encadenamiento, **no remite**.
- `VerifactuEngine` (objetivo): además serializa XML, QR y remite a la AEAT.

La estructura del registro y la huella se implementan **siempre**, incluso con
`NullEngine`: el encadenamiento no es opcional.

## Consecuencias

- (+) Inversión de dependencias (DIP) y abierto a extensión (OCP).
- (+) Permite operar y testear la cadena local sin conectividad ni certificado.
- En la arquitectura objetivo, `FiscalEngine` es un puerto del dominio; sus
  implementaciones viven en infraestructura.
