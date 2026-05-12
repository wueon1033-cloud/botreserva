# Olympic GYM — Bot de Reservas

Automatización personal para reservar clases en `reservas.olympicgym.cl`.
Se ejecuta entre las **07:00 y 07:05 AM**, revisa cada segundo si el botón
"Reservar" está disponible para la clase de **09:00 a 10:00**, hace clic
una sola vez si aparece, confirma la reserva y notifica el resultado por
Telegram.

> ⚠️ **Uso ético/legal.** Este bot está pensado para automatizar una acción
> que el dueño de la cuenta haría manualmente. **No** evade captchas, ni
> bloqueos, ni medidas anti-bot. Si el portal incorpora protecciones de
> ese tipo, debes detener el uso. Úsalo solo con tu propia cuenta y
> respeta los términos del servicio.

---

## 1. Estructura del proyecto

```
olympic_bot/
├── main.py               # Punto de entrada
├── bot.py                # Lógica principal con Playwright
├── telegram_notifier.py  # Envío de mensajes/fotos a Telegram
├── logger_config.py      # Logger a consola + archivo
├── config.py             # Carga y valida el .env
├── requirements.txt      # Dependencias
├── .env.example          # Plantilla de variables
├── .env                  # ← TÚ LO CREAS (no se sube a git)
├── logs/                 # Logs diarios rotados
└── screenshots/          # Capturas de error / verificación
```

---

## 2. Instalación

### 2.1. Requisitos previos

- Windows 10/11.
- Python 3.10 o superior. Descargar desde <https://www.python.org/downloads/>
  y marcar **"Add Python to PATH"** durante la instalación.

### 2.2. Crear entorno virtual e instalar dependencias

Abre **PowerShell** o **CMD** dentro de la carpeta del proyecto:

```powershell
cd C:\ruta\a\olympic_bot

python -m venv venv
venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
```

### 2.3. Instalar el navegador de Playwright

```powershell
python -m playwright install chromium
```

> Solo necesitas Chromium; no instales los otros navegadores para ahorrar espacio.

---

## 3. Configurar credenciales

Copia la plantilla y edítala:

```powershell
copy .env.example .env
notepad .env
```

Completa los campos:

```env
OLYMPIC_EMAIL=perezfernanda2712@gmail.com
OLYMPIC_PASSWORD=tu_contraseña_real
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

**Importante:** nunca subas el archivo `.env` a un repositorio público. Si
cambia la contraseña, solo editas `.env`, **no tocas el código**.

### 3.1. Obtener token y chat_id de Telegram

1. En Telegram, habla con **@BotFather** y crea un bot con `/newbot`.
   Te entregará el `TELEGRAM_BOT_TOKEN`.
2. Escríbele un mensaje cualquiera a tu nuevo bot (para "activarlo" en tu
   cuenta).
3. Abre en el navegador: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`.
   Busca el campo `"chat":{"id":...}` — ese número es tu `TELEGRAM_CHAT_ID`.

---

## 4. Modos de ejecución

El archivo `.env` controla cómo se comporta el bot:

| Variable    | Valor recomendado para probar | Valor recomendado para producción |
| ----------- | :---------------------------: | :-------------------------------: |
| `DRY_RUN`   | `true`                        | `false`                           |
| `HEADLESS`  | `false`                       | `true`                            |

- **`DRY_RUN=true`** → el bot inicia sesión, busca la clase, detecta el
  botón "Reservar" y manda un mensaje a Telegram, **pero NO hace clic**.
  Ideal para validar que todo funciona sin reservar de verdad.
- **`DRY_RUN=false`** → el bot **sí** hace clic y reserva cuando el botón
  esté disponible.
- **`HEADLESS=false`** → ves la ventana de Chromium (útil para depurar).
- **`HEADLESS=true`** → corre invisible en segundo plano (recomendado para
  el Programador de Tareas).

---

## 5. Ejecución manual

Con el entorno virtual activado:

```powershell
venv\Scripts\activate
python main.py
```

Comportamiento según la hora:

- **Antes de 07:00** → el bot espera hasta esa hora y luego empieza.
- **Entre 07:00 y 07:05** → empieza inmediatamente.
- **Después de 07:05** → sale de inmediato sin hacer nada (te avisa por
  Telegram que no se ejecutó).

---

## 6. Programar con el Programador de Tareas de Windows

Para que se ejecute automáticamente todos los días a las 07:00 AM:

1. Abre el **Programador de tareas** (Win + R → `taskschd.msc`).
2. Panel derecho → **Crear tarea...** (no "Crear tarea básica", porque
   necesitamos más opciones).
3. **Pestaña General:**
   - Nombre: `Olympic GYM Bot`.
   - "Ejecutar tanto si el usuario inició sesión como si no" ✅
   - "No almacenar contraseña" ✅
   - "Ejecutar con los privilegios más altos" (opcional, solo si te da
     problemas de permisos).
4. **Pestaña Desencadenadores:**
   - Nuevo → Diariamente → **07:00:00** → Repetir cada **1 día**.
5. **Pestaña Acciones:**
   - Nuevo → "Iniciar un programa".
   - **Programa o script:**
     ```
     C:\ruta\a\olympic_bot\venv\Scripts\python.exe
     ```
   - **Agregar argumentos:**
     ```
     main.py
     ```
   - **Iniciar en (importante):**
     ```
     C:\ruta\a\olympic_bot
     ```
