# Proposal: Editor visual de botoneras (consola admin)

## Intent

La botonera (perfil → página → rejilla de botones) ya está modelada y el TPV la
renderiza vía `GET /tpv/api/botonera`, pero HOY solo se puede configurar por seed o
SQL manual. La titular necesita crear y editar botoneras desde la consola de
administración con un editor visual drag & drop. Motivación: autonomía operativa
(cambiar la venta según temporada/stock) sin intervención técnica ni riesgo de dejar
la botonera del TPV en estado inválido.

## Scope

### In Scope
- **Backend (fuente de verdad, valida TODO)**: CRUD de perfiles y páginas; alta,
  edición, borrado y colocación de botones; guardado del layout de una página;
  activación de perfil; toda acción auditada (invariante 4).
- **Validaciones EN BACKEND** (un frontend con bugs o cliente manual NO puede
  persistir un layout inválido): botones dentro de la rejilla (fila/columna +
  alto/ancho ≤ filas/columnas), sin solape entre botones, destino único
  (artículo|familia|función — ya hay CHECK `ck_boton_destino_unico`), función ∈
  `FUNCIONES`, y existencia de artículo/familia referenciados.
- **Frontend**: editor drag & drop en `admin.html` (HTML/JS sin framework): rejilla,
  arrastrar/soltar y redimensionar botones, paleta de destinos, edición de
  color/icono/texto, gestión de páginas y perfiles, guardar contra la API.

### Out of Scope
- Undo/redo; gestos táctiles avanzados/multitouch; i18n de textos de botón.
- Cualquier cambio al contrato `GET /tpv/api/botonera` (mantener compatibilidad).

## Non-Goals
- Reemplazar el render del TPV.
- Tests automáticos del JS del editor (el proyecto no tiene infra de test JS): el
  frontend se verifica A MANO; el backend va con TDD estricto.

## Capabilities

### New Capabilities
- `editor-botoneras`: API admin para gestionar perfiles/páginas/botones con
  validación de rejilla en backend, activación de perfil y auditoría; editor visual
  drag & drop en la consola.

### Modified Capabilities
- None. Los endpoints nuevos viven bajo `/admin/api/*` y heredan la autenticación
  ya especificada en `consola-administracion` (sesión + rol); no cambia su requisito.

## Approach

Endpoints bajo `/admin` siguiendo el patrón existente (`require_admin`, `get_uow`,
Pydantic, mapeo de excepciones a HTTP, `LogAuditoria` con `_origen`). Servicio de
aplicación fino que centraliza las validaciones de rejilla y lanza excepciones de
dominio tipadas. El editor consume esa API y produce datos compatibles con el
contrato que ya lee el TPV.

## Affected Areas

| Área | Impacto | Descripción |
|------|--------|-------------|
| `app/presentacion/admin.py` | Modified | Router: endpoints CRUD de botoneras |
| `app/aplicacion/botoneras.py` | New | Servicio + validaciones de rejilla |
| `app/infraestructura/persistencia/modelos/botonera.py` | Reuse | Modelos ya existen |
| `app/ui/admin.html` | Modified | UI del editor drag & drop |
| `tests/` | New | Tests de validación backend + test del contrato TPV |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|------------|
| JS frágil sin tests persiste layout inválido | Media | Backend rechaza estados inválidos; verificación manual |
| Romper el contrato `/tpv/api/botonera` | Media | Mantener compatibilidad; test del contrato |
| Perfil activo ambiguo para el TPV | Media | Resolver en design (activar uno desactiva los demás) |

## Rollback Plan

Cambio aditivo: no toca ventas ni registros fiscales. Revertir = quitar los
endpoints nuevos y la UI del editor; los modelos y el contrato del TPV siguen
intactos. La configuración por seed/SQL sigue funcionando.

## Dependencies

- Ninguna externa. Reutiliza modelos, `get_uow`, `require_admin` y `LogAuditoria`
  existentes.

## Open Questions (resolver en design)

- Guardado por lote del layout de una página (bulk upsert) vs. operaciones por botón.
- ¿Un único perfil activo a la vez (activar uno desactiva los demás) para que el TPV
  sea inequívoco?
- Reglas exactas de detección de solape entre botones.

## Success Criteria

- [ ] Se puede crear/editar un perfil con páginas y botones desde la consola.
- [ ] El backend RECHAZA layouts inválidos (bounds, solape, destino único, función
      válida, referencias inexistentes), con tests que lo demuestran.
- [ ] El TPV renderiza lo editado sin cambios en `GET /tpv/api/botonera`.
- [ ] Toda acción del editor queda en el log de auditoría (invariante 4).
