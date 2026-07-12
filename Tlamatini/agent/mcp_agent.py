# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# MCP Agent (mcp_agent.py)
import json
import logging
import re
from typing import Dict, Any, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .acpx import ACPX_TOOL_NAMES, filter_acpx_tools
from .capability_registry import (
    _normalize_text,
    _score_capability,
    _tokenize,
    build_tool_capabilities,
)
from .chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
from .config_loader import get_int_config_value, load_config as _shared_load_config
from .exec_permission import get_broker
from .global_execution_planner import (
    selected_tool_names_from_plan,
    summarize_global_execution_plan,
)
from .global_state import global_state, scoped_request_state
from .orphan_reaper import reap_orphans
# Import the MCP tools defined in the same package
from .tools import get_mcp_tools
from .llm_timing import llm_timing_callbacks
from .self_healing import ModelStepUnrecoverable, SelfHealingInvoker, recovery_preamble


# Tool names whose invocation is likely to spawn an external console
# child (and therefore may leave a conhost.exe orphan if the child
# misbehaves on exit). Running the Tier-1 reaper after EVERY tool call
# would be wasteful — most tools are pure Python with no subprocess
# fan-out. The reaper is cheap (low double-digit ms with a few hundred
# processes on the box), but cheap-times-frequent still matters.
_PROCESS_SPAWNING_TOOL_NAMES: frozenset = frozenset({
    "execute_command",
    "execute_file",
    "execute_netstat",
    "unzip_file",
    "decompile_java",
    "googler",  # Playwright spawns a Chromium subtree
    "agent_starter",
    "agent_stopper",
    "agent_parametrizer",
})


def _is_external_mcp_tool_name(name: str) -> bool:
    try:
        from .external_mcp_manager import is_external_mcp_tool_name as _is_external
        return bool(_is_external(name))
    except Exception:
        return str(name or "").startswith("ext__") or str(name or "") in {
            "external_mcp_status",
            "external_mcp_reconnect",
            "external_mcp_doctor",
            "external_mcp_list_tools",
            "external_mcp_call",
            "external_mcp_import",
            "external_mcp_set_active",
            "external_mcp_wait",
        }


# ── Tool-name → ACP agent display name mapping ─────────────────────────
# Used to translate multi-turn tool calls into .flw workflow nodes.
# Wrapped chat-agent tools are resolved dynamically from the registry;
# this dict covers the non-wrapped tools.
_TOOL_TO_AGENT_DISPLAY_NAME: Dict[str, str] = {
    "execute_command": "Executer",
    "execute_file": "Pythonxer",
    "execute_netstat": "Monitor Netstat",
    "googler": "Googler",
    "agent_parametrizer": "Parametrizer",
    "agent_starter": "Starter",
    "agent_stopper": "Stopper",
    "launch_view_image": "Image Interpreter",
    "opus_analyze_image": "Image Interpreter",
    "qwen_analyze_image": "Image Interpreter",
    "unzip_file": "Executer",
    "decompile_java": "J-Decompiler",
}

# Tools that are management/monitoring only — never produce .flw nodes.
_MANAGEMENT_TOOLS: set[str] = {
    "agent_stat_getter",
    "get_current_time",
    "chat_agent_run_list",
    "chat_agent_run_status",
    "chat_agent_run_log",
    "chat_agent_run_stop",
    # Inspection / polling helpers — same role as the run_* siblings above.
    # window_present is a <100 ms yes/no probe of the desktop window list;
    # chat_agent_run_wait is a single-call replacement for a polling loop.
    # Neither is a canvas agent, so they must not surface in tool_calls_log
    # entries that drive Create Flow / agent-registry validation.
    "chat_agent_run_wait",
    "window_present",
}


# Outbound "I'm done" notification tools — Telegram / email / WhatsApp / the
# in-browser Notifier popup. Used by the completion-notification ("notification
# debt") guard in ``MultiTurnToolAgentExecutor``: when the original request
# asked to be notified ON COMPLETION and the model tries to finish WITHOUT
# having called one of these, the executor injects ONE nudge to actually send
# it — instead of letting the model confabulate a "tool backend unavailable /
# re-enable Multi-Turn" excuse (the FlowPills bug, 2026-06-24).
_NOTIFICATION_TOOLS: frozenset = frozenset({
    "chat_agent_telegrammer",
    "chat_agent_send_email",
    "chat_agent_whatsapper",
    "chat_agent_notifier",
})

# Completion cue: "when/once/after/as soon as/upon ... finish/done/complete/...".
_COMPLETION_CUE_RE = re.compile(
    r"\b(when|once|after|as soon as|upon|by the time)\b[^.?!]{0,80}?\b"
    r"(finish|finishes|finished|done|complete|completes|completed|completion|"
    r"end|ends|ended|ready|over|wrap(?:s|ped)? up)\b",
    re.IGNORECASE,
)
# Standalone completion phrasings the windowed cue above can miss.
_COMPLETION_PHRASE_RE = re.compile(
    r"\b(at the end|on completion|upon completion|when you(?:'?re| are)? done|"
    r"when you finish|after finishing|once finished|after it'?s? done)\b",
    re.IGNORECASE,
)
# Notification channel cue: an explicit channel word, OR a "send/notify/tell ME"
# style verb directed at the user.
_NOTIFY_CHANNEL_RE = re.compile(
    r"\b(telegram|whats\s?app|e-?mail|mail|notif\w*|sms|slack|discord)\b",
    re.IGNORECASE,
)
_NOTIFY_VERB_RE = re.compile(
    r"\b(send|shoot|text|message|ping|notify|alert|tell|let|drop|email|e-?mail)\b"
    r"[^.?!]{0,30}?\b(me|us|angela|him|her|them)\b",
    re.IGNORECASE,
)


def _detect_completion_notification_request(text: str) -> bool:
    """Heuristic: did the user ask to be NOTIFIED ON COMPLETION of this task?

    Returns True only when the request contains BOTH a completion cue ("when you
    finish", "once done", "upon completion", "at the end") AND an outbound
    notification cue (a channel word like telegram/email/whatsapp/notification,
    or a "send/notify/tell ME" verb directed at the user). Deliberately
    conservative: a false positive only costs ONE harmless nudge, while a false
    negative simply preserves the legacy behavior.
    """
    if not text:
        return False
    low = str(text)
    has_completion = bool(_COMPLETION_CUE_RE.search(low) or _COMPLETION_PHRASE_RE.search(low))
    if not has_completion:
        return False
    has_channel = bool(_NOTIFY_CHANNEL_RE.search(low) or _NOTIFY_VERB_RE.search(low))
    return has_channel


# Curated Exec-report map: ``tool_name`` -> ``(agent_key, agent_display)``.
# ``agent_key`` is the lowercase, separator-free token used to scope the
# per-agent CSS class (``.exec-report-<agent_key>`` /
# ``.exec-report-caption-<agent_key>``) and SHOULD match a canvas-item CSS class
# in ``agentic_control_panel.css`` so the appended table inherits the agent's
# canvas gradient. ``agent_display`` is the human-facing caption. Direct @tool
# calls and wrapped chat-agent launches that correspond to the SAME agent share
# an ``agent_key`` on purpose — their rows merge into a single
# "List of <Agent> Operations" table.
#
# IMPORTANT (2026-06-07 completeness contract): this map is NO LONGER the gate
# for *whether* an agent is captured. The Exec report must show EVERY agent that
# actually runs during a Multi-Turn request — observational/output agents
# (Talker, Shoter, Camcorder, Recorder, AudioPlayer, VideoPlayer, ...), read-only
# LLM agents (Crawler, Prompter, Summarizer, File/Image interpreters, ...) and
# any NEWLY-CREATED agent included. That auto-capture is implemented by
# ``_resolve_exec_report_spec`` below, which falls back to the wrapped chat-agent
# registry for any ``chat_agent_*`` not listed here (only the management/polling
# helpers in ``_MANAGEMENT_TOOLS`` and direct read-only @tools like ``googler``
# are excluded). Entries here are therefore an OPTIONAL refinement — add one only
# to merge a shared agent_key (a direct @tool + its wrapped launch), fix the
# display casing, or pin a CSS-matched caption gradient. A new Multi-Turn agent
# is captured even with NO entry here.
_EXEC_REPORT_TOOLS: Dict[str, Tuple[str, str]] = {
    # direct @tool calls
    "execute_command":           ("executer",       "Executer"),
    "execute_file":              ("pythonxer",      "Pythonxer"),
    "unzip_file":                ("unzip",          "Unzip"),
    "decompile_java":            ("jdecompiler",    "J-Decompiler"),
    # wrapped chat-agent launches (see chat_agent_registry.py)
    "chat_agent_executer":       ("executer",       "Executer"),
    "chat_agent_pythonxer":      ("pythonxer",      "Pythonxer"),
    "chat_agent_dockerer":       ("dockerer",       "Dockerer"),
    "chat_agent_kuberneter":     ("kuberneter",     "Kuberneter"),
    "chat_agent_ssher":          ("ssher",          "SSHer"),
    "chat_agent_scper":          ("scper",          "SCPer"),
    "chat_agent_pser":           ("pser",           "PSer"),
    "chat_agent_sqler":          ("sqler",          "SQLer"),
    "chat_agent_mongoxer":       ("mongoxer",       "Mongoxer"),
    "chat_agent_jenkinser":      ("jenkinser",      "Jenkinser"),
    "chat_agent_gitter":         ("gitter",         "Gitter"),
    "chat_agent_instant_messaging_doctor": ("instantmessagingdoctor", "Instant Messaging Doctor"),
    "chat_agent_file_creator":   ("filecreator",    "File Creator"),
    "chat_agent_move_file":      ("mover",          "Mover"),
    "chat_agent_deleter":        ("deleter",        "Deleter"),
    "chat_agent_apirer":         ("apirer",         "Apirer"),
    # Unrealer mutates the Unreal Editor's state (spawns/deletes actors,
    # creates and compiles Blueprints, adds UMG widgets, wires input
    # mappings). Read-only commands like ``get_actors_in_level`` also
    # share this agent_key on purpose so a mixed read-and-mutate flow
    # renders as one cohesive "List of Unrealer Operations" table.
    "chat_agent_unrealer":       ("unrealer",       "Unrealer"),
    # Blenderer mutates the Blender scene (creates/deletes objects, assigns
    # materials, renders, runs arbitrary editor Python) via the official
    # Blender MCP add-on socket. Read verbs (scene_info / get_objects /
    # blendfile_summary) share this agent_key so a mixed read-and-mutate flow
    # renders as one cohesive "List of Blenderer Operations" table.
    "chat_agent_blenderer":      ("blenderer",      "Blenderer"),
    "chat_agent_globber":        ("globber",        "Globber"),
    "chat_agent_grepper":        ("grepper",        "Grepper"),
    "chat_agent_editor":         ("editor",         "Editor"),
    # Video-Analyzer is observational (it WATCHES a recorded video and returns a
    # verdict — it mutates no state), but EVERY Multi-Turn agent must appear in the
    # Exec Report, so it gets its own row + caption gradient (agent_key videoanalyzer).
    "chat_agent_video_analyzer": ("videoanalyzer",  "Video-Analyzer"),
    # Playwrighter drives a real browser through a scripted flow: it submits
    # forms, clicks, logs into sites, downloads files, and otherwise changes
    # remote/web state. Read-only steps (extract_text / screenshot) share the
    # same ``playwrighter`` agent_key on purpose so a mixed read-and-act flow
    # renders as one "List of Playwrighter Operations" table.
    "chat_agent_playwrighter":   ("playwrighter",   "Playwrighter"),
    "chat_agent_send_email":     ("emailer",        "Emailer"),
    "chat_agent_telegrammer":    ("telegrammer",    "Telegrammer"),
    "chat_agent_whatsapper":     ("whatsapper",     "Whatsapper"),
    "chat_agent_notifier":       ("notifier",       "Notifier"),
    "chat_agent_j_decompiler":   ("jdecompiler",    "J-Decompiler"),
    # De-Compresser is state-changing: it CREATES files/directories on disk
    # (decompression output, compression archive). The single agent_key
    # ``decompresser`` merges both the wrapped chat-agent launch and any
    # future direct @tool call into one "List of De-Compresser Operations"
    # table in the Exec Report.
    "chat_agent_de_compresser":  ("decompresser",   "De-Compresser"),
    "chat_agent_kyber_keygen":   ("kyberkeygen",    "Kyber Keygen"),
    "chat_agent_kyber_cipher":   ("kybercipher",    "Kyber Cipher"),
    "chat_agent_kyber_deciph":   ("kyberdecipher",  "Kyber Deciph"),
    # Keyboarder is state-changing: every keystroke affects whichever
    # window currently has focus (typing into Notepad, firing hotkeys,
    # etc.). Shoter remains read-only (it only observes the screen) so
    # it stays out of the report on purpose.
    "chat_agent_keyboarder":     ("keyboarder",     "Keyboarder"),
    # Mouser is state-changing: it moves the system mouse pointer and
    # may issue a click — both observable side-effects on the desktop
    # (focus changes, foreground-window switch, button events fired at
    # whatever window happens to be at the target coordinates).
    "chat_agent_mouser":         ("mouser",         "Mouser"),
    # Windower is state-changing: it moves / resizes / minimizes / maximizes /
    # restores / closes / pins application windows (focus-only and the read-only
    # ``list`` action share the same ``windower`` agent_key on purpose so a mixed
    # query-and-manage flow renders as one "List of Windower Operations" table).
    "chat_agent_windower":       ("windower",       "Windower"),
    # Kalier is state-changing: it drives Kali offensive-security tooling
    # (nmap / gobuster / nikto / sqlmap / metasploit / hydra / john / wpscan /
    # enum4linux) and arbitrary shell commands on a Kali box via the
    # MCP-Kali-Server API. The read-only ``health`` probe shares the same
    # ``kalier`` agent_key so a mixed flow renders as one "List of Kalier
    # Operations" table.
    "chat_agent_kalier":         ("kalier",         "Kalier"),
    # Zavuerer is state-changing: it SENDS messages (SMS / WhatsApp / Telegram /
    # Email / Voice) through the Zavu unified-messaging REST API. The read-only
    # ``health`` probe shares the same ``zavuerer`` agent_key so a mixed flow renders
    # as one "List of Zavuerer Operations" table.
    "chat_agent_zavuerer":         ("zavuerer",         "Zavuerer"),
    # STM32er is state-changing: it drives the STM32 Template Project MCP server
    # to scaffold / write / build / flash / erase / reset firmware and to
    # write_memory on a running MCU. Read-only actions (get_config / read_source /
    # list_sources / read_memory / serial reads) share the ``stm32er`` agent_key
    # so a mixed firmware flow renders as one "List of STM32er Operations" table.
    "chat_agent_stm32er":        ("stm32er",        "STM32er"),
    # ESP32er is state-changing: it drives PlatformIO Core's `pio` CLI to scaffold /
    # write / build / upload (flash) ESP32 firmware. Read-only actions (boards /
    # read_source / list_sources / device_list / monitor) share the ``esp32er``
    # agent_key so a mixed firmware flow renders as one "List of ESP32er Operations"
    # table.
    "chat_agent_esp32er":        ("esp32er",        "ESP32er"),
    # ESPHomer is state-changing: it drives the `esphome` CLI to author / validate /
    # compile / upload (flash) ESPHome smart-home device firmware (YAML, no C++).
    # Read-only actions (version / read_config / config / list_artifacts / logs) share
    # the ``esphomer`` agent_key so a mixed device flow renders as one "List of ESPHomer
    # Operations" table.
    "chat_agent_esphomer":       ("esphomer",       "ESPHomer"),
    # Arduiner is state-changing: it drives the Arduino CLI (`arduino-cli`) to scaffold /
    # write / build / upload (flash) Arduino firmware. Read-only actions (boards /
    # device_list / read_source / list_sources / core_list / lib_list / monitor) share
    # the ``arduiner`` agent_key so a mixed firmware flow renders as one "List of
    # Arduiner Operations" table.
    "chat_agent_arduiner":       ("arduiner",       "Arduiner"),
    # ACPX child-process launchers (spawn / send-turn / kill an external
    # coding-agent CLI such as claude / cursor / codex / qwen / etc.).
    # All three share the ``acpx`` agent_key on purpose so spawn + every
    # follow-up send + the eventual kill merge into a single ACPx table
    # in execution order.
    "acp_spawn":                 ("acpx",           "ACPx"),
    "acp_send":                  ("acpx",           "ACPx"),
    "acp_send_and_wait":         ("acpx",           "ACPx"),
    "acp_kill":                  ("acpx",           "ACPx"),
    # acp_relay is state-changing on the destination session: it sends a
    # turn there. Group it under the same ``acpx`` key so a relay run
    # appears in execution order alongside spawn/send/kill.
    "acp_relay":                 ("acpx",           "ACPx"),
    # Markdown-driven Skill invocation through the SkillHarness. Treated
    # as state-changing because a skill can run @tool commands, write
    # files, hit external APIs, or delegate to ACPX itself.
    "invoke_skill":              ("skill",          "Skill"),
}


