# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import os
import re
import sys
from pathlib import Path


_CARDINAL_RE = re.compile(r"^(?P<base>.+)_(?P<cardinal>\d+)$")


def is_frozen_mode() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_agent_app_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def get_app_base_dir() -> Path:
    if is_frozen_mode():
        return Path(os.path.dirname(sys.executable)).resolve()
    return get_agent_app_dir()


def get_agents_root() -> Path:
    if is_frozen_mode():
        return get_app_base_dir() / "agents"
    return get_agent_app_dir() / "agents"


def get_pools_root() -> Path:
    return get_agents_root() / "pools"


def get_session_id_from_request(request) -> str:
    session_id = ""
    try:
        session_id = request.headers.get("X-Agent-Session-ID", "") or ""
    except Exception:
        session_id = ""
    session_id = os.path.basename(str(session_id).strip())
    return session_id or "default"


def get_session_pool_path(request=None, session_id: str | None = None) -> Path:
    resolved_session = session_id or (get_session_id_from_request(request) if request is not None else "default")
    return get_pools_root() / os.path.basename(resolved_session)


def safe_agent_token(value: str) -> bool:
    if not value:
        return False
    return not any(part in value for part in ("..", "/", "\\"))


def normalize_agent_type(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    text = re.sub(r"\s*\(\d+\)\s*$", "", text)
    text = text.replace("-", "_").replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    return text


def parse_canvas_agent_name(agent_name: str) -> tuple[str, str]:
    parts = [part for part in (agent_name or "").split("-") if part]
    cardinal = None
    if parts and parts[-1].isdigit():
        cardinal = parts.pop()
    base_folder_name = normalize_agent_type("_".join(parts))
    pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

    if not safe_agent_token(base_folder_name) or not safe_agent_token(pool_folder_name):
        raise ValueError("Invalid agent name")

    return base_folder_name, pool_folder_name


def pool_name_to_agent_type(folder_name: str) -> str:
    name = normalize_agent_type(folder_name)
    match = _CARDINAL_RE.match(name)
    if match:
        return match.group("base")
    return name


def pool_name_from_canvas_id(canvas_id: str) -> str:
    return parse_canvas_agent_name(canvas_id)[1]


def display_name_from_agent_type(agent_type: str) -> str:
    normalized = normalize_agent_type(agent_type)
    overrides = {
        "and": "AND",
        "or": "OR",
        "acpxer": "ACPXer",
        "emailer": "Emailer",
        "recmailer": "RecMailer",
        "ssher": "SSHer",
        "scper": "SCPer",
        "sqler": "SQLer",
        "pser": "PSer",
        # "Apirer" (not "APIrer"): agents.md AND chat_agent_registry.display_name
        # both say "Apirer", and that is the label already on the sidebar. This map
        # now drives the sidebar label directly (apps.py), so it must not churn it.
        "apirer": "Apirer",
        "pythonxer": "Pythonxer",
        "teletlamatini": "TeleTlamatini",
        "telegrammer": "Telegrammer",
        "whatsapper": "Whatsapper",
        "zavuerer": "Zavuerer",
        "j_decompiler": "J-Decompiler",
        "kyber_keygen": "Kyber-KeyGen",
        "kyber_cipher": "Kyber-Cipher",
        "kyber_decipher": "Kyber-DeCipher",
        "stm32er": "STM32er",
        "esp32er": "ESP32er",
        "esphomer": "ESPHomer",
        "arduiner": "Arduiner",
        # Without this override .title() renders "Pdfer", which violates the naming
        # convention: the display name is EXACTLY what the DB agentDescription says,
        # and that is "PDFer" (P-D-F-er), never "Pdfer" / "PDFEr" / "PDFER".
        "pdfer": "PDFer",
        # --- case-only fixes: .title() lower-cases the second capital ---
        "audioplayer": "AudioPlayer",
        "videoplayer": "VideoPlayer",
        "flowcreator": "FlowCreator",
        "flowhypervisor": "FlowHypervisor",
        "flowbacker": "FlowBacker",
        "mcp_doctor": "MCP Doctor",
        # --- hyphen fixes: acp-canvas-core.js compares the DISPLAY name lowercased
        # WITHOUT collapsing spaces, and for these it only ever tests the HYPHENATED
        # literal ('video-analyzer' / 'de-compresser'). A spaced "Video Analyzer"
        # therefore matches NOTHING and the connection is silently never persisted.
        "video_analyzer": "Video-Analyzer",
        "de_compresser": "De-Compresser",
        # These five ALSO carry hyphen-only canvas handlers. Fixed together
        # with chat_agent_registry.display_name on 2026-07-26 so the DB row,
        # the canvas handler and the agent_<display>_status enable gate all
        # agree; changing only one side would silently fail-open the gate.
        "file_creator": "File-Creator",
        "file_extractor": "File-Extractor",
        "file_interpreter": "File-Interpreter",
        "image_interpreter": "Image-Interpreter",
        "monitor_log": "Monitor-Log",
    }
    if normalized in overrides:
        return overrides[normalized]
    return normalized.replace("_", " ").title()
