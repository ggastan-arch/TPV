# Design: Convertir simplificadas en factura completa de sustitución (F3)

## Technical Approach

Cambio fiscal-CRÍTICO pero ADITIVO: no toca huella, cadena, numeración, redondeo ni los
triggers de inmutabilidad. Un único caso de uso hexagonal `ConvertirEnFacturaF3`
(patrón `emitir_venta.py`) orquesta: validar elegibilidad → construir la F3 COPIANDO las
líneas congeladas de las N simplificadas → `motor.emit(serie="F", tipo_factura="F3")` SIN
modificar el motor (ya acepta ambos parámetros) → persistir `VentaSustitucion` +
`RegistroFacturaSustituida` (N→1) → transición controlada `cobrada→sustituida` de cada
origen → auditoría `conversion_f3`. La F3 obtiene correlativo propio en serie F, encadena
al último registro global y entra en la cola de remisión existente como cualquier alta. El
ÚNICO añadido al núcleo fiscal es el bloque XML `Destinatarios/IDDestinatario`, estrictamente
condicional a F1/F3 e independiente de la huella. Sin migración Alembic (modelo, estado
`sustituida` y triggers existen desde 0001; el destinatario reutiliza `Cliente` +
`venta.cliente_id`, campo YA congelado).

## Architecture Decisions

### Decision: F3 = suma de líneas congeladas, JAMÁS re-redondeo (clave de precisión fiscal)

**Choice**: La F3 copia como nuevas `VentaLinea` TODAS las líneas de las simplificadas
origen, preservando sus `base_linea/cuota_linea/total_linea` (ya cuantizados). Totales de la
F3 = Σ de los totales de origen. `motor.emit` recalcula el `Desglose` con `_desglose(f3)`,
que agrupa por tipo sumando esos valores por-línea ya cuantizados.
**Alternatives considered**: (A) re-derivar base/cuota desde un `importe_total` agregado con
`desglosar_total`. (B) sumar sólo cabeceras sin líneas.
**Rationale**: sumar `Decimal` ya cuantizados es asociativo y EXACTO: `CuotaTotal` e
`ImporteTotal` de la F3 reconcilian al céntimo con Σ de las sustituidas, sin deriva. (A)
reintroduciría el bug clásico de redondeo (doble cuantización). (B) dejaría `_desglose`
vacío y descuadraría `CuotaTotal`. Se reutiliza la función única de `redondeo.py` sin
tocarla; no se recalcula nada, sólo se suma.

### Decision: Destinatarios vía `Cliente` + parámetro a XML (SIN migración, SIN huella)

**Choice**: El caso de uso crea/reutiliza un `Cliente` (NIF+nombre+domicilio, validado con
`validar_documento`) y fija `f3.cliente_id` ANTES del `emit` (mientras la venta es
`aparcada`, el INSERT lo congela). `registro_alta_xml` gana un parámetro
`destinatario: Destinatario | None`; emite el bloque SOLO si no es None, entre
`DescripcionOperacion` y `Desglose` (posición exacta del XSD, `RegistroFacturacionAltaType`).
En `remitir_lote.py`, para `tipo_factura ∈ {F1,F3}` se resuelve el destinatario desde
`venta.cliente_id`; para T/F2 se pasa None.
**Alternatives considered**: tabla inmutable `RegistroDestinatario` (espejo de
`RegistroFacturaSustituida`) con migración + triggers.
**Rationale**: `Destinatarios` NO entra en la huella (`huella_alta` opera sobre subconjunto
fijo art. 13: verificado en `huella.py:42-63`), luego no requiere inmutabilidad a nivel de
registro. `cliente_id` YA está en `_VENTA_CAMPOS_CONGELADOS` (ddl.py:28) → el enlace es
inmutable sin tabla nueva. Coherente con `nombre_emisor`, que tampoco se almacena en el
registro y se pasa al serializar. La tabla dedicada aportaría inmutabilidad redundante
(huella-independiente) a costa de una migración sobre el núcleo fiscal: descartada para v1.
Caveat aceptado: el contenido de `Cliente` es mutable; el snapshot que cuenta es el remitido
a la AEAT.

