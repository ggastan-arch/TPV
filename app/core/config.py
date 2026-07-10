"""Configuracion de la aplicacion (pydantic-settings).

Variables con prefijo TPV_ o desde un fichero .env.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TPV_", env_file=".env", extra="ignore"
    )

    # Base de datos local (una sola fuente de verdad, SQLite en modo WAL).
    db_path: str = "tpv.db"
    busy_timeout_ms: int = 10_000

    # Identificacion del SIF y del obligado a expedir (para el registro fiscal).
    # 00000000T es un NIF de prueba valido; sustituir por el de la titular.
    nif_emisor: str = "00000000T"
    nombre_emisor: str = "Bizkaitropik"

    # Bloque SistemaInformatico: identifica al PRODUCTOR del software (el
    # desarrollador), no a la titular. Debe coincidir con la declaracion responsable.
    nombre_productor: str = "Bizkaitropik Dev"
    nif_productor: str = "00000000T"
    nombre_sistema: str = "TPV Bizkaitropik"  # NombreSistemaInformatico (max 30)
    id_sistema: str = "BZ"                     # IdSistemaInformatico (max 2!)
    version_sistema: str = "0.1.0"             # Version (max 50)
    numero_instalacion: str = "1"              # NumeroInstalacion (max 100)

    # Directorio de los XSD oficiales de la AEAT.
    schemas_dir: str = "schemas"

    # Entorno de la AEAT para la URL del QR y los servicios web de remision.
    entorno_aeat: str = "pruebas"  # 'pruebas' | 'produccion'

    # Certificado de la titular para la remision SOAP (mutual-TLS). El certificado
    # NUNCA sale del servidor. Sin el, el cliente SOAP queda listo pero no puede remitir.
    certificado_cert_path: str | None = None  # PEM (certificado, o cert+clave juntos)
    certificado_key_path: str | None = None   # PEM de la clave privada (si va aparte)
    certificado_sello: bool = False           # endpoint de certificado de sello (www10/prewww10)

    # Control del reloj (invariante 6 de CLAUDE.md): desviacion maxima tolerada.
    max_desviacion_reloj_s: int = 60

    # Impresora de tickets ESC/POS (80 mm).
    impresora_tipo: str = "dummy"  # dummy | network
    impresora_host: str | None = None
    impresora_puerto: int = 9100
    ticket_ancho: int = 42  # columnas (Font A, 80 mm)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
