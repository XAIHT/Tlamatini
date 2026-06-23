import os
import sys
import time
import json
import base64
import yaml
import logging
import requests
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Optional, Tuple

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# Try to import LangChain/Ollama (graceful degradation if missing, though typically present)
try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    # This might happen if environment is not set up, but we assume it is based on other agents
    pass

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Logging Setup
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

PID_FILE = "agent.pid"
REANIM_FILE = "reanim.pos"


# ─────────────────────────────────────────────────────────────
# Path resolution helpers (ported from Emailer/Raiser agents)
# ─────────────────────────────────────────────────────────────

def get_pool_path() -> str:
    """
    Get the pool directory path where deployed agents reside.
    Deployed agents with cardinals (e.g., starter_1, whatsapper_1) are here.
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return parent

        # Fallback: agents/<agent_name> -> agents/pools
        return os.path.join(os.path.dirname(current_dir), 'pools')


def get_template_agents_path() -> str:
    """
    Get the template agents directory path (non-deployed agents).
    Template agents without cardinals (e.g., whatsapper, starter) are here.
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'agents')
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Check if deployed in session: pools/<session>/<agent>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return os.path.dirname(grandparent)

        # Fallback: agents/<agent_name> -> agents
        return os.path.dirname(current_dir)


def is_deployed_agent(agent_name: str) -> bool:
    """
    Check if an agent name has a cardinal suffix (is a deployed instance).
    Examples: starter_1 -> True, starter -> False
    """
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2:
        try:
            int(parts[1])
            return True
        except ValueError:
            return False
    return False


def get_agent_directory(agent_name: str) -> str:
    """
    Get the full path to an agent's directory.
    Deployed agents (with cardinal, e.g., starter_1) are in pool/.
    Template agents (without cardinal, e.g., starter) are in agents/.
    """
    if is_deployed_agent(agent_name):
        return os.path.join(get_pool_path(), agent_name)
    else:
        return os.path.join(get_template_agents_path(), agent_name)


def get_agent_log_path(agent_name: str) -> str:
    """
    Get the log file path for an agent.
    Examples:
    - starter_1 -> pool/starter_1/starter_1.log
    - starter   -> agents/starter/starter.log
    """
    agent_dir = get_agent_directory(agent_name)
    return os.path.join(agent_dir, f"{agent_name}.log")


# ─────────────────────────────────────────────────────────────
# Smart polling (ported from Emailer/Raiser pattern)
# ─────────────────────────────────────────────────────────────

def check_log_for_new_content(log_path: str, offset: int, file_sizes: Dict[str, int]) -> tuple:
    """
    Check a log file for new content starting from offset.
    Smart polling that handles:
    - Log files that don't exist initially (waits for appearance)
    - Log files that are truncated/recreated (resets offset to 0)
    - Log files that decrease in size (treats as new file)

    Args:
        log_path: Path to the log file
        offset: Current read offset
        file_sizes: Dictionary tracking last known file sizes (modified in-place)

    Returns: (new_content: str or None, new_offset: int)
    """
    last_known_size = file_sizes.get(log_path, -1)  # -1 means never seen

    if not os.path.exists(log_path):
        # File doesn't exist - reset tracking and wait
        file_sizes[log_path] = -1  # Mark as "waiting for file"
        return None, 0  # Reset offset to 0 to catch content when file appears

    try:
        current_size = os.path.getsize(log_path)

        # Detect file truncation/recreation scenarios:
        # 1. File size decreased (truncated or recreated with less content)
        # 2. File appeared after being absent (last_known_size was -1)
        # 3. Current offset is beyond file size (stale offset from reanim.pos)
        if current_size < offset or last_known_size == -1 or current_size < last_known_size:
            if last_known_size == -1:
                logging.info(f"📁 Log file appeared: {log_path}")
            elif current_size < last_known_size:
                logging.info(f"🔄 Log file truncated/recreated: {log_path} ({last_known_size} -> {current_size} bytes)")
            else:
                logging.info(f"🔄 Stale offset detected for {log_path}, resetting")
            offset = 0  # Read from beginning

        # Update tracking
        file_sizes[log_path] = current_size

        if current_size <= offset:
            return None, offset  # No new content

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()

        if new_content.strip():
            return new_content, new_offset
        return None, new_offset

    except Exception as e:
        logging.error(f"Error reading log {log_path}: {e}")
        return None, offset


