"""Botonera configurable: perfil -> pagina -> boton.

Un boton apunta EXACTAMENTE a uno de: articulo, familia (navega a hijos) o funcion
(cobrar, convertir en factura, devolucion, aparcar/desaparcar, abrir cajon,
descuento, cierre de caja). Un CHECK garantiza que el destino sea unico.

`FUNCIONES` es un concepto de DOMINIO (el conjunto de acciones rapidas soportadas
por un boton); se define en `app.dominio.servicios.botonera` y se reexporta aqui
para quien importe los modelos. La infraestructura depende del dominio, nunca al
reves (dominio puro en runtime, ver pyproject.toml [tool.importlinter])."""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.dominio.servicios.botonera import FUNCIONES
from app.infraestructura.persistencia.modelos.base import Base


class PerfilBotonera(Base):
    __tablename__ = "perfil_botonera"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    paginas: Mapped[list["PaginaBotonera"]] = relationship(
        back_populates="perfil", cascade="all, delete-orphan"
    )


class PaginaBotonera(Base):
    __tablename__ = "pagina_botonera"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    perfil_id: Mapped[int] = mapped_column(
        ForeignKey("perfil_botonera.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    columnas: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    filas: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    perfil: Mapped[PerfilBotonera] = relationship(back_populates="paginas")
    botones: Mapped[list["Boton"]] = relationship(
        back_populates="pagina", cascade="all, delete-orphan"
    )


class Boton(Base):
    __tablename__ = "boton"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pagina_id: Mapped[int] = mapped_column(
        ForeignKey("pagina_botonera.id", ondelete="CASCADE"), nullable=False
    )
    fila: Mapped[int] = mapped_column(Integer, nullable=False)
    columna: Mapped[int] = mapped_column(Integer, nullable=False)
    ancho: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    alto: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    icono: Mapped[str | None] = mapped_column(String, nullable=True)
    texto: Mapped[str | None] = mapped_column(String, nullable=True)

    # Destino: exactamente uno.
    articulo_id: Mapped[int | None] = mapped_column(
        ForeignKey("articulo.id", ondelete="RESTRICT"), nullable=True
    )
    familia_id: Mapped[int | None] = mapped_column(
        ForeignKey("familia.id", ondelete="RESTRICT"), nullable=True
    )
    funcion: Mapped[str | None] = mapped_column(String, nullable=True)

    pagina: Mapped[PaginaBotonera] = relationship(back_populates="botones")

    __table_args__ = (
        CheckConstraint(
            "((articulo_id IS NOT NULL) + (familia_id IS NOT NULL) "
            "+ (funcion IS NOT NULL)) = 1",
            name="ck_boton_destino_unico",
        ),
    )
