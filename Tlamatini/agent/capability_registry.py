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
)
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