def _resolve_exec_report_spec(tool_name: str) -> Tuple[str, str] | None:
    """Resolve the ``(agent_key, agent_display)`` for an Exec-report row, or None.

    MANDATORY COMPLETENESS CONTRACT (2026-06-07): the Exec report must show
    EVERY agent that actually runs during a Multi-Turn request — including
    observational/output agents (Talker, Shoter, Camcorder, Recorder,
    AudioPlayer, VideoPlayer, ...), read-only LLM agents (Crawler, Prompter,
    Summarizer, File/Image interpreters, ...), AND any newly-created agent —
    automatically, with no per-agent wiring.

    Resolution order:
      1. The curated ``_EXEC_REPORT_TOOLS`` map wins (shared agent_keys that
         merge a direct @tool with its wrapped launch, nicer display casing, a
         CSS-matched caption gradient).
      2. Otherwise ANY wrapped ``chat_agent_*`` tool that is NOT a
         management/polling helper is captured generically: ``agent_key`` is the
         registry spec key with separators stripped (to match the canvas-item
         CSS convention) and ``agent_display`` is the spec's display name. This
         is what makes a brand-new agent appear in the report the instant it is
         wired as a Multi-Turn tool.
      3. Everything else — the management/polling helpers in
         ``_MANAGEMENT_TOOLS`` and direct read-only @tools such as ``googler`` —
         returns None (never captured).
    """
    spec = _EXEC_REPORT_TOOLS.get(tool_name)
    if spec is not None:
        return spec
    if tool_name.startswith("chat_agent_") and tool_name not in _MANAGEMENT_TOOLS:
        wrapped = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get(tool_name)
        if wrapped is not None:
            agent_key = wrapped.key.replace("_", "").replace("-", "")
            return (agent_key, wrapped.display_name)
    return None


# ---------------------------------------------------------------------------
# Ask-Execs allowlist
# ---------------------------------------------------------------------------
# Ask Execs prompts the user (Proceed / Deny) ONLY before the tools listed
# here. This is a tight ALLOWLIST — every other tool runs without a prompt.
# The set is exactly the agents that *execute a command / script / .bat /
# instruction, locally or remotely* (Tier 1 + Tier 2). Any tool not in this
# set — including read-only tools, file/notify/messaging agents, the Kyber
# crypto agents, desktop-input agents (Mouser / Keyboarder / Windower), Scper
# (file transfer), Apirer, Playwrighter, and ``invoke_skill`` — is NOT gated.
#
# Each tool maps back to a Tier-1/Tier-2 execution agent. Both the direct
# @tool name and the wrapped ``chat_agent_*`` launcher are listed where both
# exist, so the prompt fires regardless of which surface the LLM uses.
_ASK_EXECS_REQUIRED_TOOLS: frozenset = frozenset({
    # ----- Tier 1: general-purpose arbitrary command / script execution -----
    "execute_command",          # Executer  (local shell / .bat / .sh)
    "chat_agent_executer",      # Executer
    "execute_file",             # Pythonxer (local script file)
    "chat_agent_pythonxer",     # Pythonxer
    "chat_agent_ssher",         # SSHer     (remote shell / script over SSH)
    "chat_agent_kalier",        # Kalier    (arbitrary shell on a Kali box, local/remote)
    # ----- Tier 2: domain / tool-specific command runners -------------------
    "chat_agent_pser",          # PSer       (ps / tasklist system command)
    "chat_agent_dockerer",      # Dockerer   (docker CLI; local or remote daemon)
    "chat_agent_kuberneter",    # Kuberneter (kubectl; local or remote cluster)
    "chat_agent_jenkinser",     # Jenkinser  (triggers remote CI builds)
    "chat_agent_gitter",        # Gitter     (git CLI)
    "chat_agent_sqler",         # SQLer      (executes SQL; local or remote DB)
    "chat_agent_mongoxer",      # Mongoxer   (MongoDB ops; local or remote DB)
    "decompile_java",           # J-Decompiler (runs jd-cli)
    "chat_agent_j_decompiler",  # J-Decompiler
})


def _tool_name_to_agent_display(tool_name: str) -> str | None:
    """Map a unified-agent tool name to the ACP agent display name, or None if skipped."""
    if tool_name in _MANAGEMENT_TOOLS:
        return None
    if tool_name in _TOOL_TO_AGENT_DISPLAY_NAME:
        return _TOOL_TO_AGENT_DISPLAY_NAME[tool_name]
    spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get(tool_name)
    if spec:
        return spec.display_name
    return None


def _classify_tool_kind(tool_name: str) -> str:
    """Classify a tool name into the human-facing kind shown in the Ask-Execs
    permission dialog ("what Tlamatini Tool/MCP/Agent is going to execute")."""
    if tool_name == "invoke_skill":
        return "Skill"
    if tool_name.startswith("acp_"):
        return "MCP / ACPX agent"
    if tool_name.startswith("chat_agent_"):
        return "Agent"
    return "Tool"


# PowerShell-flavoured tools whose execution shell is unambiguous.
_POWERSHELL_TOOLS: frozenset = frozenset({"chat_agent_pser"})
# Tools that run through the OS shell (the program text is a shell command).
_OS_SHELL_TOOLS: frozenset = frozenset({
    "execute_command", "chat_agent_executer", "unzip_file", "decompile_java",
    "execute_netstat", "googler",
})
# Tools that run through a Python interpreter rather than a shell.
_PYTHON_TOOLS: frozenset = frozenset({"execute_file", "chat_agent_pythonxer"})


def _infer_execution_shell(tool_name: str, tool_input: Any) -> str:
    """Best-effort description of the SHELL the tool will execute through,
    shown read-only in the Ask-Execs dialog. Informational only — it never
    changes how the tool runs."""
    import platform

    is_windows = platform.system() == "Windows"
    os_shell = "cmd.exe / PowerShell (Windows)" if is_windows else "/bin/sh (POSIX)"
    name = tool_name or ""

    if name in _POWERSHELL_TOOLS:
        return "PowerShell"
    if name in _PYTHON_TOOLS:
        return "Python interpreter"
    if name in _OS_SHELL_TOOLS:
        return os_shell
    if name == "chat_agent_ssher":
        host = tool_input.get("host") if isinstance(tool_input, dict) else None
        return f"Remote SSH shell{(' @ ' + str(host)) if host else ''}"
    if name == "chat_agent_dockerer":
        return f"Docker CLI via {os_shell}"
    if name == "chat_agent_kuberneter":
        return f"kubectl CLI via {os_shell}"
    if name == "chat_agent_kalier":
        return "Kali Linux (MCP-Kali-Server)"
    if name == "chat_agent_zavuerer":
        return "Zavu unified-messaging API (HTTPS)"
    if name == "chat_agent_stm32er":
        return "STM32 Template Project MCP"
    if name == "chat_agent_esp32er":
        return "PlatformIO Core (pio CLI)"
    if name == "chat_agent_esphomer":
        return "ESPHome (esphome CLI)"
    if name == "chat_agent_arduiner":
        return "Arduino CLI (arduino-cli)"
    if name.startswith("acp_"):
        return "External coding-agent CLI"
    if name == "invoke_skill":
        return "Tlamatini SkillHarness"
    return os_shell


logger = logging.getLogger(__name__)

# Try to import ChatOllama (newer location) – fall back to the community package
try:
    from langchain_ollama import ChatOllama
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError:  # pragma: no cover
        ChatOllama = None  # type: ignore


def _load_config() -> Dict[str, Any]:
    """Load ``config.json`` using the shared frozen/source-aware loader."""
    return _shared_load_config()


