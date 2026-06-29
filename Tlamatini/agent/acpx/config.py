# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
ACPX plugin config — Python mirror of OpenClaw's
extensions/acpx/src/config-schema.ts and config.ts.

Tlamatini reads ACPX config from the same `config.json` Tlamatini already
uses for the rest of the system. The config block lives under the top-level
key "acpx". When the key is missing, we fall back to a permissive-but-safe
default that:
    - Uses the process cwd as cwd
    - Stores ACP session state under <app-base>/.tlamatini/acpx-state/
    - permissionMode = "approve-reads"   (writes require approval)
    - nonInteractivePermissions = "deny" (deny-on-no-prompt is safer)
    - timeoutSeconds = 120
    - pluginToolsMcpBridge = False       (do NOT expose Tlamatini @tools
                                          to the ACP child by default)
    - openClawToolsMcpBridge = False
    - mcpServers = {}                    (no MCP injection by default)
    - agents = {}                        (use the built-in registry only)

Why this exact default? Because the OpenClaw configContracts entry says
`permissionMode: "approve-all"` is a "dangerousFlag" — i.e. opting into
approve-all is a security-relevant decision. We will NEVER ship a default
that auto-approves writes.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PERMISSION_MODES = ("approve-all", "approve-reads", "deny-all")
NON_INTERACTIVE_POLICIES = ("deny", "fail")

DEFAULT_TIMEOUT_SECONDS = 120


@dataclass
class McpServerConfig:
    """One MCP server to inject into an ACP session at spawn time."""
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class AcpxConfig:
    """
    Resolved ACPX plugin config. Mirrors OpenClaw's ResolvedAcpxPluginConfig.

    Attributes
    ----------
    cwd : str
        Default working directory for ACP sessions when not set per-session.
    state_dir : str
        Directory used for ACP session state and persistence.
    probe_agent : str | None
        agent_id used for the runtime health probe.
    permission_mode : str
        One of PERMISSION_MODES. Controls how the ACP child's tool calls
        are approved. "approve-reads" is the default; "approve-all" is
        flagged dangerous.
    non_interactive : str
        One of NON_INTERACTIVE_POLICIES. What to do when an interactive
        permission prompt cannot be shown (e.g. unattended runs).
    plugin_tools_mcp_bridge : bool
        When True, inject the built-in Tlamatini-tools MCP server into ACP
        sessions so the ACP agent can call Tlamatini @tools. OFF by default.
    openclaw_tools_mcp_bridge : bool
        Reserved for forward-compatibility with OpenClaw bridges. OFF.
    strict_windows_cmd_wrapper : bool
        Legacy compatibility field. Accepted and logged as ignored.
    timeout_seconds : float
        Per-turn timeout for the embedded runtime.
    queue_owner_ttl_seconds : float
        Reserved compatibility field; ignored by this implementation.
    mcp_servers : dict[str, McpServerConfig]
        Named MCP servers to inject. Empty by default.
    agents : dict[str, str]
        agent_id -> command override map. Built-in registry is used for
        agents not listed here.
    """
    cwd: str = ""
    state_dir: str = ""
    probe_agent: Optional[str] = None
    permission_mode: str = "approve-reads"
    non_interactive: str = "deny"
    plugin_tools_mcp_bridge: bool = False
    openclaw_tools_mcp_bridge: bool = False
    strict_windows_cmd_wrapper: bool = False
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    queue_owner_ttl_seconds: float = 0.0
    mcp_servers: Dict[str, McpServerConfig] = field(default_factory=dict)
    agents: Dict[str, str] = field(default_factory=dict)
    agents_env: Dict[str, Dict[str, str]] = field(default_factory=dict)


def _coerce_perm_mode(value: Any) -> str:
    if isinstance(value, str) and value in PERMISSION_MODES:
        return value
    return "approve-reads"


def _coerce_non_interactive(value: Any) -> str:
    if isinstance(value, str) and value in NON_INTERACTIVE_POLICIES:
        return value
    return "deny"


