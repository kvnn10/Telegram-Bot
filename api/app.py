# VERSION FINAL CORREGIDA
# - Multiusuario por ALLOWED_CHAT_IDS
# - Todos los botones
# - Comandos manuales estables
# - Sin flujo roto de "envíame el IMEI" en botones
# - Parser mejorado de garantía y AppleCare

import os
import re
import time
import html
from typing import Dict, Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_KEY = os.getenv("IFREEICLOUD_PHP_API_KEY", "").strip()
IFREEICLOUD_URL = os.getenv("IFREEICLOUD_URL", "https://api.ifreeicloud.co.uk").strip().rstrip("/")

ALLOWED_CHAT_IDS = {
    x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
}

IDENTIFIER_REGEX = re.compile(r"^[A-Za-z0-9]{8,20}$")

USER_STATS: Dict[str, Dict[str, Any]] = {}

SERVICES = {
    "model": "0",
    "fmi": "4",
    "fmidev": "125",
    "blacklist": "55",
    "carrier": "255",
    "sample": "238",
    "macfmi": "247",
}


def is_allowed(chat_id) -> bool:
    return str(chat_id) in ALLOWED_CHAT_IDS


def main_buttons() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "📲 Model", "callback_data": "model"},
                {"text": "📱 FMI", "callback_data": "fmi"},
            ],
            [
                {"text": "🌐 FMI Dev", "callback_data": "fmidev"},
                {"text": "🚨 Blacklist", "callback_data": "blacklist"},
            ],
            [
                {"text": "📡 Carrier", "callback_data": "carrier"},
                {"text": "🧪 Sample", "callback_data": "sample"},
            ],
            [
                {"text": "💻 Mac FMI", "callback_data": "macfmi"},
                {"text": "🆔 MyID", "callback_data": "myid"},
            ],
            [
                {"text": "📊 Historial", "callback_data": "history"},
                {"text": "📈 Contador", "callback_data": "count"},
            ],
        ]
    }


def telegram_api(method: str, payload: Dict[str, Any]) -> None:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
        json=payload,
        timeout=30,
    )


def send(chat_id, text, buttons=True):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if buttons:
        payload["reply_markup"] = main_buttons()
    telegram_api("sendMessage", payload)


def answer_callback(callback_query_id: str):
    telegram_api("answerCallbackQuery", {"callback_query_id": callback_query_id})


