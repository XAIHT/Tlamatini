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


# Built-in registry. agent_id -> AcpAgentSpec.
# These commands are what the user is expected to have on PATH if they want
# to spawn a given agent. We intentionally do NOT shell-resolve them at
# import time — the resolution happens in windows_spawn.py at spawn time
# and any "command not found" condition surfaces through acp_doctor().
DEFAULT_ACP_AGENTS: Dict[str, AcpAgentSpec] = {
    "claude":   AcpAgentSpec("claude",   "claude",
                             description="Anthropic Claude Code CLI"),
    "cursor":   AcpAgentSpec("cursor",   "cursor-agent",
                             description="Cursor agent CLI"),
    "codex":    AcpAgentSpec("codex",    "codex",
                             description="OpenAI Codex (ACP path)"),
    "copilot":  AcpAgentSpec("copilot",  "copilot",
                             description="GitHub Copilot CLI"),
    "gemini":   AcpAgentSpec("gemini",   "gemini",
                             description="Google Gemini CLI"),
    "qwen":     AcpAgentSpec("qwen",     "qwen-code",
                             description="Alibaba Qwen Code CLI"),
    "pi":       AcpAgentSpec("pi",       "pi",
                             description="Pi assistant CLI"),
    "droid":    AcpAgentSpec("droid",    "droid",
                             description="Factory Droid CLI"),
    "iflow":    AcpAgentSpec("iflow",    "iflow",
                             description="iFlow CLI"),
    "kilocode": AcpAgentSpec("kilocode", "kilocode",
                             description="Kilocode CLI"),
    "kimi":     AcpAgentSpec("kimi",     "kimi",
                             description="Kimi CLI"),
    "kiro":     AcpAgentSpec("kiro",     "kiro",
                             description="Kiro CLI"),
    "opencode": AcpAgentSpec("opencode", "opencode",
                             description="OpenCode CLI"),
    # Tlamatini-as-ACP-server: makes Tlamatini spawnable as a child of
    # OpenClaw or Claude Code. The actual ACP server module is
    # forward-compatibility-only in this revision; the entry exists so the
    # registry has a slot for it.
    "tlamatini": AcpAgentSpec(
        "tlamatini",
        sys.executable,
        args=["-m", "agent.acpx.self_acp_server"],
        description="Tlamatini-as-ACP-server (self-host)",
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
            )
        elif merged_env != spec.env:
            registry[agent_id] = AcpAgentSpec(
                agent_id=spec.agent_id,
                command=spec.command,
                args=list(spec.args),
                env=merged_env,
                description=spec.description,
            )
        else:
            registry[agent_id] = spec
    for agent_id, command in overrides.items():
        if agent_id not in registry:
            registry[agent_id] = AcpAgentSpec(
                agent_id=agent_id,
                command=command,
                args=[],
                env=dict(env_overrides.get(agent_id) or {}),
                description="(user-defined)",
            )
    return registry