def _coerce_mcp_servers(raw: Any) -> Dict[str, McpServerConfig]:
    out: Dict[str, McpServerConfig] = {}
    if not isinstance(raw, dict):
        return out
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        if not isinstance(command, str) or not command.strip():
            continue
        out[str(name)] = McpServerConfig(
            command=command.strip(),
            args=[str(a) for a in (spec.get("args") or [])],
            env={str(k): str(v) for k, v in (spec.get("env") or {}).items()},
        )
    return out


def _coerce_agents(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for agent_id, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        if isinstance(command, str) and command.strip():
            out[str(agent_id)] = command.strip()
    return out


def _coerce_agents_env(raw: Any) -> Dict[str, Dict[str, str]]:
    """Pluck per-agent env maps out of the same `acpx.agents` JSON block.

    Returns agent_id -> {ENV_NAME: VALUE}. Keys/values are coerced to str so
    the dict is safe to splat into `os.environ` at spawn time. An entry is
    skipped silently when the spec has no `env` dict, so existing string-only
    overrides remain valid and the legacy `agents: Dict[str, str]` shape is
    untouched.
    """
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for agent_id, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        env = spec.get("env")
        if not isinstance(env, dict) or not env:
            continue
        out[str(agent_id)] = {str(k): str(v) for k, v in env.items()}
    return out


def _app_base_dir() -> Path:
    """Return the application base directory (where config.json lives).

    - Frozen mode: directory containing the executable.
    - Source mode: ``agent/`` (two parents up from this file).

    This keeps all runtime state under the installation directory,
    avoiding writes to the user's home folder — which may be
    permission-restricted on corporate machines.
    """
    import sys
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).resolve().parent.parent          # agent/


def _default_state_dir() -> str:
    return str(_app_base_dir() / ".tlamatini" / "acpx-state")


def _default_cwd() -> str:
    return str(Path.cwd())


def load_acpx_config(config_dict: Optional[Dict[str, Any]] = None) -> AcpxConfig:
    """
    Build an AcpxConfig from a Tlamatini config.json dict.

    Parameters
    ----------
    config_dict : dict, optional
        The full top-level config.json. The "acpx" sub-key is read.
        When None, an empty dict is used and all defaults apply.

    Returns
    -------
    AcpxConfig
    """
    if config_dict is None:
        config_dict = {}
    raw = config_dict.get("acpx") or {}
    if not isinstance(raw, dict):
        raw = {}

    cwd = raw.get("cwd") or _default_cwd()
    state_dir = raw.get("stateDir") or _default_state_dir()
    Path(state_dir).mkdir(parents=True, exist_ok=True)

    return AcpxConfig(
        cwd=str(cwd),
        state_dir=str(state_dir),
        probe_agent=(raw.get("probeAgent") or None) and str(raw.get("probeAgent")),
        permission_mode=_coerce_perm_mode(raw.get("permissionMode")),
        non_interactive=_coerce_non_interactive(raw.get("nonInteractivePermissions")),
        plugin_tools_mcp_bridge=bool(raw.get("pluginToolsMcpBridge", False)),
        openclaw_tools_mcp_bridge=bool(raw.get("openClawToolsMcpBridge", False)),
        strict_windows_cmd_wrapper=bool(raw.get("strictWindowsCmdWrapper", False)),
        timeout_seconds=float(raw.get("timeoutSeconds") or DEFAULT_TIMEOUT_SECONDS),
        queue_owner_ttl_seconds=float(raw.get("queueOwnerTtlSeconds") or 0.0),
        mcp_servers=_coerce_mcp_servers(raw.get("mcpServers")),
        agents=_coerce_agents(raw.get("agents")),
        agents_env=_coerce_agents_env(raw.get("agents")),
    )


