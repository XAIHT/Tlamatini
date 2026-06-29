# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
ACP agent registry — the agent_id -> command map.

This is a Python mirror of OpenClaw's createAgentRegistry() output. The
defaults match the AgentId mapping documented in
extensions/acpx/skills/acp-router/SKILL.md so Tlamatini and OpenClaw
agree on which CLI is "claude", which is "qwen", etc.

User overrides in config.json:
    {
      "acpx": {
        "agents": {
          "claude": { "command": "C:/Users/me/AppData/Roaming/npm/claude.cmd" },
          "cursor": { "command": "/usr/local/bin/cursor-agent" }
        }
      }
    }

Custom agent ids may be added; they will appear in list_acp_agents().
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AcpAgentSpec:
    agent_id: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    # Transport profile. Controls how AcpSession.send_turn drives the
    # child process:
    #   "json-acp"       — child speaks the JSON-ACP envelope on stdout,
    #                      so the runtime drains until "done": true.
    #                      This is the strict ACP contract.
    #   "tui-repl"       — child is an interactive TUI (kiro, kimi, ...).
    #                      Stdout is heavily block-buffered when piped,
    #                      the child has no JSON envelope, and may
    #                      produce zero events for many seconds.
    #   "one-shot"       — the child does one task per process
    #                      invocation. Runtime closes stdin after the
    #                      first write and waits for child exit.
    #   "oneshot-prompt" — child is invoked one-shot per turn with the
    #                      prompt passed as a CLI argument behind
    #                      ``prompt_arg_flag`` (e.g.
    #                      ``claude -p "<task>"`` or
    #                      ``gemini --prompt "<task>"``). stdin is
    #                      closed immediately and the runtime captures
    #                      the full stdout to EOF. This is the ONLY
    #                      transport that reliably captures TUI agents'
    #                      responses on Windows — interactive TUIs
    #                      detect a piped stdout and refuse to flush.
    transport: str = "tui-repl"
    # Per-agent drain budgets used by send_turn. ``None`` means "use the
    # caller-provided default" (back-compat). These are conservative TUI
    # numbers — a JSON-ACP child can be configured with longer waits in
    # config.json.acpx.agents.<id> if needed.
    default_idle_seconds: Optional[float] = None
    default_startup_grace_seconds: Optional[float] = None
    default_timeout_seconds: Optional[float] = None
    # When True, ``acp_spawn`` returns immediately with the session_id
    # and does NOT drain the initial turn output. The drain happens on
    # the next ``acp_send`` / ``acp_send_and_wait`` / ``acp_transcript``.
    # This decouples spawn latency from content latency — the LLM gets
    # back a session it can chain into in <1s, instead of waiting the
    # full 45s every time.
    spawn_returns_immediately: bool = False
    # ── oneshot-prompt parameters ────────────────────────────────────
    # The CLI flag that introduces the user prompt as an argv arg. When
    # set together with ``transport="oneshot-prompt"``, the runtime
    # builds argv as ``[exe, *args, *prompt_subcommand_args,
    # prompt_arg_flag, "<task>"]`` (or appends ``"<task>"`` directly
    # when the flag is empty/whitespace). Examples:
    #   claude:  prompt_arg_flag="-p"
    #   gemini:  prompt_arg_flag="-p"
    #   cursor:  prompt_arg_flag="-p"
    #   codex:   prompt_subcommand_args=["exec"]  (no flag, positional)
    prompt_arg_flag: Optional[str] = None
    prompt_subcommand_args: List[str] = field(default_factory=list)


# Built-in registry. agent_id -> AcpAgentSpec.
# These commands are what the user is expected to have on PATH if they want
# to spawn a given agent. We intentionally do NOT shell-resolve them at
# import time — the resolution happens in windows_spawn.py at spawn time
# and any "command not found" condition surfaces through acp_doctor().
# TUI defaults: 8 s hard cap, 2 s idle, 3 s startup grace. These are
# tuned so a TUI REPL that produces nothing (the common case for kiro/
# kimi on a piped stdin) returns the spawn within ~3 s instead of the
# previous 45 s — a ~15× speedup on the common path.
_TUI_IDLE = 2.0
_TUI_GRACE = 3.0
_TUI_TIMEOUT = 8.0

