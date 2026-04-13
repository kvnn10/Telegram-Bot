import os
import re
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID")
IFREEICLOUD_URL = os.getenv("IFREEICLOUD_URL")
IFREEICLOUD_PHP_API_KEY = os.getenv("IFREEICLOUD_PHP_API_KEY")

IDENTIFIER_REGEX = re.compile(r"^[A-Za-z0-9]{8,20}$")

SERVICES = {
    "fmi": "4",
    "fmidev": "125",
    "blacklist": "55",
    "carrier": "255",
    "model": "0",
    "sample": "238",
    "macfmi": "247",
}

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })

def parse_fmi(data):
    text = str(data).upper()
    if "ON" in text:
        return "ON 🔴"
    if "OFF" in text:
        return "OFF 🟢"
    return "N/D"

def parse_blacklist(data):
    text = str(data).upper()
    if "CLEAN" in text or "NOT BLACKLISTED" in text:
        return "LIMPIO ✅"
    if "BLACKLIST" in text:
        return "EN LISTA NEGRA 🚫"
    return "N/D"

def query_api(identifier, service):
    r = requests.post(IFREEICLOUD_URL, data={
        "service": service,
        "imei": identifier,
        "key": IFREEICLOUD_PHP_API_KEY
    }, timeout=30)

    try:
        return r.json()
    except:
        return r.text

def build_response(cmd, imei, data):
    if cmd in ["fmi", "fmidev"]:
        status = parse_fmi(data)
        return f"""📱 RESULTADO IMEI

IMEI: {imei}

FMI: {status}

Consulta: Correcta"""

    if cmd == "blacklist":
        status = parse_blacklist(data)
        return f"""🚨 BLACKLIST STATUS

IMEI: {imei}

Estado: {status}

Consulta: Correcta"""

    return f"""📱 RESULTADO IMEI

IMEI: {imei}

Consulta: Correcta"""

def handler(request):
    if request.method == "GET":
        return {"statusCode": 200, "body": "OK"}

    body = request.get_json()

    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if str(chat_id) != ALLOWED_CHAT_ID:
        return {"statusCode": 200, "body": "ok"}

    if not text.startswith("/"):
        send_message(chat_id, "Usa un comando como /fmi 356XXXX")
        return {"statusCode": 200, "body": "ok"}

    parts = text.split(" ", 1)
    cmd = parts[0].replace("/", "")
    imei = parts[1] if len(parts) > 1 else ""

    if cmd not in SERVICES:
        send_message(chat_id, "Comando no válido")
        return {"statusCode": 200, "body": "ok"}

    if not IDENTIFIER_REGEX.match(imei):
        send_message(chat_id, "IMEI inválido")
        return {"statusCode": 200, "body": "ok"}

    send_message(chat_id, "Consultando...")

    data = query_api(imei, SERVICES[cmd])
    result = build_response(cmd, imei, data)

    send_message(chat_id, result)

    return {"statusCode": 200, "body": "ok"}