def load_tlamatini_config_json() -> Dict[str, Any]:
    """
    Best-effort loader for Tlamatini's config.json. Resolves both source
    mode and frozen mode the same way config_loader.py does, then returns
    an empty dict on failure (so ACPX never blocks Django startup).
    """
    try:
        import sys
        if getattr(sys, "frozen", False):
            base = Path(os.path.dirname(sys.executable))
        else:
            base = Path(__file__).resolve().parent.parent
        candidate = base / "config.json"
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# ── Dynamic config-file instrumentation ────────────────────────────────
#
# Why this exists
# ---------------
# `config.json` is the user-editable surface in BOTH source mode (read from
# `Tlamatini/agent/config.json`) and frozen mode (read from
# `<install-dir>/config.json` next to the executable). When a user upgrades
# Tlamatini to a build that ships ACPX, their *existing* `config.json` does
# not yet contain an `acpx` block — and editing-by-default-omission would
# leave them without any visible documentation of the new surface.
#
# `ensure_acpx_block_in_config_json()` solves this with a single rule:
#
#   "If config.json exists AND lacks an `acpx` key, atomically rewrite it
#    with the documented default block appended. Preserve every existing
#    key in its original order."
#
# This runs once per Django boot (from agent/apps.py via boot_acpx).
# Mode-aware:
#   - Frozen: writes alongside `sys.executable` (the user's install dir).
#   - Source: writes next to `agent/config.json` (the dev workspace).
#
# Failure is swallowed silently — never block startup over config writes.
# The DEFAULT_ACPX_CONFIG_BLOCK below is the *single source of truth* for
# both this helper and the source-tree config.json.
DEFAULT_ACPX_CONFIG_BLOCK: Dict[str, Any] = {
    "_acpx_cwd_comment": (
        "Default working directory for ACP child processes when no "
        "per-spawn cwd is given. Empty string = use the Django process "
        "cwd at runtime."
    ),
    "cwd": "",
    "_acpx_stateDir_comment": (
        "Where AcpSession transcripts and per-session JSON records are "
        "written. Empty string = <app-base>/.tlamatini/acpx-state/ "
        "(kept under the installation directory to avoid writes to "
        "restricted user-profile folders on corporate machines)."
    ),
    "stateDir": "",
    "_acpx_probeAgent_comment": (
        "agent_id used by acp_doctor's --version probe. Empty string = "
        "first resolvable agent in the registry. Set to 'claude' / "
        "'cursor' / etc. to pin it."
    ),
    "probeAgent": "",
    "_acpx_permissionMode_comment": (
        "One of 'approve-reads' (default; reads auto-approved, writes "
        "need a prompt), 'deny-all' (lockdown; even acp_spawn is "
        "blocked), 'approve-all' (FLAGGED DANGEROUS; auto-approves every "
        "action including writes/shell/network). Mirrors OpenClaw's "
        "ACPX_PERMISSION_MODES vocabulary exactly."
    ),
    "permissionMode": "approve-reads",
    "_acpx_nonInteractivePermissions_comment": (
        "What to do when an action needs a prompt but no operator can "
        "answer (Multi-Turn unattended runs). 'deny' = action denied, "
        "run continues. 'fail' = whole spawn/skill fails hard."
    ),
    "nonInteractivePermissions": "deny",
    "_acpx_timeoutSeconds_comment": (
        "Per-turn timeout for the embedded runtime (acp_send / initial "
        "spawn drain). Default 120s; bump for slow CLIs like Gemini "
        "cold-start."
    ),
    "timeoutSeconds": 120,
    "_acpx_pluginToolsMcpBridge_comment": (
        "When true, inject a built-in MCP server into ACP children that "
        "exposes Tlamatini @tools to the child. OFF by default — opting "
        "a less-trusted runtime into our tool surface is a deliberate "
        "security choice."
    ),
    "pluginToolsMcpBridge": False,
    "_acpx_openClawToolsMcpBridge_comment": (
        "Reserved for forward compatibility with OpenClaw's "
        "openClaw-tools bridge. OFF by default."
    ),
    "openClawToolsMcpBridge": False,
    "_acpx_strictWindowsCmdWrapper_comment": (
        "Legacy compatibility field. Accepted and logged as ignored; the "
        "current windows_spawn module handles .cmd/.bat resolution itself."
    ),
    "strictWindowsCmdWrapper": False,
    "_acpx_mcpServers_comment": (
        "Optional named MCP servers to inject into ACP child sessions at "
        "spawn time. Empty by default. Each entry: { command: 'python', "
        "args: ['-m', '...'], env: {...} }."
    ),
    "mcpServers": {},
    "_acpx_agents_comment": (
        "Per-agent_id command overrides. Empty = use the built-in registry "
        "(claude/cursor/codex/copilot/gemini/qwen/pi/droid/iflow/"
        "kilocode/kimi/kiro/opencode/tlamatini). Override when the binary "
        "lives outside PATH."
    ),
    "agents": {},
}


