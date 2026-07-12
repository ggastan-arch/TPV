"""Adaptadores SQLAlchemy de los puertos de repositorio.

Envuelven una `Session`. Las entidades son los modelos ORM (ADR-0001)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dominio.puertos import TotalesRangoZ
from app.infraestructura.reloj import ahora_huso
from app.infraestructura.persistencia.modelos import (
    Articulo,
    Boton,
    CierreZ,
    Cliente,
    CodigoBarras,
    ConfiguracionEmpresa,
    Familia,
    LogAuditoria,
    MovimientoStock,
    PaginaBotonera,
    PerfilBotonera,
    RegistroFiscal,
    RemisionIntento,
    TipoIVA,
    Usuario,
    Venta,
)

# Estados terminales de aceptacion: ya no hace falta reintentar la remision.
ESTADOS_ACEPTADOS = ("aceptado", "aceptado_con_errores")


def _escapar_comodines_like(texto: str) -> str:
    """Escapa `\\`, `%` y `_` para que `ilike(..., escape="\\")` los trate como
    texto literal en vez de comodines LIKE."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class RepositorioArticulosSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, articulo_id: int) -> Articulo | None:
        return self._s.get(Articulo, articulo_id)

    def buscar_por_codigo(self, codigo: str) -> Articulo | None:
        cb = self._s.execute(
            select(CodigoBarras).where(CodigoBarras.codigo == codigo)
        ).scalars().first()
        return self._s.get(Articulo, cb.articulo_id) if cb else None

    def agregar(self, articulo: Articulo) -> None:
        self._s.add(articulo)

    def listar(self, incluir_inactivos: bool = True) -> list[Articulo]:
        stmt = select(Articulo).order_by(Articulo.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Articulo.activo.is_(True))
        return list(self._s.execute(stmt).scalars())

    def buscar_por_nombre(self, q: str, limite: int = 20) -> list[Articulo]:
        """Busqueda incremental (lupa del TPV): subcadena case-insensitive sobre
        `nombre` o `nombre_corto`, solo articulos activos. Guarda de longitud
        minima (2 caracteres) para no ejecutar coincidencias con q vacio/1
        caracter. Los comodines LIKE `%`/`_` de `q` se escapan para que se
        traten como texto literal, no como wildcard."""
        q = q.strip()
        if len(q) < 2:
            return []
        patron = f"%{_escapar_comodines_like(q)}%"
        stmt = (
            select(Articulo)
            .where(
                Articulo.activo.is_(True),
                Articulo.nombre.ilike(patron, escape="\\")
                | Articulo.nombre_corto.ilike(patron, escape="\\"),
            )
            .order_by(Articulo.nombre)
            .limit(limite)
        )
        return list(self._s.execute(stmt).scalars())


class RepositorioTiposIvaSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, tipo_iva_id: int) -> TipoIVA | None:
        return self._s.get(TipoIVA, tipo_iva_id)

    def agregar(self, tipo_iva: TipoIVA) -> None:
        self._s.add(tipo_iva)

    def listar(self, incluir_inactivos: bool = True) -> list[TipoIVA]:
        stmt = select(TipoIVA).order_by(TipoIVA.id)
        if not incluir_inactivos:
            stmt = stmt.where(TipoIVA.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioFamiliasSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, familia_id: int) -> Familia | None:
        return self._s.get(Familia, familia_id)

    def agregar(self, familia: Familia) -> None:
        self._s.add(familia)

    def listar(self, incluir_inactivos: bool = True) -> list[Familia]:
        stmt = select(Familia).order_by(Familia.orden, Familia.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Familia.activo.is_(True))
        return list(self._s.execute(stmt).scalars())

    def hijos(self, familia_id: int, solo_activos: bool = False) -> list[Familia]:
        stmt = select(Familia).where(Familia.parent_id == familia_id)
        if solo_activos:
            stmt = stmt.where(Familia.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioAuditoriaSQL:
    def __init__(self, session: Session):
        self._s = session

    def registrar(
        self, *, accion: str, entidad: str | None = None, entidad_id: str | None = None,
        detalle: str | None = None, usuario_id: int | None = None, origen: str = "local",
    ) -> None:
        self._s.add(LogAuditoria(
            fecha_hora_huso=ahora_huso(), usuario_id=usuario_id, accion=accion,
            entidad=entidad, entidad_id=entidad_id, detalle=detalle, origen=origen))


class RepositorioClientesSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, cliente_id: int) -> Cliente | None:
        return self._s.get(Cliente, cliente_id)

    def agregar(self, cliente: Cliente) -> None:
        self._s.add(cliente)

    def listar(self, incluir_inactivos: bool = True) -> list[Cliente]:
        stmt = select(Cliente).order_by(Cliente.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Cliente.activo.is_(True))
        return list(self._s.execute(stmt).scalars())


