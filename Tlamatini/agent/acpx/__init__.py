"""
ACPX runtime for Tlamatini.

This package implements a Python port of OpenClaw's ACPX plugin
(extensions/acpx/). It spawns external coding-agent CLIs (Claude Code,
Cursor, Codex, Gemini, Qwen, Kiro, Kimi, iFlow, Factory Droid, Kilocode,
OpenCode, Pi) as child processes and brokers them as Tlamatini tools.

Public surface:
    - AcpxRuntime, AcpAgentSpec, AcpSession, FileSessionStore
    - AcpRuntimeError
    - PERMISSION_MODES, NON_INTERACTIVE_POLICIES
    - get_acpx_runtime() -> singleton AcpxRuntime
    - The four @tool functions: acp_spawn, acp_send, acp_kill, acp_doctor,
      list_acp_agents (registered through agent.tools.get_mcp_tools()).

Side-by-side compatibility with OpenClaw:
    - configSchema is a verbatim mirror of extensions/acpx/openclaw.plugin.json.
    - Permission vocabulary (approve-all / approve-reads / deny-all) and
      the non-interactive policy (deny / fail) match.
    - agent_id default registry matches the AgentId mapping in
      extensions/acpx/skills/acp-router/SKILL.md.
"""

from .config import (
    AcpxConfig,
    PERMISSION_MODES,
    NON_INTERACTIVE_POLICIES,
    DEFAULT_TIMEOUT_SECONDS,
    load_acpx_config,
)
from .agent_registry import (
    AcpAgentSpec,
    DEFAULT_ACP_AGENTS,
    build_agent_registry,
)
from .session_store import FileSessionStore, AcpSessionRecord
from .runtime import (
    AcpxRuntime,
    AcpSession,
    AcpRuntimeError,
    get_acpx_runtime,
    DEFAULT_MAX_EVENT_CHARS,
    extract_last_assistant_text,
    trim_event_payload,
    trim_events,
)
from .tools import (
    acp_spawn,
    acp_send,
    acp_send_and_wait,
    acp_kill,
    acp_doctor,
    acp_transcript,
    acp_session_status,
    acp_list_sessions,
    acp_relay,
    list_acp_agents,
    invoke_skill,
    list_skills,
)

__all__ = [
    "AcpxConfig",
    "PERMISSION_MODES",
    "NON_INTERACTIVE_POLICIES",
    "DEFAULT_TIMEOUT_SECONDS",
    "load_acpx_config",
    "AcpAgentSpec",
    "DEFAULT_ACP_AGENTS",
    "build_agent_registry",
    "FileSessionStore",
    "AcpSessionRecord",
    "AcpxRuntime",
    "AcpSession",
    "AcpRuntimeError",
    "get_acpx_runtime",
    "DEFAULT_MAX_EVENT_CHARS",
    "extract_last_assistant_text",
    "trim_event_payload",
    "trim_events",
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
]
