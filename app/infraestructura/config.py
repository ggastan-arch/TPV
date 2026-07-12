"""Configuracion de la aplicacion (pydantic-settings).

Variables con prefijo TPV_ o desde un fichero .env.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ruta de la BD de produccion (unica fuente de verdad fuera de modo demo). Se
# expone como constante para que la salvaguarda de arranque (app/main.py) pueda
# comparar rutas absolutas sin duplicar el literal.
DB_PATH_PRODUCCION = "tpv.db"

# Perfil DEMO (aislado): BD y emisor propios, certificado nunca cargado
# (invariante 7). Vease docs/adr/0009-perfil-de-arranque-demo.md.
DEMO_DB_PATH = "tpv_demo.db"
DEMO_NIF = "00000000T"
DEMO_NOMBRE = "AcuaTPV DEMO (documento de prueba)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TPV_", env_file=".env", extra="ignore"
    )

    # Perfil de arranque: 'produccion' (por defecto, comportamiento actual) o
    # 'demo' (aislado). Se lee de TPV_PROFILE sin el prefijo TPV_ habitual
    # (validation_alias fija el nombre exacto de la variable).
    perfil: Literal["produccion", "demo"] = Field(
        "produccion", validation_alias="TPV_PROFILE"
    )

    # Base de datos local (una sola fuente de verdad, SQLite en modo WAL).
    db_path: str = DB_PATH_PRODUCCION
    busy_timeout_ms: int = 10_000

    # Identificacion del SIF y del obligado a expedir (para el registro fiscal).
    # 00000000T es un NIF de prueba valido; sustituir por el de la persona titular.
    nif_emisor: str = "00000000T"
    nombre_emisor: str = "AcuaTPV"

    # Bloque SistemaInformatico: identifica al PRODUCTOR del software (el
    # desarrollador), no a la persona titular. Debe coincidir con la declaracion responsable.
    nombre_productor: str = "AcuaTPV Dev"
    nif_productor: str = "00000000T"
    nombre_sistema: str = "TPV AcuaTPV"  # NombreSistemaInformatico (max 30)
    id_sistema: str = "AT"                     # IdSistemaInformatico (max 2!)
    version_sistema: str = "0.1.0"             # Version (max 50)
    numero_instalacion: str = "1"              # NumeroInstalacion (max 100)

    # Directorio de los XSD oficiales de la AEAT.
    schemas_dir: str = "schemas"

    # Secreto para firmar la cookie de sesion de la consola de administracion.
    # EN PRODUCCION hay que sobreescribirlo con TPV_SESSION_SECRET (valor largo y aleatorio).
    session_secret: str = "dev-secreto-de-sesion-CAMBIAR-en-produccion"

    # Entorno de la AEAT para la URL del QR y los servicios web de remision.
    entorno_aeat: str = "pruebas"  # 'pruebas' | 'produccion'

    # Certificado de la persona titular para la remision SOAP (mutual-TLS). El certificado
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

    @model_validator(mode="after")
    def _resolver_perfil(self) -> "Settings":
        """En modo demo fuerza BD y emisor propios y anula el certificado.

        Se ejecuta ANTES de crear `engine`/`SessionLocal` (singletons de modulo
        en db.py), de modo que estos nacen ya ligados a la BD demo. No admite
        override por variable de entorno: el aislamiento no es negociable
        (invariante 5: nada de "modo formacion"; invariante 7: el certificado
        nunca se carga en demo).
        """
        if self.perfil == "demo":
            self.db_path = DEMO_DB_PATH
            self.nif_emisor = DEMO_NIF
            self.nombre_emisor = DEMO_NOMBRE
            self.certificado_cert_path = None
            self.certificado_key_path = None
        return self


settings = Settings()
