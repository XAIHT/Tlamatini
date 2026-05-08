from dataclasses import dataclass
import logging
import re
from typing import Iterable

from .chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS

logger = logging.getLogger(__name__)


_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_RUN_ID_RE = re.compile(r"\brun[_\- ]?id\b|\b[0-9a-f]{10,32}\b", re.IGNORECASE)
_FILE_REFERENCE_RE = re.compile(
    r"(?:"
    r"[A-Za-z]:[\\/]"
    r"|\\\\"
    r"|\*\.[A-Za-z0-9]{1,10}\b"
    r"|\b[\w\-]+\.(?:py|js|ts|tsx|jsx|json|ya?ml|md|txt|xml|html|css|java|cs|go|rs|php|rb|sh|ps1|sql|csv|ini|cfg|toml|log|bat)\b"
    r")",
    re.IGNORECASE,
)
_SYSTEM_REFERENCE_RE = re.compile(
    r"\b(?:cpu|memory|ram|disk|storage|system|process(?:es)?|network|bandwidth|uptime|resource(?:s)?|performance|netstat|port(?:s)?|socket(?:s)?)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "get",
    "how", "i", "if", "in", "into", "is", "it", "its", "me", "my", "of",
    "on", "or", "please", "show", "that", "the", "this", "to", "up", "use",
    "using", "want", "what", "with", "you",
}
_RUN_CONTROL_TOOL_NAMES = (
    "chat_agent_run_list",
    "chat_agent_run_status",
    "chat_agent_run_log",
    "chat_agent_run_stop",
    "chat_agent_run_wait",
)

# ACPX tool name groups. Used by the planner to:
#   1. Boost the new tool-surface scores via _EXTRA_HINTS_BY_TOOL_NAME so
#      the LLM-facing planner picks them when the prompt mentions
#      "transcript", "harvest", "relay", "hand off", "wait for answer",
#      "session status", "list sessions", etc.
#   2. Co-select operational siblings when a primary ACPX tool fires —
#      e.g. selecting acp_spawn implies acp_kill / acp_doctor are
#      operationally needed even if their individual score is low.
ACPX_TOOL_NAMES = (
    "acp_spawn",
    "acp_send",
    "acp_send_and_wait",
    "acp_kill",
    "acp_doctor",
    "acp_transcript",
    "acp_session_status",
    "acp_list_sessions",
    "acp_relay",
    "list_acp_agents",
    "invoke_skill",
    "list_skills",
)

