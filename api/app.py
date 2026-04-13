# FINAL PREMIUM APP.PY (PARSEADO BONITO)

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

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=30,
    )


def clean(text):
    if isinstance(text, dict):
        return text
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


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
    res = requests.post(IFREEICLOUD_URL, data=payload, timeout=30)

    try:
        return res.json()
    except Exception:
        return clean(res.text)


def get_response_text(result):
    if isinstance(result, dict):
        return str(result.get("response", "")).strip()
    return str(result).strip()


def get_object(result):
    if isinstance(result, dict):
        obj = result.get("object", {})
        if isinstance(obj, dict):
            return obj
    return {}


def parse_model_result(result):
    obj = get_object(result)

    model = (
        obj.get("model")
        or obj.get("modelName")
        or obj.get("device")
        or obj.get("name")
        or "No disponible"
    )

    brand = (
        obj.get("brand")
        or obj.get("manufacturer")
        or obj.get("make")
        or "No disponible"
    )

    response_text = get_response_text(result).upper()

    status = "No disponible"
    if "ACTIVATED" in response_text:
        status = "Activado ✅"

    warranty = "No disponible"
    if "OUT OF WARRANTY" in response_text or "EXPIRED" in response_text or "COBERTURA VENCIÓ" in response_text:
        warranty = "Expirada ❌"
    elif "LIMITED WARRANTY" in response_text or "COVERAGE ACTIVE" in response_text:
        warranty = "Vigente ✅"

    applecare = "No disponible"
    if (
        "APPLECARE ELIGIBLE: NO" in response_text
        or "OUT OF WARRANTY" in response_text
        or "REPAIRS AND SERVICE COVERAGE: EXPIRED" in response_text
        or "TELEPHONE TECHNICAL SUPPORT: EXPIRED" in response_text
        or "COBERTURA VENCIÓ" in response_text
    ):
        applecare = "No ❌"
    elif "APPLECARE ELIGIBLE: YES" in response_text or "APPLECARE+" in response_text:
        applecare = "Sí ✅"

    return brand, model, status, warranty, applecare


def parse_fmi_result(result):
    obj = get_object(result)
    text = (get_response_text(result) + " " + str(obj)).upper()

    if "FIND MY: ON" in text or "FIND MY IPHONE: ON" in text or "FMION TRUE" in text or '"FMION":TRUE' in text:
        return "ON 🔴"
    if "FIND MY: OFF" in text or "FIND MY IPHONE: OFF" in text or "FMION FALSE" in text or '"FMION":FALSE' in text:
        return "OFF 🟢"
    if " ON" in text:
        return "ON 🔴"
    if " OFF" in text:
        return "OFF 🟢"
    return "No disponible"


@app.get("/")
def root():
    return {"ok": True}


