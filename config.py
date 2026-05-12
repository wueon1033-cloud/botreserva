"""
config.py
---------
Carga y valida la configuración desde el archivo .env.
Si una variable obligatoria falta, lanza un error claro.
"""

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from dotenv import load_dotenv


# Ruta raíz del proyecto (donde está este archivo)
BASE_DIR = Path(__file__).resolve().parent

# Carpetas para logs y screenshots
LOGS_DIR = BASE_DIR / "logs"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
LOGS_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Cargar variables desde .env
load_dotenv(BASE_DIR / ".env")


def _get_required(key: str) -> str:
    """Lee una variable obligatoria desde el entorno. Falla si está vacía."""
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"Falta la variable obligatoria '{key}' en el archivo .env. "
            f"Copia .env.example a .env y rellena los valores."
        )
    return value


def _get_optional(key: str, default: str) -> str:
    """Lee una variable opcional con valor por defecto."""
    value = os.getenv(key, "").strip()
    return value if value else default


def _parse_bool(value: str) -> bool:
    """Convierte 'true'/'false' (en cualquier capitalización) a booleano."""
    return value.strip().lower() in {"1", "true", "yes", "y", "si", "sí"}


def _parse_time(value: str, field_name: str) -> time:
    """Convierte 'HH:MM' a un objeto datetime.time."""
    try:
        hh, mm = value.strip().split(":")
        return time(hour=int(hh), minute=int(mm))
    except Exception as exc:
        raise RuntimeError(
            f"El valor de {field_name} ('{value}') no tiene formato HH:MM válido."
        ) from exc


@dataclass(frozen=True)
class Settings:
    # Credenciales
    olympic_email: str
    olympic_password: str
    telegram_bot_token: str
    telegram_chat_id: str

    # URLs
    login_url: str
    agenda_url: str

    # Ventana de ejecución
    target_start_time: time
    target_end_time: time

    # Clase objetivo
    target_class_start: str  # se guarda como string "09:00" porque se busca como texto en el DOM
    target_class_end: str    # idem

    # Comportamiento
    check_interval_seconds: float
    headless: bool
    dry_run: bool


def load_settings() -> Settings:
    """Construye el objeto Settings leyendo el .env."""
    return Settings(
        olympic_email=_get_required("OLYMPIC_EMAIL"),
        olympic_password=_get_required("OLYMPIC_PASSWORD"),
        telegram_bot_token=_get_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get_required("TELEGRAM_CHAT_ID"),
        login_url=_get_optional(
            "LOGIN_URL",
            "https://reservas.olympicgym.cl/accounts/login/?next=/agenda/",
        ),
        agenda_url=_get_optional(
            "AGENDA_URL",
            "https://reservas.olympicgym.cl/agenda/",
        ),
        target_start_time=_parse_time(
            _get_optional("TARGET_START_TIME", "07:00"), "TARGET_START_TIME"
        ),
        target_end_time=_parse_time(
            _get_optional("TARGET_END_TIME", "07:05"), "TARGET_END_TIME"
        ),
        target_class_start=_get_optional("TARGET_CLASS_START", "09:00"),
        target_class_end=_get_optional("TARGET_CLASS_END", "10:00"),
        check_interval_seconds=float(_get_optional("CHECK_INTERVAL_SECONDS", "1")),
        headless=_parse_bool(_get_optional("HEADLESS", "false")),
        dry_run=_parse_bool(_get_optional("DRY_RUN", "true")),
    )
