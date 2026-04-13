import os
import re
import html
import time
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
IFREEICLOUD_URL = os.getenv("IFREEICLOUD_URL", "https://api.ifreeicloud.co.uk").strip().rstrip("/")
IFREEICLOUD_PHP_API_KEY = os.getenv("IFREEICLOUD_PHP_API_KEY", "").strip()

IDENTIFIER_REGEX = re.compile(r"^[A-Za-z0-9]{8,20}$")

SERVICES = {
    "model": {"id": "0", "usage": "/model 356XXXXXXXXXXXX", "title": "📲 DEVICE INFO"},
    "fmi": {"id": "4", "usage": "/fmi 356XXXXXXXXXXXX", "title": "📱 IMEI CHECK"},
    "fmidev": {"id": "125", "usage": "/fmidev 356XXXXXXXXXXXX", "title": "📱 IMEI CHECK"},
    "blacklist": {"id": "55", "usage": "/blacklist 356XXXXXXXXXXXX", "title": "🚨 BLACKLIST CHECK"},
    "carrier": {"id": "255", "usage": "/carrier 356XXXXXXXXXXXX", "title": "📡 CARRIER CHECK"},
    "sample": {"id": "238", "usage": "/sample 356XXXXXXXXXXXX", "title": "🧪 FREE CHECK SAMPLE"},
    "macfmi": {"id": "247", "usage": "/macfmi C02XXXXXXXXX", "title": "💻 MACBOOK CHECK"},
}

BUTTONS = {
    "btn_model": "model",
    "btn_fmi": "fmi",
    "btn_fmidev": "fmidev",
    "btn_blacklist": "blacklist",
    "btn_carrier": "carrier",
    "btn_sample": "sample",
    "btn_macfmi": "macfmi",
}

PENDING_ACTIONS: Dict[str, str] = {}

def normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()

def is_valid_identifier(value: str) -> bool:
    return bool(IDENTIFIER_REGEX.fullmatch(value))