# When ANY of the keys in this map is selected, every name in the
# corresponding tuple is auto-co-selected (regardless of its individual
# score). The pattern mirrors the existing run-control auto-injection.
ACPX_CO_SELECTION_RULES: dict[str, tuple[str, ...]] = {
    # Spawning a child means the LLM will need to terminate it AND verify
    # the runtime is healthy first. Doctor + kill are operational siblings.
    "acp_spawn": ("acp_doctor", "acp_kill"),
    # The relay helper depends on transcript reads from the source session
    # and a kill of the destination once the hand-off is logged.
    "acp_relay": ("acp_transcript", "acp_kill"),
    # send-and-wait usually appears in flows that also need transcript
    # capture for evidence rows in the Exec Report.
    "acp_send_and_wait": ("acp_transcript",),
}
_EXTRA_HINTS_BY_TOOL_NAME = {
    "get_current_time": ("time", "date", "day", "clock", "today", "now"),
    "execute_file": ("script", "python", "run file", "execute file", "launch script"),
    "execute_command": (
        "command", "shell", "terminal", "cmd", "console", "powershell",
        "install", "uninstall", "download", "build", "compile", "make", "cmake",
        "setup", "configure", "update", "upgrade", "deploy",
        "pip install", "npm install", "choco install", "winget install",
        "apt install", "brew install", "yarn add", "cargo install",
        "git clone", "git pull", "mkdir", "execute",
        "run command", "run script",
    ),
    "execute_netstat": ("netstat", "port", "socket", "listen", "connection"),
    "launch_view_image": ("image", "show image", "view image", "open image", "picture"),
    "unzip_file": ("zip", "unzip", "extract archive", "decompress"),
    "decompile_java": ("decompile", "jar", "war", "class", "java"),
    "agent_parametrizer": ("parametrize", "parametrise", "configure template agent"),
    "agent_starter": ("start agent", "run agent", "launch agent"),
    "agent_stopper": ("stop agent", "kill agent", "terminate agent"),
    "agent_stat_getter": ("agent status", "agent state", "is agent running"),
    "chat_agent_run_list": ("run list", "recent runs", "latest runs"),
    "chat_agent_run_status": ("run status", "status", "running"),
    "chat_agent_run_log": ("run log", "logs", "output"),
    "chat_agent_run_stop": ("stop run", "cancel run", "terminate run"),
    # ── ACPX tool surface ────────────────────────────────────────────
    # Hints are tuned so the prompts in agent/migrations/0072 + 0073
    # (and the End-to-End ACPX Pipeline / Multi-CLI ACPX Relay demos)
    # actually score these tools above the planner's max_selected cap.
    # The corpus that the planner sees includes phrases like "harvest
    # transcript", "hand off content", "spawn a peer agent", "wait for
    # a complete answer", "pin leg A to gemini", etc., so we mirror
    # those phrases here.
    "acp_spawn": (
        "spawn", "spawn an agent", "spawn child", "spawn a child",
        "spawn an external", "external coding agent", "external cli",
        "acp_spawn", "acpx", "acp ", "spawn the cli", "launch cli",
        "launch claude", "launch cursor", "launch gemini", "launch codex",
        "launch qwen", "launch agent_id", "launch session",
        "agent_id", "leg a", "leg b", "first child", "second child",
    ),
    "acp_send": (
        "follow-up turn", "follow up turn", "next turn", "send turn",
        "continue with that session", "continue session",
        "acp_send", "send to session", "talk to session",
        "ask the session", "send the next prompt", "next prompt",
    ),
    "acp_send_and_wait": (
        "wait for", "wait for the answer", "wait for a complete answer",
        "wait for the full answer", "until idle", "settle",
        "settled", "complete answer", "synchronous", "sync send",
        "send and wait", "block until", "wait until done",
        "acp_send_and_wait", "wait for the child",
    ),
    "acp_kill": (
        "kill session", "kill the session", "terminate session",
        "graceful kill", "dual graceful kill", "tear down session",
        "close session", "stop the child", "stop the agent",
        "acp_kill", "killed", "killed=true",
        "shut down the session", "end the session",
    ),
    "acp_doctor": (
        "doctor", "acp doctor", "acp_doctor", "health probe",
        "is acpx healthy", "acpx availability", "details array",
        "ok is true", "ok is false", "probe agent",
        "acpx runtime health", "runtime health",
    ),
    "acp_transcript": (
        "transcript", "harvest transcript", "harvest the transcript",
        "transcript path", "read transcript", "read the transcript",
        "transcript_path", "ndjson", "compress the transcript",
        "summarize the transcript", "fetch transcript",
        "acp_transcript", "transcript content", "evidence",
        "cite transcript", "transcript evidence", "harvest",
    ),
    "acp_session_status": (
        "session status", "is session alive", "is the session alive",
        "session alive", "session pid", "session_id status",
        "transcript size", "last event", "alive",
        "acp_session_status",
    ),
    "acp_list_sessions": (
        "list sessions", "list acp sessions", "list active sessions",
        "enumerate sessions", "all sessions", "live sessions",
        "open sessions", "running sessions",
        "acp_list_sessions",
    ),
    "acp_relay": (
        "relay", "hand off", "hand-off", "handoff",
        "hand off content", "hand-off content", "hand-off pattern",
        "pass the analysis", "pass the transcript",
        "feed the output", "feed the answer", "send leg a output",
        "send leg-a output", "leg a to leg b", "leg-a to leg-b",
        "from session a", "from session b", "into session a",
        "into session b", "src to dst", "source to destination",
        "acp_relay", "multi-cli relay",
    ),
    "list_acp_agents": (
        "list acp agents", "list agents", "registered agents",
        "available agents", "which agents are resolvable",
        "resolvable", "agent_id list", "list_acp_agents",
        "acp registry",
    ),
    "invoke_skill": (
        "invoke skill", "invoke_skill", "invoke a skill",
        "run skill", "skill harness", "skill_name",
        "summarize skill", "fallback skill",
        "tlamatini skill", "execute skill",
    ),
    "list_skills": (
        "list skills", "list_skills", "available skills",
        "registered skills", "skill catalog", "what skills",
    ),
    # ── Desktop-UI tool surface ──────────────────────────────────────
    # Wrapped chat-agent tools that interact with the live desktop. The
    # planner historically failed to prioritise these on prompts like
    # "type X into notepad", "press the keys", "as if I were typing"
    # because the wrapped specs' implicit hints (derived from the agent
    # description) didn't include the natural-language verbs the user
    # actually uses. Adding explicit signal tokens here lifts these
    # tools above the cap on those prompts.
    "chat_agent_keyboarder": (
        "keyboarder", "keyboard", "type", "typed", "typing", "to type",
        "press", "press the keys", "press the key", "pressing keys",
        "keystrokes", "send keys", "send the keys", "input the text",
        "as if i were typing", "like i were pressing", "like if i were pressing",
        "as if i pressed", "simulate typing", "simulated typing",
        "hotkey", "hot key", "keyboard shortcut", "shortcut",
        "alt+f4", "alt+n", "ctrl+s", "ctrl+c", "ctrl+v",
        "type into notepad", "type in notepad", "type into", "type in",
        "write into notepad", "write to notepad",
        "insert the text", "insert text",
    ),
    "chat_agent_mouser": (
        "mouser", "mouse", "click", "click on", "double click",
        "double-click", "right click", "right-click", "drag",
        "drag and drop", "move the mouse", "move the cursor",
        "mouse cursor", "mouse pointer", "pointer", "scroll",
        "click button", "click the button", "press the mouse",
        # Locate-then-click vocabulary — the planner must surface Mouser
        # whenever the user names a target by appearance / window / label.
        "click save", "click ok", "click cancel", "click apply", "click submit",
        "click yes", "click no", "click close", "click next", "click finish",
        "click on the button", "tap the button", "press the button on screen",
        "focus the window", "focus window", "click into", "click in",
        "click center", "click top-right", "click bottom-left",
        "find the button", "find the button on screen", "locate the button",
        "locate the image", "locate image", "click where",
        # New movement_type modes the LLM can pick.
        "click_at_window", "click at window", "locate_image",
        "scroll up", "scroll down", "scroll wheel",
        "drag from", "drag to", "drag selection",
    ),
    "chat_agent_shoter": (
        "screenshot", "screen capture", "capture the screen",
        "take a screenshot", "snap screenshot", "shoter",
        "grab the screen", "snapshot of the screen",
    ),
    "window_present": (
        "is notepad open", "is notepad running", "is the window open",
        "window present", "window is visible", "visible on screen",
        "is the application open", "is the app open",
        "check if notepad", "did notepad open", "did the window open",
        "window exists", "find window", "window title",
    ),
    "chat_agent_sleeper": (
        "wait", "wait for", "wait n seconds", "wait 30 seconds",
        "wait a few seconds", "wait some seconds", "sleep",
        "pause for", "pause", "delay", "hold for",
        "milliseconds", "for n seconds", "after n seconds",
    ),
    "chat_agent_run_wait": (
        "wait for the run", "wait for run", "wait for run_id",
        "wait until the run finishes", "block until run finishes",
        "wait for the agent to finish", "wait for agent",
        "drain the run", "settle the run",
    ),
}
_CONTEXT_HINTS = {
    "system_context": (
        "cpu", "memory", "ram", "disk", "storage", "system", "performance",
        "resource", "resources", "process", "processes", "network", "bandwidth",
        "uptime", "port", "ports", "socket", "sockets", "netstat", "running",
        "usage", "load", "available", "free", "used",
    ),
    "files_context": (
        "file", "files", "folder", "folders", "directory", "directories",
        "path", "paths", "repo", "repository", "project", "codebase",
        "source", "source code", "module", "modules", "class", "classes",
        "function", "functions", "readme", "config", "open", "show",
        "read", "view", "find", "search", "locate", "list",
    ),
}