# ─────────────────────────────────────────────────────────────
# Config / PID / Reanim helpers
# ─────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"❌ Error loading config: {e}")
        return {}

def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")

def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception:
            return

def load_reanim_offsets() -> Dict[str, int]:
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def save_reanim_offsets(offsets: Dict[str, int]):
    try:
        with open(REANIM_FILE, "w", encoding="utf-8") as f:
            yaml.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Could not save offsets: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# WhatsApp senders
# ═════════════════════════════════════════════════════════════════════════════
# PROFESSIONAL DEFAULT — Meta's official WhatsApp Cloud API (Graph API). This is
# the same enterprise backbone WhatsTlamatini uses; stdlib-only (urllib) so this
# self-contained pool agent needs no extra dependency. The legacy TextMeBot path
# is kept ONLY as an optional fallback (provider: textmebot) so older flows keep
# working — new sends default to Meta Cloud API.
#
# WhatsApp policy (a HARD platform rule, not a code limit):
#   * A free-form TEXT message is only deliverable inside the 24-hour
#     customer-service window (the recipient messaged this number in the last
#     24h). Outside it, Meta rejects the text (error 131047 / re-engagement).
#   * To START a cold conversation you MUST send an APPROVED TEMPLATE message
#     (config: template / template_language / template_params). Templates are
#     created and approved once in Meta WhatsApp Manager.
# ─────────────────────────────────────────────────────────────────────────────


def _is_placeholder(value: str) -> bool:
    """Treat repo placeholders like '<WHATSAPP_ACCESS_TOKEN goes here>' as empty."""
    v = str(value or '').strip()
    return v.startswith('<') and v.endswith('>')


def _clean(value: str) -> str:
    v = str(value or '').strip()
    return '' if _is_placeholder(v) else v


def _normalize_msisdn(number: str) -> str:
    """Meta Cloud API wants the recipient as country-code + number, digits only
    (no '+', spaces, dashes or parentheses).
    '+52 1 (555) 555-5555' -> '5215555555555'."""
    return ''.join(ch for ch in str(number or '') if ch.isdigit())


def _extract_wamid(resp_body: str) -> str:
    """Pull the outbound message id (wamid...) out of a Graph API success body."""
    try:
        data = json.loads(resp_body)
        msgs = data.get("messages") or []
        if isinstance(msgs, list) and msgs:
            return str(msgs[0].get("id") or "")
    except Exception:
        pass
    return ""