def strip_html_tags(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def query_ifreeicloud(identifier: str, service_id: str) -> Any:
    payload = {
        "service": service_id,
        "imei": identifier,
        "key": IFREEICLOUD_PHP_API_KEY,
    }
    response = requests.post(IFREEICLOUD_URL, data=payload, timeout=30)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return response.text

def get_obj(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        obj = data.get("object")
        if isinstance(obj, dict):
            return obj
    return {}

def get_response_text(data: Any) -> str:
    if isinstance(data, dict):
        for key in ["response", "message", "error"]:
            value = data.get(key)
            if value:
                return strip_html_tags(str(value))
    return strip_html_tags(str(data))

def collect_text_candidates(data: Any) -> str:
    parts = []
    def walk(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (str, int, float, bool)):
            parts.append(str(value))
            return
        if isinstance(value, dict):
            for k, v in value.items():
                parts.append(str(k))
                walk(v)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
    walk(data)
    return strip_html_tags(" | ".join(parts))

def pick_first(obj: Dict[str, Any], keys: list[str]) -> Optional[str]:
    for key in keys:
        value = obj.get(key)
        if value not in (None, "", []):
            return str(value)
    return None

def parse_success(data: Any) -> str:
    if isinstance(data, dict):
        if data.get("success") is True:
            return "Correcta"
        if data.get("success") is False:
            return "Error"
    return "Correcta"

def parse_error_detail(data: Any) -> str:
    if isinstance(data, dict):
        for key in ["error", "message", "response"]:
            value = data.get(key)
            if value:
                text = strip_html_tags(str(value)).strip()
                if text:
                    return text[:300]
    text = strip_html_tags(str(data)).strip()
    return text[:300] if text else "Sin detalle"

def parse_fmi_status(data: Any) -> str:
    blob = collect_text_candidates(data).upper()
    obj = get_obj(data)
    on_patterns = [
        "FMION TRUE", "FMION: TRUE", "FIND MY IPHONE ON", "FIND MY IPHONE: ON",
        "FIND MY ON", "FIND MY: ON", "ICLOUD ON", "FMI ON",
    ]
    off_patterns = [
        "FMION FALSE", "FMION: FALSE", "FIND MY IPHONE OFF", "FIND MY IPHONE: OFF",
        "FIND MY OFF", "FIND MY: OFF", "ICLOUD OFF", "FMI OFF",
    ]
    if any(x in blob for x in on_patterns):
        return "ON 🔴"
    if any(x in blob for x in off_patterns):
        return "OFF 🟢"
    for key in ["fmion", "fmi", "find_my_iphone", "find_my", "icloud", "icloud_status"]:
        if key in obj:
            value = str(obj.get(key)).strip().lower()
            if value in ["true", "on", "yes", "1"]:
                return "ON 🔴"
            if value in ["false", "off", "no", "0"]:
                return "OFF 🟢"
    return "No disponible"

def parse_blacklist_status(data: Any) -> str:
    blob = collect_text_candidates(data).upper()
    obj = get_obj(data)
    if "NOT BLACKLISTED" in blob or "CLEAN" in blob:
        return "LIMPIO ✅"
    if "BLACKLISTED" in blob or "BLACKLIST" in blob or "BLOCKED" in blob:
        return "EN LISTA NEGRA 🚫"
    value = pick_first(obj, ["blacklist", "blacklisted", "status"])
    if value:
        v = value.upper()
        if "CLEAN" in v or "NOT BLACKLISTED" in v:
            return "LIMPIO ✅"
        if "BLACKLIST" in v or "BLOCKED" in v:
            return "EN LISTA NEGRA 🚫"
    return "No disponible"

def parse_carrier_info(data: Any) -> tuple[str, str]:
    obj = get_obj(data)
    blob = collect_text_candidates(data)
    carrier = pick_first(obj, ["carrier", "network", "operator"]) or "No disponible"
    simlock = pick_first(obj, ["simlock", "sim_lock", "sim-lock", "lock_status"]) or "No disponible"
    if carrier == "No disponible":
        m = re.search(r"CARRIER\s*:?\s*([^\n|,]+)", blob, re.IGNORECASE)
        if m:
            carrier = m.group(1).strip()
    upper_blob = blob.upper()
    if simlock == "No disponible":
        if "UNLOCKED" in upper_blob:
            simlock = "UNLOCKED 🔓"
        elif "LOCKED" in upper_blob:
            simlock = "LOCKED 🔒"
    return carrier, simlock

def parse_model_info(data: Any) -> tuple[str, str]:
    try:
        if isinstance(data, dict):
            obj = data.get("object", {}) or {}
            brand = obj.get("brand") or obj.get("manufacturer") or obj.get("make")
            model = obj.get("model") or obj.get("device") or obj.get("name") or obj.get("product")
            if brand or model:
                return brand or "No disponible", model or "No disponible"
        text = get_response_text(data)
        brand_match = re.search(r"BRAND\s*:?\s*([^\n|,]+)", text, re.IGNORECASE)
        model_match = re.search(r"MODEL\s*:?\s*([^\n|,]+)", text, re.IGNORECASE)
        brand = brand_match.group(1).strip() if brand_match else "No disponible"
        model = model_match.group(1).strip() if model_match else "No disponible"
        return brand, model
    except Exception:
        return "No disponible", "No disponible"

def premium_success(value: str) -> str:
    if value.lower() == "correcta":
        return "Correcta ✅"
    if value.lower() == "error":
        return "Error ⚠️"
    return value

def should_hide_error_detail(command_name: str, data: Any) -> bool:
    if command_name in ["fmi", "fmidev", "macfmi"]:
        return parse_fmi_status(data) != "No disponible"
    if command_name == "model":
        brand, model = parse_model_info(data)
        return brand != "No disponible" or model != "No disponible"
    if command_name == "blacklist":
        return parse_blacklist_status(data) != "No disponible"
    if command_name == "carrier":
        carrier, simlock = parse_carrier_info(data)
        return carrier != "No disponible" or simlock != "No disponible"
    return False

def build_card(title: str, lines: list[str]) -> str:
    return (
        "┏━━━━━━━━━━━━━━━━━━┓\n"
        f"{title}\n"
        "┗━━━━━━━━━━━━━━━━━━┛\n\n"
        + "\n".join(lines)
    )

def build_result_message(command_name: str, identifier: str, data: Any, elapsed_ms: int) -> str:
    success_raw = parse_success(data)
    success_text = premium_success(success_raw)
    error_detail = parse_error_detail(data)
    hide_error = should_hide_error_detail(command_name, data)

    if command_name in ["fmi", "fmidev"]:
        status = parse_fmi_status(data)
        lines = [
            f"• *IMEI:* `{identifier}`",
            f"• *FMI:* `{status}`",
            f"• *Consulta:* `{success_text}`",
            f"• *Tiempo:* `{elapsed_ms} ms`",
        ]
        if success_raw.lower() == "error" and not hide_error:
            lines.append(f"• *Detalle API:* `{error_detail}`")
        return build_card("📱 *IMEI CHECK*", lines)

    if command_name == "macfmi":
        status = parse_fmi_status(data)
        lines = [
            f"• *Serial/IMEI:* `{identifier}`",
            f"• *FMI:* `{status}`",
            f"• *Consulta:* `{success_text}`",
            f"• *Tiempo:* `{elapsed_ms} ms`",
        ]
        if success_raw.lower() == "error" and not hide_error:
            lines.append(f"• *Detalle API:* `{error_detail}`")
        return build_card("💻 *MACBOOK CHECK*", lines)

    if command_name == "blacklist":
        status = parse_blacklist_status(data)
        lines = [
            f"• *IMEI:* `{identifier}`",
            f"• *Estado:* `{status}`",
            f"• *Consulta:* `{success_text}`",
            f"• *Tiempo:* `{elapsed_ms} ms`",
        ]
        if success_raw.lower() == "error" and not hide_error:
            lines.append(f"• *Detalle API:* `{error_detail}`")
        return build_card("🚨 *BLACKLIST CHECK*", lines)

    if command_name == "carrier":
        carrier, simlock = parse_carrier_info(data)
        lines = [
            f"• *IMEI:* `{identifier}`",
            f"• *Carrier:* `{carrier}`",
            f"• *SIM-Lock:* `{simlock}`",
            f"• *Consulta:* `{success_text}`",
            f"• *Tiempo:* `{elapsed_ms} ms`",
        ]
        if success_raw.lower() == "error" and not hide_error:
            lines.append(f"• *Detalle API:* `{error_detail}`")
        return build_card("📡 *CARRIER CHECK*", lines)

    if command_name == "model":
        brand, model = parse_model_info(data)
        lines = [
            f"• *IMEI:* `{identifier}`",
            f"• *Marca:* `{brand}`",
            f"• *Modelo:* `{model}`",
            f"• *Consulta:* `{success_text}`",
            f"• *Tiempo:* `{elapsed_ms} ms`",
        ]
        if success_raw.lower() == "error" and not hide_error:
            lines.append(f"• *Detalle API:* `{error_detail}`")
        return build_card("📲 *DEVICE INFO*", lines)

    detail = get_response_text(data) or "Sin detalle"
    lines = [
        f"• *IMEI:* `{identifier}`",
        f"• *Detalle:* `{detail[:300]}`",
        f"• *Consulta:* `{success_text}`",
        f"• *Tiempo:* `{elapsed_ms} ms`",
    ]
    if success_raw.lower() == "error" and not hide_error:
        lines.append(f"• *Detalle API:* `{error_detail}`")
    return build_card("🧪 *FREE CHECK SAMPLE*", lines)

def main_menu_markup() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "📲 Model", "callback_data": "btn_model"},
                {"text": "📱 FMI", "callback_data": "btn_fmi"},
            ],
            [
                {"text": "🌐 FMI Dev", "callback_data": "btn_fmidev"},
                {"text": "🚨 Blacklist", "callback_data": "btn_blacklist"},
            ],
            [
                {"text": "📡 Carrier", "callback_data": "btn_carrier"},
                {"text": "🧪 Sample", "callback_data": "btn_sample"},
            ],
            [
                {"text": "💻 Mac FMI", "callback_data": "btn_macfmi"},
                {"text": "🆔 MyID", "callback_data": "btn_myid"},
            ],
        ]
    }