6. **Pestaña Condiciones:**
   - Desmarca "Iniciar la tarea solo si el equipo está conectado a la
     corriente alterna" si usas notebook.
   - Marca "Reactivar el equipo para ejecutar esta tarea" si tu PC suele
     estar suspendida a esa hora.
7. **Pestaña Configuración:**
   - "Permitir que la tarea se ejecute a petición" ✅
   - "Si la tarea se ejecuta más de:" → 30 minutos (margen de seguridad).
   - "Si la tarea ya se está ejecutando:" → No iniciar una nueva instancia.

Recomendación: para producción pon `HEADLESS=true` y `DRY_RUN=false` en
`.env`. Antes de eso, prueba al menos un día con `DRY_RUN=true` para
confirmar que detecta el botón correctamente.

---

## 7. Validar que Telegram funciona (prueba rápida)

```powershell
python -c "from config import load_settings; from logger_config import setup_logger; from telegram_notifier import TelegramNotifier; s = load_settings(); n = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id, setup_logger()); n.send_message('Test desde Olympic GYM bot ✅')"
```

Si te llega el mensaje, las credenciales de Telegram están bien.

---

## 8. Qué mensajes manda el bot

1. **Al iniciar:** `🟢 Bot Olympic GYM iniciado a las 07:00. Intentando reservar clase 09:00 - 10:00.`
2. **Si encuentra la clase pero aún no está disponible (una sola vez):** `🔎 Clase encontrada, pero aún no disponible. Seguimiento activo.`
3. **Si reserva exitosamente:** `✅ Reserva exitosa. Clase 09:00 - 10:00 reservada correctamente.`
4. **Si no logra reservar al llegar las 07:05:** `❌ No se pudo reservar la clase 09:00 - 10:00 entre 07:00 y 07:05. Motivo: botón no disponible.`
5. **Si falla algo:** `⚠️ Error en el bot Olympic GYM: [detalle]. Se guardó captura de pantalla.` + foto adjunta.

---

## 9. Mantenimiento: si el HTML del portal cambia

Todos los selectores están **centralizados al principio de `bot.py`**, en
el bloque `# SELECTORES`. Si Olympic cambia su sitio:

- **Login roto** → revisa `SEL_LOGIN_EMAIL`, `SEL_LOGIN_PASSWORD`,
  `SEL_LOGIN_SUBMIT`.
- **No detecta el botón** → ajusta las constantes `TEXT_NOT_AVAILABLE`,
  `TEXT_RESERVE`. La búsqueda de la fila usa los textos `"09:00"` y
  `"10:00"`, que son insensibles al rediseño del CSS — eso es deliberado
  para que sea robusto.
- **Diálogo de confirmación distinto** → añade el texto del nuevo botón
  a la tupla `TEXT_CONFIRM_BUTTONS`.

Recomendaciones para hacer selectores más robustos a futuros cambios:

- Prefiere selectores por **texto visible** (`has-text`) o atributos
  semánticos (`name`, `id`) sobre clases CSS, que cambian con cualquier
  rediseño.
- Si el portal incorpora `data-testid` o atributos similares, úsalos.
- Evita XPaths posicionales del estilo `//div[3]/table/tr[2]`: se rompen
  con cualquier cambio de layout.

---

## 10. Solución de problemas

| Síntoma                                              | Causa probable / Solución                                                                                          |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `RuntimeError: Falta la variable obligatoria 'OLYMPIC_EMAIL'` | No existe `.env` o está incompleto. Copia `.env.example` a `.env` y rellénalo.                                     |
| `playwright._impl._errors.Error: Executable doesn't exist`   | Falta instalar el navegador. Ejecuta `python -m playwright install chromium`.                                      |
| El bot no clickea aunque el botón aparezca                   | Probablemente estás en `DRY_RUN=true`. Cambia a `false` en `.env`.                                                 |
| La tarea programada no se dispara                            | Verifica en "Historial" del Programador de Tareas. Comprueba que la ruta de Python sea la del venv, no la global. |
| Login falla aunque la contraseña sea correcta                | Revisa la captura en `screenshots/`. Si Olympic agregó captcha, **el bot no debe ni intentar evadirlo**.           |
| Mensajes de Telegram no llegan                               | Verifica `TELEGRAM_CHAT_ID` (debe ser numérico) y que hayas mandado al menos un mensaje al bot primero.            |

---

## 11. Códigos de salida

Útiles si quieres encadenar otra acción en Task Scheduler:

| Código | Significado                              |
| :----: | ---------------------------------------- |
|   0    | Éxito (reservó, ya estaba reservada o dry-run) |
|   1    | Error genérico                           |
|   2    | Timeout (no apareció el botón en 5 min)  |
|   3    | Sin cupos                                |
|   4    | Clase no encontrada                      |
|   5    | Fallo de login                           |

---

## 12. Recomendaciones finales

- **Primera semana:** corre el bot manualmente con `DRY_RUN=true` y
  `HEADLESS=false`. Observa cómo se comporta el sitio.
- **Cuando confíes:** cambia a `DRY_RUN=false` y `HEADLESS=true`, y
  programa la tarea en Windows.
- **Revisa logs periódicamente:** `logs/olympic_bot_YYYY-MM-DD.log`
  contiene todo el detalle.
- **Si el portal añade verificación humana (captcha, "no soy un robot"),
  detén el uso del bot.** En ese caso el sitio te está diciendo
  explícitamente que no quiere automatización.