class WhatsAppCloudClient:
    """Professional WhatsApp sender via Meta's official Graph (Cloud) API.

    Stdlib-only (urllib). Supports a free-form TEXT message (24h window) AND an
    approved TEMPLATE message (cold-start), with rich error surfacing so a failed
    token / un-opted-in recipient / un-approved template is obvious in the log.
    """

    DEFAULT_API_VERSION = "v20.0"
    MAX_BODY_LEN = 4000  # WhatsApp text-body hard limit is 4096; leave headroom

    def __init__(self, phone_number_id: str, access_token: str,
                 graph_base: str = "https://graph.facebook.com", api_version: str = ""):
        self.phone_number_id = _clean(phone_number_id)
        self.access_token = _clean(access_token)
        self.graph_base = (_clean(graph_base) or "https://graph.facebook.com").rstrip('/')
        self.api_version = _clean(api_version) or self.DEFAULT_API_VERSION

    @property
    def configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    def _post(self, payload: Dict) -> Tuple[bool, str, str]:
        if not self.configured:
            return False, "whatsapp.phone_number_id or whatsapp.access_token missing", ""
        url = f"{self.graph_base}/{self.api_version}/{self.phone_number_id}/messages"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if 200 <= resp.status < 300:
                    return True, body, _extract_wamid(body)
                return False, f"HTTP {resp.status}: {body[:400]}", ""
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = str(exc)
            return False, f"HTTPError {exc.code}: {err_body[:400]}", ""
        except Exception as exc:
            return False, f"send error: {exc}", ""

    def send_text(self, to: str, text: str) -> Tuple[bool, str, str]:
        """Send a (possibly long) free-form text by chunking. 24h-window only."""
        recipient = _normalize_msisdn(to)
        if not recipient:
            return False, "no recipient (empty WhatsApp number)", ""
        if not text:
            return True, "", ""
        chunks = [text[i:i + self.MAX_BODY_LEN]
                  for i in range(0, len(text), self.MAX_BODY_LEN)] or [text]
        ok_all, last_info, last_id = True, "", ""
        for chunk in chunks:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": chunk},
            }
            ok, info, mid = self._post(payload)
            last_info = info
            last_id = mid or last_id
            if ok:
                logging.info(f"✅ WhatsApp(Cloud) text → {recipient}: OK ({len(chunk)} chars)")
            else:
                ok_all = False
                logging.error(f"❌ WhatsApp(Cloud) text → {recipient}: FAIL — {info}")
                if "131047" in info or "re-engagement" in info.lower() or "24" in info:
                    logging.error(
                        "   ↳ This recipient is OUTSIDE the 24-hour window. A cold WhatsApp "
                        "MUST use an APPROVED TEMPLATE — set `template:` (and template_language / "
                        "template_params) instead of a plain `message:`."
                    )
                break
        return ok_all, last_info, last_id

    def send_template(self, to: str, template_name: str,
                      language: str = "en_US", body_params=None) -> Tuple[bool, str, str]:
        """Send an APPROVED template message — the official way to start a cold
        conversation (outside the 24h window)."""
        recipient = _normalize_msisdn(to)
        if not recipient:
            return False, "no recipient (empty WhatsApp number)", ""
        template = {"name": template_name, "language": {"code": (language or "en_US").strip()}}
        if body_params:
            template["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in body_params],
            }]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": template,
        }
        ok, info, mid = self._post(payload)
        if ok:
            logging.info(f"✅ WhatsApp(Cloud) template '{template_name}' → {recipient}: OK")
        else:
            logging.error(f"❌ WhatsApp(Cloud) template '{template_name}' → {recipient}: FAIL — {info}")
        return ok, info, mid


def _resolve_whatsapp_cfg(config: Dict) -> Dict:
    """Resolve Meta Cloud API credentials: config.yaml `whatsapp:` block first
    (seeded from config.json globals by the wrapped tool), then env-var fallback
    so canvas/.flw runs work too."""
    wa = config.get('whatsapp') or {}
    if not isinstance(wa, dict):
        wa = {}
    return {
        'phone_number_id': _clean(wa.get('phone_number_id') or os.environ.get('WHATSAPP_PHONE_NUMBER_ID')),
        'access_token': _clean(wa.get('access_token') or os.environ.get('WHATSAPP_ACCESS_TOKEN')),
        'graph_base': (_clean(wa.get('graph_base') or os.environ.get('WHATSAPP_GRAPH_BASE'))
                       or 'https://graph.facebook.com'),
        'api_version': (_clean(wa.get('api_version') or os.environ.get('WHATSAPP_API_VERSION'))
                        or 'v20.0'),
    }