def telegram_api(method: str, payload: Dict[str, Any]) -> requests.Response:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    return requests.post(url, json=payload, timeout=30)

def send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_api("sendMessage", payload)

def answer_callback_query(callback_query_id: str) -> None:
    telegram_api("answerCallbackQuery", {"callback_query_id": callback_query_id})

def send_start(chat_id: int) -> None:
    send_message(
        chat_id,
        "┏━━━━━━━━━━━━━━━━━━━━┓\n"
        "🤖 *IMEI Check Server*\n"
        "┗━━━━━━━━━━━━━━━━━━━━┛\n\n"
        "Selecciona una consulta o escribe un comando.\n\n"
        "También puedes usar:\n"
        "• `/model 356XXXXXXXXXXXX`\n"
        "• `/fmi 356XXXXXXXXXXXX`\n"
        "• `/fmidev 356XXXXXXXXXXXX`\n"
        "• `/blacklist 356XXXXXXXXXXXX`\n"
        "• `/carrier 356XXXXXXXXXXXX`\n"
        "• `/sample 356XXXXXXXXXXXX`\n"
        "• `/macfmi C02XXXXXXXXX`\n"
        "• `/myid`",
        reply_markup=main_menu_markup(),
    )

def run_service(chat_id: int, command_name: str, identifier: str) -> None:
    if not is_valid_identifier(identifier):
        send_message(chat_id, "❌ Dato inválido. Envía un IMEI o serial válido.")
        return

    send_message(chat_id, "⏳ Consultando, espera un momento...")

    started = time.perf_counter()
    try:
        data = query_ifreeicloud(identifier, SERVICES[command_name]["id"])
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        message = build_result_message(command_name, identifier, data, elapsed_ms)
        send_message(chat_id, message[:3900], reply_markup=main_menu_markup())
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        send_message(
            chat_id,
            "┏━━━━━━━━━━━━━━┓\n"
            "❌ *ERROR DE CONSULTA*\n"
            "┗━━━━━━━━━━━━━━┛\n\n"
            f"• *Tiempo:* `{elapsed_ms} ms`\n"
            f"• *Detalle:* `{str(exc)[:3000]}`",
            reply_markup=main_menu_markup(),
        )

