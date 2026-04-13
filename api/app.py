# APP PREMIUM VERSION - CLEAN UI (NO SPAM BUTTONS)

import os
import re
import time
import html
from typing import Dict, Any
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_KEY = os.getenv("IFREEICLOUD_PHP_API_KEY", "").strip()
IFREEICLOUD_URL = os.getenv("IFREEICLOUD_URL", "https://api.ifreeicloud.co.uk").strip()

ALLOWED_CHAT_IDS = {
    x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
}

SERVICES = {
    "model": "0",
    "fmi": "4",
    "fmidev": "125",
    "blacklist": "55",
    "carrier": "255",
    "sample": "238",
    "macfmi": "247",
}

USER_STATS: Dict[str, Dict[str, Any]] = {}

def is_allowed(chat_id):
    return str(chat_id) in ALLOWED_CHAT_IDS

def buttons():
    return {
        "inline_keyboard": [
            [{"text": "📲 Model", "callback_data": "model"},
             {"text": "📱 FMI", "callback_data": "fmi"}],
            [{"text": "🌐 FMI Dev", "callback_data": "fmidev"},
             {"text": "🚨 Blacklist", "callback_data": "blacklist"}],
            [{"text": "📡 Carrier", "callback_data": "carrier"},
             {"text": "🧪 Sample", "callback_data": "sample"}],
            [{"text": "💻 Mac FMI", "callback_data": "macfmi"},
             {"text": "🆔 MyID", "callback_data": "myid"}],
            [{"text": "📊 Historial", "callback_data": "history"},
             {"text": "📈 Contador", "callback_data": "count"}],
        ]
    }

def send(chat_id, text, with_buttons=False):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if with_buttons:
        payload["reply_markup"] = buttons()

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=payload)

def clean(text):
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def update_user(chat_id, value):
    uid = str(chat_id)
    if uid not in USER_STATS:
        USER_STATS[uid] = {"count": 0, "history": []}
    USER_STATS[uid]["count"] += 1
    USER_STATS[uid]["history"].append(value)

def query(service, identifier):
    payload = {
        "service": SERVICES[service],
        "imei": identifier,
        "key": API_KEY,
    }
    res = requests.post(IFREEICLOUD_URL, data=payload)
    return clean(res.text)

@app.get("/")
def root():
    return {"ok": True}

@app.post("/api/webhook")
async def webhook(req: Request):
    data = await req.json()

    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]

        if not is_allowed(chat_id):
            return {"ok": True}

        action = cb["data"]

        if action == "myid":
            send(chat_id, f"🆔 Tu ID: `{chat_id}`")
            return {"ok": True}

        if action == "history":
            hist = USER_STATS.get(str(chat_id), {}).get("history", [])
            send(chat_id, "\n".join(hist) or "Sin historial")
            return {"ok": True}

        if action == "count":
            count = USER_STATS.get(str(chat_id), {}).get("count", 0)
            send(chat_id, f"📊 Consultas: {count}")
            return {"ok": True}

        if action in SERVICES:
            send(chat_id, f"👉 Usa:
`/{action} 356XXXXXXXXXXXX`")
            return {"ok": True}

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()

    if not is_allowed(chat_id):
        return {"ok": True}

    if text.startswith("/start"):
        send(chat_id, "🤖 IMEI Check PRO
Selecciona una opción:", True)
        return {"ok": True}

    for action in SERVICES:
        if text.startswith(f"/{action}"):
            parts = text.split()
            if len(parts) < 2:
                send(chat_id, "❌ Falta IMEI")
                return {"ok": True}

            imei = parts[1]
            send(chat_id, "⏳ Consultando...")

            start = time.time()
            result = query(action, imei)
            elapsed = int((time.time() - start) * 1000)

            update_user(chat_id, f"{action}:{imei}")

            send(chat_id, f"✅ Resultado:
`{result[:500]}`
⏱ {elapsed}ms", True)
            return {"ok": True}

    return {"ok": True}