class RepositorioVentasSQL:
    def __init__(self, session: Session):
        self._s = session

    def agregar(self, venta: Venta) -> None:
        self._s.add(venta)

    def buscar(self, venta_id: int) -> Venta | None:
        return self._s.get(Venta, venta_id)


class RepositorioUsuariosSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, usuario_id: int) -> Usuario | None:
        return self._s.get(Usuario, usuario_id)

    def buscar_por_nombre(self, nombre: str) -> Usuario | None:
        return self._s.execute(
            select(Usuario).where(Usuario.nombre == nombre)
        ).scalars().first()

    def agregar(self, usuario: Usuario) -> None:
        self._s.add(usuario)

    def listar(self, incluir_inactivos: bool = True) -> list[Usuario]:
        stmt = select(Usuario).order_by(Usuario.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(Usuario.activo.is_(True))
        return list(self._s.execute(stmt).scalars())

    def contar_administradores_activos(self, excluir_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(Usuario).where(
            Usuario.rol == "administracion", Usuario.activo.is_(True))
        if excluir_id is not None:
            stmt = stmt.where(Usuario.id != excluir_id)
        return self._s.execute(stmt).scalar_one()


class RepositorioRegistrosSQL:
    def __init__(self, session: Session):
        self._s = session

    def buscar(self, registro_id: int) -> RegistroFiscal | None:
        return self._s.get(RegistroFiscal, registro_id)

    def pendientes(self, maximo: int = 1000) -> list[RegistroFiscal]:
        stmt = (
            select(RegistroFiscal)
            .where(RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS))
            .order_by(RegistroFiscal.orden)
            .limit(min(maximo, 1000))
        )
        return list(self._s.execute(stmt).scalars())

    def contar_pendientes(self) -> int:
        stmt = (
            select(func.count())
            .select_from(RegistroFiscal)
            .where(RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS))
        )
        return self._s.execute(stmt).scalar_one()

    def hay_incidencia_pendiente(self) -> bool:
        stmt = (
            select(RemisionIntento.id)
            .join(RegistroFiscal, RemisionIntento.registro_fiscal_id == RegistroFiscal.id)
            .where(
                RemisionIntento.incidencia.is_(True),
                RegistroFiscal.estado_remision.not_in(ESTADOS_ACEPTADOS),
            )
            .limit(1)
        )
        return self._s.execute(stmt).first() is not None

    def registros_a_reintentar(
        self, ahora: datetime | None = None, intervalo_horas: int = 1
    ) -> list[RegistroFiscal]:
        ahora = ahora or datetime.now().astimezone()
        limite = timedelta(hours=intervalo_horas)
        a_reintentar = []
        for reg in self.pendientes():
            ultimo = self._ultimo_intento(reg.id)
            if ultimo is None or ahora - datetime.fromisoformat(ultimo.fecha_hora_huso) >= limite:
                a_reintentar.append(reg)
        return a_reintentar

    def ultimos(self, limite: int = 10) -> list[RegistroFiscal]:
        stmt = select(RegistroFiscal).order_by(RegistroFiscal.orden.desc()).limit(limite)
        return list(self._s.execute(stmt).scalars())

    def max_orden_alta(self) -> int:
        """Mayor `orden` entre los registros de tipo alta (0 si no existe ninguno).
        Fija `hasta_orden` del Cierre Z (ver design.md, mecanismo de rango)."""
        stmt = select(func.max(RegistroFiscal.orden)).where(
            RegistroFiscal.tipo_registro == "alta"
        )
        return self._s.execute(stmt).scalar_one_or_none() or 0

    def registrar_resultado(
        self, registro: RegistroFiscal, resultado: str, *,
        codigo_error: str | None = None, descripcion: str | None = None,
        csv: str | None = None,
    ) -> None:
        """Anota el intento (append-only) y actualiza el estado canonico del registro.
        Una incidencia (no se pudo remitir) deja el registro 'pendiente' para reintento."""
        incidencia = resultado == "incidencia"
        self._s.add(RemisionIntento(
            registro_fiscal_id=registro.id, fecha_hora_huso=ahora_huso(),
            resultado=resultado, incidencia=incidencia,
            codigo_error=codigo_error, descripcion=descripcion, csv=csv))
        registro.estado_remision = "pendiente" if incidencia else resultado

    def _ultimo_intento(self, registro_id: int) -> RemisionIntento | None:
        stmt = (
            select(RemisionIntento)
            .where(RemisionIntento.registro_fiscal_id == registro_id)
            .order_by(RemisionIntento.id.desc())
            .limit(1)
        )
        return self._s.execute(stmt).scalars().first()