def _ensure_chat_tool_model(llm):
    """Return a chat model that supports ``bind_tools`` when possible."""
    from langchain_ollama.llms import OllamaLLM

    if isinstance(llm, OllamaLLM) and ChatOllama is not None:
        config = _load_config()

        # Resolve model, endpoint and temperature from config → llm → defaults
        model = (
            config.get("unified_agent_model")
            or getattr(llm, "model", None)
            or "llama3.2:latest"
        )
        base_url = (
            config.get("unified_agent_base_url")
            or getattr(llm, "base_url", None)
            or "http://localhost:11434"
        )
        temperature = (
            config.get("unified_agent_temperature")
            if config.get("unified_agent_temperature") is not None
            else (getattr(llm, "temperature", None) or 0.0)
        )

        # Logging source of each parameter
        if config.get("unified_agent_model"):
            print(f"--- Using unified_agent_model from config.json: {model} ---")
        elif getattr(llm, "model", None):
            print(f"--- Using model from LLM instance: {model} ---")
        else:
            print(f"--- Using default model: {model} ---")

        # Authentication / extra client kwargs
        client_kwargs: Dict[str, Any] = {}
        token = config.get("ollama_token", "")
        private_client_kwargs = getattr(llm, "_client_kwargs", None)
        public_client_kwargs = getattr(llm, "client_kwargs", None)
        if token:
            client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
        elif private_client_kwargs:
            client_kwargs = private_client_kwargs or {}
        elif public_client_kwargs:
            client_kwargs = public_client_kwargs or {}

        # Bound the Ollama call so a transient cloud/serving stall fails fast
        # (<=120s) instead of hanging the whole turn forever. setdefault never
        # overrides an explicit/inherited timeout.
        client_kwargs.setdefault("timeout", 120.0)

        # Build kwargs accepted by ChatOllama
        chat_kwargs: Dict[str, Any] = {
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "callbacks": llm_timing_callbacks(),
        }

        # Propagate optional Ollama parameters if they exist
        for attr in ["top_k", "top_p", "repeat_penalty", "num_ctx", "num_predict"]:
            if hasattr(llm, attr):
                val = getattr(llm, attr)
                if val is not None:
                    chat_kwargs[attr] = val

        # #2 STABLE-PROMPT REUSE: pin the model in memory (keep_alive) so the
        # byte-stable system-prompt prefix — the executor caches one prompt per
        # tool-set, with no per-turn variance — keeps its KV cache between turns.
        # Ollama then reuses the common prefix instead of re-prefilling the whole
        # (now-trimmed) tool block every turn. Honors the OLLAMA_KEEP_ALIVE
        # contract from gpu_perf.py (default -1 = never unload). No-op for :cloud
        # models (they don't live in local VRAM).
        import os as _os
        _keep_alive_raw = _os.environ.get("OLLAMA_KEEP_ALIVE", "-1").strip()
        try:
            chat_kwargs["keep_alive"] = int(_keep_alive_raw)
        except (TypeError, ValueError):
            chat_kwargs["keep_alive"] = _keep_alive_raw or -1

        # Pass auth headers if supported
        if client_kwargs:
            chat_kwargs["client_kwargs"] = client_kwargs

        # Instantiate ChatOllama – fall back to a minimal config on TypeError
        try:
            getted_llm = ChatOllama(**chat_kwargs)
        except TypeError as e:  # pragma: no cover
            print(
                f"--- Warning: Some parameters not supported by ChatOllama, retrying with basic config: {e} ---"
            )
            basic_kwargs = {
                "model": model,
                "base_url": base_url,
                "temperature": temperature,
                "callbacks": llm_timing_callbacks(),
            }
            if client_kwargs:
                basic_kwargs["client_kwargs"] = client_kwargs
            getted_llm = ChatOllama(**basic_kwargs)

        print(
            f"--- Converted OllamaLLM to ChatOllama for tool calling (model={model}, base_url={base_url}) ---"
        )
        return getted_llm

    return llm