DEFAULT_ACPX_DOCUMENTATION_KEYS: Dict[str, str] = {
    "_section_acpx": (
        "ACPX Runtime + Skills (added 2026-04-29). The whole 'acpx' block "
        "is OPTIONAL — when missing, every value below is the safe default "
        "applied automatically by agent/acpx/config.py::load_acpx_config. "
        "Documenting the keys here makes the surface discoverable."
    ),
    "_acpx_doc_url": (
        "See ACPX.md at the repo root and docs/claude/acpx.md (when "
        "present) for the full contract."
    ),
}


DEFAULT_ACPX_TRAILING_DOC_KEYS: Dict[str, str] = {
    "_section_acpx_skills": (
        "Skills are loaded from agent/skills_pkg/<dir>/SKILL.md. The "
        "catalog is self-discovering; nothing in config.json controls it. "
        "Run `python manage.py acpx_lint` to validate the catalog."
    ),
    "_section_acpx_tools": (
        "ACPX exposes 7 LangChain @tools to the unified agent (acp_spawn "
        "/ acp_send / acp_kill / acp_doctor / list_acp_agents / "
        "invoke_skill / list_skills). Each is a row in the Tool table "
        "seeded by migration 0071_acpx_skills and is independently "
        "toggleable through the existing tools dialog UI."
    ),
}


def find_config_json_path() -> Path | None:
    """Locate the user-editable `config.json` for the current mode."""
    import sys
    try:
        if getattr(sys, "frozen", False):
            base = Path(os.path.dirname(sys.executable))
        else:
            base = Path(__file__).resolve().parent.parent
        candidate = base / "config.json"
        return candidate if candidate.exists() else None
    except Exception:
        return None


def ensure_acpx_block_in_config_json(*,
                                     config_path: Path | None = None,
                                     overwrite: bool = False) -> bool:
    """
    Make sure `config.json` has an `acpx` block. If absent, append the
    documented defaults atomically (write to <path>.tmp, then os.replace).

    Parameters
    ----------
    config_path : Path | None
        When None, use `find_config_json_path()` to locate the file.
    overwrite : bool
        When True, *replace* an existing `acpx` block with the documented
        defaults. Use only for repair tooling — the boot path always uses
        overwrite=False so user customizations are preserved.

    Returns
    -------
    bool
        True iff the file was rewritten. False when no change was needed
        or when the file does not exist.
    """
    target = config_path or find_config_json_path()
    if target is None or not target.exists():
        return False
    try:
        text = target.read_text(encoding="utf-8")
        existing = json.loads(text)
        if not isinstance(existing, dict):
            return False
    except Exception:
        return False

    if "acpx" in existing and not overwrite:
        return False

    new_data: Dict[str, Any] = {}
    # Preserve every existing key in its original order, removing only
    # the doc-key/section-key + acpx-block when overwrite is requested.
    skip_keys = set()
    if overwrite:
        skip_keys |= set(DEFAULT_ACPX_DOCUMENTATION_KEYS)
        skip_keys |= set(DEFAULT_ACPX_TRAILING_DOC_KEYS)
        skip_keys.add("acpx")
    for k, v in existing.items():
        if k in skip_keys:
            continue
        new_data[k] = v

    # Append the documented block at the tail.
    for k, v in DEFAULT_ACPX_DOCUMENTATION_KEYS.items():
        new_data[k] = v
    new_data["acpx"] = dict(DEFAULT_ACPX_CONFIG_BLOCK)
    for k, v in DEFAULT_ACPX_TRAILING_DOC_KEYS.items():
        new_data[k] = v

    serialized = json.dumps(new_data, indent=2, ensure_ascii=False)
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(serialized + "\n", encoding="utf-8")
        os.replace(tmp, target)
        return True
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False