def _coerce_param_list(value):
    """Accept template_params as a real list, or a '||'-separated string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(p) for p in value]
    text = str(value).strip()
    if not text:
        return []
    return [p.strip() for p in text.split('||') if p.strip()]


# Twilio path (the EASY professional option; provider: twilio) ──────────────────
# Twilio wraps Meta underneath but hands you 3 ready values from its dashboard
# (Account SID, Auth Token, a WhatsApp From number) — no Meta app, no token dance.
# Free 2-minute sandbox for testing. Stdlib-only (urllib + basic auth).
def _resolve_twilio_cfg(config: Dict) -> Dict:
    tw = config.get('twilio') or {}
    if not isinstance(tw, dict):
        tw = {}
    return {
        'account_sid': _clean(tw.get('account_sid') or os.environ.get('TWILIO_ACCOUNT_SID')),
        'auth_token': _clean(tw.get('auth_token') or os.environ.get('TWILIO_AUTH_TOKEN')),
        'from_number': _clean(tw.get('from_number') or os.environ.get('TWILIO_WHATSAPP_FROM')),
    }


def _twilio_wa_address(number: str) -> str:
    """Twilio wants the WhatsApp address as 'whatsapp:+<E164>'."""
    raw = str(number or '').strip()
    if raw.lower().startswith('whatsapp:'):
        return raw
    digits = _normalize_msisdn(raw)
    return f"whatsapp:+{digits}" if digits else ""


def send_twilio(account_sid: str, auth_token: str, from_number: str,
                to: str, body: str) -> Tuple[bool, str, str]:
    """Send a WhatsApp via Twilio's Messages API. Returns (ok, info, message_sid)."""
    account_sid = _clean(account_sid)
    auth_token = _clean(auth_token)
    if not account_sid or not auth_token:
        return False, "twilio.account_sid or twilio.auth_token missing", ""
    to_addr = _twilio_wa_address(to)
    from_addr = _twilio_wa_address(from_number)
    if not to_addr:
        return False, "no recipient (empty WhatsApp number)", ""
    if not from_addr:
        return False, "twilio.from_number missing (your Twilio WhatsApp sender)", ""
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    form = urllib.parse.urlencode({"From": from_addr, "To": to_addr, "Body": body or ""}).encode("utf-8")
    token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            sid = ""
            try:
                sid = str(json.loads(resp_body).get("sid") or "")
            except Exception:
                pass
            if 200 <= resp.status < 300:
                logging.info(f"✅ WhatsApp(Twilio) → {to_addr}: OK")
                return True, resp_body, sid
            return False, f"HTTP {resp.status}: {resp_body[:400]}", ""
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(exc)
        logging.error(f"❌ WhatsApp(Twilio) → {to_addr}: FAIL — HTTP {exc.code}: {err_body[:300]}")
        return False, f"HTTPError {exc.code}: {err_body[:400]}", ""
    except Exception as exc:
        logging.error(f"❌ WhatsApp(Twilio) error: {exc}")
        return False, f"send error: {exc}", ""