class RepositorioCierresZSQL:
    """Cierre Z: snapshot inmutable derivado por rango de `registro_fiscal.orden`.
    Solo LECTURA sobre `venta`/`registro_fiscal` (invariante 1); jamas los muta."""

    def __init__(self, session: Session):
        self._s = session

    def ultimo(self) -> CierreZ | None:
        stmt = select(CierreZ).order_by(CierreZ.numero.desc()).limit(1)
        return self._s.execute(stmt).scalars().first()

    def agregar(self, cierre: CierreZ) -> None:
        self._s.add(cierre)

    def buscar(self, numero: int) -> CierreZ | None:
        stmt = select(CierreZ).where(CierreZ.numero == numero)
        return self._s.execute(stmt).scalars().first()

    def listar(self, limite: int = 100) -> list[CierreZ]:
        stmt = select(CierreZ).order_by(CierreZ.numero.desc()).limit(limite)
        return list(self._s.execute(stmt).scalars())

    def cobradas_por_rango_orden(self, desde_orden: int, hasta_orden: int) -> TotalesRangoZ:
        """Agrega totales y desgloses de las ventas `cobrada` cuyo registro de ALTA
        tiene `orden` en [desde_orden, hasta_orden]. Rango vacio -> totales en cero
        (Z a cero permitido, ver design.md)."""
        if hasta_orden < desde_orden:
            return TotalesRangoZ(
                num_tickets=0, base_total=Decimal("0.00"), cuota_total=Decimal("0.00"),
                total_con_iva=Decimal("0.00"), desglose_iva=[], desglose_pago=[],
            )

        stmt = (
            select(Venta)
            .join(RegistroFiscal, RegistroFiscal.venta_id == Venta.id)
            .where(
                RegistroFiscal.tipo_registro == "alta",
                RegistroFiscal.orden >= desde_orden,
                RegistroFiscal.orden <= hasta_orden,
                Venta.estado == "cobrada",
            )
        )
        ventas = list(self._s.execute(stmt).scalars())

        base_total = Decimal("0.00")
        cuota_total = Decimal("0.00")
        total_con_iva = Decimal("0.00")
        bases_iva: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0.00"))
        cuotas_iva: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0.00"))
        por_medio: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

        for venta in ventas:
            base_total += venta.base_total
            cuota_total += venta.cuota_total
            total_con_iva += venta.total_con_iva
            for linea in venta.lineas:
                bases_iva[linea.tipo_iva_porcentaje] += linea.base_linea
                cuotas_iva[linea.tipo_iva_porcentaje] += linea.cuota_linea
            for pago in venta.pagos:
                por_medio[pago.medio] += pago.importe

        return TotalesRangoZ(
            num_tickets=len(ventas),
            base_total=base_total,
            cuota_total=cuota_total,
            total_con_iva=total_con_iva,
            desglose_iva=[
                (tipo, bases_iva[tipo], cuotas_iva[tipo]) for tipo in sorted(bases_iva)
            ],
            desglose_pago=sorted(por_medio.items()),
        )


