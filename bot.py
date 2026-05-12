"""
bot.py
------
Lógica principal del bot Olympic GYM con Playwright.

Diseño:
- Una clase OlympicBot que encapsula todo el flujo (login, navegación,
  detección y clic).
- Selectores definidos como constantes arriba, fáciles de actualizar si
  el HTML cambia.
- Toda interacción con la página tiene timeouts cortos y manejo de errores.
- El bucle de intentos se detiene SIEMPRE al llegar a TARGET_END_TIME,
  haya o no reservado.
- Estados posibles del resultado:
    * "reserved"        -> reservó exitosamente
    * "already_reserved"-> ya había una reserva previa
    * "no_slots"        -> clase encontrada pero sin cupos
    * "class_not_found" -> no encontró la clase 09:00-10:00 en la agenda
    * "login_failed"    -> no pudo iniciar sesión
    * "timeout"         -> se acabó la ventana sin lograr reservar
    * "error"           -> excepción inesperada
    * "dry_run_detected"-> en modo prueba: encontró el botón "Reservar" pero NO clickeó
"""

from __future__ import annotations

import logging
import time as time_module
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    ElementHandle,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from config import SCREENSHOTS_DIR, Settings
from telegram_notifier import TelegramNotifier


# =====================================================
# SELECTORES (centralizados para fácil mantenimiento)
# =====================================================

# --- Login ---
SEL_LOGIN_EMAIL = "#id_login"
SEL_LOGIN_PASSWORD = "#id_password"
SEL_LOGIN_SUBMIT = 'button[type="submit"]'

# Heurísticas para detectar que el login fue exitoso (cualquiera de estas
# señales basta): que la URL contenga /agenda/ o que el formulario haya
# desaparecido.
LOGIN_SUCCESS_URL_FRAGMENT = "/agenda"
SEL_LOGIN_ERROR_HINTS = ".errorlist, .alert-danger, .alert.alert-error"

# --- Agenda / botón de la clase ---
# Texto exacto del botón cuando aún no se puede reservar.
TEXT_NOT_AVAILABLE = "Aún no disponible"
# Texto cuando ya se puede reservar.
TEXT_RESERVE = "Reservar"
# Texto cuando ya tenemos la reserva hecha (puede variar; se manejan varias variantes).
TEXTS_ALREADY_RESERVED = (
    "reservado",
    "reservada",
    "cancelar reserva",
    "ya reservaste",
    "ya reservada",
)
# Texto cuando no hay cupos.
TEXTS_NO_SLOTS = ("sin cupo", "sin cupos", "cupo completo", "completo", "lleno")

# Diálogo de confirmación (varias posibilidades).
TEXT_CONFIRM_BUTTONS = ("Confirmar", "Sí, reservar", "Sí", "Aceptar")


# =====================================================
# RESULTADO
# =====================================================

@dataclass
class BotResult:
    status: str
    detail: str = ""
    screenshot_path: Optional[Path] = None


# =====================================================
# BOT
# =====================================================

