"""
main.py
-------
Punto de entrada del bot Olympic GYM.

Flujo:
1. Cargar configuración desde .env.
2. Configurar logger y Telegram.
3. Si la hora actual es ANTERIOR a TARGET_START_TIME, esperar hasta esa hora.
   Si es POSTERIOR a TARGET_END_TIME, salir sin abrir el navegador.
4. Lanzar el bot.
5. Enviar el mensaje de Telegram correspondiente al resultado.

Pensado para ser invocado por el Programador de Tareas de Windows a las 07:00 AM.
"""

from __future__ import annotations

import sys
from datetime import datetime

from bot import BotResult, OlympicBot, wait_until
from config import load_settings
from logger_config import add_telegram_handler, setup_logger
from telegram_notifier import TelegramNotifier


def build_final_message(result: BotResult, dry_run: bool, class_label: str) -> str:
    """Construye el mensaje final de Telegram según el resultado."""
    if result.status == "reserved":
        return (
            f"✅ <b>Reserva exitosa.</b>\n"
            f"Clase {class_label} reservada correctamente."
        )
    if result.status == "already_reserved":
        return (
            f"ℹ️ La clase {class_label} ya estaba reservada previamente. "
            f"No se hizo nada nuevo."
        )
    if result.status == "dry_run_detected":
        return (
            f"🧪 <b>Modo prueba (DRY_RUN).</b>\n"
            f"Se detectó el botón <b>Reservar</b> para {class_label} pero "
            f"<b>no se hizo clic</b>.\n"
            f"Para reservar de verdad, pon <code>DRY_RUN=false</code> en .env."
        )
    if result.status == "no_slots":
        return (
            f"❌ No se pudo reservar la clase {class_label}.\n"
            f"Motivo: <b>sin cupos</b>."
        )
    if result.status == "class_not_found":
        return (
            f"❌ No se pudo reservar la clase {class_label}.\n"
            f"Motivo: <b>clase no encontrada</b> en la agenda."
        )
    if result.status == "login_failed":
        return (
            f"❌ No se pudo iniciar sesión en Olympic GYM. "
            f"Revisa las credenciales en .env."
        )
    if result.status == "timeout":
        return (
            f"❌ No se pudo reservar la clase {class_label} entre 07:00 y 07:05.\n"
            f"Motivo: <b>botón no disponible</b> dentro de la ventana de tiempo."
        )
    # error genérico
    return (
        f"⚠️ <b>Error en el bot Olympic GYM:</b>\n"
        f"{result.detail}\n"
        f"Se guardó captura de pantalla."
    )


def main() -> int:
    settings = load_settings()
    logger = setup_logger()

    class_label = f"{settings.target_class_start} - {settings.target_class_end}"
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        logger=logger,
    )
    add_telegram_handler(logger, notifier)

    logger.info("=" * 60)
    logger.info("Olympic GYM Bot iniciado")
    logger.info(
        "Ventana: %s - %s | Clase: %s | DRY_RUN=%s | HEADLESS=%s",
        settings.target_start_time.strftime("%H:%M"),
        settings.target_end_time.strftime("%H:%M"),
        class_label,
        settings.dry_run,
        settings.headless,
    )
    logger.info("=" * 60)

    # ---- Validación de ventana de tiempo ----
    now_time = datetime.now().time()
    if now_time >= settings.target_end_time:
        logger.warning(
            "Hora actual (%s) ya pasó TARGET_END_TIME (%s). Saliendo.",
            now_time.strftime("%H:%M:%S"),
            settings.target_end_time.strftime("%H:%M"),
        )
        notifier.send_message(
            "⏭️ Bot Olympic GYM no ejecutado: ya pasó la ventana de 07:00 a 07:05."
        )
        return 0

    if now_time < settings.target_start_time:
        now_dt = datetime.now()
        start_dt = now_dt.replace(
            hour=settings.target_start_time.hour,
            minute=settings.target_start_time.minute,
            second=0,
            microsecond=0,
        )
        seconds_until = (start_dt - now_dt).total_seconds()
        if seconds_until > 600:  # más de 10 min → demasiado pronto (e.g. GitHub Actions en temporada incorrecta)
            logger.info(
                "Demasiado pronto (%.0f min hasta %s). Saliendo.",
                seconds_until / 60,
                settings.target_start_time.strftime("%H:%M"),
            )
            return 0
        logger.info(
            "Esperando hasta %s para iniciar...",
            settings.target_start_time.strftime("%H:%M"),
        )
        wait_until(settings.target_start_time, logger)

    # ---- Notificación de inicio ----
    notifier.send_message(
        f"🟢 Bot Olympic GYM iniciado a las "
        f"{settings.target_start_time.strftime('%H:%M')}. "
        f"Intentando reservar clase {class_label}."
        + (" <i>(modo prueba)</i>" if settings.dry_run else "")
    )

    # ---- Ejecutar bot ----
    with OlympicBot(settings=settings, notifier=notifier, logger=logger) as bot:
        result: BotResult = bot.run()

    # ---- Notificación final ----
    msg = build_final_message(result, settings.dry_run, class_label)
    logger.info("Resultado final: status=%s detail=%s", result.status, result.detail)
    notifier.send_message(msg)

    # Si hay screenshot relevante, enviarla también
    if result.screenshot_path:
        notifier.send_photo(result.screenshot_path, caption=f"Captura: {result.status}")

    # Código de salida útil para Task Scheduler
    exit_codes = {
        "reserved": 0,
        "already_reserved": 0,
        "dry_run_detected": 0,
        "timeout": 2,
        "no_slots": 3,
        "class_not_found": 4,
        "login_failed": 5,
        "error": 1,
    }
    return exit_codes.get(result.status, 1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        sys.exit(130)