@dataclass(frozen=True)
class ToolCapability:
    tool_name: str
    description: str
    kind: str
    aliases: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()
    example_request: str = ""
    long_running: bool = False


@dataclass(frozen=True)
class ContextCapability:
    key: str
    hints: tuple[str, ...]


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_normalize_text(value))
        if len(token) > 1 and token not in _STOPWORDS
    }


def _split_tool_name(name: str) -> tuple[str, ...]:
    parts = [part for part in re.split(r"[^a-z0-9]+", name.lower()) if part]
    return tuple(parts)


def build_context_capabilities(*, system_enabled: bool, files_enabled: bool) -> list[ContextCapability]:
    capabilities: list[ContextCapability] = []
    if system_enabled:
        capabilities.append(ContextCapability(
            key="system_context",
            hints=tuple(_CONTEXT_HINTS["system_context"]),
        ))
    if files_enabled:
        capabilities.append(ContextCapability(
            key="files_context",
            hints=tuple(_CONTEXT_HINTS["files_context"]),
        ))
    return capabilities


def build_tool_capabilities(tools: Iterable) -> list[ToolCapability]:
    wrapped_specs = {spec.tool_name: spec for spec in WRAPPED_CHAT_AGENT_SPECS}
    capabilities: list[ToolCapability] = []

    for tool in tools:
        spec = wrapped_specs.get(tool.name)
        if spec is not None:
            capabilities.append(ToolCapability(
                tool_name=tool.name,
                description=tool.description,
                kind="wrapped_agent",
                aliases=tuple(spec.aliases),
                hints=tuple(spec.security_hints),
                example_request=spec.example_request,
                long_running=bool(spec.long_running),
            ))
            continue

        extra_hints = _EXTRA_HINTS_BY_TOOL_NAME.get(tool.name, ())
        kind = "tool"
        if tool.name.startswith("agent_"):
            kind = "template_agent"
        elif tool.name in _RUN_CONTROL_TOOL_NAMES:
            kind = "run_control"

        capabilities.append(ToolCapability(
            tool_name=tool.name,
            description=tool.description,
            kind=kind,
            hints=tuple(extra_hints),
        ))

    return capabilities