# Legacy TextMeBot path (optional fallback; provider: textmebot) ────────────────
def send_textmebot(phone: str, apikey: str, message: str) -> bool:
    if not phone or not apikey:
        logging.warning("⚠️ TextMeBot Phone or API Key missing. Cannot send message.")
        return False

    # Truncate message to avoid URL length limits
    if len(message) > 500:
        message = message[:500] + "..."

    encoded_msg = urllib.parse.quote(message, safe='')
    url = f"https://api.textmebot.com/send.php?recipient={phone}&apikey={apikey}&text={encoded_msg}"

    try:
        # TextMeBot API uses GET requests. Add Content-Length: 0 to avoid 411.
        headers = {"Content-Length": "0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            logging.info(f"✅ WhatsApp(TextMeBot, legacy) sent to {phone}")
            return True
        else:
            # Log full details for debugging API issues
            logging.error(f"❌ WhatsApp(TextMeBot) failed: HTTP {response.status_code}")
            logging.error(f"   URL (truncated): {url[:150]}...")
            logging.error(f"   Response: {response.text[:300]}")
            return False
    except Exception as e:
        logging.error(f"❌ WhatsApp(TextMeBot) error: {e}")
        return False


def resolve_provider(config: Dict) -> str:
    """Auto-detect the send provider with ZERO user choice. Explicit `provider:`
    always wins; otherwise we look at WHAT IS CONFIGURED and pick it:
    Meta Cloud API → Twilio → legacy TextMeBot → (else Meta, which then reports
    its missing creds clearly). This is the 'operation manner' auto-detection."""
    explicit = str(config.get('provider') or '').strip().lower()
    if explicit in ('meta', 'cloud', 'whatsapp_cloud', 'cloud_api'):
        return 'meta'
    if explicit in ('twilio',):
        return 'twilio'
    if explicit in ('textmebot', 'legacy'):
        return 'textmebot'
    wa = _resolve_whatsapp_cfg(config)
    tw = _resolve_twilio_cfg(config)
    tb = config.get('textmebot') or {}
    if wa['phone_number_id'] and wa['access_token']:
        return 'meta'
    if tw['account_sid'] and tw['auth_token']:
        return 'twilio'
    if _clean((tb or {}).get('apikey')):
        return 'textmebot'
    return 'meta'


def send_message_via_provider(config: Dict, recipient: str, message: str) -> Tuple[bool, str, str, str]:
    """Provider-agnostic send used by BOTH the one-shot path and the log-monitor
    alerts. Returns (ok, provider, info, message_id)."""
    provider = resolve_provider(config)
    if provider == 'textmebot':
        tb = config.get('textmebot') or {}
        ok = send_textmebot(_clean(recipient) or _clean(tb.get('phone')),
                            _clean(tb.get('apikey')), message)
        return ok, 'textmebot', ('ok' if ok else 'textmebot send failed'), ''

    if provider == 'twilio':
        tw = _resolve_twilio_cfg(config)
        if not (tw['account_sid'] and tw['auth_token']):
            logging.error(
                "❌ Twilio not configured. Set twilio.account_sid + twilio.auth_token + "
                "twilio.from_number (config.json globals / config.yaml), or env "
                "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM."
            )
            return False, 'twilio', 'account_sid or auth_token missing', ''
        ok, info, sid = send_twilio(tw['account_sid'], tw['auth_token'],
                                    tw['from_number'], recipient, message)
        return ok, 'twilio', info, sid

    # provider == 'meta'
    wa = _resolve_whatsapp_cfg(config)
    client = WhatsAppCloudClient(wa['phone_number_id'], wa['access_token'],
                                 wa['graph_base'], wa['api_version'])
    if not client.configured:
        logging.error(
            "❌ Meta WhatsApp Cloud API not configured. Set whatsapp.phone_number_id + "
            "whatsapp.access_token (Config → URLs / config.json globals, or the agent's "
            "config.yaml), or env WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN."
        )
        return False, 'meta', 'phone_number_id or access_token missing', ''

    template = _clean(config.get('template'))
    if template:
        lang = _clean(config.get('template_language')) or 'en_US'
        params = _coerce_param_list(config.get('template_params'))
        ok, info, mid = client.send_template(recipient, template, lang, params)
    else:
        ok, info, mid = client.send_text(recipient, message)
    return ok, 'meta', info, mid


def analyze_log_chunk(llm, config, chunk: str, source_agent: str) -> Optional[str]:
    """
    Analyze a log chunk using LLM. Returns a message if actionable, None otherwise.
    """
    if not chunk.strip():
        return None

    keywords_str = config.get('keywords', '')
    system_prompt_tmpl = config.get('system_prompt', '')

    # Hybrid approach: keyword pre-filter then LLM summarization
    keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
    chunk_lower = chunk.lower()

    hit = False
    for k in keywords:
        if k in chunk_lower:
            hit = True
            break

    if not hit and keywords:
        return None  # Skip if no keywords found (if keywords are defined)

    # Perform LLM Analysis
    try:
        prompt = system_prompt_tmpl.format(source_agent=source_agent, keywords=keywords_str)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Log Entry:\n{chunk}")
        ]
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        logging.error(f"LLM Error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Contacts book resolver (inline; mirrors agent/contacts.py)
# ─────────────────────────────────────────────────────────────
# Self-contained pool agents cannot import agent.*, so resolve a person's NAME ->
# their messaging handle here. contacts.json lives next to config.json; we find
# it via the inherited TLAMATINI_CONTACTS env (set by the Django side) and fall
# back to a walk-up search so the agent also works when launched standalone.
def _find_contacts_file():
    candidate = (os.environ.get('TLAMATINI_CONTACTS') or '').strip()
    if candidate and os.path.isfile(candidate):
        return candidate
    cur = os.path.dirname(os.path.abspath(__file__))
    seen = []
    for _ in range(10):
        seen.append(os.path.join(cur, 'contacts.json'))
        seen.append(os.path.join(cur, 'agent', 'contacts.json'))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if getattr(sys, 'frozen', False):
        seen.append(os.path.join(os.path.dirname(sys.executable), 'contacts.json'))
    for path in seen:
        if os.path.isfile(path):
            return path
    return ''


def _resolve_contact(query, channel):
    """Resolve a contact NAME/alias to its `channel` identifier ('' if not found)."""
    import json as _json
    needle = ' '.join(str(query or '').strip().lower().split())
    if not needle:
        return ''
    path = _find_contacts_file()
    if not path:
        logging.warning("contacts.json not found - cannot resolve a contact_name.")
        return ''
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            data = _json.load(handle)
    except Exception as exc:
        logging.warning(f"Could not read contacts.json ({path}): {exc}")
        return ''
    contacts = data.get('contacts', []) if isinstance(data, dict) else data
    if not isinstance(contacts, list):
        return ''

    def _names(contact):
        raw = [contact.get('name', '')] + list(contact.get('aliases') or [])
        return [' '.join(str(n).strip().lower().split()) for n in raw if str(n or '').strip()]

    for contact in contacts:                       # exact name/alias first
        if isinstance(contact, dict) and needle in _names(contact):
            return str(contact.get(channel) or '').strip()
    for contact in contacts:                       # then forgiving token match
        if not isinstance(contact, dict):
            continue
        for name in _names(contact):
            tokens = name.split()
            if needle in name or name in needle or (needle.split() and all(t in tokens for t in needle.split())):
                return str(contact.get(channel) or '').strip()
    return ''


def _resolve_recipient(config: Dict) -> Tuple[str, str]:
    """Resolve the outbound recipient for a one-shot/alert send.
    Priority: contact_name (Contacts book) → explicit `to` / whatsapp.to →
    legacy textmebot.phone. Returns (recipient, source_label)."""
    _tb = config.get('textmebot') or {}
    _wa = config.get('whatsapp') or {}
    contact_name = str(config.get('contact_name') or _tb.get('contact_name') or '').strip()
    if contact_name:
        resolved = _resolve_contact(contact_name, 'whatsapp')
        if resolved:
            logging.info(f"📇 Resolved contact '{contact_name}' → WhatsApp '{resolved}'")
            return resolved, f"contact:{contact_name}"
        logging.error(f"❌ Contact '{contact_name}' not found (or has no 'whatsapp') in contacts.json")
        return '', f"contact:{contact_name}(unresolved)"
    explicit = (str(config.get('to') or '').strip()
                or str((_wa or {}).get('to') or '').strip()
                or str(_tb.get('phone') or '').strip())
    return explicit, 'explicit'


def _emit_section(provider: str, recipient: str, msg_type: str, status: str,
                  message_id: str, body: str):
    """Atomic structured result for the log (single logging.info call)."""
    logging.info(
        f"INI_SECTION_WHATSAPPER<<<\n"
        f"provider: {provider}\n"
        f"recipient: {recipient}\n"
        f"message_type: {msg_type}\n"
        f"status: {status}\n"
        f"message_id: {message_id}\n"
        f"\n"
        f"{body}\n"
        f">>>END_SECTION_WHATSAPPER"
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    config = load_config()

    # --- One-shot direct send (Contacts-aware, Meta Cloud API default) --------
    # When a message (or a template) + a recipient are present and there is
    # NOTHING to monitor (no source_agents), send the WhatsApp NOW and exit —
    # the "send Ana a message" path. The recipient is resolved from the Contacts
    # book when a contact_name is given, else the literal `to` / textmebot.phone.
    _tb = config.get('textmebot', {}) or {}
    _oneshot_msg = str(config.get('message') or _tb.get('message') or '').strip()
    _template = _clean(config.get('template'))
    if (_oneshot_msg or _template) and not (config.get('source_agents') or []):
        recipient, rsource = _resolve_recipient(config)
        provider = resolve_provider(config)
        logging.info(f"📱 WHATSAPPER one-shot send mode (provider={provider}, recipient_src={rsource})")
        ok = False
        info = ''
        mid = ''
        if recipient:
            ok, provider, info, mid = send_message_via_provider(config, recipient, _oneshot_msg)
        else:
            info = "no recipient (give contact_name, to, or textmebot.phone)"
            logging.error(f"❌ One-shot WhatsApp needs a recipient — {info}.")
        msg_type = 'template' if _template else 'text'
        status = 'sent' if ok else 'failed'
        body = _template if _template else (_oneshot_msg or info)
        _emit_section(provider, _normalize_msisdn(recipient) if provider == 'meta' else recipient,
                      msg_type, status, mid, body if ok else (info or body))
        time.sleep(0.4)
        remove_pid_file()
        logging.info(f"🏁 Whatsapper one-shot finished (sent={ok}, provider={provider}).")
        return

    source_agents = config.get('source_agents', [])
    if isinstance(source_agents, str):
        source_agents = [s.strip() for s in source_agents.split(',') if s.strip()]

    if not source_agents:
        logging.warning("⚠️ No source agents configured to monitor.")

    logging.info("📱 WHATSAPPER AGENT STARTED (Dark Green)")
    logging.info(f"📁 Pool path: {get_pool_path()}")
    logging.info(f"📁 Template path: {get_template_agents_path()}")
    logging.info(f"👀 Monitoring: {source_agents}")
    logging.info(f"🔍 Keywords: {config.get('keywords', '')}")
    logging.info(f"📨 Provider: {resolve_provider(config)}")
    logging.info(f"🤖 Model: {config['llm']['model']}")
    logging.info(f"⏱️ Poll interval: {config.get('poll_interval', 5)}s")

    # Log resolved paths for debugging
    for source in source_agents:
        log_path = get_agent_log_path(source)
        logging.info(f"   📄 {source} log: {log_path} (exists: {os.path.exists(log_path)})")

    logging.info("=" * 60)

    # State
    offsets = load_reanim_offsets()
    poll_interval = config.get('poll_interval', 1)

    # Initialize offsets for new sources (start at 0 to catch everything)
    for agent in source_agents:
        if agent not in offsets:
            offsets[agent] = 0

    # Initialize LLM once (shared across all source agents)
    try:
        llm = ChatOllama(
            base_url=config['llm']['base_url'],
            model=config['llm']['model'],
            temperature=config['llm']['temperature']
        )
    except Exception as e:
        logging.error(f"❌ Failed to init LLM: {e}")
        remove_pid_file()
        return

    # Recipient for monitor-mode alerts (resolved once at startup).
    alert_recipient, _ = _resolve_recipient(config)

    # File size tracking for smart polling per source agent
    file_sizes: Dict[str, int] = {}
    for agent in source_agents:
        lp = get_agent_log_path(agent)
        file_sizes[lp] = os.path.getsize(lp) if os.path.exists(lp) else -1

    try:
        # Single-threaded main loop: iterate over all sources each cycle
        while True:
            for agent_name in source_agents:
                try:
                    log_path = get_agent_log_path(agent_name)
                    current_offset = offsets.get(agent_name, 0)

                    # Smart polling: handles missing files, truncation, appearing files
                    new_content, new_offset = check_log_for_new_content(
                        log_path, current_offset, file_sizes
                    )
                    offsets[agent_name] = new_offset

                    # Analyze if there's new content
                    if new_content:
                        alert_msg = analyze_log_chunk(llm, config, new_content, agent_name)

                        if alert_msg:
                            logging.info(f"🚨 Keywords detected in {agent_name}!")
                            send_message_via_provider(config, alert_recipient, alert_msg)

                except Exception as e:
                    logging.error(f"Error monitoring {agent_name}: {e}")

            # Save offsets after each full cycle
            save_reanim_offsets(offsets)

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logging.info("Stopping Whatsapper agent...")
    except Exception as e:
        logging.error(f"Critical Error: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
        logging.info("Whatsapper Stopped.")

if __name__ == "__main__":
    main()