# One-shot-prompt defaults. Each turn re-spawns the CLI with the prompt
# as a CLI arg and waits for the child to exit; an LLM answer can take
# up to ~3 minutes, so the hard cap is generous. ``idle`` and ``grace``
# are unused for this transport (the runtime drains until child exit /
# timeout) but kept set so the per-spec resolver in runtime.send doesn't
# fall back to the conservative TUI numbers.
_OS_TIMEOUT = 180.0
_OS_IDLE = 10.0
_OS_GRACE = 2.0

DEFAULT_ACP_AGENTS: Dict[str, AcpAgentSpec] = {
    # ── One-shot prompt mode ───────────────────────────────────────
    # These CLIs render to a TUI when run interactively, so a long-
    # lived child fed via stdin captures NOTHING on Windows: the TUI
    # detects the piped stdout, refuses to flush, and the transcript
    # only sees the outbound prompt. The fix is to call them in their
    # own non-interactive mode (``-p "<task>"``) per turn — the CLI
    # then prints the answer to stdout and exits, which the runtime
    # captures verbatim.
    "claude":   AcpAgentSpec("claude",   "claude",
                             description="Anthropic Claude Code CLI",
                             transport="oneshot-prompt",
                             prompt_arg_flag="-p",
                             default_idle_seconds=_OS_IDLE,
                             default_startup_grace_seconds=_OS_GRACE,
                             default_timeout_seconds=_OS_TIMEOUT),
    "codex":    AcpAgentSpec("codex",    "codex",
                             description="OpenAI Codex CLI",
                             transport="oneshot-prompt",
                             prompt_subcommand_args=["exec"],
                             default_idle_seconds=_OS_IDLE,
                             default_startup_grace_seconds=_OS_GRACE,
                             default_timeout_seconds=_OS_TIMEOUT),
    "cursor":   AcpAgentSpec("cursor",   "cursor-agent",
                             description="Cursor agent CLI",
                             transport="oneshot-prompt",
                             prompt_arg_flag="-p",
                             default_idle_seconds=_OS_IDLE,
                             default_startup_grace_seconds=_OS_GRACE,
                             default_timeout_seconds=_OS_TIMEOUT),
    "gemini":   AcpAgentSpec("gemini",   "gemini",
                             description="Google Gemini CLI",
                             transport="oneshot-prompt",
                             prompt_arg_flag="-p",
                             default_idle_seconds=_OS_IDLE,
                             default_startup_grace_seconds=_OS_GRACE,
                             default_timeout_seconds=_OS_TIMEOUT),
    "qwen":     AcpAgentSpec("qwen",     "qwen-code",
                             description="Alibaba Qwen Code CLI",
                             transport="oneshot-prompt",
                             prompt_arg_flag="-p",
                             default_idle_seconds=_OS_IDLE,
                             default_startup_grace_seconds=_OS_GRACE,
                             default_timeout_seconds=_OS_TIMEOUT),
    # ── Long-lived TUI REPLs ───────────────────────────────────────
    # These remain on the legacy ``tui-repl`` transport because we do
    # not yet know the right one-shot flag for each. If their stdout
    # capture turns out to be empty, override to ``oneshot-prompt`` in
    # ``config.json.acpx.agents.<id>``. The original 45 s hang is
    # avoided by ``spawn_returns_immediately=True`` plus the
    # transport-aware idle rule.
    "copilot":  AcpAgentSpec("copilot",  "copilot",
                             description="GitHub Copilot CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "pi":       AcpAgentSpec("pi",       "pi",
                             description="Pi assistant CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "droid":    AcpAgentSpec("droid",    "droid",
                             description="Factory Droid CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "iflow":    AcpAgentSpec("iflow",    "iflow",
                             description="iFlow CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "kilocode": AcpAgentSpec("kilocode", "kilocode",
                             description="Kilocode CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "kimi":     AcpAgentSpec("kimi",     "kimi",
                             description="Kimi CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "kiro":     AcpAgentSpec("kiro",     "kiro",
                             description="Kiro CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    "opencode": AcpAgentSpec("opencode", "opencode",
                             description="OpenCode CLI",
                             transport="tui-repl",
                             default_idle_seconds=_TUI_IDLE,
                             default_startup_grace_seconds=_TUI_GRACE,
                             default_timeout_seconds=_TUI_TIMEOUT,
                             spawn_returns_immediately=True),
    # Tlamatini-as-ACP-server: makes Tlamatini spawnable as a child of
    # OpenClaw or Claude Code. The actual ACP server module is
    # forward-compatibility-only in this revision; the entry exists so the
    # registry has a slot for it.
    "tlamatini": AcpAgentSpec(
        "tlamatini",
        sys.executable,
        args=["-m", "agent.acpx.self_acp_server"],
        description="Tlamatini-as-ACP-server (self-host)",
        transport="json-acp",
    ),
}


