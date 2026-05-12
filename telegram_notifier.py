"""
telegram_notifier.py
--------------------
Envía mensajes (y opcionalmente capturas de pantalla) a un chat de Telegram
usando la Bot API. No depende de python-telegram-bot para mantenerlo simple.

Nunca lanza excepciones hacia arriba: si Telegram falla, solo lo registra,
porque la prioridad del bot es reservar la clase, no notificar.
"""

import logging
from pathlib import Path
from typing import Optional

import requests


class TelegramNotifier:
    """Cliente minimalista de la Bot API de Telegram."""

    API_BASE = "https://api.telegram.org"
    REQUEST_TIMEOUT = 10  # segundos

    def __init__(self, bot_token: str, chat_id: str, logger: logging.Logger):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._logger = logger

    # ---------------------------------------------------------------
    # Mensajes de texto
    # ---------------------------------------------------------------
    def send_message(self, text: str) -> bool:
        """Envía un mensaje de texto. Devuelve True si tuvo éxito."""
        url = f"{self.API_BASE}/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, data=payload, timeout=self.REQUEST_TIMEOUT)
            if response.ok:
                self._logger.debug("Mensaje Telegram enviado.")
                return True
            self._logger.warning(
                "Telegram respondió con error %s: %s",
                response.status_code,
                response.text[:200],
            )
        except requests.RequestException as exc:
            self._logger.warning("No se pudo enviar mensaje a Telegram: %s", exc)
        return False

    # ---------------------------------------------------------------
    # Fotos (screenshots de error)
    # ---------------------------------------------------------------
    def send_photo(self, photo_path: Path, caption: Optional[str] = None) -> bool:
        """Envía una imagen como captura. Devuelve True si tuvo éxito."""
        if not photo_path.exists():
            self._logger.warning("El archivo de captura no existe: %s", photo_path)
            return False

        url = f"{self.API_BASE}/bot{self._bot_token}/sendPhoto"
        try:
            with open(photo_path, "rb") as fp:
                files = {"photo": fp}
                data = {"chat_id": self._chat_id}
                if caption:
                    data["caption"] = caption
                response = requests.post(
                    url, data=data, files=files, timeout=self.REQUEST_TIMEOUT
                )
            if response.ok:
                self._logger.debug("Foto enviada a Telegram.")
                return True
            self._logger.warning(
                "Telegram (foto) respondió con error %s: %s",
                response.status_code,
                response.text[:200],
            )
        except (requests.RequestException, OSError) as exc:
            self._logger.warning("No se pudo enviar foto a Telegram: %s", exc)
        return False