_ACPX_SIGNAL_TOKENS = frozenset({
    # Tokens that indicate the user is talking about the ACPX surface,
    # used as a multiplier source so multiple hits compound rather than
    # plateauing at the per-phrase cap.
    "acp", "acpx", "acp_spawn", "acp_send", "acp_kill", "acp_doctor",
    "acp_transcript", "acp_relay", "acp_session_status", "acp_list_sessions",
    "spawn", "transcript", "transcripts", "harvest", "relay",
    "handoff", "settle", "settled", "leg", "session_id", "session",
    "agent_id", "gemini", "claude", "cursor", "codex", "qwen",
    "doctor", "kill", "killed", "skill", "skill_name", "invoke",
    "openclaw",
})


def _score_capability(capability: ToolCapability, request_text: str, request_tokens: set[str]) -> int:
    score = 0

    normalized_name = capability.tool_name.lower()
    if normalized_name in request_text:
        score += 14

    if capability.tool_name in _RUN_CONTROL_TOOL_NAMES and _RUN_ID_RE.search(request_text):
        score += 14

    phrases = [*capability.aliases, *capability.hints]
    for phrase in phrases:
        normalized_phrase = _normalize_text(phrase)
        if normalized_phrase and normalized_phrase in request_text:
            score += 12 if normalized_phrase in capability.aliases else 10

    if capability.example_request:
        example_tokens = _tokenize(capability.example_request)
        overlap = len(example_tokens & request_tokens)
        score += min(overlap, 3)

    tool_tokens = set(_split_tool_name(capability.tool_name))
    tool_tokens |= _tokenize(capability.description)
    for phrase in phrases:
        tool_tokens |= _tokenize(phrase)

    overlap = request_tokens & tool_tokens
    score += min(len(overlap), 5) * 2

    if capability.kind == "wrapped_agent" and overlap:
        score += 2

    if capability.long_running and any(token in request_tokens for token in {"monitor", "watch", "track", "poll"}):
        score += 3

    # ── ACPX boost ────────────────────────────────────────────────────
    # Without this, the new ACPX surface tools (acp_send_and_wait,
    # acp_transcript, acp_relay, acp_session_status, acp_list_sessions)
    # score in the 8-10 band on real ACPX prompts and lose the 11-of-24
    # planner slot race to higher-scoring chat_agent_* peers. The boost
    # mirrors the run-control auto-selection rule by recognizing that
    # an ACPX prompt body is itself a strong signal — multiple ACPX
    # signal tokens compound here instead of plateauing on phrase caps.
    if capability.tool_name in ACPX_TOOL_NAMES:
        signal_hits = len(request_tokens & _ACPX_SIGNAL_TOKENS)
        if signal_hits > 0:
            # +3 per signal token, capped at +18. Three or more ACPX
            # signal tokens reliably push every ACPX tool above 24,
            # ahead of the chat_agent_* peer group.
            score += min(signal_hits * 3, 18)

    return score