def build_agent_registry(overrides: Optional[Dict[str, str]] = None,
                         env_overrides: Optional[Dict[str, Dict[str, str]]] = None,
                         ) -> Dict[str, AcpAgentSpec]:
    """
    Merge user overrides with DEFAULT_ACP_AGENTS.

    Parameters
    ----------
    overrides : dict[str, str] | None
        Map of agent_id -> command. When an entry exists in DEFAULT_ACP_AGENTS,
        only the command is overridden (args/env are preserved). When the
        entry is brand-new, an AcpAgentSpec is created with empty args/env.
    env_overrides : dict[str, dict[str, str]] | None
        Optional per-agent env injection. Each {ENV_NAME: VALUE} dict is
        merged on top of the default spec's env (override wins on key
        conflict) and used at spawn time, where it is layered on top of
        `os.environ`. This is how the demo flow gets `GEMINI_API_KEY` into
        the gemini child without touching the parent Django process env.

    Returns
    -------
    dict[str, AcpAgentSpec]
        The fully-resolved registry. Order is: defaults first, then any
        new ids from overrides in the order they were declared.
    """
    overrides = overrides or {}
    env_overrides = env_overrides or {}
    registry: Dict[str, AcpAgentSpec] = {}
    for agent_id, spec in DEFAULT_ACP_AGENTS.items():
        merged_env = {**spec.env, **(env_overrides.get(agent_id) or {})}
        if agent_id in overrides:
            registry[agent_id] = AcpAgentSpec(
                agent_id=spec.agent_id,
                command=overrides[agent_id],
                args=list(spec.args),
                env=merged_env,
                description=spec.description,
                transport=spec.transport,
                default_idle_seconds=spec.default_idle_seconds,
                default_startup_grace_seconds=spec.default_startup_grace_seconds,
                default_timeout_seconds=spec.default_timeout_seconds,
                spawn_returns_immediately=spec.spawn_returns_immediately,
                prompt_arg_flag=spec.prompt_arg_flag,
                prompt_subcommand_args=list(spec.prompt_subcommand_args),
            )
        elif merged_env != spec.env:
            registry[agent_id] = AcpAgentSpec(
                agent_id=spec.agent_id,
                command=spec.command,
                args=list(spec.args),
                env=merged_env,
                description=spec.description,
                transport=spec.transport,
                default_idle_seconds=spec.default_idle_seconds,
                default_startup_grace_seconds=spec.default_startup_grace_seconds,
                default_timeout_seconds=spec.default_timeout_seconds,
                spawn_returns_immediately=spec.spawn_returns_immediately,
                prompt_arg_flag=spec.prompt_arg_flag,
                prompt_subcommand_args=list(spec.prompt_subcommand_args),
            )
        else:
            registry[agent_id] = spec
    for agent_id, command in overrides.items():
        if agent_id not in registry:
            # Unknown user-defined agent: assume tui-repl with TUI defaults
            # so they get the fast-path drain by default. Users can extend
            # the spec via config.json.acpx.agents.<id> later.
            registry[agent_id] = AcpAgentSpec(
                agent_id=agent_id,
                command=command,
                args=[],
                env=dict(env_overrides.get(agent_id) or {}),
                description="(user-defined)",
                transport="tui-repl",
                default_idle_seconds=2.0,
                default_startup_grace_seconds=3.0,
                default_timeout_seconds=8.0,
                spawn_returns_immediately=True,
            )
    return registry