def clean(text):
    text = html.unescape(str(text))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_model(text):
    match = re.search(r"(iPhone [^\n]+)", text)
    if match:
        return match.group(1).strip()

    match = re.search(r"Model:\s*([^\n]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return "No disponible"


def parse_status(text):
    upper = text.upper()
    if "ACTIVATED" in upper:
        return "Activado ✅"
    return "No disponible"


def parse_warranty(text):
    upper = text.upper()
    if "OUT OF WARRANTY" in upper or "EXPIRED" in upper or "COBERTURA VENCIÓ" in upper:
        return "Expirada ❌"
    if "LIMITED WARRANTY" in upper or "COVERAGE ACTIVE" in upper:
        return "Vigente ✅"
    return "No disponible"


def parse_applecare(text):
    upper = text.upper()

    if (
        "APPLECARE ELIGIBLE: NO" in upper
        or "NOT COVERED" in upper
        or "OUT OF WARRANTY" in upper
        or "REPAIRS AND SERVICE COVERAGE: EXPIRED" in upper
        or "TELEPHONE TECHNICAL SUPPORT: EXPIRED" in upper
        or "COBERTURA VENCIÓ" in upper
    ):
        return "No ❌"

    if (
        "APPLECARE ELIGIBLE: YES" in upper
        or "APPLECARE+" in upper
        or "COVERAGE ACTIVE" in upper
    ):
        return "Sí ✅"

    return "No disponible"


def parse_fmi(text):
    upper = text.upper()
    if "FIND MY: ON" in upper or "FIND MY IPHONE: ON" in upper or "FMION TRUE" in upper or "FMI: ON" in upper:
        return "ON 🔴"
    if "FIND MY: OFF" in upper or "FIND MY IPHONE: OFF" in upper or "FMION FALSE" in upper or "FMI: OFF" in upper:
        return "OFF 🟢"
    if " ON" in upper:
        return "ON 🔴"
    if " OFF" in upper:
        return "OFF 🟢"
    return "No disponible"


def parse_blacklist(text):
    upper = text.upper()
    if "NOT BLACKLISTED" in upper or "CLEAN" in upper:
        return "LIMPIO ✅"
    if "BLACKLISTED" in upper or "BLACKLIST" in upper or "BLOCKED" in upper:
        return "EN LISTA NEGRA 🚫"
    return "No disponible"


def parse_carrier(text):
    m = re.search(r"Carrier:\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    m = re.search(r"Network:\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return "No disponible"


def parse_simlock(text):
    upper = text.upper()
    if "UNLOCKED" in upper:
        return "UNLOCKED 🔓"
    if "LOCKED" in upper:
        return "LOCKED 🔒"
    return "No disponible"


def update_user(chat_id, value):
    uid = str(chat_id)

    if uid not in USER_STATS:
        USER_STATS[uid] = {"count": 0, "history": []}

    USER_STATS[uid]["count"] += 1
    USER_STATS[uid]["history"].append(value)

    if len(USER_STATS[uid]["history"]) > 10:
        USER_STATS[uid]["history"].pop(0)


def query(service, identifier):
    payload = {
        "service": SERVICES[service],
        "imei": identifier,
        "key": API_KEY,
    }

    response = requests.post(IFREEICLOUD_URL, data=payload, timeout=30)
    return clean(response.text)


def render_result(action, identifier, result, elapsed):
    if action == "model":
        return (
            "📲 *DEVICE INFO*\n\n"
            f"• *IMEI:* `{identifier}`\n"
            f"• *Modelo:* {parse_model(result)}\n"
            f"• *Estado:* {parse_status(result)}\n"
            f"• *Garantía:* {parse_warranty(result)}\n"
            f"• *AppleCare:* {parse_applecare(result)}\n\n"
            f"⏱ *Tiempo:* `{elapsed} ms`"
        )

    if action in ("fmi", "fmidev"):
        title = "📱 *IMEI CHECK*" if action == "fmi" else "🌐 *FMI DEV CHECK*"
        return (
            f"{title}\n\n"
            f"• *IMEI:* `{identifier}`\n"
            f"• *FMI:* {parse_fmi(result)}\n\n"
            f"⏱ *Tiempo:* `{elapsed} ms`"
        )

    if action == "blacklist":
        return (
            "🚨 *BLACKLIST CHECK*\n\n"
            f"• *IMEI:* `{identifier}`\n"
            f"• *Estado:* {parse_blacklist(result)}\n\n"
            f"⏱ *Tiempo:* `{elapsed} ms`"
        )

    if action == "carrier":
        return (
            "📡 *CARRIER CHECK*\n\n"
            f"• *IMEI:* `{identifier}`\n"
            f"• *Carrier:* {parse_carrier(result)}\n"
            f"• *SIM-Lock:* {parse_simlock(result)}\n\n"
            f"⏱ *Tiempo:* `{elapsed} ms`"
        )

    if action == "sample":
        trimmed = result[:600] if result else "Sin detalle"
        return (
            "🧪 *FREE CHECK SAMPLE*\n\n"
            f"• *IMEI:* `{identifier}`\n"
            f"• *Detalle:* `{trimmed}`\n\n"
            f"⏱ *Tiempo:* `{elapsed} ms`"
        )

    if action == "macfmi":
        return (
            "💻 *MAC FMI CHECK*\n\n"
            f"• *Serial/IMEI:* `{identifier}`\n"
            f"• *FMI:* {parse_fmi(result)}\n\n"
            f"⏱ *Tiempo:* `{elapsed} ms`"
        )

    return (
        "📦 *RESULTADO*\n\n"
        f"• *Dato:* `{identifier}`\n\n"
        f"⏱ *Tiempo:* `{elapsed} ms`"
    )


def run_lookup(chat_id, action, identifier):
    if not IDENTIFIER_REGEX.match(identifier):
        send(chat_id, "❌ Dato inválido. Usa un IMEI o serial válido.", False)
        return

    send(chat_id, "⏳ Consultando, espera un momento...", False)

    start = time.time()
    try:
        result = query(action, identifier)
        elapsed = int((time.time() - start) * 1000)
        update_user(chat_id, f"{action}: {identifier}")
        send(chat_id, render_result(action, identifier, result, elapsed), True)
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        send(
            chat_id,
            "❌ *ERROR DE CONSULTA*\n\n"
            f"• *Detalle:* `{str(exc)[:500]}`\n"
            f"• *Tiempo:* `{elapsed} ms`",
            True,
        )


@app.get("/")
async def root():
    return {"ok": True, "service": "telegrambotk"}


@app.post("/api/webhook")
async def webhook(req: Request):
    if not TELEGRAM_BOT_TOKEN or not API_KEY:
        return JSONResponse({"ok": False, "error": "Missing env vars"}, status_code=500)

    data = await req.json()

    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        callback_id = cb["id"]

        answer_callback(callback_id)

        if not is_allowed(chat_id):
            return {"ok": True}

        action = cb["data"]

        if action == "myid":
            send(chat_id, f"🆔 Tu chat ID es: `{chat_id}`", True)
            return {"ok": True}

        if action == "history":
            hist = USER_STATS.get(str(chat_id), {}).get("history", [])
            text = "\n".join(f"• `{x}`" for x in hist) if hist else "Sin historial"
            send(chat_id, f"📊 *Historial*\n\n{text}", True)
            return {"ok": True}

        if action == "count":
            count = USER_STATS.get(str(chat_id), {}).get("count", 0)
            send(chat_id, f"📈 Has hecho *{count} consultas*", True)
            return {"ok": True}

        if action in SERVICES:
            example = "/macfmi C02XXXXXXXXX" if action == "macfmi" else f"/{action} 356XXXXXXXXXXXX"
            send(
                chat_id,
                f"✅ Seleccionaste *{action.upper()}*\n\nEnvía el dato así:\n`{example}`",
                True,
            )
            return {"ok": True}

        return {"ok": True}

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not is_allowed(chat_id):
        return {"ok": True}

    text = (msg.get("text", "") or "").strip()

    if text.startswith("/start") or text.startswith("/help"):
        send(
            chat_id,
            "🤖 *IMEI Check PRO*\n\n"
            "Selecciona una opción o usa comandos manuales:\n"
            "• `/model 356XXXXXXXXXXXX`\n"
            "• `/fmi 356XXXXXXXXXXXX`\n"
            "• `/fmidev 356XXXXXXXXXXXX`\n"
            "• `/blacklist 356XXXXXXXXXXXX`\n"
            "• `/carrier 356XXXXXXXXXXXX`\n"
            "• `/sample 356XXXXXXXXXXXX`\n"
            "• `/macfmi C02XXXXXXXXX`\n"
            "• `/myid`",
            True,
        )
        return {"ok": True}

    if text.startswith("/myid"):
        send(chat_id, f"🆔 Tu chat ID es: `{chat_id}`", True)
        return {"ok": True}

    for action in SERVICES.keys():
        prefix = f"/{action}"
        if text.startswith(prefix):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                example = "/macfmi C02XXXXXXXXX" if action == "macfmi" else f"/{action} 356XXXXXXXXXXXX"
                send(chat_id, f"❌ Uso correcto:\n`{example}`", True)
                return {"ok": True}
            identifier = parts[1].strip()
            run_lookup(chat_id, action, identifier)
            return {"ok": True}

    send(
        chat_id,
        "Usa los botones o envía un comando como `/model 356XXXXXXXXXXXX`",
        True,
    )
    return {"ok": True}
