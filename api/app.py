# VERSION 10/10 - PREMIUM + MULTIUSUARIO + BOTONES + CONTADOR + HISTORIAL
# Incluye comandos manuales /start /myid /model <imei> /fmi <imei>

import os
import re
import time
import html
from typing import Dict, Any

import requests
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("IFREEICLOUD_PHP_API_KEY")
IFREEICLOUD_URL = "https://api.ifreeicloud.co.uk"

ALLOWED_CHAT_IDS = {
    x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
}

IDENTIFIER_REGEX = re.compile(r"^[A-Za-z0-9]{8,20}$")

USER_STATS: Dict[str, Dict[str, Any]] = {}

SERVICES = {
    "model": "0",
    "fmi": "4",
}


def is_allowed(chat_id):
    return str(chat_id) in ALLOWED_CHAT_IDS


def send(chat_id, text, buttons=True):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "📲 Model", "callback_data": "model"},
                    {"text": "📱 FMI", "callback_data": "fmi"}
                ],
                [
                    {"text": "📊 Historial", "callback_data": "history"},
                    {"text": "📈 Contador", "callback_data": "count"}
                ]
            ]
        }

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=30,
    )


def clean(text):
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_model(text):
    match = re.search(r"(iPhone [^\n]+)", text)
    return match.group(1) if match else "No disponible"


def parse_status(text):
    return "Activado ✅" if "Activated" in text else "No disponible"


def parse_warranty(text):
    return "Expirada ❌" if "Out Of Warranty" in text else "Vigente ✅"


def parse_applecare(text):
    return "No" if "AppleCare Eligible: No" in text else "Sí"


def update_user(chat_id, imei):
    uid = str(chat_id)

    if uid not in USER_STATS:
        USER_STATS[uid] = {"count": 0, "history": []}

    USER_STATS[uid]["count"] += 1
    USER_STATS[uid]["history"].append(imei)

    if len(USER_STATS[uid]["history"]) > 5:
        USER_STATS[uid]["history"].pop(0)


def query(service, imei):
    payload = {
        "service": SERVICES[service],
        "imei": imei,
        "key": API_KEY
    }

    r = requests.post(IFREEICLOUD_URL, data=payload, timeout=30)
    return clean(r.text)


def run_lookup(chat_id, action, imei):
    if not IDENTIFIER_REGEX.match(imei):
        send(chat_id, "❌ IMEI inválido", False)
        return

    start = time.time()
    result = query(action, imei)
    elapsed = int((time.time() - start) * 1000)

    update_user(chat_id, imei)

    if action == "model":
        text = (
            "📲 *DEVICE INFO*\n\n"
            f"• IMEI: `{imei}`\n"
            f"• Modelo: {parse_model(result)}\n"
            f"• Estado: {parse_status(result)}\n"
            f"• Garantía: {parse_warranty(result)}\n"
            f"• AppleCare: {parse_applecare(result)}\n\n"
            f"⏱ {elapsed} ms"
        )
        send(chat_id, text)

    if action == "fmi":
        fmi = "ON 🔴" if "ON" in result.upper() else "OFF 🟢"
        text = (
            "📱 *IMEI CHECK*\n\n"
            f"• IMEI: `{imei}`\n"
            f"• FMI: {fmi}\n\n"
            f"⏱ {elapsed} ms"
        )
        send(chat_id, text)


@app.get("/")
async def root():
    return {"ok": True, "service": "telegrambotk"}


@app.post("/api/webhook")
async def webhook(req: Request):
    data = await req.json()

    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]

        if not is_allowed(chat_id):
            return {"ok": True}

        action = cb["data"]

        if action == "history":
            hist = USER_STATS.get(str(chat_id), {}).get("history", [])
            text = "\n".join(hist) if hist else "Sin historial"
            send(chat_id, f"📊 *Historial:*\n{text}")
            return {"ok": True}

        if action == "count":
            count = USER_STATS.get(str(chat_id), {}).get("count", 0)
            send(chat_id, f"📈 Has hecho *{count} consultas*")
            return {"ok": True}

        send(chat_id, f"✅ Seleccionaste *{action.upper()}*\n\nEnvíame el IMEI para continuar.", False)
        USER_STATS.setdefault(str(chat_id), {})["pending"] = action
        return {"ok": True}

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not is_allowed(chat_id):
        return {"ok": True}

    text = (msg.get("text", "") or "").strip()

    if text.startswith("/start"):
        send(chat_id, "🤖 *IMEI Check PRO*\nSelecciona una opción:")
        return {"ok": True}

    if text.startswith("/myid"):
        send(chat_id, f"🆔 Tu ID: `{chat_id}`", False)
        return {"ok": True}

    if text.startswith("/model"):
        parts = text.split()
        if len(parts) < 2:
            send(chat_id, "❌ Usa: `/model 356XXXXXXXXXXXX`", False)
            return {"ok": True}
        run_lookup(chat_id, "model", parts[1].strip())
        return {"ok": True}

    if text.startswith("/fmi"):
        parts = text.split()
        if len(parts) < 2:
            send(chat_id, "❌ Usa: `/fmi 356XXXXXXXXXXXX`", False)
            return {"ok": True}
        run_lookup(chat_id, "fmi", parts[1].strip())
        return {"ok": True}

    uid = str(chat_id)
    action = USER_STATS.get(uid, {}).get("pending")

    if action:
        imei = text
        USER_STATS[uid]["pending"] = None
        run_lookup(chat_id, action, imei)
        return {"ok": True}

    send(chat_id, "Usa los botones o envía un comando como `/model 356XXXXXXXXXXXX`", True)
    return {"ok": True}