@app.post("/api/webhook")
async def webhook(req: Request):
    if not TELEGRAM_BOT_TOKEN or not API_KEY:
        return JSONResponse({"ok": False, "error": "Missing env vars"}, status_code=500)

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
            text = "\n".join(hist) or "Sin historial"
            send(chat_id, f"📊 *Historial*\n\n{text}")
            return {"ok": True}

        if action == "count":
            count = USER_STATS.get(str(chat_id), {}).get("count", 0)
            send(chat_id, f"📈 Consultas: *{count}*")
            return {"ok": True}

        if action in SERVICES:
            example = "/macfmi C02XXXXXXXXX" if action == "macfmi" else f"/{action} 356XXXXXXXXXXXX"
            send(chat_id, f"👉 Usa:\n`{example}`")
            return {"ok": True}

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()

    if not is_allowed(chat_id):
        return {"ok": True}

    if text.startswith("/start") or text.startswith("/help"):
        send(chat_id, "🤖 *IMEI Check PRO*\nSelecciona una opción:", True)
        return {"ok": True}

    if text.startswith("/myid"):
        send(chat_id, f"🆔 Tu ID: `{chat_id}`")
        return {"ok": True}

    for action in SERVICES:
        if text.startswith(f"/{action}"):
            parts = text.split()
            if len(parts) < 2:
                example = "/macfmi C02XXXXXXXXX" if action == "macfmi" else f"/{action} 356XXXXXXXXXXXX"
                send(chat_id, f"❌ Usa:\n`{example}`")
                return {"ok": True}

            imei = parts[1]
            send(chat_id, "⏳ Consultando...")

            start = time.time()
            result = query(action, imei)
            elapsed = int((time.time() - start) * 1000)

            update_user(chat_id, f"{action}:{imei}")

            if action == "model":
                brand, model, status, warranty, applecare = parse_model_result(result)
                pretty = (
                    "📲 *DEVICE INFO*\n\n"
                    f"• *IMEI:* `{imei}`\n"
                    f"• *Marca:* {brand}\n"
                    f"• *Modelo:* {model}\n"
                    f"• *Estado:* {status}\n"
                    f"• *Garantía:* {warranty}\n"
                    f"• *AppleCare:* {applecare}\n\n"
                    f"⏱ *Tiempo:* `{elapsed} ms`"
                )
                send(chat_id, pretty, True)
                return {"ok": True}

            if action in ("fmi", "fmidev", "macfmi"):
                fmi = parse_fmi_result(result)
                if action == "fmidev":
                    title = "🌐 *FMI DEV CHECK*"
                elif action == "macfmi":
                    title = "💻 *MAC FMI CHECK*"
                else:
                    title = "📱 *IMEI CHECK*"

                pretty = (
                    f"{title}\n\n"
                    f"• *IMEI/Serial:* `{imei}`\n"
                    f"• *FMI:* {fmi}\n\n"
                    f"⏱ *Tiempo:* `{elapsed} ms`"
                )
                send(chat_id, pretty, True)
                return {"ok": True}

            if action == "blacklist":
                txt = str(get_response_text(result)).upper()
                estado = "LIMPIO ✅" if ("NOT BLACKLISTED" in txt or "CLEAN" in txt) else ("EN LISTA NEGRA 🚫" if ("BLACKLIST" in txt or "BLOCKED" in txt) else "No disponible")
                pretty = (
                    "🚨 *BLACKLIST CHECK*\n\n"
                    f"• *IMEI:* `{imei}`\n"
                    f"• *Estado:* {estado}\n\n"
                    f"⏱ *Tiempo:* `{elapsed} ms`"
                )
                send(chat_id, pretty, True)
                return {"ok": True}

            if action == "carrier":
                txt = get_response_text(result)
                carrier_match = re.search(r"Carrier:\s*([^\n]+)", txt, re.IGNORECASE)
                carrier = carrier_match.group(1).strip() if carrier_match else "No disponible"
                upper = txt.upper()
                sim = "UNLOCKED 🔓" if "UNLOCKED" in upper else ("LOCKED 🔒" if "LOCKED" in upper else "No disponible")
                pretty = (
                    "📡 *CARRIER CHECK*\n\n"
                    f"• *IMEI:* `{imei}`\n"
                    f"• *Carrier:* {carrier}\n"
                    f"• *SIM-Lock:* {sim}\n\n"
                    f"⏱ *Tiempo:* `{elapsed} ms`"
                )
                send(chat_id, pretty, True)
                return {"ok": True}

            if action == "sample":
                txt = get_response_text(result)[:500] or "Sin detalle"
                pretty = (
                    "🧪 *FREE CHECK SAMPLE*\n\n"
                    f"• *IMEI:* `{imei}`\n"
                    f"• *Detalle:* `{txt}`\n\n"
                    f"⏱ *Tiempo:* `{elapsed} ms`"
                )
                send(chat_id, pretty, True)
                return {"ok": True}

            send(chat_id, f"✅ Consulta completada\n⏱ `{elapsed} ms`", True)
            return {"ok": True}

    return {"ok": True}
