# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Instant Messaging Doctor Agent - Telegrammer/Whatsapper diagnostics

import os
import sys

os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import json
import logging
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as exc:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {exc}\n")

CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w', encoding='utf-8').close()

logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

PID_FILE = "agent.pid"
PLACEHOLDER_RE = re.compile(r"^\s*(?:<.*>|\$\{.*\}|REPLACE_ME|PASTE_.*|TODO)\s*$", re.I)


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        logging.error("Error: config.yaml not found.")
        return {}
    except Exception as exc:
        logging.error("Error parsing config.yaml: %s", exc)
        return {}


def write_pid_file() -> None:
    try:
        with open(PID_FILE, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except Exception as exc:
        logging.error("Failed to write PID file: %s", exc)


def remove_pid_file() -> None:
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as exc:
            logging.error("Failed to remove PID file: %s", exc)
            return


def get_python_command() -> List[str]:
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    if sys.platform.startswith("win"):
        carried = os.path.join(os.path.dirname(sys.executable), "python", "python.exe")
        if os.path.exists(carried):
            return [carried]
        bundled = os.path.join(os.path.dirname(sys.executable), "python.exe")
        if os.path.exists(bundled):
            return [bundled]
        return ["python"]
    return ["python3"]


def get_agent_env() -> Dict[str, str]:
    env = os.environ.copy()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = getattr(sys, "_MEIPASS") or ""
        if meipass:
            parts = [p for p in env.get("PATH", "").split(os.pathsep) if os.path.normpath(p) != os.path.normpath(meipass)]
            env["PATH"] = os.pathsep.join(parts)
    return env


def get_pool_path() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(grandparent) == "pools":
        return parent
    if os.path.basename(parent) == "pools":
        return parent
    return os.path.join(os.path.dirname(current_dir), "pools")


def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    direct = os.path.join(agent_dir, f"{agent_name}.py")
    if os.path.exists(direct):
        return direct
    parts = agent_name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        base_path = os.path.join(agent_dir, f"{base}.py")
        if os.path.exists(base_path):
            return base_path
    return direct


def is_agent_running(agent_name: str) -> bool:
    pid_path = os.path.join(get_agent_directory(agent_name), PID_FILE)
    if not os.path.exists(pid_path):
        return False
    try:
        with open(pid_path, "r", encoding="utf-8") as handle:
            pid = int(handle.read().strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_agents_to_stop(agent_names: List[str]) -> None:
    if not agent_names:
        return
    waited = 0.0
    while True:
        running = [name for name in agent_names if is_agent_running(name)]
        if not running:
            return
        if waited >= 10.0:
            logging.error("WAITING FOR AGENTS TO STOP: %s still running", running)
            waited = 0.0
        time.sleep(0.5)
        waited += 0.5


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    if not os.path.exists(script_path):
        logging.error("Agent script not found: %s", script_path)
        return False
    kwargs: Dict[str, Any] = {"cwd": agent_dir, "env": get_agent_env()}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(get_python_command() + [script_path], **kwargs)
        logging.info("Started agent '%s' with PID: %s", agent_name, proc.pid)
        return True
    except Exception as exc:
        logging.error("Failed to start agent '%s': %s", agent_name, exc)
        return False


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if not text or PLACEHOLDER_RE.match(text):
        return ""
    return text


def _looks_secret_present(value: Any) -> bool:
    return bool(_clean(value))


def _redact(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return f"<set: {len(text)} chars>"


def _normalize_msisdn(number: str) -> str:
    return "".join(ch for ch in str(number or "") if ch.isdigit())


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 30) -> Tuple[bool, str, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    return _open_json(req, timeout)


def _get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Tuple[bool, str, Dict[str, Any]]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    return _open_json(req, timeout)


def _open_json(req: urllib.request.Request, timeout: int) -> Tuple[bool, str, Dict[str, Any]]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except Exception:
                parsed = {}
            return 200 <= resp.status < 300, f"HTTP {resp.status}", parsed
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {}
        return False, _format_http_error(exc.code, parsed, body), parsed
    except Exception as exc:
        return False, f"request_error: {exc}", {}


def _format_http_error(status: int, parsed: Dict[str, Any], raw: str) -> str:
    err = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(err, dict):
        bits = [f"HTTP {status}"]
        if err.get("code") is not None:
            bits.append(f"code={err.get('code')}")
        if err.get("type"):
            bits.append(f"type={err.get('type')}")
        if err.get("message"):
            bits.append(str(err.get("message")))
        return " ".join(bits)
    return f"HTTP {status}: {str(raw)[:360]}"


def _ancestor_candidates(start: str) -> List[str]:
    out = []
    current = os.path.abspath(start)
    for _ in range(12):
        out.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return out


def _find_app_file(config: Dict[str, Any], key: str, filenames: List[str]) -> str:
    explicit = _clean(config.get(key))
    if explicit and os.path.exists(explicit):
        return explicit
    env_key = "TLAMATINI_CONTACTS" if key == "contacts_path" else ""
    if env_key:
        env_path = _clean(os.environ.get(env_key))
        if env_path and os.path.exists(env_path):
            return env_path
    for root in _ancestor_candidates(os.path.dirname(os.path.abspath(__file__))):
        for rel in filenames:
            candidate = os.path.join(root, rel)
            if os.path.exists(candidate):
                return candidate
    frozen_root = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""
    if frozen_root:
        for rel in filenames:
            candidate = os.path.join(frozen_root, rel)
            if os.path.exists(candidate):
                return candidate
    return explicit


def _read_json_file(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logging.warning("Could not read JSON file %s: %s", path, exc)
        return {}


def _contacts_list(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = raw.get("contacts") if isinstance(raw, dict) else []
    if isinstance(items, dict):
        return [dict({"name": key}, **(value if isinstance(value, dict) else {})) for key, value in items.items()]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _match_contact(raw_contacts: Dict[str, Any], name: str) -> Tuple[Optional[Dict[str, Any]], str]:
    wanted = _clean(name).lower()
    if not wanted:
        return None, "no contact_name supplied"
    for contact in _contacts_list(raw_contacts):
        names = [str(contact.get("name") or "")]
        aliases = contact.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        names.extend(str(alias) for alias in aliases)
        if any(wanted == item.strip().lower() for item in names if item):
            return contact, "exact"
    for contact in _contacts_list(raw_contacts):
        names = [str(contact.get("name") or "")]
        aliases = contact.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        names.extend(str(alias) for alias in aliases)
        if any(wanted in item.strip().lower() for item in names if item):
            return contact, "fuzzy"
    return None, "not found"


def _merge_telegram_cfg(config: Dict[str, Any], global_cfg: Dict[str, Any]) -> Dict[str, Any]:
    tg = config.get("telegram") if isinstance(config.get("telegram"), dict) else {}
    return {
        "chat_id": _clean(tg.get("chat_id") or config.get("telegram_chat_id")),
        "bot_token": _clean(tg.get("bot_token") or global_cfg.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")),
        "provider": (_clean(tg.get("provider")) or "auto").lower(),
        "api_id": _clean(tg.get("api_id") or global_cfg.get("telegram_api_id") or os.environ.get("TELEGRAM_API_ID")),
        "api_hash": _clean(tg.get("api_hash") or global_cfg.get("telegram_api_hash") or os.environ.get("TELEGRAM_API_HASH")),
        "session_name": _clean(tg.get("session_name") or global_cfg.get("telegram_session_name") or os.environ.get("TELEGRAM_SESSION_NAME")),
        "session_string": _clean(tg.get("session_string") or global_cfg.get("telegram_session_string") or os.environ.get("TELEGRAM_SESSION_STRING")),
    }


def _merge_whatsapp_cfg(config: Dict[str, Any], global_cfg: Dict[str, Any]) -> Dict[str, Any]:
    wa = config.get("whatsapp") if isinstance(config.get("whatsapp"), dict) else {}
    return {
        "to": _clean(wa.get("to") or config.get("to") or global_cfg.get("whatsapp_to")),
        "phone_number_id": _clean(wa.get("phone_number_id") or global_cfg.get("whatsapp_phone_number_id") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")),
        "access_token": _clean(wa.get("access_token") or global_cfg.get("whatsapp_access_token") or os.environ.get("WHATSAPP_ACCESS_TOKEN")),
        "graph_base": _clean(wa.get("graph_base") or global_cfg.get("whatsapp_graph_base") or os.environ.get("WHATSAPP_GRAPH_BASE")) or "https://graph.facebook.com",
        "api_version": _clean(wa.get("api_version") or global_cfg.get("whatsapp_api_version") or os.environ.get("WHATSAPP_API_VERSION")) or "v20.0",
        "verify_token": _clean(wa.get("verify_token") or global_cfg.get("whatsapp_verify_token") or os.environ.get("WHATSAPP_VERIFY_TOKEN")) or "tlamatini",
        "webhook_host": _clean(wa.get("webhook_host")) or "0.0.0.0",
        "webhook_port": int(wa.get("webhook_port") or os.environ.get("WHATSAPP_WEBHOOK_PORT") or 8086),
        "webhook_path": _clean(wa.get("webhook_path")) or "/wa-webhook",
    }


def _telegram_get_me(token: str) -> Tuple[str, str]:
    if not token:
        return "missing", "telegram.bot_token is missing"
    ok, info, data = _get_json(f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/getMe")
    if ok and data.get("ok"):
        result = data.get("result") or {}
        return "ready", f"Bot API token valid as @{result.get('username', '') or result.get('first_name', 'bot')}"
    return "blocked", info


def _telegram_get_chat(token: str, recipient: str) -> Tuple[str, str]:
    if not token or not recipient:
        return "skipped", "no Telegram recipient to validate"
    encoded = urllib.parse.urlencode({"chat_id": recipient})
    ok, info, data = _get_json(f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/getChat?{encoded}")
    if ok and data.get("ok"):
        chat = data.get("result") or {}
        return "ready", f"recipient reachable via Bot API (id={chat.get('id', '')})"
    if recipient.startswith("@"):
        return "needs_operator", (
            "Bot API could not resolve this @username. Keep the @username in config, "
            "but the user must press Start/message the bot once, or configure Telegrammer "
            "official user-session credentials for private cold sends."
        )
    return "blocked", info


def _whatsapp_validate_number(wa_cfg: Dict[str, Any]) -> Tuple[str, str]:
    if not wa_cfg["phone_number_id"] or not wa_cfg["access_token"]:
        return "missing", "whatsapp.phone_number_id or whatsapp.access_token is missing"
    base = wa_cfg["graph_base"].rstrip("/")
    version = wa_cfg["api_version"].strip("/")
    url = f"{base}/{version}/{urllib.parse.quote(wa_cfg['phone_number_id'])}?fields=id,display_phone_number,verified_name"
    ok, info, data = _get_json(url, {"Authorization": f"Bearer {wa_cfg['access_token']}"})
    if ok:
        return "ready", f"Cloud API token accepted for {data.get('display_phone_number', wa_cfg['phone_number_id'])}"
    if "code=190" in info or "HTTP 401" in info:
        return "blocked", (
            "Meta rejected authentication. Generate a fresh System User token with "
            "whatsapp_business_messaging and whatsapp_business_management, assign the "
            "WhatsApp asset, update whatsapp_access_token, and restart Tlamatini."
        )
    return "blocked", info


def _send_whatsapp_template(wa_cfg: Dict[str, Any], recipient: str, template: str, language: str, params: List[Any]) -> Tuple[str, str, str]:
    if not template:
        return "skipped", "no template requested", ""
    if not recipient:
        return "blocked", "no WhatsApp recipient", ""
    base = wa_cfg["graph_base"].rstrip("/")
    version = wa_cfg["api_version"].strip("/")
    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _normalize_msisdn(recipient),
        "type": "template",
        "template": {"name": template, "language": {"code": language or "en_US"}},
    }
    if params:
        payload["template"]["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": str(item)} for item in params],
        }]
    url = f"{base}/{version}/{urllib.parse.quote(wa_cfg['phone_number_id'])}/messages"
    ok, info, data = _post_json(url, payload, {"Authorization": f"Bearer {wa_cfg['access_token']}"})
    if ok:
        messages = data.get("messages") if isinstance(data, dict) else []
        mid = str((messages or [{}])[0].get("id") or "")
        return "sent", f"template {template} accepted by Meta", mid
    return "blocked", info, ""


def _send_telegram_text(tg_cfg: Dict[str, Any], recipient: str, message: str) -> Tuple[str, str, str]:
    if not message:
        return "skipped", "no message requested", ""
    if not tg_cfg["bot_token"]:
        return "missing", "telegram.bot_token is missing", ""
    status, detail = _telegram_get_chat(tg_cfg["bot_token"], recipient)
    if status != "ready":
        return status, detail, ""
    payload = {"chat_id": recipient, "text": message}
    url = f"https://api.telegram.org/bot{urllib.parse.quote(tg_cfg['bot_token'], safe=':')}/sendMessage"
    ok, info, data = _post_json(url, payload, {})
    if ok and data.get("ok"):
        result = data.get("result") or {}
        return "sent", "Telegram message accepted by Bot API", str(result.get("message_id") or "")
    return "blocked", info, ""


def _coerce_param_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    text = str(value).strip()
    if not text:
        return []
    if "||" in text:
        return [part.strip() for part in text.split("||")]
    return [text]


def _ollama_summary(config: Dict[str, Any], report: Dict[str, Any]) -> str:
    if not config.get("use_llm", True):
        return ""
    ollama = config.get("ollama") if isinstance(config.get("ollama"), dict) else {}
    url = _clean(ollama.get("url") or config.get("ollama_url") or os.environ.get("OLLAMA_URL")) or "http://localhost:11434"
    model = _clean(ollama.get("model") or config.get("model")) or "glm-5.2:cloud"
    timeout = int(ollama.get("timeout_seconds") or 45)
    prompt = (
        "You are Tlamatini's Instant Messaging Doctor. Summarize this JSON diagnosis "
        "in exact operator steps. Do not invent credentials or claim delivery when a platform blocked it.\n\n"
        + json.dumps(report, ensure_ascii=False, indent=2)
    )
    payload = {"model": model, "prompt": prompt, "stream": False}
    ok, info, data = _post_json(f"{url.rstrip('/')}/api/generate", payload, {}, timeout=timeout)
    if ok:
        return str(data.get("response") or "").strip()
    logging.warning("Ollama summary unavailable: %s", info)
    return ""


def _overall_status(statuses: List[str]) -> str:
    if any(item in {"blocked", "missing"} for item in statuses):
        return "blocked"
    if any(item == "needs_operator" for item in statuses):
        return "needs_operator"
    if any(item == "sent" for item in statuses):
        return "sent"
    if all(item in {"ready", "skipped"} for item in statuses):
        return "ready"
    return "attention"


def diagnose(config: Dict[str, Any]) -> Dict[str, Any]:
    config_path = _find_app_file(config, "config_path", ["config.json", os.path.join("Tlamatini", "agent", "config.json")])
    contacts_path = _find_app_file(config, "contacts_path", ["contacts.json", os.path.join("Tlamatini", "agent", "contacts.json")])
    global_cfg = _read_json_file(config_path)
    contacts_raw = _read_json_file(contacts_path)
    contact, contact_match = _match_contact(contacts_raw, str(config.get("contact_name") or ""))
    tg_cfg = _merge_telegram_cfg(config, global_cfg)
    wa_cfg = _merge_whatsapp_cfg(config, global_cfg)
    if contact:
        tg_cfg["chat_id"] = _clean(contact.get("telegram")) or tg_cfg["chat_id"]
        wa_cfg["to"] = _clean(contact.get("whatsapp")) or wa_cfg["to"]

    platform = (_clean(config.get("platform")) or "both").lower()
    retry_send = bool(config.get("retry_send", False))
    message = str(config.get("message") or "").strip()
    template = _clean(config.get("template"))
    template_language = _clean(config.get("template_language")) or "en_US"
    template_params = _coerce_param_list(config.get("template_params"))

    checks: Dict[str, Any] = {}
    statuses: List[str] = []

    contact_status = "ready" if (not config.get("contact_name") or contact) else "missing"
    checks["contacts"] = {
        "status": contact_status,
        "match": contact_match,
        "contacts_path": contacts_path,
        "contact_name": config.get("contact_name") or "",
        "telegram": bool(contact and contact.get("telegram")),
        "whatsapp": bool(contact and contact.get("whatsapp")),
    }
    statuses.append(contact_status)

    retry_status = "skipped"
    retry_detail = ""
    retry_message_id = ""

    if platform in {"both", "telegram"}:
        token_status, token_detail = _telegram_get_me(tg_cfg["bot_token"])
        recipient = _clean(config.get("telegram_recipient") or tg_cfg["chat_id"])
        recipient_status, recipient_detail = _telegram_get_chat(tg_cfg["bot_token"], recipient)
        user_session_ready = bool(tg_cfg["api_id"] and tg_cfg["api_hash"] and (tg_cfg["session_name"] or tg_cfg["session_string"]))
        if retry_send and message:
            retry_status, retry_detail, retry_message_id = _send_telegram_text(tg_cfg, recipient, message)
        checks["telegram"] = {
            "status": _overall_status([token_status, recipient_status]),
            "token_status": token_status,
            "token_detail": token_detail,
            "recipient": recipient,
            "recipient_status": recipient_status,
            "recipient_detail": recipient_detail,
            "provider": tg_cfg["provider"],
            "user_session_ready": user_session_ready,
            "retry_status": retry_status,
            "retry_detail": retry_detail,
            "message_id": retry_message_id,
            "token_redacted": _redact(tg_cfg["bot_token"]),
        }
        statuses.extend([token_status, recipient_status])
        if retry_status != "skipped":
            statuses.append(retry_status)

    if platform in {"both", "whatsapp"}:
        wa_status, wa_detail = _whatsapp_validate_number(wa_cfg)
        recipient = _normalize_msisdn(_clean(config.get("whatsapp_to") or wa_cfg["to"]))
        recipient_status = "ready" if recipient else "missing"
        if retry_send and template:
            retry_status, retry_detail, retry_message_id = _send_whatsapp_template(
                wa_cfg, recipient, template, template_language, template_params)
        checks["whatsapp"] = {
            "status": _overall_status([wa_status, recipient_status]),
            "credential_status": wa_status,
            "credential_detail": wa_detail,
            "recipient": recipient,
            "recipient_status": recipient_status,
            "phone_number_id": wa_cfg["phone_number_id"],
            "token_redacted": _redact(wa_cfg["access_token"]),
            "template": template,
            "template_language": template_language,
            "retry_status": retry_status,
            "retry_detail": retry_detail,
            "message_id": retry_message_id,
            "free_text_policy": "Free-form WhatsApp text delivers only inside the 24-hour customer-service window; cold sends require an approved template.",
        }
        statuses.extend([wa_status, recipient_status])
        if retry_status != "skipped":
            statuses.append(retry_status)

    actions = []
    if checks.get("whatsapp", {}).get("credential_status") in {"blocked", "missing"}:
        actions.append("Regenerate a Meta System User access token with whatsapp_business_messaging and whatsapp_business_management, assign the WABA/phone asset, update whatsapp_access_token, then restart Tlamatini.")
    if checks.get("whatsapp", {}).get("recipient_status") == "missing":
        actions.append("Add a WhatsApp phone number with country code to contacts.json, or pass whatsapp.to explicitly.")
    if checks.get("telegram", {}).get("recipient_status") == "needs_operator":
        actions.append("Have the Telegram recipient press Start/message the bot once, or configure Telegrammer's official user-session credentials for private @username cold sends.")
    if checks.get("telegram", {}).get("token_status") in {"blocked", "missing"}:
        actions.append("Create or paste a valid @BotFather bot token into telegram_bot_token / telegram.bot_token.")

    result = {
        "status": _overall_status(statuses),
        "platform": platform,
        "contact_status": contact_status,
        "telegram_status": checks.get("telegram", {}).get("status", "skipped"),
        "whatsapp_status": checks.get("whatsapp", {}).get("status", "skipped"),
        "repair_status": "operator_required" if actions else "not_needed",
        "retry_status": retry_status,
        "actions_required": " | ".join(actions),
        "config_path": config_path,
        "contacts_path": contacts_path,
        "checks": checks,
        "failure_log_excerpt": str(config.get("failure_log_excerpt") or "")[-4000:],
    }
    result["llm_summary"] = _ollama_summary(config, result)
    return result


def _emit_section(result: Dict[str, Any]) -> None:
    body = json.dumps(result, ensure_ascii=False, indent=2)
    logging.info(
        "INI_SECTION_INSTANT_MESSAGING_DOCTOR<<<\n"
        f"platform: {result.get('platform', '')}\n"
        f"status: {result.get('status', '')}\n"
        f"telegram_status: {result.get('telegram_status', '')}\n"
        f"whatsapp_status: {result.get('whatsapp_status', '')}\n"
        f"contact_status: {result.get('contact_status', '')}\n"
        f"repair_status: {result.get('repair_status', '')}\n"
        f"retry_status: {result.get('retry_status', '')}\n"
        f"actions_required: {result.get('actions_required', '')}\n"
        "\n"
        f"{body}\n"
        ">>>END_SECTION_INSTANT_MESSAGING_DOCTOR"
    )


def main() -> None:
    config = load_config()
    write_pid_file()
    exit_code = 0
    try:
        if _IS_REANIMATED:
            logging.info("%s REANIMATED (resuming from pause)", CURRENT_DIR_NAME)
            logging.info("=" * 60)
        target_agents = config.get("target_agents", [])
        if not isinstance(target_agents, list):
            target_agents = []
        logging.info("INSTANT MESSAGING DOCTOR AGENT STARTED")
        result = diagnose(config)
        _emit_section(result)
        logging.info("Instant Messaging Doctor summary: %s", json.dumps({
            "status": result.get("status"),
            "telegram_status": result.get("telegram_status"),
            "whatsapp_status": result.get("whatsapp_status"),
            "retry_status": result.get("retry_status"),
        }, ensure_ascii=False))
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                start_agent(target)
        logging.info("Instant Messaging Doctor agent finished.")
    except Exception as exc:
        logging.error("Critical Error: %s", exc, exc_info=True)
        exit_code = 1
    finally:
        time.sleep(0.4)
        remove_pid_file()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