### Decision: bloque Destinatarios ESTRICTAMENTE condicional (T byte-idéntica)

**Choice**: `if destinatario is not None:` envuelve el bloque; sin destinatario, el árbol XML
es idéntico al actual. Test golden de regresión sobre una T (F2): `git diff` de su XML = 0.
**Rationale**: invariante duro "emisión de simplificadas inalterada". La rama condicional no
se ejecuta nunca para T/F2 (destinatario=None), garantizando salida byte-idéntica.

### Decision: elegibilidad en el caso de uso, no en la BD

**Choice**: nueva query `RepositorioVentas.convertibles()` = `serie='T'` AND
`estado='cobrada'` AND `id NOT IN (SELECT venta_sustituida_id FROM venta_sustitucion)`. El
caso de uso revalida cada id y lanza excepciones amigables ANTES de cualquier INSERT.
**Alternatives considered**: confiar en el `UNIQUE(venta_sustituida_id)` (IntegrityError crudo).
**Rationale**: el UNIQUE es la red de seguridad, no la UX. Pre-check → HTTP 409/422 legible.

### Decision: Cierre Z — doble conteo entre periodos ACEPTADO y documentado

**Choice**: no se bloquea la conversión por Z. Si la T ya cayó en un Z pasado (inmutable) y la
F3 genera `orden` nuevo en un Z futuro, el mismo hecho económico se cuenta dos veces.
**Rationale**: decisión de negocio cerrada en la propuesta; Z es inmutable (ddl.py). Se añade
nota de conciliación en el informe de módulos. Sin mecanismo compensatorio en v1.

**Superseded por `cierre-z-f3-sustitucion`**: `cobradas_por_rango_orden` pasa a incluir
`Venta.estado IN ('cobrada', 'sustituida')` y excluye la F3 sustituta
(`venta_sustituta_id`). El origen T se cuenta exactamente una vez, en la ventana de
`orden` propia, sea la conversión del mismo periodo o cross-period; la F3 nunca aporta
un total fantasma. El "doble conteo ACEPTADO" descrito arriba ya NO aplica desde ese
cambio. Ver `openspec/specs/cierre-z/spec.md`, requirement "Cuadre de totales y
desgloses".

## Data Flow

    Admin UI ──POST /api/ventas/convertir {ids[], nif, nombre, domicilio}
      │  require_admin (PIN/rol)
      ▼  ConvertirEnFacturaF3.ejecutar (una transacción)
      ├─ ventas.convertibles() + revalidar cada id ─► SimplificadaNoElegible/YaSustituida
      ├─ validar_documento(nif) ─────────────────────► DestinatarioInvalido
      ├─ Cliente(nif,nombre,domicilio) ─► f3.cliente_id
      ├─ f3.lineas = copia de Σ VentaLinea origen (valores congelados)
      ├─ motor.emit(f3, serie="F", tipo_factura="F3")  ─► correlativo F, huella→último global,
      │                                                    Desglose=Σ por tipo, cola remisión
      ├─ por origen: RegistroFacturaSustituida + VentaSustitucion(N→1)
      ├─ por origen: estado cobrada→sustituida (trigger permitido, campos congelados)
      └─ auditoría "conversion_f3"  ─► commit
      ▼  (después, asíncrono) RemitirLote ─► registro_alta_xml(reg, destinatario=venta.cliente)
                                             └─ <Destinatarios> entre DescripcionOperacion y Desglose

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/aplicacion/convertir_en_factura_f3.py` | Create | Caso de uso + excepciones (`SinSimplificadas`, `SimplificadaNoElegible`, `YaSustituida`, `DestinatarioInvalido`). |
| `app/dominio/puertos.py` | Modify | `RepositorioVentas.convertibles()` en el Protocol. |
| `app/infraestructura/persistencia/repositorios.py` | Modify | Implementa `convertibles()` (T + cobrada + no sustituida). |
| `app/infraestructura/fiscal/xml.py` | Modify | Dataclass `Destinatario`; param `destinatario=None` en `registro_alta_xml`; bloque condicional entre `DescripcionOperacion` y `Desglose`. |
| `app/aplicacion/remitir_lote.py` | Modify | Para F1/F3 resolver destinatario desde `venta.cliente_id` y pasarlo al serializar. |
| `app/dominio/servicios/validaciones_negocio.py` | Modify | `validar_alta(..., tiene_destinatario=True)` cableado para F3 (regla ya existe). |
| `app/presentacion/admin.py` | Modify | `GET /api/ventas/convertibles` + `POST /api/ventas/convertir` (auth, auditoría, mapeo de excepciones). |
| `app/ui/admin.html` | Modify | Panel "Convertir en factura" (Nocturne): multiselección 1..N + form destinatario + confirmar. |

## Interfaces / Contracts

```python
# app/aplicacion/convertir_en_factura_f3.py
@dataclass
class DatosDestinatario:
    nif: str
    nombre: str
    domicilio: str