class RepositorioConfiguracionSQL:
    """Ajuste de empresa global: fila singleton `id=1`. Tabla MUTABLE (no es dato
    fiscal): sin triggers de inmutabilidad."""

    def __init__(self, session: Session):
        self._s = session

    def control_stock_activo(self) -> bool:
        cfg = self._s.get(ConfiguracionEmpresa, 1)
        return bool(cfg.control_stock_activo) if cfg is not None else False

    def fijar_control_stock(self, activo: bool) -> None:
        cfg = self._s.get(ConfiguracionEmpresa, 1)
        cfg.control_stock_activo = activo


# Signo del efecto de cada tipo de movimiento sobre el saldo (design.md: `cantidad`
# se guarda siempre como magnitud positiva; el signo lo aporta `tipo`).
_SIGNO_MOVIMIENTO = {"entrada": Decimal("1"), "venta": Decimal("-1"), "merma": Decimal("-1")}


class RepositorioStockSQL:
    """Stock informativo: agregacion on-the-fly en Python/Decimal, nunca `SUM` SQL
    (los importes se guardan como TEXT; `SUM` degradaria a coma flotante)."""

    def __init__(self, session: Session):
        self._s = session

    def agregar(self, movimiento: MovimientoStock) -> None:
        self._s.add(movimiento)

    def movimientos(self, articulo_id: int) -> list[MovimientoStock]:
        stmt = (
            select(MovimientoStock)
            .where(MovimientoStock.articulo_id == articulo_id)
            .order_by(MovimientoStock.id)
        )
        return list(self._s.execute(stmt).scalars())

    def stock_actual(self, articulo_id: int) -> Decimal:
        saldo = Decimal("0")
        for movimiento in self.movimientos(articulo_id):
            saldo += _SIGNO_MOVIMIENTO[movimiento.tipo] * movimiento.cantidad
        return saldo

    def rastreados_en_negativo(self) -> list[tuple[int, Decimal]]:
        ids_rastreados = self._s.execute(
            select(Articulo.id).where(Articulo.control_stock.is_(True)).order_by(Articulo.id)
        ).scalars()
        negativos = []
        for articulo_id in ids_rastreados:
            saldo = self.stock_actual(articulo_id)
            if saldo < 0:
                negativos.append((articulo_id, saldo))
        return negativos


class RepositorioBotoneraSQL:
    """Botonera configurable (perfil -> pagina -> boton). Tabla mutable (config,
    no dato fiscal): sin triggers de inmutabilidad. El borrado en cascada de
    perfil/pagina se hace con `session.delete(...)` directamente, apoyado en
    `cascade="all, delete-orphan"` de las relaciones del modelo."""

    def __init__(self, session: Session):
        self._s = session

    def arbol(self) -> list[PerfilBotonera]:
        """Perfiles con sus paginas y botones (para el editor completo)."""
        stmt = select(PerfilBotonera).order_by(PerfilBotonera.id)
        return list(self._s.execute(stmt).scalars())

    def buscar_perfil(self, perfil_id: int) -> PerfilBotonera | None:
        return self._s.get(PerfilBotonera, perfil_id)

    def agregar_perfil(self, perfil: PerfilBotonera) -> None:
        self._s.add(perfil)

    def perfiles(self) -> list[PerfilBotonera]:
        """Todos los perfiles (usado por `activar_perfil` para desactivar los
        demas en la misma transaccion)."""
        stmt = select(PerfilBotonera).order_by(PerfilBotonera.id)
        return list(self._s.execute(stmt).scalars())

    def buscar_pagina(self, pagina_id: int) -> PaginaBotonera | None:
        return self._s.get(PaginaBotonera, pagina_id)

    def agregar_pagina(self, pagina: PaginaBotonera) -> None:
        self._s.add(pagina)

    def reemplazar_botones(self, pagina: PaginaBotonera, botones: list[Boton]) -> None:
        """Reemplazo atomico: vacia la coleccion (delete-orphan borra los
        botones previos en el flush) y agrega los nuevos."""
        pagina.botones.clear()
        self._s.flush()
        pagina.botones.extend(botones)
