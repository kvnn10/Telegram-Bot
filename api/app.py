# Device Check - Telegram Bot (Premium Ready)

import os
import re
import time
import html
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("IFREEICLOUD_PHP_API_KEY")
URL = os.getenv("IFREEICLOUD_URL")

BOT_USERNAME = os.getenv("BOT_USERNAME", "").replace("@", "")

ALLOWED = [x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()]

SERVICES = {
    "model": "0",
    "fmi": "4",
    "fmidev": "125",
    "blacklist": "55",
    "carrier": "255",
    "sample": "238",
    "macfmi": "247",
}

def is_allowed(chat_id):
    return str(chat_id) in ALLOWED

def normalize(text):
    if "@" in text:
        parts = text.split()
        cmd = parts[0]
        if "@" in cmd:
            base, mention = cmd.split("@")
            if BOT_USERNAME.lower() == mention.lower():
                parts[0] = base
        return " ".join(parts)
    return text

def clean_html(text):
    text = html.unescape(str(text))
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def send(chat_id, text):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })

def query(service, imei):
    r = requests.post(URL, data={
        "service": SERVICES[service],
        "imei": imei,
        "key": API_KEY
    })
    try:
        return r.json()
    except:
        return {"response": r.text}

def extract(text, key):
    m = re.search(rf"{key}:\s*(.+)", text, re.I)
    return m.group(1).strip() if m else "No disponible"

def parse_fmi(result):
    text = clean_html(result.get("response", "")).upper()
    if "ON" in text:
        return "ON 🔴"
    if "OFF" in text:
        return "OFF 🟢"
    return "No disponible"

@app.get("/")
def root():
    return {"ok": True}

@app.post("/api/webhook")
async def webhook(req: Request):
    data = await req.json()
    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = normalize((msg.get("text") or "").strip())

    if not is_allowed(chat_id):
        return {"ok": True}

    for cmd in SERVICES:
        if text.startswith(f"/{cmd}"):
            parts = text.split()
            if len(parts) < 2:
                send(chat_id, f"Usa: /{cmd} 123456789")
                return {"ok": True}

            imei = parts[1]
            send(chat_id, "Consultando...")
            start = time.time()
            result = query(cmd, imei)
            t = int((time.time() - start)*1000)

            raw = clean_html(result.get("response", ""))

            if cmd == "carrier":
                out = f"📡 *CARRIER*\n\nIMEI: `{imei}`\nCarrier: {extract(raw,'Carrier')}\nPaís: {extract(raw,'Country')}\nSIM: {extract(raw,'SIM-Lock Status')}\n\n⏱ {t} ms"
            elif cmd == "fmi":
                out = f"📱 *FMI*\n\nIMEI: `{imei}`\nEstado: {parse_fmi(result)}\n\n⏱ {t} ms"
            else:
                out = f"📲 *RESULT*\n\nIMEI: `{imei}`\nDetalle:\n`{raw[:300]}`\n\n⏱ {t} ms"

            send(chat_id, out)
            return {"ok": True}

    return {"ok": True}