class ConvertirEnFacturaF3:
    def __init__(self, uow: UnidadDeTrabajo, motor: MotorFiscal): ...
    def ejecutar(self, *, usuario_id: int, origen: str,
                 simplificada_ids: list[int],
                 destinatario: DatosDestinatario) -> ResultadoConversion: ...
# Excepciones → HTTP: SinSimplificadas 422 | SimplificadaNoElegible 409 |
#                     YaSustituida 409 | DestinatarioInvalido 422

# app/infraestructura/fiscal/xml.py
@dataclass
class Destinatario:
    nombre: str
    nif: str
# registro_alta_xml(reg, *, nombre_emisor, sistema, anterior=None, destinatario=None)
#   -> si destinatario: <Destinatarios><IDDestinatario><NombreRazon/><NIF/></IDDestinatario></Destinatarios>
#      (posición XSD: tras DescripcionOperacion, antes de Desglose)

# app/dominio/puertos.py
class RepositorioVentas(Protocol):
    def convertibles(self) -> list["Venta"]: ...   # serie='T' AND cobrada AND no sustituida
```

## Testing Strategy

Strict TDD (`python -m pytest`). Formaliza el flujo hoy hecho a mano en `test_sustitucion.py`.

| Test | Qué valida |
|------|-----------|
| `test_convertir_n_simplificadas_en_una_f3` | N→1 e2e: alta serie F/F3, `VentaSustitucion` + `RegistroFacturaSustituida` por origen, orígenes→`sustituida`. |
| `test_totales_f3_reconcilian_sin_deriva` | `CuotaTotal`/`ImporteTotal`/Desglose de la F3 == Σ de las sustituidas, al céntimo (IVA mezclado 21+10). |
| `test_elegibilidad_rechaza_no_cobrada_no_T_o_inexistente` | `SimplificadaNoElegible`. |
| `test_convertir_dos_veces_una_T_falla` | `YaSustituida` (pre-check, no IntegrityError). |
| `test_nif_destinatario_invalido` | `DestinatarioInvalido`. |
| `test_huella_f3_independiente_del_destinatario` | Frontera fiscal: la huella de la F3 no cambia con/sin destinatario. |
| `test_xml_f3_con_destinatarios_valida_xsd` | Golden F3: bloque `Destinatarios` presente, valida contra XSD oficial. |
| `test_xml_simplificada_T_byte_identica` | Regresión: XML de una T inalterado (destinatario=None). |
| `test_verify_chain_ok_tras_conversion` | Integridad de cadena: `verify_chain().ok` tras convertir; +1 registro global. |
| `test_endpoint_convertir_audita_y_devuelve_f3` | API admin: auth, auditoría `conversion_f3`, 200. |

## Migration / Rollout

No migration required. Modelo (`VentaSustitucion`, `RegistroFacturaSustituida`), estado
`sustituida` y triggers existen desde 0001; el destinatario reutiliza `Cliente` +
`venta.cliente_id` (ya congelado). Rollback = revertir el commit; la rama condicional
`Destinatarios` queda inerte para T/F2. Las F3 ya emitidas son inmutables (invariante 1): el
rollback sólo impide crear nuevas.

## Open Questions

- [ ] Contenido impreso de la F3 (lista de T sustituidas): `NumSerieFactura` + fecha de cada
  una (default de la propuesta). No bloquea el diseño.
