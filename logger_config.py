"""
logger_config.py
----------------
Configura un logger que escribe simultáneamente a la consola y a un archivo
en la carpeta logs/, con rotación por día. Opcionalmente, también a Telegram
para WARNING y superior (usando add_telegram_handler).
"""

import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from config import LOGS_DIR


def setup_logger(name: str = "olympic_bot") -> logging.Logger:
    """
    Devuelve un logger único (configurado solo una vez aunque se llame varias veces).
    - Consola: nivel INFO con formato corto.
    - Archivo: nivel DEBUG con formato detallado, rotación diaria (conserva 14 días).
    """
    logger = logging.getLogger(name)

    # Evitar duplicar handlers si se llama varias veces
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ---- Handler de consola ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # ---- Handler de archivo (rotación diaria) ----
    log_file = LOGS_DIR / f"olympic_bot_{datetime.now():%Y-%m-%d}.log"
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------------------
# Handler de Telegram (WARNING+)
# ---------------------------------------------------------------------------

def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TelegramLogHandler(logging.Handler):
    """Reenvía mensajes WARNING+ al chat de Telegram del bot."""

    def __init__(self, notifier, level: int = logging.WARNING) -> None:
        super().__init__(level)
        self._notifier = notifier
        self._handling = False  # evita recursión si send_message() llama al logger

    def emit(self, record: logging.LogRecord) -> None:
        if self._handling:
            return
        self._handling = True
        try:
            msg = self.format(record)
            self._notifier.send_message(f"<code>{_escape_html(msg)}</code>")
        except Exception:  # nunca dejar que un handler rompa el bot
            pass
        finally:
            self._handling = False


def add_telegram_handler(logger: logging.Logger, notifier) -> None:
    """Añade al logger un handler que envía WARNING+ a Telegram."""
    handler = TelegramLogHandler(notifier, level=logging.WARNING)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(handler)