def handle_command(chat_id: int, text: str) -> None:
    parts = text.strip().split(maxsplit=1)
    command = parts[0].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in ["/start", "/help"]:
        send_start(chat_id)
        return

    if command == "/myid":
        send_message(chat_id, f"🆔 Tu chat ID es: `{chat_id}`", reply_markup=main_menu_markup())
        return

    cmd_map = {
        "/model": "model",
        "/fmi": "fmi",
        "/fmidev": "fmidev",
        "/blacklist": "blacklist",
        "/carrier": "carrier",
        "/sample": "sample",
        "/macfmi": "macfmi",
    }

    if command not in cmd_map:
        send_message(chat_id, "❌ Comando no reconocido.", reply_markup=main_menu_markup())
        return

    command_name = cmd_map[command]
    if not arg:
        send_message(chat_id, f"Uso correcto:\n`{SERVICES[command_name]['usage']}`", reply_markup=main_menu_markup())
        return

    run_service(chat_id, command_name, normalize_identifier(arg))

def handle_button(chat_id: int, callback_data: str) -> None:
    if callback_data == "btn_myid":
        send_message(chat_id, f"🆔 Tu chat ID es: `{chat_id}`", reply_markup=main_menu_markup())
        return

    command_name = BUTTONS.get(callback_data)
    if not command_name:
        send_message(chat_id, "❌ Botón no válido.", reply_markup=main_menu_markup())
        return

    PENDING_ACTIONS[str(chat_id)] = command_name

    prompt = "Envíame el IMEI para continuar."
    if command_name == "macfmi":
        prompt = "Envíame el serial o IMEI del MacBook."

    send_message(chat_id, f"✅ Seleccionaste *{command_name.upper()}*\n\n{prompt}", reply_markup=main_menu_markup())

@app.get("/")
async def root():
    return {"ok": True, "service": "telegrambotk"}

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    if not TELEGRAM_BOT_TOKEN or not ALLOWED_CHAT_ID or not IFREEICLOUD_PHP_API_KEY:
        return JSONResponse({"ok": False, "error": "Missing env vars"}, status_code=500)

    update = await request.json()

    callback_query = update.get("callback_query")
    if callback_query:
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        callback_data = callback_query.get("data", "")
        callback_query_id = callback_query.get("id", "")

        if str(chat_id) == ALLOWED_CHAT_ID:
            answer_callback_query(callback_query_id)
            handle_button(chat_id, callback_data)

        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if str(chat_id) != ALLOWED_CHAT_ID:
        return {"ok": True}

    if text.startswith("/"):
        handle_command(chat_id, text)
        return {"ok": True}

    pending = PENDING_ACTIONS.get(str(chat_id))
    if pending:
        identifier = normalize_identifier(text)
        PENDING_ACTIONS.pop(str(chat_id), None)
        run_service(chat_id, pending, identifier)
        return {"ok": True}

    send_message(
        chat_id,
        "Envíame un comando o usa los botones del menú.",
        reply_markup=main_menu_markup(),
    )
    return {"ok": True}