def _score_context_capability(capability: ContextCapability, request_text: str, request_tokens: set[str]) -> int:
    score = 0

    for phrase in capability.hints:
        normalized_phrase = _normalize_text(phrase)
        if normalized_phrase and normalized_phrase in request_text:
            score += 4

    hint_tokens = set()
    for phrase in capability.hints:
        hint_tokens |= _tokenize(phrase)
    score += min(len(request_tokens & hint_tokens), 5) * 2

    if capability.key == "files_context":
        if _FILE_REFERENCE_RE.search(request_text):
            score += 6
        if any(token in request_tokens for token in {"repo", "repository", "project", "codebase", "source"}):
            score += 3
        if any(token in request_tokens for token in {"file", "files", "folder", "directory", "path", "paths"}):
            score += 3
    elif capability.key == "system_context":
        if _SYSTEM_REFERENCE_RE.search(request_text):
            score += 6
        if any(token in request_tokens for token in {"usage", "performing", "performance", "running", "available", "free", "used", "health"}):
            score += 2

    return score


def select_tools_for_request(request_text: str, tools: Iterable, max_selected: int = 50) -> list:
    tools_list = list(tools)
    if not tools_list:
        return []

    capabilities = build_tool_capabilities(tools_list)
    normalized_request = _normalize_text(request_text)
    request_tokens = _tokenize(normalized_request)

    scored = []
    for index, capability in enumerate(capabilities):
        score = _score_capability(capability, normalized_request, request_tokens)
        scored.append((score, index, capability))

    positive = [item for item in scored if item[0] > 0]
    if not positive:
        return tools_list

    top_score = max(item[0] for item in positive)
    if top_score < 4:
        return tools_list

    positive.sort(key=lambda item: (-item[0], item[1], item[2].tool_name))
    selected_names = {
        capability.tool_name
        for _score, _index, capability in positive[:max_selected]
    }

    selected_wrapped_agent = any(
        capability.kind == "wrapped_agent" and capability.tool_name in selected_names
        for _score, _index, capability in positive
    )
    if selected_wrapped_agent or _RUN_ID_RE.search(normalized_request):
        for control_name in _RUN_CONTROL_TOOL_NAMES:
            if any(tool.name == control_name for tool in tools_list):
                selected_names.add(control_name)

    # ACPX co-selection: when a primary ACPX tool is selected, pull in
    # its operational siblings even if their own score didn't make the
    # cut. Same shape as the run-control auto-injection above.
    available_names = {tool.name for tool in tools_list}
    for primary, siblings in ACPX_CO_SELECTION_RULES.items():
        if primary in selected_names:
            for sibling in siblings:
                if sibling in available_names:
                    selected_names.add(sibling)

    selected_tools = [tool for tool in tools_list if tool.name in selected_names]
    return selected_tools or tools_list


def select_context_capabilities_for_request(
    request_text: str,
    *,
    system_enabled: bool,
    files_enabled: bool,
    max_selected: int = 2,
) -> tuple[str, ...]:
    capabilities = build_context_capabilities(
        system_enabled=system_enabled,
        files_enabled=files_enabled,
    )
    if not capabilities:
        return ()

    normalized_request = _normalize_text(request_text)
    request_tokens = _tokenize(normalized_request)

    scored = []
    for index, capability in enumerate(capabilities):
        score = _score_context_capability(capability, normalized_request, request_tokens)
        scored.append((score, index, capability))

    selected = [
        capability.key
        for score, _index, capability in sorted(scored, key=lambda item: (-item[0], item[1]))
        if score >= 4
    ][:max_selected]

    ordered = []
    for key in ("system_context", "files_context"):
        if key in selected:
            ordered.append(key)
    return tuple(ordered)
