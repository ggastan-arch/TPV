"""Series de numeracion y registro de facturacion (RegistroAlta / RegistroAnulacion).

Estructura conforme a la Orden HAC/1177/2024 (docs/VERIFACTU_ESQUEMAS_HAC1177.md 3):
huella, huella_anterior, encadenamiento, fecha_hora_huso, estado_remision.
La cadena de huellas es UNICA por sistema (no por serie) y estrictamente secuencial:
el campo `orden` fija la posicion en la cadena.

Fase 1: la estructura y el encadenamiento se implementan ya (NullEngine). Fase 2:
serializacion XML, QR y remision a la AEAT (VerifactuEngine). Los registros son
INMUTABLES salvo `estado_remision` (metadato de envio, no forma parte de la huella).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infraestructura.tipos import Dinero, Porcentaje
from app.infraestructura.persistencia.modelos.base import Base

# Series correlativas separadas (invariante 2): simplificadas, completas, rectificativas.
TIPOS_FACTURA = ("F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5")

# Estados de remision (canonicos, en registro_fiscal.estado_remision) y resultados
# de cada intento de envio (historico append-only en remision_intento).
ESTADOS_REMISION = (
    "no_remitido",
    "pendiente",
    "aceptado",
    "aceptado_con_errores",
    "rechazado",
    # Terminal anomalo, no reintentable automaticamente (rechazo de cabecera o
    # duplicado "Anulada"): requiere accion explicita de un administrador
    # (endpoint /api/fiscal/reencolar). Sin CHECK en BD (columna String plana,
    # sin migracion): ver design.md, decision "SIN migracion Alembic".
    "requiere_intervencion",
)
RESULTADOS_REMISION = (
    "enviado",
    "aceptado",
    "aceptado_con_errores",
    "rechazado",
    "incidencia",
)


class Serie(Base):
    __tablename__ = "serie"

    codigo: Mapped[str] = mapped_column(String, primary_key=True)  # 'T' | 'F' | 'R'
    descripcion: Mapped[str] = mapped_column(String, nullable=False)
    tipo_factura_default: Mapped[str] = mapped_column(String, nullable=False)


class ContadorSerie(Base):
    """Ultimo numero asignado por serie y ejercicio. Se incrementa dentro de la
    transaccion de emision (BEGIN IMMEDIATE) -> numeracion sin huecos ni duplicados."""

    __tablename__ = "contador_serie"

    serie: Mapped[str] = mapped_column(
        ForeignKey("serie.codigo", ondelete="RESTRICT"), primary_key=True
    )
    ejercicio: Mapped[int] = mapped_column(Integer, primary_key=True)
    ultimo_numero: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RegistroFiscal(Base):
    __tablename__ = "registro_fiscal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Posicion en la cadena unica del sistema (monotona, sin huecos).
    orden: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    tipo_registro: Mapped[str] = mapped_column(String, nullable=False)  # alta | anulacion
    venta_id: Mapped[int] = mapped_column(
        ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Campos del registro (nombres alineados con el anexo de la Orden) ---
    id_emisor: Mapped[str] = mapped_column(String, nullable=False)  # IDEmisorFactura (NIF)
    num_serie_factura: Mapped[str] = mapped_column(String, nullable=False)  # NumSerieFactura
    fecha_expedicion: Mapped[str] = mapped_column(String, nullable=False)  # FechaExpedicionFactura
    tipo_factura: Mapped[str] = mapped_column(String, nullable=False)  # TipoFactura (L2)
    descripcion_operacion: Mapped[str | None] = mapped_column(String, nullable=True)
    cuota_total: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)  # CuotaTotal
    importe_total: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)  # ImporteTotal

    # --- Encadenamiento (bloque Encadenamiento) ---
    primer_registro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registro_anterior_id: Mapped[int | None] = mapped_column(
        ForeignKey("registro_fiscal.id", ondelete="RESTRICT"), nullable=True
    )
    huella_anterior: Mapped[str | None] = mapped_column(String, nullable=True)
    huella: Mapped[str] = mapped_column(String, nullable=False)  # SHA-256 hex mayusculas
    tipo_huella: Mapped[str] = mapped_column(String, nullable=False, default="01")  # 01=SHA-256
    fecha_hora_huso_gen_registro: Mapped[str] = mapped_column(String, nullable=False)

    # Metadato de envio (NO forma parte de la huella; editable por el motor).
    estado_remision: Mapped[str] = mapped_column(String, nullable=False, default="no_remitido")

    # Para RegistroAnulacion: el alta que se anula.
    registro_alta_anulado_id: Mapped[int | None] = mapped_column(
        ForeignKey("registro_fiscal.id", ondelete="RESTRICT"), nullable=True
    )

    desglose: Mapped[list["RegistroFiscalDesglose"]] = relationship(
        back_populates="registro", cascade="all, delete-orphan",
        foreign_keys="RegistroFiscalDesglose.registro_fiscal_id",
    )
    facturas_sustituidas: Mapped[list["RegistroFacturaSustituida"]] = relationship(
        back_populates="registro", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("orden", name="uq_registro_orden"),)


class RegistroFiscalDesglose(Base):
    """DetalleDesglose por tipo impositivo presente en la factura (Orden 3.1)."""

    __tablename__ = "registro_fiscal_desglose"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registro_fiscal_id: Mapped[int] = mapped_column(
        ForeignKey("registro_fiscal.id", ondelete="CASCADE"), nullable=False
    )
    impuesto: Mapped[str] = mapped_column(String, nullable=False, default="01")  # 01 = IVA
    clave_regimen: Mapped[str] = mapped_column(String, nullable=False, default="01")  # general
    calificacion: Mapped[str] = mapped_column(String, nullable=False, default="S1")
    tipo_impositivo: Mapped[Decimal] = mapped_column(Porcentaje(), nullable=False)
    base_imponible: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)
    cuota_repercutida: Mapped[Decimal] = mapped_column(Dinero(), nullable=False)

    registro: Mapped[RegistroFiscal] = relationship(
        back_populates="desglose", foreign_keys=[registro_fiscal_id]
    )


class RegistroFacturaSustituida(Base):
    """Bloque FacturasSustituidas: identifica las simplificadas que sustituye un F3."""

    __tablename__ = "registro_factura_sustituida"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registro_fiscal_id: Mapped[int] = mapped_column(
        ForeignKey("registro_fiscal.id", ondelete="CASCADE"), nullable=False
    )
    id_emisor: Mapped[str] = mapped_column(String, nullable=False)
    num_serie_factura: Mapped[str] = mapped_column(String, nullable=False)
    fecha_expedicion: Mapped[str] = mapped_column(String, nullable=False)

    registro: Mapped[RegistroFiscal] = relationship(back_populates="facturas_sustituidas")


class RemisionIntento(Base):
    """Historico APPEND-ONLY de intentos de remision a la AEAT de un registro.

    El estado canonico vive en registro_fiscal.estado_remision; aqui queda el rastro
    de cada envio (resultado, incidencia, CSV, error). Los reintentos (>=1/hora) y la
    marca de incidencia del siguiente envio se derivan de este historico.
    """

    __tablename__ = "remision_intento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registro_fiscal_id: Mapped[int] = mapped_column(
        ForeignKey("registro_fiscal.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_hora_huso: Mapped[str] = mapped_column(String, nullable=False)
    resultado: Mapped[str] = mapped_column(String, nullable=False)
    incidencia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    codigo_error: Mapped[str | None] = mapped_column(String, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    csv: Mapped[str | None] = mapped_column(String, nullable=True)  # CSV de la AEAT

    __table_args__ = (
        CheckConstraint(
            "resultado IN ('enviado','aceptado','aceptado_con_errores',"
            "'rechazado','incidencia')",
            name="ck_remision_resultado",
        ),
    )
