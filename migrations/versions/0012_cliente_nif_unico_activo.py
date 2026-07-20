"""cliente: indice unico parcial sobre `nif` para clientes ACTIVOS.

Revision ID: 0012_cliente_nif_unico_activo
Revises: 0011_venta_trigger_campos_congelados
Create Date: 2026-07-20

Cierra un hueco de integridad de datos: `cliente.nif` es NULLABLE (el NIF es
opcional en la factura simplificada) y no tenia ninguna restriccion UNIQUE, asi
que hasta ahora era posible dar de alta DOS clientes ACTIVOS con el mismo NIF.
`RepositorioClientesSQL.buscar_por_nif` (repositorios.py) ya filtraba solo
`activo=True`, pero nada en el esquema ni en la capa de aplicacion impedia
crear el duplicado en primer lugar.

Regla decidida por el usuario: el NIF debe ser unico ENTRE CLIENTES ACTIVOS
cuando esta presente.
- Varios clientes SIN NIF son validos (NULL nunca colisiona en un indice
  UNIQUE, ni en SQLite ni en el estandar SQL).
- Un cliente INACTIVO con ese NIF NO bloquea un alta nueva (p. ej. un cliente
  dado de baja y vuelto a crear con los mismos datos).

`ServicioClientes.crear`/`actualizar` (app/aplicacion/clientes.py) ya rechazan
esto en la capa de aplicacion ANTES de llegar aqui (excepcion `NifDuplicado`,
mapeada a HTTP 409 en app/presentacion/tpv.py y admin.py). Este indice es la
red de seguridad de BD: defensa en profundidad para cualquier otra via de
escritura -- presente o futura -- que pueda saltarse esa capa, empezando por
`ServicioClientes.activar` (reactivar un cliente inactivo NO repite el
chequeo de aplicacion y depende de este indice para rechazar la colision).

`op.create_index` NATIVO con `sqlite_where` (indice parcial), NUNCA
`batch_alter_table`: no recrea la tabla `cliente` ni toca ninguna de sus
filas, y no interfiere con ningun trigger de inmutabilidad de
`venta`/`registro_fiscal` (esta migracion no los toca en absoluto).

CAVEAT (a proposito, sin resolver aqui): si una base de datos REAL ya
tuviera dos o mas clientes ACTIVOS con el mismo NIF antes de aplicar esta
migracion, `upgrade()` FALLARA -- SQLite rechaza crear un indice UNIQUE sobre
datos que ya lo violan. Esta migracion NO intenta detectar ni de-duplicar
esos casos automaticamente: eso exigiria una decision de negocio (que
cliente activo se conserva, si el resto se desactiva, etc.) fuera del
alcance de un script de migracion. Los datos de demostracion (`make seed`) se
resiembran limpios y no tienen este problema; si aparece en una BD real,
resolver el duplicado a mano antes de reintentar `upgrade`.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_cliente_nif_unico_activo"
down_revision = "0011_venta_trigger_campos_congelados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_cliente_nif_activo", "cliente", ["nif"],
        unique=True, sqlite_where=sa.text("nif IS NOT NULL AND activo = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_cliente_nif_activo", table_name="cliente")