class MultiTurnToolAgentExecutor:
    """
    Explicit multi-turn tool-calling executor.

    This avoids the opaque AgentExecutor path and gives the backend direct
    control over tool-call / observation turns, which is required for the
    wrapped chat-agent runtime tools.
    """

    def __init__(self, llm, system_prompt: str, tools, max_iterations: int = 4096):
        self.llm = llm
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.max_iterations = max_iterations
        self.bound_llm = llm.bind_tools(self.tools) if self.tools else None
        # Per-invocation log of every tool call (populated during invoke()).
        self._tool_calls_log: list[Dict[str, Any]] = []
        # Per-invocation Exec report buffer — one entry per state-changing
        # tool call (see _EXEC_REPORT_TOOLS). Only surfaced to the browser
        # when the user toggled the Exec report checkbox on.
        self._exec_report_enabled: bool = False
        self._exec_report_entries: list[Dict[str, Any]] = []
        # Ask-Execs (per-tool permission prompt) per-invocation state. Set
        # fresh at the top of invoke() because executor instances are cached
        # and reused across requests (see CapabilityAwareToolAgentExecutor).
        self._ask_execs_enabled: bool = False
        self._ask_execs_user_id: Any = None
        # Populated when the user DENIED a tool execution: halts the chain and
        # is surfaced to the browser as the red "Execution interrupted" banner.
        self._exec_denied: Optional[Dict[str, Any]] = None
        self._pending_denial_detail: Optional[Dict[str, Any]] = None
        # Per-invocation accumulator of Tier-1 orphan-reaper survivors
        # (processes the executor failed to kill after a tool call).
        # The consumer flushes this list AFTER it broadcasts the final
        # answer to the user, surfacing it as a follow-up chat message.
        self._orphan_survivors: list = []
        # Per-tool invocation counter (populated during invoke()). Complements
        # the consecutive-signature repetition detector: that one catches
        # identical-arg loops, this one catches semantic loops where the LLM
        # keeps reaching for the same hammer (e.g. pythonxer) with varying
        # scripts when a specialized tool would finish the job faster.
        self._tool_call_counts: Dict[str, int] = {}

    @staticmethod
    def _extract_exec_report_command(tool_input: Any, tool_name: str = "") -> str:
        """Pull a human-readable "command / intent" string out of the tool
        input dict so it can be rendered in the Exec report. Covers:

        - direct @tool inputs (``{"command": "..."}`` / ``{"path_filename":
          "..."}``)
        - wrapped chat-agent launches (``{"__arg1": "..."}`` /
          ``{"request": "..."}``)
        - ACPX child-process launchers (``acp_spawn`` shows
          ``[<agent_id>] <task>``, ``acp_send`` shows the turn text,
          ``acp_kill`` shows ``kill <session_id>``)
        - Skill harness invocations (``invoke_skill`` shows
          ``<skill_name>(<args>)``)

        Falls back to a compact ``key=value`` summary so the report never
        shows an empty cell. ``tool_name`` is optional only for backward
        compatibility with older callers; new code should always pass it.
        """
        if tool_input is None:
            return ""
        if isinstance(tool_input, str):
            return tool_input
        if not isinstance(tool_input, dict):
            return str(tool_input)

        # ACPX / Skill tool-specific formatters. These use argument keys
        # the legacy tools never use, and the user wants the report to
        # show the meaningful intent (which CLI was spawned, which skill
        # was invoked, which session was killed) rather than a raw
        # key=value dump.
        if tool_name == "acp_spawn":
            agent_id = str(tool_input.get("agent_id") or "").strip()
            task = str(tool_input.get("task") or "").strip()
            if agent_id and task:
                return f"[{agent_id}] {task}"
            return task or agent_id or ""
        if tool_name in ("acp_send", "acp_send_and_wait"):
            text = str(tool_input.get("text") or "").strip()
            session_id = str(tool_input.get("session_id") or "").strip()
            if session_id and text:
                return f"[{session_id}] {text}"
            return text or session_id or ""
        if tool_name == "acp_kill":
            session_id = str(tool_input.get("session_id") or "").strip()
            return f"kill {session_id}" if session_id else "kill"
        if tool_name == "acp_relay":
            src = str(tool_input.get("session_id_src") or "").strip()
            dst = str(tool_input.get("session_id_dst") or "").strip()
            transform = str(tool_input.get("transform") or "last_assistant_text").strip()
            if src and dst:
                return f"relay [{src}] → [{dst}] ({transform})"
            return transform
        if tool_name == "invoke_skill":
            skill_name = str(tool_input.get("skill_name") or "").strip()
            args_json = tool_input.get("args_json")
            if args_json in (None, "", {}):
                return skill_name
            args_repr = (
                args_json if isinstance(args_json, str)
                else json.dumps(args_json, ensure_ascii=False, sort_keys=True)
            )
            return f"{skill_name}({args_repr})" if skill_name else args_repr

        for key in ("command", "path_filename", "request", "__arg1"):
            value = tool_input.get(key)
            if value:
                return str(value)
        values = [v for v in tool_input.values() if v not in (None, "")]
        if len(values) == 1:
            return str(values[0])
        return ", ".join(f"{k}={v}" for k, v in tool_input.items() if v not in (None, ""))

    # ------------------------------------------------------------------
    # Ask-Execs permission gate
    # ------------------------------------------------------------------

    def _requires_exec_permission(self, tool_name: str) -> bool:
        """True when a tool call should be confirmed by the user before it
        runs under Ask Execs.

        This is a tight ALLOWLIST: the prompt fires ONLY for the Tier 1 +
        Tier 2 execution agents enumerated in ``_ASK_EXECS_REQUIRED_TOOLS``
        (the agents that execute a command / script / .bat / instruction,
        locally or remotely). Every other tool — read-only tools, management /
        polling helpers, file / notify / messaging agents, crypto, desktop-input
        agents, Scper, Apirer, Playwrighter, ``invoke_skill``, etc. — runs
        without a prompt."""
        if not tool_name:
            return False
        return tool_name in _ASK_EXECS_REQUIRED_TOOLS

    def _build_exec_permission_detail(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Assemble the detail dict shown in the browser's Ask-Execs dialog:
        what is going to execute, its parameters, the program text, and the
        shell it runs through."""
        tool_name = tool_call.get("name", "")
        raw_args = tool_call.get("args", {}) or {}
        agent_display = (
            (_resolve_exec_report_spec(tool_name) or (None, None))[1]
            or _tool_name_to_agent_display(tool_name)
            or tool_name
        )
        try:
            parameters = json.dumps(raw_args, indent=2, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            parameters = str(raw_args)
        return {
            "tool_name": tool_name,
            "agent_display": agent_display,
            "kind": _classify_tool_kind(tool_name),
            "program": self._extract_exec_report_command(raw_args, tool_name),
            "shell": _infer_execution_shell(tool_name, raw_args),
            "parameters": parameters,
        }

    def _request_exec_permission(self, tool_call: Dict[str, Any]) -> str:
        """Block on the browser's Proceed/Deny choice for ``tool_call``.

        Returns ``"proceed"`` or ``"deny"``. Stashes the detail so a denial can
        reuse it for the banner without rebuilding. Fails OPEN only when no
        broker is registered (unit tests / detached browser) — the consumer
        always registers a broker when Ask Execs is on, so in production this
        is a real round-trip."""
        detail = self._build_exec_permission_detail(tool_call)
        self._pending_denial_detail = detail
        broker = (
            get_broker(self._ask_execs_user_id)
            if self._ask_execs_user_id is not None
            else None
        )
        if broker is None:
            logger.warning(
                "[AskExecs] no broker registered for user=%s; proceeding (fail-open)",
                self._ask_execs_user_id,
            )
            return "proceed"
        decision = broker.request_permission(detail)
        logger.info(
            "[AskExecs] tool=%s decision=%s", detail.get("tool_name"), decision
        )
        return decision

    def _record_exec_denial(self, tool_call: Dict[str, Any]) -> None:
        """Capture the denied tool call so the chain can halt and the browser
        can render the red "Execution interrupted" banner."""
        detail = self._pending_denial_detail or self._build_exec_permission_detail(tool_call)
        self._exec_denied = {
            "tool_name": detail.get("tool_name", ""),
            "agent_display": detail.get("agent_display", ""),
            "kind": detail.get("kind", "Tool"),
            "command": detail.get("program", ""),
            "shell": detail.get("shell", ""),
            "parameters": detail.get("parameters", ""),
        }

    def _reap_after_tool(self, tool_name: str) -> None:
        """Tier-1 cleanup: after a tool call that may have spawned an
        external console child, reap any orphaned conhost.exe / dead
        descendants it left behind.

        Cheap and silent: errors are swallowed (they go to the reaper's
        own log). Survivors are accumulated on the executor instance so
        Tier 2 (the consumer's post-answer hook) can surface them to
        the user in a single follow-up chat message.
        """
        if not tool_name:
            return
        if (tool_name not in _PROCESS_SPAWNING_TOOL_NAMES
                and not tool_name.startswith("chat_agent_")
                and not tool_name.startswith("acp_")):
            return
        try:
            result = reap_orphans(
                scope=f"tier1:after:{tool_name}",
                include_self_tree=True,
                include_pool_scan=False,   # Tier 2/3 do the wider sweep
                include_console_host_sweep=True,
                # Coalesce: a Multi-Turn burst calls this after every tool. The
                # cheap self-tree zombie reap still runs each time, but the wider
                # console-host snapshot scan runs at most once per this interval, so
                # rapid back-to-back tool calls can't stack full sweeps.
                min_full_scan_interval=8.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[MultiTurnExecutor] Tier-1 reap raised: %s", exc)
            return
        if result.survivors:
            # Accumulate so the consumer can render one summary at the
            # end of the request instead of N per-tool pop-ups.
            self._orphan_survivors.extend(result.survivors)

    def _invoke_tool(self, tool_call: Dict[str, Any]) -> str:
        tool_name = tool_call.get("name", "")
        tool = self.tool_map.get(tool_name)
        if tool is None:
            logger.warning("[MultiTurnExecutor._invoke_tool] Tool '%s' NOT FOUND in tool_map. Available: %s",
                           tool_name, list(self.tool_map.keys()))
            display_name = _tool_name_to_agent_display(tool_name)
            if display_name is not None:
                self._tool_calls_log.append({
                    "tool_name": tool_name,
                    "args": tool_call.get("args", {}),
                    "success": False,
                    "agent_display_name": display_name,
                })
            return json.dumps({
                "status": "error",
                "message": f"Tool '{tool_name}' is not available in this session.",
                "retryable": False,
            })

        raw_args = tool_call.get("args", {})
        tool_input = raw_args if raw_args not in (None, "") else {}
        is_chat_agent_tool = tool_name.startswith("chat_agent_")
        if is_chat_agent_tool:
            logger.info("[MultiTurnExecutor._invoke_tool] Invoking WRAPPED CHAT AGENT tool: %s with args: %.500s",
                        tool_name, str(tool_input))

        try:
            result = tool.invoke(tool_input)
        except Exception as exc:
            logger.error("[MultiTurnExecutor._invoke_tool] Tool '%s' raised exception: %s", tool_name, exc, exc_info=True)
            display_name = _tool_name_to_agent_display(tool_name)
            if display_name is not None:
                self._tool_calls_log.append({
                    "tool_name": tool_name,
                    "args": dict(tool_input) if isinstance(tool_input, dict) else {},
                    "success": False,
                    "agent_display_name": display_name,
                })
            # ── Exec report capture (exception path) ──
            # The tables must show what was attempted regardless of whether
            # the underlying tool returned cleanly, raised, or the wrapping
            # answer was later classified FAILURE. Skipping capture here
            # would silently drop ACPX/Skill rows whenever the child CLI is
            # missing on PATH, the harness raised, or the tool args were
            # malformed — exactly the cases the user most needs to see.
            exec_report_spec = _resolve_exec_report_spec(tool_name)
            if exec_report_spec is not None:
                agent_key, agent_display = exec_report_spec
                self._exec_report_entries.append({
                    "tool_name": tool_name,
                    "agent_key": agent_key,
                    "agent_display": agent_display,
                    "command": self._extract_exec_report_command(tool_input, tool_name),
                    "success": False,
                })
            # Tier-1 reap: tool just blew up, almost certainly leaving
            # half-spawned children behind. Sweep them now so the orphan
            # count stays bounded across long Multi-Turn loops.
            self._reap_after_tool(tool_name)
            return json.dumps({
                "status": "error",
                "message": f"Tool '{tool_name}' raised an exception: {exc}",
                "retryable": False,
            })

        if is_chat_agent_tool:
            logger.info("[MultiTurnExecutor._invoke_tool] WRAPPED CHAT AGENT tool '%s' returned: %.1000s", tool_name, str(result))

        # Determine success: check for error/failure indicators in the result.
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        call_success = True
        try:
            parsed = json.loads(result_str)
            if isinstance(parsed, dict):
                status = str(parsed.get("status", "")).lower()
                if status in ("error", "failed"):
                    call_success = False
        except (json.JSONDecodeError, TypeError):
            pass

        display_name = _tool_name_to_agent_display(tool_name)
        if display_name is not None:
            self._tool_calls_log.append({
                "tool_name": tool_name,
                "args": dict(tool_input) if isinstance(tool_input, dict) else {},
                "success": call_success,
                "agent_display_name": display_name,
            })

        # ── Exec report capture ──
        # Always record entries for any tool in _EXEC_REPORT_TOOLS, regardless
        # of the per-request flag — capture is cheap, and decoupling capture
        # from rendering means a future layer that drops the flag (as the
        # UnifiedAgentChain payload whitelist once did) cannot silently hide
        # the data. The flag only gates whether the tables reach the user.
        exec_report_spec = _resolve_exec_report_spec(tool_name)
        if exec_report_spec is not None:
            agent_key, agent_display = exec_report_spec
            self._exec_report_entries.append({
                "tool_name": tool_name,
                "agent_key": agent_key,
                "agent_display": agent_display,
                "command": self._extract_exec_report_command(tool_input, tool_name),
                "success": call_success,
            })

        # Tier-1 reap: tool returned cleanly. Sweep any console-host
        # orphans left behind by the child process tree (only a no-op
        # for pure-Python tools — see _PROCESS_SPAWNING_TOOL_NAMES).
        self._reap_after_tool(tool_name)

        if isinstance(result, str):
            return result
        return result_str

    # ------------------------------------------------------------------
    # Repetition detection helpers
    # ------------------------------------------------------------------

    @classmethod
    def _call_signature(cls, tool_calls) -> str:
        """Return a deterministic string fingerprint for a list of tool calls.

        Polling/management tools listed in ``_TOOL_QUOTA_EXEMPT`` are excluded
        from the signature on purpose: calling ``chat_agent_run_status`` with
        the same ``run_id`` 3+ times while the underlying child is still
        ``status=running`` is legitimate progress, not a repetition. Counting
        them tripped the breaker on long-running tools (image_interpreter,
        crawler) before the LLM had any new information to act on.
        """
        parts = []
        for call in sorted(tool_calls, key=lambda c: c.get("name", "")):
            name = call.get("name", "")
            if name in cls._TOOL_QUOTA_EXEMPT:
                continue
            args = call.get("args") or {}
            parts.append(f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}")
        return "|".join(parts)

    # Maximum consecutive identical tool-call rounds before the loop is
    # broken.  Keeping this small prevents runaway iteration while still
    # allowing legitimate retries (e.g. polling a running agent twice).
    _REPEAT_LIMIT = 3

    # Per-tool invocation ceilings for a single Multi-Turn request. Exceeded
    # counts short-circuit the call with a directed nudge instead of letting
    # the LLM burn iterations retrying the same tool with shuffled arguments.
    # Management/polling tools are exempt (see ``_TOOL_QUOTA_EXEMPT``) because
    # polling a ``run_id`` 10+ times is legitimate.
    _TOOL_QUOTA_SOFT_WARN = 64
    _TOOL_QUOTA_HARD_STOP = 256
    _TOOL_QUOTA_EXEMPT: set[str] = {
        "agent_stat_getter",
        "chat_agent_run_list",
        "chat_agent_run_status",
        "chat_agent_run_log",
        "chat_agent_run_stop",
        "chat_agent_run_wait",
        "window_present",
        "get_current_time",
    }
    # Tools for which a soft-warn nudge recommends a specialized alternative.
    _TOOL_ALTERNATIVE_HINT: Dict[str, str] = {
        "chat_agent_pythonxer": (
            "You have already launched Pythonxer several times in this request. "
            "If the remaining work is file creation, prefer chat_agent_file_creator "
            "(one call per file) — it is more reliable for multi-line content with "
            "embedded quotes than embedding Python ``open(..., 'w')`` scripts. "
            "For file deletion use chat_agent_deleter; for moves, chat_agent_move_file. "
            "Keep using Pythonxer only if the remaining step is genuine computation."
        ),
        "execute_command": (
            "You have already executed several shell commands in this request. "
            "If you are verifying files you just created, a single ``dir /s`` or "
            "``ls -R`` is enough — further execute_command calls with similar "
            "intent are probably redundant. Consider summarizing and finalizing."
        ),
    }

    def _degraded_answer_from_results(self, messages, step) -> str:
        """Build a TRUTHFUL final answer from the tool results already collected,
        used when a model step could not be reached (the user cancelled, or every
        recovery tactic was exhausted) AFTER >=1 agent ran. It NEVER claims 'no
        tools ran' — the real work is preserved and surfaced, and the Create Flow
        button reflects the successful agents."""
        ran = list(self._tool_calls_log)
        ok = [e for e in ran if e.get("success")]
        last_results: list[str] = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                content = str(getattr(msg, "content", "") or "")
                if "[REPETITION BREAKER]" in content:
                    continue
                last_results.append(content)
                if len(last_results) >= 5:
                    break
        why = ("you cancelled" if getattr(step, "reason", "") == "user_cancelled"
               else "the model became unreachable and every recovery tactic was exhausted")
        lines = [
            f"⚠️ I stopped the model step because {why}, but your Multi-Turn run had "
            "ALREADY executed its agents — nothing was lost and the run was NOT discarded. "
            "Here is what actually ran this turn:",
            "",
        ]
        for e in ran:
            mark = "✅" if e.get("success") else "❌"
            name = e.get("tool_name") or e.get("agent_display") or "tool"
            lines.append(f"- {mark} {name}")
        if last_results:
            lines.append("")
            lines.append("Most recent tool results:")
            lines.append("\n---\n".join(reversed(last_results)))
        lines.append("")
        lines.append(
            f"({len(ok)} of {len(ran)} tool call(s) succeeded — you can click "
            "**Create Flow** to build a workflow from the successful agents.)"
        )
        return "\n".join(lines)

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Reset per-invocation tool call log.
        self._tool_calls_log = []
        # Track wrapped chat-agent calls to avoid duplicate launches.
        self._wrapped_agent_signatures: set[str] = set()
        # Reset Exec report state for this request; honour the per-request flag.
        self._exec_report_enabled = bool(payload.get("exec_report_enabled", False))
        self._exec_report_entries = []
        # Reset per-tool call counters for this request.
        self._tool_call_counts = {}
        # Reset Ask-Execs permission state for this request.
        self._ask_execs_enabled = bool(payload.get("ask_execs_enabled", False))
        self._ask_execs_user_id = payload.get("ask_execs_user_id")
        self._exec_denied = None
        self._pending_denial_detail = None

        # ── Self-healing model-step invoker (Angela, 2026-07-06 REDESIGN) ──
        # EVERY model call in this loop is routed through the healer so a
        # transient network blip is retried / re-strategized and ANNOUNCED to
        # the user live, and a run that already did real work is finished
        # gracefully (never discarded, never a lying "no tools ran"). Reset per
        # request because executor instances are cached and reused.
        self._healer = SelfHealingInvoker(
            user_id=self._ask_execs_user_id,
            plain_llm=self.llm,
            # She keeps trying distinct tactics up to her full turn budget and
            # never gives up on her own — only the USER (Cancel) stops her.
            max_attempts=get_int_config_value(
                "unified_agent_llm_step_max_tactics", 4096, minimum=1
            ),
            # Per-attempt watchdog: a call that does not answer in this many
            # seconds is ABANDONED (never waited on) so she never hangs.
            attempt_timeout=float(get_int_config_value(
                "unified_agent_llm_step_timeout_seconds", 80, minimum=15
            )),
        )

        input_text = payload.get("input", "")
        # ── Completion-notification ("notification debt") guard state ──
        # If the request asked to be notified ON COMPLETION (telegram/email/...),
        # the loop must not finish until a notification tool has actually been
        # called. Enforced in the final-answer branch below.
        self._completion_notification_due = _detect_completion_notification_request(input_text)
        self._notification_tools_called: set[str] = set()
        self._notification_nudged = False
        self._stashed_final_answer = ""
        chat_history = payload.get("chat_history", []) or []
        planner_summary = str(payload.get("planner_summary", "") or "").strip()
        messages = [
            SystemMessage(content=self.system_prompt),
        ]
        if planner_summary:
            messages.append(SystemMessage(
                content=(
                    "REQUEST-SCOPED GLOBAL EXECUTION PLAN:\n"
                    f"{planner_summary}\n\n"
                    "Follow this planner output. Prefetch stages have already been applied before this executor runs. "
                    "Use only the planned tool and monitor stages unless the plan is empty."
                )
            ))

        def _history_content(msg: Any) -> str:
            if isinstance(msg, BaseMessage):
                return str(getattr(msg, "content", "") or "")
            if isinstance(msg, dict):
                return str(msg.get("content", "") or "")
            return str(msg or "")

        history_items = list(chat_history)[-8:] if isinstance(chat_history, (list, tuple)) else []
        if history_items and _history_content(history_items[-1]).strip() == str(input_text).strip():
            history_items = history_items[:-1]
        for hist_msg in history_items:
            if isinstance(hist_msg, ToolMessage):
                continue
            if isinstance(hist_msg, BaseMessage):
                messages.append(hist_msg)
                continue
            if isinstance(hist_msg, dict):
                role = str(hist_msg.get("type") or hist_msg.get("role") or "").lower()
                content = _history_content(hist_msg)
                if not content:
                    continue
                messages.append(AIMessage(content=content) if role in {"assistant", "ai"} else HumanMessage(content=content))
                continue
            content = _history_content(hist_msg)
            if content:
                messages.append(HumanMessage(content=content))
        messages.append(HumanMessage(content=input_text))

        if not self.tools:
            try:
                response = self._healer.invoke(self.llm, messages, label="answering")
            except ModelStepUnrecoverable as _step:
                return self._build_result_dict(
                    "⚠️ I could not reach the model for this request after trying every "
                    f"recovery tactic ({_step.reason}). No tools were selected for this "
                    "request, so nothing was executed — please try again."
                )
            answer = getattr(response, "content", "") or ""
            if not str(answer).strip():
                answer = "The planner selected no tools for this request, and the model returned an empty response."
            return self._build_result_dict(str(answer))

        # --- Repetition tracking state ---
        last_signature: str | None = None
        repeat_count: int = 0

        for iteration in range(self.max_iterations):
            try:
                response = self._healer.invoke(
                    self.bound_llm, messages, label=f"working on step {iteration + 1}"
                )
            except ModelStepUnrecoverable as _step:
                # The model step could not be reached — either the USER cancelled,
                # or every distinct recovery tactic was exhausted. NEVER discard
                # the run: if any agent already ran, finish GRACEFULLY from that
                # real work so the Create Flow button + Exec report survive and the
                # answer is TRUTHFUL. Only when nothing ran yet do we surface it to
                # the chain (a pure-Q&A with no work to preserve).
                if self._tool_calls_log or self._exec_report_entries:
                    print(
                        "--- MultiTurnToolAgentExecutor: model step unreachable "
                        f"({_step.reason}) after {_step.attempts} tactic(s); finishing "
                        f"gracefully from {len(self._tool_calls_log)} tool call(s) already "
                        "done (run NOT discarded) ---"
                    )
                    return self._build_result_dict(
                        self._degraded_answer_from_results(messages, _step)
                    )
                raise
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []

            print(f"--- MultiTurnToolAgentExecutor iteration {iteration + 1}/{self.max_iterations}")
            if tool_calls:
                print(f"--- Tool calls requested: {[call.get('name') for call in tool_calls]}")

            if not tool_calls:
                # ── Completion-notification ("notification debt") guard ──
                # The user asked to be notified ON COMPLETION (telegram/email/...)
                # but the model is about to finish WITHOUT having called any
                # notification tool. Inject ONE nudge to actually send it,
                # instead of letting it confabulate a "tool backend unavailable /
                # re-enable Multi-Turn" excuse. Fires at most once per request.
                if (
                    self._completion_notification_due
                    and not self._notification_tools_called
                    and not self._notification_nudged
                ):
                    self._notification_nudged = True
                    # Preserve the substantive answer (e.g. the analysis) so the
                    # follow-up notification turn can't discard the deliverable.
                    pre_nudge_answer = str(getattr(response, "content", "") or "")
                    if pre_nudge_answer.strip():
                        self._stashed_final_answer = pre_nudge_answer
                    logger.info(
                        "[MultiTurnExecutor] Notification-debt guard fired: the request "
                        "asked for a completion notification but no notification tool was "
                        "called — nudging the model to send it now."
                    )
                    messages.append(HumanMessage(content=(
                        "You are about to give your FINAL answer, but this request asked you "
                        "to NOTIFY the user on completion (e.g. send a Telegram / email / "
                        "WhatsApp message / notification) and you have NOT yet called any "
                        "notification tool. Send it NOW: call the appropriate tool "
                        "(chat_agent_telegrammer / chat_agent_send_email / "
                        "chat_agent_whatsapper / chat_agent_notifier) with a concise "
                        "completion message. The tools ARE available right now — you have "
                        "been calling them this turn — so do NOT claim the backend is "
                        "'unavailable', do NOT claim a 'transient network error', and do NOT "
                        "tell the user to re-enable Multi-Turn. If, and ONLY if, the tool "
                        "call itself returns an error, report the EXACT tool name and the "
                        "verbatim error it returned."
                    )))
                    continue

                answer = getattr(response, "content", "") or ""
                if not str(answer).strip():
                    # The model finished tool-calling but returned empty content.
                    # Nudge it once to produce a summary from the collected tool results.
                    print("--- MultiTurnToolAgentExecutor: empty final response, nudging model to summarize ---")
                    # response already appended at line 211 — just add the nudge
                    messages.append(HumanMessage(content=(
                        "You have finished executing tools but returned an empty response. "
                        "Please now provide your final answer summarizing what you did and "
                        "the results you obtained. Do NOT call any more tools."
                    )))
                    try:
                        retry_response = self._healer.invoke(
                            self.bound_llm, messages, label="summarizing the results"
                        )
                    except ModelStepUnrecoverable:
                        retry_response = None
                    if retry_response is not None:
                        answer = getattr(retry_response, "content", "") or ""
                        retry_tool_calls = getattr(retry_response, "tool_calls", None) or []
                    else:
                        answer = ""
                        retry_tool_calls = []
                    if not str(answer).strip() or retry_tool_calls:
                        # Nudge failed — collect last real tool results as fallback answer.
                        print("--- MultiTurnToolAgentExecutor: nudge failed, collecting tool results as fallback ---")
                        last_real_results = []
                        for msg in reversed(messages):
                            if isinstance(msg, ToolMessage) and "[REPETITION BREAKER]" not in msg.content:
                                last_real_results.append(msg.content)
                                if len(last_real_results) >= 5:
                                    break
                        if last_real_results:
                            answer = (
                                "Here are the results from the executed tool calls:\n\n"
                                + "\n---\n".join(reversed(last_real_results))
                            )
                        else:
                            answer = "The tool-calling model returned an empty final response."
                # The stashed deliverable (if any) is folded back in CENTRALLY by
                # _build_result_dict, so EVERY terminal exit path preserves it —
                # not just this clean-finish return (the repetition-breaker,
                # iteration-limit and degraded paths dropped it). (2026-07-11 audit #3)
                return self._build_result_dict(str(answer))

            # --- Repetition detection ---
            # An empty signature means every tool in this turn is in
            # ``_TOOL_QUOTA_EXEMPT`` (polling / management). Skip the
            # repetition check entirely for that turn — polling a running
            # child is the whole point of those tools.
            sig = self._call_signature(tool_calls)
            if sig == "":
                # Reset the counter so a real tool call coming after a
                # polling burst can still be detected as repeating.
                last_signature = None
                repeat_count = 0
            elif sig == last_signature:
                repeat_count += 1
            else:
                last_signature = sig
                repeat_count = 1

            if repeat_count >= self._REPEAT_LIMIT:
                # Give the LLM one chance to wrap up by injecting a
                # nudge message instead of executing the duplicate calls.
                tool_names = [c.get("name") for c in tool_calls]
                print(
                    f"--- Repetition breaker activated: '{tool_names}' "
                    f"called {repeat_count} times with identical args. "
                    "Injecting stop nudge."
                )
                # Append synthetic ToolMessage results so the message
                # list stays schema-valid, then add a nudge.
                for tool_call in tool_calls:
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.get("id", ""),
                            name=tool_call.get("name", ""),
                            content=(
                                "[REPETITION BREAKER] This exact tool call with identical "
                                "parameters has already been executed and its output was "
                                "returned in a previous iteration. Repeating it will not "
                                "produce new information. You MUST now produce your final "
                                "answer based on the results you already have. Do NOT call "
                                "any more tools."
                            ),
                        )
                    )
                # Give the model one more chance to produce a final answer.
                try:
                    final_response = self._healer.invoke(
                        self.bound_llm, messages, label="wrapping up"
                    )
                except ModelStepUnrecoverable:
                    final_response = None
                if final_response is not None:
                    answer = getattr(final_response, "content", "") or ""
                    final_tool_calls = getattr(final_response, "tool_calls", None) or []
                else:
                    answer = ""
                    final_tool_calls = []
                if final_tool_calls:
                    # Model still insists on calling tools — force-stop.
                    print("--- Repetition breaker: model still requesting tools after nudge. Force-stopping.")
                    if not str(answer).strip():
                        # Collect the last real tool result to include in the answer.
                        last_real_results = []
                        for msg in reversed(messages):
                            if isinstance(msg, ToolMessage) and "[REPETITION BREAKER]" not in msg.content:
                                last_real_results.append(msg.content)
                                if len(last_real_results) >= 3:
                                    break
                        answer = (
                            "The tool-calling loop was stopped because the model kept "
                            "repeating the same tool call. Here are the last tool results "
                            "before the loop was broken:\n\n"
                            + "\n---\n".join(reversed(last_real_results))
                        )
                return self._build_result_dict(str(answer))

            # --- Normal tool execution ---
            for tool_call in tool_calls:
                tool_name = tool_call.get("name", "")
                # Mark that the model has attempted the requested completion
                # notification so the notification-debt guard above stays quiet.
                if tool_name in _NOTIFICATION_TOOLS:
                    self._notification_tools_called.add(tool_name)
                # Dedup: skip duplicate wrapped chat-agent calls with identical args
                if tool_name.startswith("chat_agent_") and tool_name not in _MANAGEMENT_TOOLS:
                    dedup_sig = f"{tool_name}:{json.dumps(tool_call.get('args', {}), sort_keys=True, ensure_ascii=False)}"
                    if dedup_sig in self._wrapped_agent_signatures:
                        logger.info(
                            "[MultiTurnExecutor] DEDUP: skipping duplicate wrapped-agent call: %s",
                            tool_name,
                        )
                        messages.append(
                            ToolMessage(
                                tool_call_id=tool_call.get("id", ""),
                                name=tool_name,
                                content=json.dumps({
                                    "status": "skipped",
                                    "message": (
                                        f"This exact '{tool_name}' call with identical parameters "
                                        "was already executed earlier in this session. "
                                        "Use the results from the previous execution."
                                    ),
                                }),
                            )
                        )
                        continue
                    self._wrapped_agent_signatures.add(dedup_sig)

                # Per-tool quota: hard-stop after HARD cap, warn after SOFT cap.
                prior_count = self._tool_call_counts.get(tool_name, 0)
                if tool_name not in self._TOOL_QUOTA_EXEMPT:
                    if prior_count >= self._TOOL_QUOTA_HARD_STOP:
                        logger.info(
                            "[MultiTurnExecutor] QUOTA HARD-STOP for tool=%s count=%d",
                            tool_name, prior_count,
                        )
                        messages.append(
                            ToolMessage(
                                tool_call_id=tool_call.get("id", ""),
                                name=tool_name,
                                content=json.dumps({
                                    "status": "skipped",
                                    "message": (
                                        f"[QUOTA HARD-STOP] You have invoked '{tool_name}' "
                                        f"{prior_count} times in this request — the per-tool cap "
                                        f"is {self._TOOL_QUOTA_HARD_STOP}. No further calls to "
                                        f"'{tool_name}' will be executed this turn. "
                                        "Produce your FINAL answer summarizing what has been "
                                        "accomplished so far. Do NOT call any more tools."
                                    ),
                                }),
                            )
                        )
                        # Record the attempt in the log so Create-Flow / Exec Report
                        # can still see that the LLM tried (with success=False).
                        display_name = _tool_name_to_agent_display(tool_name)
                        if display_name is not None:
                            self._tool_calls_log.append({
                                "tool_name": tool_name,
                                "args": dict(tool_call.get("args", {}) or {}),
                                "success": False,
                                "agent_display_name": display_name,
                            })
                        continue
                    if prior_count + 1 == self._TOOL_QUOTA_SOFT_WARN:
                        hint = self._TOOL_ALTERNATIVE_HINT.get(
                            tool_name,
                            f"You have invoked '{tool_name}' {self._TOOL_QUOTA_SOFT_WARN} times "
                            "in this request. If the task is complete, produce your final answer; "
                            "otherwise consider whether a specialized tool would finish faster.",
                        )
                        # Attach the hint to the tool result below so the LLM
                        # sees it alongside the actual output (non-blocking).
                        soft_warn_hint = hint
                    else:
                        soft_warn_hint = None
                else:
                    soft_warn_hint = None
                self._tool_call_counts[tool_name] = prior_count + 1

                # ── Ask-Execs permission gate ──
                # When enabled, block on the browser's Proceed/Deny choice
                # BEFORE the tool runs. A denial halts the entire chain: we
                # record what was denied (for the red banner) and finalize
                # immediately, so no further tools in this or later turns run.
                if self._ask_execs_enabled and self._requires_exec_permission(tool_name):
                    decision = self._request_exec_permission(tool_call)
                    if decision != "proceed":
                        self._record_exec_denial(tool_call)
                        denied = self._exec_denied or {}
                        denied_kind = denied.get("kind", "Tool")
                        denied_name = denied.get("agent_display") or tool_name
                        denied_cmd = denied.get("command", "")
                        answer = (
                            f"⛔ Execution interrupted. You denied the {denied_kind} "
                            f"\"{denied_name}\" from running"
                            + (f": {denied_cmd}" if denied_cmd else "")
                            + ". The Multi-Turn chain was halted at this step and no "
                            "further tools were executed."
                        )
                        return self._build_result_dict(answer)

                tool_result = self._invoke_tool(tool_call)
                if soft_warn_hint:
                    tool_result = (
                        tool_result
                        + "\n\n[PLANNER HINT] "
                        + soft_warn_hint
                    )
                messages.append(
                    ToolMessage(
                        tool_call_id=tool_call.get("id", ""),
                        name=tool_name,
                        content=tool_result,
                    )
                )

        return self._build_result_dict(
            "The tool-calling loop hit its iteration limit before producing a final answer. "
            "Summarize the latest observed tool state or refine the request."
        )

    def _merge_stashed_final_answer(self, answer: str) -> str:
        """Fold a deferred deliverable back into the FINAL answer, on EVERY path.

        The notification-debt guard stashes the substantive answer and continues
        the loop so the requested completion notification is sent first. Whatever
        path the run then exits by — clean finish, repetition-breaker,
        iteration-limit, or degraded/unrecoverable — the deferred deliverable
        must survive. Success-aware: if the notification SUCCEEDED prefer the
        (longer) stashed deliverable; if it FAILED keep the honest failure report
        visible and append the deliverable below it. Idempotent — a stash already
        present in ``answer`` is not re-appended. (2026-07-11 audit #3)
        """
        stash = (self._stashed_final_answer or "").strip()
        if not stash:
            return str(answer)
        answer_str = str(answer)
        if stash in answer_str:
            return answer_str  # already folded in (defensive; only one exit fires)
        notification_ok = any(
            entry.get("tool_name") in _NOTIFICATION_TOOLS and entry.get("success")
            for entry in self._tool_calls_log
        )
        if notification_ok:
            if len(stash) > len(answer_str.strip()):
                return self._stashed_final_answer
            return answer_str
        return answer_str.rstrip() + "\n\n---\n\n" + self._stashed_final_answer

    def _build_result_dict(self, answer: str) -> Dict[str, Any]:
        """Assemble the final executor return dict. ``exec_report_entries``
        is always populated from the captured state-changing tool calls;
        the chain above gates rendering on ``exec_report_enabled``. Emitting
        the entries unconditionally prevents a whitelist-style bug from ever
        silently hiding the data again.
        """
        # Fold a deferred deliverable (stashed before the completion-notification
        # nudge) back into the FINAL answer on EVERY terminal exit path — not just
        # the clean-finish return, which was the only path that restored it.
        # (2026-07-11 audit #3)
        answer = self._merge_stashed_final_answer(answer)
        # Drop into global_state so the WebSocket consumer can surface
        # surviving orphan PIDs as a follow-up chat message after it
        # broadcasts the main answer. The list is small (usually empty)
        # but bypassing the result_dict/chain whitelist gauntlet keeps
        # the contract robust against future payload-rebuild drops.
        try:
            # Keyed by THIS request's user id (like last_request_meta) so a
            # concurrent request (another tab / TeleTlamatini / a different user)
            # can never read OUR survivor list — or clear it before we do. The id
            # is always forwarded as ask_execs_user_id (== the conversation user
            # id), so writer and consumer agree on the slot. (2026-07-12 audit [3])
            global_state.set_state(
                f"last_orphan_survivors::{self._ask_execs_user_id}",
                list(self._orphan_survivors),
            )
        except Exception:  # noqa: BLE001 — never block the answer path
            pass
        # Prepend the self-healing recovery note (if any) so the FINAL, persisted
        # answer ALWAYS tells the user what Tlamatini went through — never silent,
        # never dishonest. Covers every exit path since they all funnel here.
        healer = getattr(self, "_healer", None)
        if healer is not None and getattr(healer, "recovery_events", None):
            answer = recovery_preamble(healer.recovery_events) + str(answer)
        result: Dict[str, Any] = {
            "output": answer,
            "tool_calls_log": list(self._tool_calls_log),
            "exec_report_enabled": bool(self._exec_report_enabled),
            "exec_report_entries": list(self._exec_report_entries),
            "orphan_survivors": list(self._orphan_survivors),
        }
        # When the user denied a tool under Ask Execs, carry the denial detail
        # up so the consumer can render the red "Execution interrupted" banner.
        # This is independent of exec_report_enabled — the banner always shows.
        if self._exec_denied:
            result["exec_report_denied"] = dict(self._exec_denied)
        return result


# Wrapped chat-agent tools whose presence means the firmware/engine "scaffold
# projects under your Templates directory" rule (prompt.pmt Rule 16) is relevant
# for the request. When none are bound the whole Templates rule block is dropped.
_FIRMWARE_TEMPLATE_TOOL_NAMES = frozenset({
    "chat_agent_stm32er",
    "chat_agent_esp32er",
    "chat_agent_esphomer",
    "chat_agent_arduiner",
    "chat_agent_unrealer",
    "chat_agent_blenderer",
})


_STEP_BY_STEP_SYSTEM_GUIDANCE = """
**STEP-BY-STEP MODE**:
- The user explicitly asked for paced setup or troubleshooting. Do exactly one concrete step at a time, then stop and wait for the user's requested short reply, READY, screenshot, log, or command output before continuing.
- Treat the user's next short reply as the answer to your previous Step-by-Step checkpoint. A bare username, DONE, ERROR, NOWINDOW, yes/no, path, or pasted output is continuation state, not a brand-new unrelated request.
- Keep each step short enough for a non-expert to perform. Include the exact command, menu path, file path, or click target for that one step.
- For new or unknown MCP setup, call `external_mcp_doctor` first. If it reports source/docs/repository URLs, investigate those through Crawler/Googler only when the next step is unclear.
- To ADD an MCP the user names or pastes (e.g. "add the redis MCP"), call `external_mcp_import` with its JSON config, then `external_mcp_set_active` to connect it, then `external_mcp_wait('<key>', 120)` to BLOCK until it is ready (a first-run Docker image pull or npx/uvx download is slow — do NOT poll external_mcp_status in a loop and give up; wait, and if it times out call external_mcp_wait again with a bigger timeout). Do this YOURSELF with these tools — never claim you lack a file-writing/shell tool and never push the user to the dialog.
- For MCP setup, inspect `external_mcp_status`; if tools are missing or a server is large, use `external_mcp_list_tools` before saying a tool is unavailable.
- For any External MCP tool not directly selected, use `external_mcp_call` with the raw tool name discovered from `external_mcp_list_tools`.
- Diagnose in layers: config JSON, required runtime (Docker/node/npx/uvx/python), process spawn, transport, initialize, tools/list, schema, then a small safe read/write test when appropriate.
- Never dump a whole installation plan at once unless the user asks for the full plan. In normal Step-by-Step mode, end with a clear READY checkpoint.
"""


def _build_system_prompt(preeliminary_prompt: str, tools, step_by_step_enabled: bool = False) -> str:
    import platform
    import sys as _sys
    # Lazy import (avoids any rag<->mcp_agent import-cycle at module load).
    from .rag.config import apply_conditional_rule_blocks

    # Keep the per-tool system-prompt list to ONE short line each. The model
    # ALREADY receives every tool's full name / description / parameters through
    # bind_tools() (the API ``tools`` field) — repeating the full multi-line
    # descriptions here is pure duplication that, with the entire tool surface
    # bound in Multi-Turn, costs ~5k redundant tokens EVERY turn. One short line
    # keeps the model oriented while the real schema travels through bind_tools.
    def _one_line(text: str) -> str:
        flat = " ".join(str(text or "").split())
        if not flat:
            return ""
        dot = flat.find(". ")
        if 0 < dot <= 96:
            return flat[: dot + 1]
        return (flat[:108].rstrip() + "…") if len(flat) > 110 else flat

    tool_descriptions = "\n".join(
        f"- {tool.name}: {_one_line(tool.description)}" for tool in tools
    )

    # Inject the feature-gated rule blocks (ACPX mechanics → Rule 12, Templates
    # directory → Rule 16) ONLY when their tool surface is actually bound for
    # this request. With ACPX disabled, filter_acpx_tools has already stripped
    # every acp_*/skill tool from ``tools`` upstream, so this drops ~1.8k words
    # of ACPX instructions a smaller model would otherwise have to read and obey
    # for tools it does not even have. Same idea for the firmware Templates rule.
    tool_names = {getattr(tool, "name", "") for tool in tools}
    preeliminary_prompt = apply_conditional_rule_blocks(
        preeliminary_prompt,
        include_acpx=bool(tool_names & ACPX_TOOL_NAMES),
        include_templates=bool(tool_names & _FIRMWARE_TEMPLATE_TOOL_NAMES),
    )

    # Remove the empty placeholder blocks from the base prompt since context
    # is injected into the user message by the chain, not into the system prompt.
    cleaned_prompt = re.sub(
        r"<system_context>\s*\{system_context\}\s*</system_context>",
        "",
        preeliminary_prompt,
    )
    cleaned_prompt = re.sub(
        r"<files_context>\s*\{files_context\}\s*</files_context>",
        "",
        cleaned_prompt,
    )
    cleaned_prompt = re.sub(
        r"<context>\s*\{context\}\s*</context>",
        "",
        cleaned_prompt,
    )
    # Escape any remaining curly braces that could break .format()
    escaped_prompt = cleaned_prompt.replace("{", "{{").replace("}", "}}")

    # Build a live platform information block
    os_name = platform.system()  # 'Windows', 'Linux', 'Darwin'
    os_version = platform.version()
    os_arch = platform.machine()
    is_windows = os_name == "Windows"
    is_frozen = getattr(_sys, "frozen", False)

    platform_block = (
        f"**PLATFORM INFORMATION** (live detection — use the correct commands for this OS):\n"
        f"- Operating System: {os_name} {platform.release()} ({os_version})\n"
        f"- Architecture: {os_arch}\n"
        f"- Runtime: {'Frozen executable' if is_frozen else 'Python source'}\n"
    )
    if is_windows:
        platform_block += (
            "- Shell: cmd.exe / PowerShell (Windows)\n"
            "- Package managers: winget, choco, pip, npm (NOT apt, yum, pacman, brew)\n"
            "- Path separator: backslash (\\)\n"
            "- Use Windows-native commands: dir (not ls), type (not cat), mkdir, rmdir, copy, move, del\n"
            "- NEVER use Linux/macOS commands (apt, sudo, chmod, chown, ln, grep) — they do not exist on this system\n"
        )
    else:
        platform_block += (
            "- Shell: bash / sh\n"
            "- Use Unix-native commands: ls, cat, mkdir, rm, cp, mv\n"
        )

    step_by_step_block = _STEP_BY_STEP_SYSTEM_GUIDANCE if step_by_step_enabled else ""

    return f"""{escaped_prompt}

{platform_block}
{step_by_step_block}

You have access to the following tools. Use them proactively whenever the user's request can benefit from them:

{tool_descriptions}

**TOOL SELECTION GUIDE** (pick the right tool for the task):
- **Run a shell/system command** → `execute_command` (install packages, build software, run any CLI command)
- **Run a Python script file** → `execute_file`
- **Run inline Python code** → `chat_agent_pythonxer` (with script='...')
- **Crawl/scrape a website** → `chat_agent_crawler` (with url='...' and system_prompt='...')
- **Search the web** → `googler` (with query='...')
- **Call an HTTP API** → `chat_agent_apirer` (with url='...' and method='GET/POST')
- **Run SQL on a database** → `chat_agent_sqler` (with connection_string='...' and query='...')
- **Run MongoDB queries** → `chat_agent_mongoxer` (with mongodb.connection_string='...')
- **SSH into a remote host** → `chat_agent_ssher` (with host='...' and command='...')
- **Transfer files via SCP** → `chat_agent_scper` (with host='...' and local_path='...')
- **Git operations** → `chat_agent_gitter` (with repo_path='...' and operation='...')
- **Docker operations** → `chat_agent_dockerer` (with command='docker ...')
- **Kubernetes operations** → `chat_agent_kuberneter` (with command='kubectl ...')
- **Send email** → `chat_agent_send_email` (with smtp.username='...' and to='...')
- **Send Telegram message** → `chat_agent_telegrammer`
- **Send WhatsApp message** → `chat_agent_whatsapper`
- **Desktop notification** → `chat_agent_notifier` (with title='...' and message='...')
- **Take a screenshot** → `chat_agent_shoter` (silent — file saved to disk, NO viewer popup. Pair with `chat_agent_image_interpreter` to read what's on screen. NEVER follow with `launch_view_image` — that would pop a viewer window and steal focus from the workflow's target app)
- **Move the mouse / click a window to focus it before typing** → `chat_agent_mouser` (with movement_type='localized' and end_posx=... and end_posy=... and button_click='left'). Use this BEFORE `chat_agent_keyboarder` whenever the target app may not already have focus (e.g. after launching Notepad — click into its edit area first, then type)
- **Type into a desktop app / send keystrokes / press hotkeys** → `chat_agent_keyboarder` (with input_sequence="..." — literal text wraps in quotes; key names and `+`-joined chords go bare; comma-separated. Example: `"home, 'Hello world', enter"`)
- **Analyze an image** → `chat_agent_image_interpreter` (with images_pathfilenames='...')
- **Create a file** → `chat_agent_file_creator` (with filepath='...' and content='...')
- **Extract text from documents** → `chat_agent_file_extractor` (with path='...')
- **Summarize text with LLM** → `chat_agent_summarize_text` (with input_text='...')
- **Send a sub-prompt to LLM** → `chat_agent_prompter` (with prompt='...')
- **Encrypt data (PQC)** → `chat_agent_kyber_cipher`
- **Decrypt data (PQC)** → `chat_agent_kyber_deciph`
- **Generate PQC keys** → `chat_agent_kyber_keygen`
- **PowerShell** → `chat_agent_pser` (with command='...')
- **Jenkins jobs** → `chat_agent_jenkinser`
- **Monitor a log file** → `chat_agent_monitor_log` (long-running)
- **Monitor network** → `chat_agent_monitor_netstat` (long-running)
- **Check running agents** → `chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`
- **Stop an agent** → `chat_agent_run_stop` (with run_id='...')
- **Get current time** → `get_current_time`
- **View network connections** → `execute_netstat`
- **Open an image** → `launch_view_image`
- **Unzip archive** → `unzip_file`
- **Decompile Java** → `decompile_java`
- **Configure a template agent** → `agent_parametrizer`
- **Start a template agent** → `agent_starter`
- **Stop a template agent** → `agent_stopper`
- **Check template agent status** → `agent_stat_getter`

**IMPORTANT**: If the user's request requires an action that can be performed with a tool, you **MUST use that tool** — do not just explain how the user could do it themselves. You are an OPERATOR: execute, don't advise.

**TOOL ROUTING RULES** (MANDATORY — always prefer the specialized tool):
- **Image analysis** → ALWAYS use `chat_agent_image_interpreter`. NEVER use `chat_agent_pythonxer` to write vision API scripts — the Image Interpreter agent already handles base64 encoding, LLM vision calls, and multi-image batch processing internally. Pass images_pathfilenames='<path or wildcard>' and optionally prompt_user='<what to describe>' — it runs interpreter_model_1 (qwen3.5:cloud) + interpreter_model_2 (gemma4:cloud) IN PARALLEL on two Ollama connections, then merging_model (glm-5.2:cloud) fuses both interpretations into one definitive report.
- **File reading/interpretation** → use `chat_agent_file_interpreter`, NOT `chat_agent_pythonxer` with open().
- **Text extraction from PDFs/DOCX** → use `chat_agent_file_extractor`, NOT `chat_agent_pythonxer`.
- **Web crawling** → use `chat_agent_crawler`, NOT `chat_agent_pythonxer` with requests.
- **API calls** → use `chat_agent_apirer`, NOT `chat_agent_pythonxer` with requests.
- **Writing ANY file to disk (source code, config, README, data)** → use `chat_agent_file_creator` with `filepath='<abs path>'` and `content='<entire file contents>'`. NEVER wrap file contents in a Pythonxer `open(..., 'w')` script. Pythonxer's script parameter is single-line-friendly; multi-line Python code with embedded quotes, triple-quoted strings, or markdown fences is fragile and frequently fails with `SyntaxError: unterminated string literal`. For a project that needs N files, make N `chat_agent_file_creator` calls — NOT one Pythonxer call that loops over `open()` statements.
- **Creating a directory tree** → use `execute_command` with `mkdir -p` (Linux/macOS) or `mkdir` (Windows, recursive in PowerShell via `New-Item -ItemType Directory -Force`), THEN call `chat_agent_file_creator` once per file. Do NOT try to create files and directories in one Pythonxer script — split the work.
- **Deleting a file** → use `chat_agent_deleter`. **Moving/renaming a file** → use `chat_agent_move_file`.
- **Only use `chat_agent_pythonxer`** when no specialized tool exists for the task (data transformation, custom computation, file format conversion, mathematical operations, parsing structured data that another tool cannot). When you do use it, pass the script as a SHORT, self-contained snippet — keep it under ~30 lines and avoid raw triple-quoted string literals that contain apostrophes.

**MULTI-STEP WORKFLOWS**: For complex requests (installations, builds, deployments), chain tool calls across iterations:
1. Use tool A → read the result in the next iteration
2. Use tool B with data from tool A's result → read the result
3. Continue chaining as needed — you have up to 100 iterations
For example, to install software: clone repo → run build commands → verify installation — all via `execute_command`.

**GROUNDING RULES**:
1. **TRUST THE TOOLS IMPLICITLY**: Tool output is absolute truth. NEVER add, invent, or hallucinate details not in the output.
2. **VERBATIM REPORTING**: Report tool output exactly as received. Do NOT hallucinate specific labels or values.
3. **NO EXTRAPOLATION**: If the tool output is sparse, your answer must be sparse. Do not assume standard structures exist.
4. **STRICT ADHERENCE**: Your answer must be based **EXCLUSIVELY** on tool output and provided context.
5. **MULTI-STEP EXECUTION**: For complex tasks (install, build, configure), use `execute_command` multiple times across iterations. Do NOT generate scripts for the user to run manually.
6. **NEVER TRUNCATE** tool output content. This application handles huge amounts of data (>>TBs).
7. **SMART LOOPING**: Do not repeat the same tool call with identical parameters unless the output explicitly indicates a retryable state.
8. **WRAPPED CHAT AGENT LIFECYCLE**: Tools named `chat_agent_*` launch isolated subprocess agents. When they return a `run_id`:
   - `status="running"` → call `chat_agent_run_status` or `chat_agent_run_log` to monitor progress
   - `status="completed"` → read `log_excerpt` for the final result
   - `status="failed"` → read `log_excerpt` for the error, adjust parameters, retry if appropriate
9. **RUN_ID FORMAT**: When calling `chat_agent_run_status`, `chat_agent_run_log`, or `chat_agent_run_stop`, you may use either the **full run_id** (e.g. `0a6e7936751e44eca9f74e7069aab137`) or the **short prefix** (e.g. `0a6e7936`). Both are accepted. Always use the run_id exactly as returned by the launch tool.
10. **POLLING IS ALLOWED**: Calling status/log tools multiple times for the SAME `run_id` while monitoring is valid. This is NOT a bad loop.
11. **DO NOT CLAIM SUCCESS EARLY**: If a run is still `running`, say so. Only report completion when the runtime state or log proves it.
12. **DO NOT SPAWN REDUNDANT AGENTS**: If you already launched a tool and it is still `running`, do NOT launch the same tool again with similar parameters. Wait for the first one to complete by polling its status/log. Only retry after a confirmed failure.
13. **TRUSTED WRAPPED AGENTS**: They manage their own isolated runtime directories and may operate outside normal path restrictions.
14. **PARAMETER FORMAT FOR chat_agent_* TOOLS**: Pass parameters as `key='value'` pairs in the request string. For nested config, use dotted notation: `llm.model='gpt-4'`, `smtp.username='user@example.com'`. Include ALL required parameters.

<question>
{{input}}
</question>


Answer:

"""


# ---------------------------------------------------------------------------
# Tool-surface token budgeting (Angela, 2026-06-19)
# ---------------------------------------------------------------------------
# Binding the FULL enabled surface (88 agents + active External-MCP tools) can
# overflow the model context window. Observed live: "prompt too long 273284 >
# 262144", which crashed Multi-Turn into a basic-LLM fallback ("tool backend
# unavailable"). Instead of blindly binding everything OR starving the operator
# with a tiny planner subset, we RANK the surface (reusing the same capability
# scorer + planner picks used elsewhere) and fill a token budget: a guaranteed
# operator CORE is always kept, then the planner's picks, then capability-scored
# tools by descending score until the budget is reached. The low-rank tail is
# dropped — never silently (the dropped count is always logged).
_TOOL_BUDGET_CONTEXT_LIMIT_DEFAULT = 262144
_TOOL_BUDGET_RESPONSE_HEADROOM = 8192
_TOOL_BUDGET_SAFETY_MARGIN = 4096

# Operator essentials the LLM must never be starved of, even on an off-topic
# prompt — the file / shell / python / edit / search core plus the cheap
# run-control + time/window helpers. Kept regardless of score so Multi-Turn
# always has hands to work with.
_CORE_ALWAYS_BOUND_TOOLS = frozenset({
    "chat_agent_file_creator", "chat_agent_editor", "chat_agent_grepper",
    "chat_agent_globber", "chat_agent_file_extractor", "chat_agent_file_interpreter",
    "chat_agent_executer", "chat_agent_pythonxer",
    "execute_command", "execute_file",
    "chat_agent_run_status", "chat_agent_run_log", "chat_agent_run_list",
    "chat_agent_run_stop", "get_current_time", "window_present",
})

_EMERGENCY_CORE_TOOL_ORDER = (
    "get_current_time",
    "execute_command",
    "execute_file",
    "chat_agent_executer",
    "chat_agent_pythonxer",
    "chat_agent_file_creator",
    "chat_agent_editor",
    "chat_agent_grepper",
    "chat_agent_globber",
    "chat_agent_file_extractor",
    "chat_agent_file_interpreter",
    "chat_agent_run_status",
    "chat_agent_run_log",
    "chat_agent_run_list",
    "chat_agent_run_stop",
    "window_present",
)


def _estimate_text_tokens(text) -> int:
    """Cheap, model-agnostic token estimate (~4 chars per token)."""
    return max(0, len(str(text or "")) // 4)


def _estimate_tool_schema_tokens(tool) -> int:
    """Approximate the tokens one tool's schema costs through ``bind_tools()``."""
    try:
        from langchain_core.utils.function_calling import convert_to_openai_tool
        text = json.dumps(convert_to_openai_tool(tool), ensure_ascii=False, default=str)
    except Exception:
        parts = [getattr(tool, "name", ""), getattr(tool, "description", "")]
        try:
            parts.append(json.dumps(getattr(tool, "args", {}) or {}, ensure_ascii=False, default=str))
        except Exception:
            pass
        text = " ".join(part for part in parts if part)
    return max(1, len(text) // 4)


def _budget_select_tools(request_tools, *, system_prompt_text, input_text,
                         chat_history, global_execution_plan):
    """Rank-and-budget the bound tool surface so the prompt fits the model window.

    Best case (everything fits): return the full surface unchanged (dropped=0).
    Otherwise: keep the guaranteed operator CORE + the planner's picks + the
    highest capability-scored tools, filling a token budget, and drop the
    low-rank tail. Returns ``(selected_tools, used_tool_tokens, dropped_count)``.
    """
    tools_list = list(request_tools)
    if len(tools_list) <= 1:
        return tools_list, 0, 0

    context_limit = get_int_config_value(
        "unified_agent_context_limit", _TOOL_BUDGET_CONTEXT_LIMIT_DEFAULT, minimum=8192
    )
    overhead = (
        _estimate_text_tokens(system_prompt_text)
        + _estimate_text_tokens(input_text)
        + sum(_estimate_text_tokens(message) for message in (chat_history or []))
    )
    tool_budget = (
        context_limit - overhead - _TOOL_BUDGET_RESPONSE_HEADROOM - _TOOL_BUDGET_SAFETY_MARGIN
    )
    costs = [(_estimate_tool_schema_tokens(tool), tool) for tool in tools_list]
    full_cost = sum(cost for cost, _ in costs)
    cost_by_id = {id(tool): cost for cost, tool in costs}
    if tool_budget <= 0:
        # Prompt + context/history already consumed the response/safety reserve.
        # Do NOT reopen a fresh 32k-ish tool budget here: that was the exact
        # overflow bug (the prompt alone was near the ceiling, then tools pushed
        # it over). Keep only the always-safe operator core, and only the core
        # tools that fit inside the remaining hard context window. If nothing
        # fits, return no tools; upstream context summarization/truncation must
        # reduce the non-tool prompt before a tool surface can be safely bound.
        hard_tool_budget = max(0, context_limit - overhead)
        by_name = {getattr(tool, "name", ""): tool for tool in tools_list}
        selected, used = [], 0
        for name in _EMERGENCY_CORE_TOOL_ORDER:
            tool = by_name.get(name)
            if tool is None:
                continue
            cost = cost_by_id[id(tool)]
            if used + cost <= hard_tool_budget:
                selected.append(tool)
                used += cost
        dropped = len(tools_list) - len(selected)
        return selected, used, dropped

    if full_cost <= tool_budget:
        return tools_list, full_cost, 0  # everything fits — bind the full surface

    planner_names = (
        set(selected_tool_names_from_plan(global_execution_plan))
        if global_execution_plan else set()
    )
    try:
        normalized_request = _normalize_text(input_text)
        request_tokens = _tokenize(input_text)
        capability_by_name = {
            capability.tool_name: capability
            for capability in build_tool_capabilities(tools_list)
        }
    except Exception:
        normalized_request, request_tokens, capability_by_name = "", set(), {}

    def _priority(tool) -> tuple:
        name = getattr(tool, "name", "")
        capability = capability_by_name.get(name)
        score = 0
        if capability is not None:
            try:
                score = _score_capability(capability, normalized_request, request_tokens)
            except Exception:
                score = 0
        if name in _CORE_ALWAYS_BOUND_TOOLS:
            tier = 3
        elif name in planner_names:
            tier = 2
        elif score > 0:
            tier = 1
        else:
            tier = 0
        return (tier, score, name)

    ranked = sorted(tools_list, key=_priority, reverse=True)
    selected, used = [], 0
    for tool in ranked:
        cost = cost_by_id[id(tool)]
        is_core = getattr(tool, "name", "") in _CORE_ALWAYS_BOUND_TOOLS
        if is_core or used + cost <= tool_budget:
            selected.append(tool)
            used += cost
    dropped = len(tools_list) - len(selected)
    return selected, used, dropped


class CapabilityAwareToolAgentExecutor:
    """
    Delegates to the legacy full-tool executor by default and only applies
    Phase 1 selective capability binding when the request explicitly enables it.
    """

    def __init__(self, llm, preeliminary_prompt: str, tools, max_iterations: int = 4096):
        self.llm = llm
        self.preeliminary_prompt = preeliminary_prompt
        self.tools = list(tools)
        self.max_iterations = max_iterations
        self._executor_cache: Dict[tuple[str, ...], MultiTurnToolAgentExecutor] = {}
        self.legacy_executor = self._get_executor_for_tools(self.tools)

    def _get_executor_for_tools(self, tools_subset, step_by_step_enabled: bool = False):
        key = tuple([f"__step_by_step__={int(bool(step_by_step_enabled))}"] + [tool.name for tool in tools_subset])
        cached = self._executor_cache.get(key)
        if cached is not None:
            return cached

        executor = MultiTurnToolAgentExecutor(
            llm=self.llm,
            system_prompt=_build_system_prompt(
                self.preeliminary_prompt,
                tools_subset,
                step_by_step_enabled=step_by_step_enabled,
            ),
            tools=tools_subset,
            max_iterations=self.max_iterations,
        )
        self._executor_cache[key] = executor
        return executor

    def _refresh_external_mcp_tool_surface(self) -> None:
        """Refresh External-MCP tools before each request.

        The unified agent is normally cached for speed, but External MCP tools
        are live capabilities: they can appear after Roblox Studio, Docker, npx,
        or another backend finishes connecting. Reconcile just that slice of the
        tool surface per request so the 88-agent planner sees reality.
        """
        try:
            from .external_mcp_manager import get_external_mcp_tools
            fresh_external = list(get_external_mcp_tools())
        except Exception:
            logger.exception("[ExternalMCP] request-time tool refresh failed")
            return

        current_external_names = [
            tool.name for tool in self.tools
            if _is_external_mcp_tool_name(getattr(tool, "name", ""))
        ]
        fresh_external_names = [tool.name for tool in fresh_external]
        if current_external_names == fresh_external_names:
            return

        base_tools = [
            tool for tool in self.tools
            if not _is_external_mcp_tool_name(getattr(tool, "name", ""))
        ]
        self.tools = base_tools + fresh_external
        self._executor_cache = {
            key: executor
            for key, executor in self._executor_cache.items()
            if not any(_is_external_mcp_tool_name(name) for name in key)
        }
        self.legacy_executor = self._get_executor_for_tools(self.tools)
        print(
            "--- CapabilityAwareToolAgentExecutor: refreshed External MCP tool surface "
            f"{current_external_names} -> {fresh_external_names}",
            flush=True,
        )

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_text = payload.get("input", "")
        chat_history = payload.get("chat_history", []) or []
        multi_turn_enabled = bool(payload.get("multi_turn_enabled", False))
        self._refresh_external_mcp_tool_surface()
        # Exec report is multi-turn-only: outside multi-turn we strip it.
        exec_report_enabled = bool(payload.get("exec_report_enabled", False)) and multi_turn_enabled
        # ACPX defaults to DISABLED. The user must explicitly tick the
        # toolbar checkbox to opt into the ACPX-aided flow; otherwise we
        # filter every LLM-facing ACPX tool out of self.tools BEFORE planning
        # or capability-based selection runs, so the entire ACPX surface
        # is invisible to the request and the system runs the legacy
        # Multi-Turn / one-shot mechanics.
        acpx_enabled = bool(payload.get("acpx_enabled", False))
        request_tools = filter_acpx_tools(self.tools, acpx_enabled)
        global_execution_plan = payload.get("global_execution_plan")
        # Ask-Execs is a Multi-Turn-only modifier: the per-tool permission
        # prompt only exists in the multi-turn executor loop, so it is ignored
        # entirely on the legacy one-shot path below.
        ask_execs_enabled = bool(payload.get("ask_execs_enabled", False)) and multi_turn_enabled
        ask_execs_user_id = payload.get("ask_execs_user_id")
        step_by_step_enabled = bool(payload.get("step_by_step_enabled", False))

        with scoped_request_state(
            multi_turn_enabled=multi_turn_enabled,
            suppress_visible_consoles=multi_turn_enabled,
        ):
            if not multi_turn_enabled:
                print(
                    "--- CapabilityAwareToolAgentExecutor: multi-turn disabled; "
                    f"using legacy full-tool binding (acpx_enabled={acpx_enabled}) ---"
                )
                # Legacy path: rebuild a one-shot executor over the request-scoped
                # tool set so disabling ACPX in legacy mode also strips the ACPX
                # tools from the LLM's bind_tools() list.
                if step_by_step_enabled or not acpx_enabled:
                    legacy_executor = self._get_executor_for_tools(
                        request_tools,
                        step_by_step_enabled=step_by_step_enabled,
                    )
                    return legacy_executor.invoke({"input": input_text, "chat_history": chat_history})
                return self.legacy_executor.invoke({"input": input_text, "chat_history": chat_history})

            # === MANDATE (Angela, 2026-06-16, refined 2026-06-19) ===
            # Multi-Turn must let Tlamatini SEE the tools she needs — binding a tiny
            # planner subset once starved the operator ("no file/shell tool bound").
            # But blindly binding the FULL surface (88 agents + active External-MCP
            # tools) overflowed the model window live ("prompt too long 273284 >
            # 262144") and crashed the turn into a basic-LLM fallback. So we
            # RANK-AND-BUDGET (_budget_select_tools): when the whole surface fits,
            # bind it all unchanged; when it does not, keep a guaranteed operator
            # CORE + the planner's picks + the highest capability-scored tools until
            # a token budget is reached, and drop the low-rank tail (logged, never
            # silent). ACPX is still filtered per the toolbar checkbox; External MCP
            # tools were refreshed above; the planner summary is still forwarded
            # below for ordering hints.
            _planned_count = (
                len(selected_tool_names_from_plan(global_execution_plan))
                if global_execution_plan else 0
            )
            selected_tools, _tool_tokens, _dropped = _budget_select_tools(
                request_tools,
                system_prompt_text=self.preeliminary_prompt,
                input_text=input_text,
                chat_history=chat_history,
                global_execution_plan=global_execution_plan,
            )
            if _dropped:
                print(
                    "--- CapabilityAwareToolAgentExecutor: multi-turn enabled; tool "
                    f"surface OVER budget — kept {len(selected_tools)}/{len(request_tools)} "
                    f"highest-ranked tools (~{_tool_tokens} tool-tokens), dropped {_dropped} "
                    f"low-rank tools to fit the model window (planner hinted "
                    f"{_planned_count}; acpx_enabled={acpx_enabled})"
                )
            else:
                print(
                    "--- CapabilityAwareToolAgentExecutor: multi-turn enabled; binding "
                    f"the FULL enabled surface: {len(selected_tools)} tools (~{_tool_tokens} "
                    f"tool-tokens, within budget; planner hinted {_planned_count}; "
                    f"acpx_enabled={acpx_enabled})"
                )
            executor = self._get_executor_for_tools(
                selected_tools,
                step_by_step_enabled=step_by_step_enabled,
            )
            executor_payload = {"input": input_text, "chat_history": chat_history}
            # Always forward the conversation user id so the executor's
            # self-healing invoker can push LIVE recovery status to THIS user's
            # chat (independent of Ask-Execs).
            executor_payload["ask_execs_user_id"] = ask_execs_user_id
            if exec_report_enabled:
                executor_payload["exec_report_enabled"] = True
            if ask_execs_enabled:
                executor_payload["ask_execs_enabled"] = True
            if global_execution_plan:
                executor_payload["global_execution_plan"] = global_execution_plan
                executor_payload["planner_summary"] = (
                    payload.get("planner_summary")
                    or summarize_global_execution_plan(global_execution_plan)
                )
            return executor.invoke(executor_payload)


def create_unified_agent(llm, preeliminary_prompt: str):
    """
    Build a single multi-turn tool‑calling agent that can both chat and invoke MCP tools.
    """
    tools = get_mcp_tools()
    print(f"--- create_unified_agent: {len(tools)} tools available:")
    for t in tools:
        print(f"    - {t.name}: {t.description[:50]}..." if len(t.description) > 50 else f"    - {t.name}: {t.description}")

    getted_llm = _ensure_chat_tool_model(llm)
    if not hasattr(getted_llm, "bind_tools"):
        raise RuntimeError("The configured unified agent model does not support bind_tools().")

    max_iterations = get_int_config_value("unified_agent_max_iterations", 4096, minimum=1)
    print(f"--- Unified agent max iterations: {max_iterations} ---")
    return CapabilityAwareToolAgentExecutor(
        llm=getted_llm,
        preeliminary_prompt=preeliminary_prompt,
        tools=tools,
        max_iterations=max_iterations,
    )