class OlympicBot:
    """Encapsula la sesión completa del bot."""

    def __init__(
        self,
        settings: Settings,
        notifier: TelegramNotifier,
        logger: logging.Logger,
    ):
        self.settings = settings
        self.notifier = notifier
        self.logger = logger

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._reserved_clicked = False  # candado anti-doble-clic

    # ---------------------------------------------------------------
    # Ciclo de vida del navegador
    # ---------------------------------------------------------------
    def __enter__(self) -> "OlympicBot":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.settings.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        # Un contexto fresco evita arrastrar cookies viejas que confundan el login.
        self._context = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="es-CL",
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(15_000)  # 15 s por acción
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as exc:  # cierre defensivo
            self.logger.warning("Error cerrando navegador: %s", exc)

    # ---------------------------------------------------------------
    # Capturas
    # ---------------------------------------------------------------
    def _save_screenshot(self, tag: str) -> Optional[Path]:
        """Guarda screenshot con marca de tiempo y devuelve la ruta."""
        if not self._page:
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"{ts}_{tag}.png"
        try:
            self._page.screenshot(path=str(path), full_page=True)
            self.logger.info("Screenshot guardado: %s", path.name)
            return path
        except Exception as exc:
            self.logger.warning("No se pudo guardar screenshot: %s", exc)
            return None

    # ---------------------------------------------------------------
    # Login
    # ---------------------------------------------------------------
    def login(self) -> bool:
        """Inicia sesión. Devuelve True si tuvo éxito."""
        assert self._page is not None
        page = self._page

        self.logger.info("Navegando al login...")
        page.goto(self.settings.login_url, wait_until="domcontentloaded")

        try:
            page.wait_for_selector(SEL_LOGIN_EMAIL, timeout=10_000)
        except PlaywrightTimeoutError:
            self.logger.error("No apareció el formulario de login.")
            self._save_screenshot("login_form_missing")
            return False

        self.logger.info("Llenando credenciales...")
        page.fill(SEL_LOGIN_EMAIL, self.settings.olympic_email)
        page.fill(SEL_LOGIN_PASSWORD, self.settings.olympic_password)

        # Click en submit y espera de navegación
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                page.click(SEL_LOGIN_SUBMIT)
        except PlaywrightTimeoutError:
            # Algunos sitios no disparan navigation event sino que recargan;
            # damos un margen extra y seguimos.
            self.logger.debug("No se detectó evento de navegación; continúo.")

        # Validar éxito
        current_url = page.url
        if LOGIN_SUCCESS_URL_FRAGMENT in current_url:
            self.logger.info("Login exitoso. URL actual: %s", current_url)
            return True

        # Si hay mensaje de error visible
        error_text = ""
        try:
            error_el = page.query_selector(SEL_LOGIN_ERROR_HINTS)
            if error_el:
                error_text = (error_el.text_content() or "").strip()
        except Exception:
            pass

        self.logger.error(
            "Login falló. URL=%s. Mensaje del sitio: %r", current_url, error_text
        )
        self._save_screenshot("login_failed")
        return False

    # ---------------------------------------------------------------
    # Navegar a la agenda (si no estamos ya allí)
    # ---------------------------------------------------------------
    def goto_agenda(self) -> bool:
        assert self._page is not None
        page = self._page
        if "/agenda" not in page.url:
            self.logger.info("Navegando a la agenda...")
            try:
                page.goto(self.settings.agenda_url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError:
                self.logger.error("Timeout cargando la agenda.")
                self._save_screenshot("agenda_timeout")
                return False
        # Pequeño wait extra por contenido dinámico
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            pass
        return True

    # ---------------------------------------------------------------
    # Localizar la fila/tarjeta de la clase 09:00 - 10:00
    # ---------------------------------------------------------------
    def _class_xpath(self) -> str:
        start = self.settings.target_class_start
        end = self.settings.target_class_end
        return (
            f"xpath=//*[contains(normalize-space(.), '{start}') "
            f"and contains(normalize-space(.), '{end}')]"
            f"[not(.//*[contains(normalize-space(.), '{start}') "
            f"and contains(normalize-space(.), '{end}')])]"
        )

    def find_class_row(self) -> Optional[Locator]:
        """Devuelve la primera fila que coincide con la clase objetivo."""
        rows = self.find_all_class_rows()
        return rows[0] if rows else None

    def find_all_class_rows(self) -> list:
        """Devuelve TODAS las filas que coinciden (hoy + mañana, etc.)."""
        assert self._page is not None
        try:
            locators = self._page.locator(self._class_xpath())
            count = locators.count()
            result = []
            for i in range(count):
                try:
                    loc = locators.nth(i)
                    loc.wait_for(state="attached", timeout=1_000)
                    result.append(loc)
                except Exception:
                    pass
            return result
        except Exception:
            return []

    # ---------------------------------------------------------------
    # Inspeccionar el estado del botón dentro de la fila
    # ---------------------------------------------------------------
    def inspect_class_state(self, row: Locator) -> str:
        """
        Devuelve uno de: 'reserve' | 'not_available' | 'already_reserved'
                       | 'no_slots' | 'unknown'
        basado en el texto visible en la fila/tarjeta.
        """
        try:
            text = (row.text_content() or "").strip().lower()
        except Exception:
            return "unknown"

        if any(token in text for token in TEXTS_ALREADY_RESERVED):
            return "already_reserved"
        if any(token in text for token in TEXTS_NO_SLOTS):
            return "no_slots"
        if TEXT_RESERVE.lower() in text and TEXT_NOT_AVAILABLE.lower() not in text:
            return "reserve"
        if TEXT_NOT_AVAILABLE.lower() in text:
            return "not_available"
        return "unknown"

    # ---------------------------------------------------------------
    # Hacer clic en el botón "Reservar" dentro de la fila
    # ---------------------------------------------------------------
    def click_reserve_button(self, row: Locator) -> bool:
        """Intenta clickear el botón con texto exacto 'Reservar'. Una sola vez."""
        if self._reserved_clicked:
            self.logger.debug("Ya se hizo clic previamente; ignorando.")
            return False

        # Botón cuyo texto contenga "Reservar" (case-sensitive según la página).
        button = row.locator(f"button:has-text('{TEXT_RESERVE}')").first
        try:
            button.wait_for(state="visible", timeout=2_000)
        except PlaywrightTimeoutError:
            self.logger.warning("El botón Reservar no es visible en la fila.")
            return False

        self._reserved_clicked = True  # candado ANTES del clic
        try:
            button.click(timeout=5_000)
            self.logger.info("Clic en 'Reservar' realizado.")
            return True
        except Exception as exc:
            self.logger.error("Falló el clic en 'Reservar': %s", exc)
            return False

    # ---------------------------------------------------------------
    # Confirmar reserva si aparece un diálogo
    # ---------------------------------------------------------------
    def confirm_if_needed(self) -> None:
        """Si tras clickear aparece un diálogo de confirmación, lo acepta."""
        assert self._page is not None
        page = self._page

        # Manejo de window.confirm nativo (por si lo usaran)
        page.once("dialog", lambda d: d.accept())

        # Diálogos en HTML (Bootstrap modal, etc.)
        for label in TEXT_CONFIRM_BUTTONS:
            try:
                confirm = page.locator(f"button:has-text('{label}')").last
                if confirm.count() > 0 and confirm.is_visible(timeout=1500):
                    confirm.click(timeout=2_000)
                    self.logger.info("Diálogo de confirmación aceptado (%s).", label)
                    return
            except (PlaywrightTimeoutError, Exception):
                continue
        self.logger.debug("No apareció diálogo de confirmación adicional.")

    # ---------------------------------------------------------------
    # Verificar que la reserva quedó hecha
    # ---------------------------------------------------------------
    def verify_reservation(self) -> bool:
        """Tras clickear y confirmar, verifica que la fila muestre estado de reservada."""
        # Damos un par de segundos para que el backend procese
        time_module.sleep(2)

        # Recargar la agenda para ver el estado real (de forma controlada, una vez)
        if not self.goto_agenda():
            return False

        row = self.find_class_row()
        if not row:
            self.logger.warning("Tras reservar no se encontró la fila para verificar.")
            return False
        state = self.inspect_class_state(row)
        self.logger.info("Estado tras reservar: %s", state)
        return state == "already_reserved"

    # ---------------------------------------------------------------
    # Loop principal de intentos
    # ---------------------------------------------------------------
    def attempt_loop(self) -> BotResult:
        """
        Bucle por minutos: cada 60 segundos recarga la agenda, verifica el
        botón y manda notificación a Telegram con el resultado del intento.
        Sale en cuanto reserva, detecta sin cupos, o se acaba TARGET_END_TIME.
        """
        end_time = self.settings.target_end_time
        class_label = f"{self.settings.target_class_start} - {self.settings.target_class_end}"

        while True:
            now = datetime.now()
            if now.time() >= end_time:
                self.logger.info("Ventana de tiempo agotada (%s).", end_time)
                return BotResult(status="timeout", detail="Botón nunca apareció disponible.")

            time_str = now.strftime("%H:%M")

            # Recargar agenda fresca en cada intento
            if not self.goto_agenda():
                return BotResult(status="error", detail="No cargó la agenda.")

            try:
                row = self.find_class_row()
            except Exception as exc:
                self.logger.warning("Error buscando clase, recargando: %s", exc)
                time_module.sleep(5)
                continue

            try:
                state = self.inspect_class_state(row) if row else "not_available"
            except Exception as exc:
                self.logger.warning("Error inspeccionando estado, recargando: %s", exc)
                time_module.sleep(5)
                continue

            self.logger.debug("Estado %s: %s", time_str, state)

            # 1) Ya reservada
            if state == "already_reserved":
                self.logger.info("La clase ya estaba reservada previamente.")
                return BotResult(status="already_reserved", detail="Reserva preexistente detectada.")

            # 2) Sin cupos
            if state == "no_slots":
                self.logger.warning("La clase está sin cupos.")
                shot = self._save_screenshot("no_slots")
                return BotResult(status="no_slots", detail="Clase sin cupos disponibles.", screenshot_path=shot)

            # 3) Botón "Reservar" presente en al menos una fila
            if state == "reserve":
                self.logger.info("¡Botón 'Reservar' detectado!")
                if self.settings.dry_run:
                    shot = self._save_screenshot("dry_run_detected")
                    return BotResult(
                        status="dry_run_detected",
                        detail="Modo prueba: se detectó el botón Reservar pero NO se clickeó.",
                        screenshot_path=shot,
                    )
                # Reservar todas las clases disponibles (hoy + mañana)
                n = self._reserve_all_available(class_label)
                shot = self._save_screenshot("reserved_ok")
                if n > 0:
                    return BotResult(
                        status="reserved",
                        detail=f"Se reservaron {n} clase(s) {class_label}.",
                        screenshot_path=shot,
                    )
                shot2 = self._save_screenshot("reserve_click_failed")
                return BotResult(status="error", detail="Falló el clic en el botón Reservar.", screenshot_path=shot2)

            # 4) No disponible / desconocido → notificar y esperar 60 segundos
            self.notifier.send_message(
                f"🔄 <b>{time_str}</b> — Clase {class_label} no disponible. "
                f"Próximo intento en 1 min."
            )

            # Esperar 60 s pero salir antes si se acaba la ventana
            sleep_until = now + timedelta(seconds=60)
            while datetime.now() < sleep_until:
                time_module.sleep(1)
                if datetime.now().time() >= end_time:
                    break

    def _reserve_all_available(self, class_label: str) -> int:
        """
        Intenta reservar TODAS las filas con botón 'Reservar' disponible.
        Recarga la agenda entre cada reserva. Devuelve cuántas reservó.
        """
        total = 0
        while True:
            if not self.goto_agenda():
                break
            rows = self.find_all_class_rows()
            clicked_one = False
            for row in rows:
                try:
                    state = self.inspect_class_state(row)
                except Exception:
                    continue
                if state != "reserve":
                    continue
                self.logger.info("Reservando clase disponible (%d ya reservada/s).", total)
                self._reserved_clicked = False  # resetear candado para siguiente clase
                if self.click_reserve_button(row):
                    self.confirm_if_needed()
                    total += 1
                    clicked_one = True
                    self.notifier.send_message(
                        f"✅ Clase {class_label} reservada ({total} en total). "
                        f"Buscando más clases disponibles..."
                    )
                    time_module.sleep(2)
                    break  # recargar agenda para buscar la siguiente
            if not clicked_one:
                break  # no quedan más disponibles
        return total

    # ---------------------------------------------------------------
    # Orquestación pública
    # ---------------------------------------------------------------
    def run(self) -> BotResult:
        try:
            if not self.login():
                shot = self._save_screenshot("login_error_final")
                return BotResult(
                    status="login_failed",
                    detail="No se pudo iniciar sesión con las credenciales provistas.",
                    screenshot_path=shot,
                )
            return self.attempt_loop()
        except Exception as exc:
            self.logger.exception("Excepción no controlada en el bot.")
            shot = self._save_screenshot("unexpected_error")
            return BotResult(
                status="error",
                detail=f"{type(exc).__name__}: {exc}",
                screenshot_path=shot,
            )


# =====================================================
# UTILIDAD: esperar hasta una hora del día
# =====================================================

def wait_until(target: time, logger: logging.Logger) -> None:
    """
    Bloquea la ejecución hasta que el reloj local llegue a `target`.
    Si ya pasó, vuelve inmediatamente.
    """
    while True:
        now = datetime.now().time()
        if now >= target:
            return
        # Dormir como máximo 30 s, así si el sistema se suspende y reanuda
        # el bot reacciona rápido.
        remaining = (
            datetime.combine(datetime.today(), target)
            - datetime.combine(datetime.today(), now)
        ).total_seconds()
        sleep_for = min(30, max(0.5, remaining))
        logger.debug("Esperando inicio: faltan ~%.1fs", remaining)
        time_module.sleep(sleep_for)
