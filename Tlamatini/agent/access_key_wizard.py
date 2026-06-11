"""Backend helpers for the graphical Access Keys Wizard.

The wizard is intentionally conservative with secrets:

* load/status endpoints return only configured/missing states;
* POST payloads treat blank strings as "leave the existing value alone";
* values are written to the local ``data.keys`` vault first, then projected
  into the runtime files that already consume those values.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from .config_loader import find_config_path, load_config, save_config_updates


@dataclass(frozen=True)
class WizardField:
    key: str
    label: str
    group: str
    kind: str = "secret"
    required: bool = False
    json_key: Optional[str] = None
    acpx_env: Tuple[Tuple[str, str], ...] = ()
    yaml_rules: Tuple[Tuple[str, Tuple[str, ...], bool], ...] = ()
    note: str = ""


@dataclass(frozen=True)
class WizardGroup:
    key: str
    title: str
    fields: Tuple[WizardField, ...] = field(default_factory=tuple)


WIZARD_GROUPS: Tuple[WizardGroup, ...] = (
    WizardGroup(
        key="acpx",
        title="ACPX and LLM Providers",
        fields=(
            WizardField(
                key="ANTHROPIC_API_KEY",
                label="Claude / Anthropic API key",
                group="acpx",
                required=False,
                json_key="ANTHROPIC_API_KEY",
                acpx_env=(("claude", "ANTHROPIC_API_KEY"),),
            ),
            WizardField(
                key="GEMINI_API_KEY",
                label="Gemini API key",
                group="acpx",
                required=False,
                json_key="GEMINI_API_KEY",
                acpx_env=(("gemini", "GEMINI_API_KEY"),),
                note="Can also fill GOOGLE_API_KEY for gemini-cli compatibility.",
            ),
            WizardField(
                key="GOOGLE_API_KEY",
                label="Google API key alias",
                group="acpx",
                required=False,
                acpx_env=(("gemini", "GOOGLE_API_KEY"),),
                note="Usually the same value as GEMINI_API_KEY.",
            ),
            WizardField(
                key="OPENAI_API_KEY",
                label="OpenAI API key / Codex",
                group="acpx",
                required=False,
                acpx_env=(("codex", "OPENAI_API_KEY"),),
            ),
            WizardField(
                key="DASHSCOPE_API_KEY",
                label="DashScope API key / Qwen",
                group="acpx",
                required=False,
                acpx_env=(("qwen", "DASHSCOPE_API_KEY"),),
            ),
            WizardField(
                key="OLLAMA_TOKEN",
                label="Ollama token",
                group="acpx",
                required=False,
                json_key="ollama_token",
                note="Optional for local Ollama installs.",
            ),
        ),
    ),
    WizardGroup(
        key="telegram",
        title="Telegram Bridges",
        fields=(
            WizardField(
                key="TELEGRAMER_API_ID",
                label="Telegramer API ID",
                group="telegram",
                kind="text",
                yaml_rules=(("telegramer", ("telegram", "api_id"), False),),
            ),
            WizardField(
                key="TELEGRAMER_API_HASH",
                label="Telegramer API hash",
                group="telegram",
                yaml_rules=(("telegramer", ("telegram", "api_hash"), False),),
            ),
            WizardField(
                key="TELEGRAMER_CHAT_ID",
                label="Telegramer chat",
                group="telegram",
                kind="text",
                yaml_rules=(("telegramer", ("telegram", "chat_id"), False),),
            ),
            WizardField(
                key="TELEGRAMRX_API_ID",
                label="TelegramRX API ID",
                group="telegram",
                kind="text",
                yaml_rules=(("telegramrx", ("telegram", "api_id"), False),),
            ),
            WizardField(
                key="TELEGRAMRX_API_HASH",
                label="TelegramRX API hash",
                group="telegram",
                yaml_rules=(("telegramrx", ("telegram", "api_hash"), False),),
            ),
            WizardField(
                key="TELEGRAMRX_LISTEN_CHAT",
                label="TelegramRX listen chat",
                group="telegram",
                kind="text",
                yaml_rules=(("telegramrx", ("telegram", "listen_chat"), False),),
            ),
            WizardField(
                key="TELETLAMATINI_API_ID",
                label="TeleTlamatini API ID",
                group="telegram",
                kind="text",
                yaml_rules=(("teletlamatini", ("telegram", "api_id"), False),),
            ),
            WizardField(
                key="TELETLAMATINI_API_HASH",
                label="TeleTlamatini API hash",
                group="telegram",
                yaml_rules=(("teletlamatini", ("telegram", "api_hash"), False),),
            ),
            WizardField(
                key="TELETLAMATINI_BOT_TOKEN",
                label="TeleTlamatini bot token",
                group="telegram",
                yaml_rules=(("teletlamatini", ("telegram", "bot_token"), False),),
            ),
            WizardField(
                key="TELETLAMATINI_PASSWORD",
                label="TeleTlamatini access password",
                group="telegram",
                yaml_rules=(("teletlamatini", ("password",), True),),
            ),
            WizardField(
                key="TLAMATINI_USERNAME",
                label="Tlamatini login username",
                group="telegram",
                kind="text",
                yaml_rules=(("teletlamatini", ("tlamatini", "username"), False),),
            ),
            WizardField(
                key="TLAMATINI_PASSWORD",
                label="Tlamatini login password",
                group="telegram",
                yaml_rules=(("teletlamatini", ("tlamatini", "password"), True),),
            ),
        ),
    ),
    WizardGroup(
        key="email",
        title="Email Bridges",
        fields=(
            WizardField(
                key="EMAILER_USERNAME",
                label="Emailer SMTP username",
                group="email",
                kind="text",
                yaml_rules=(("emailer", ("smtp", "username"), False),),
            ),
            WizardField(
                key="EMAILER_PASSWORD",
                label="Emailer SMTP app password",
                group="email",
                yaml_rules=(("emailer", ("smtp", "password"), True),),
            ),
            WizardField(
                key="RECMAILER_USERNAME",
                label="RecMailer IMAP username",
                group="email",
                kind="text",
                yaml_rules=(("recmailer", ("imap", "username"), False),),
            ),
            WizardField(
                key="RECMAILER_PASSWORD",
                label="RecMailer IMAP app password",
                group="email",
                yaml_rules=(("recmailer", ("imap", "password"), True),),
            ),
        ),
    ),
)

FIELD_BY_KEY: Dict[str, WizardField] = {
    field.key: field
    for group in WIZARD_GROUPS
    for field in group.fields
}

AGENT_YAML_RELATIVE_PATHS: Dict[str, Tuple[str, str]] = {
    "telegramer": (
        "Tlamatini/agent/agents/telegramer/config.yaml",
        "agents/telegramer/config.yaml",
    ),
    "telegramrx": (
        "Tlamatini/agent/agents/telegramrx/config.yaml",
        "agents/telegramrx/config.yaml",
    ),
    "teletlamatini": (
        "Tlamatini/agent/agents/teletlamatini/config.yaml",
        "agents/teletlamatini/config.yaml",
    ),
    "emailer": (
        "Tlamatini/agent/agents/emailer/config.yaml",
        "agents/emailer/config.yaml",
    ),
    "recmailer": (
        "Tlamatini/agent/agents/recmailer/config.yaml",
        "agents/recmailer/config.yaml",
    ),
}


def _config_path() -> Path:
    path = find_config_path()
    if not path:
        raise FileNotFoundError("config.json could not be located on disk")
    return Path(path).resolve()


def _repo_root_from_config(config_path: Path) -> Path:
    # Source mode: <repo>/Tlamatini/agent/config.json
    if config_path.parent.name == "agent" and config_path.parent.parent.name == "Tlamatini":
        return config_path.parents[2]
    # Frozen mode: <install-dir>/config.json
    return config_path.parent


def _data_keys_path(repo_root: Optional[Path] = None) -> Path:
    root = repo_root or _repo_root_from_config(_config_path())
    return root / "data.keys"


def _agent_yaml_path(repo_root: Path, agent_name: str) -> Optional[Path]:
    for rel in AGENT_YAML_RELATIVE_PATHS.get(agent_name, ()):
        candidate = repo_root / Path(rel)
        if candidate.exists():
            return candidate
    return None


def _parse_keys_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    return text.startswith("<") and "goes here" in text and text.endswith(">")


def _has_real_value(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not _is_placeholder(text)


def _nested_get(data: Any, path: Iterable[str]) -> Any:
    cur = data
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _yaml_value(repo_root: Path, agent_name: str, yaml_path: Tuple[str, ...]) -> Any:
    path = _agent_yaml_path(repo_root, agent_name)
    if path is None:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return _nested_get(data, yaml_path)


def _field_status(field: WizardField, *,
                  keys: Dict[str, str],
                  config: Dict[str, Any],
                  repo_root: Path) -> Dict[str, Any]:
    sources: Dict[str, bool] = {
        "data_keys": _has_real_value(keys.get(field.key)),
    }
    if field.json_key:
        sources["config_json"] = _has_real_value(config.get(field.json_key))
    if field.acpx_env:
        acpx = config.get("acpx") if isinstance(config.get("acpx"), dict) else {}
        agents = acpx.get("agents") if isinstance(acpx.get("agents"), dict) else {}
        env_ok = True
        env_seen = False
        for agent_id, env_key in field.acpx_env:
            agent = agents.get(agent_id) if isinstance(agents, dict) else None
            env = agent.get("env") if isinstance(agent, dict) else None
            value = env.get(env_key) if isinstance(env, dict) else None
            env_seen = env_seen or value is not None
            env_ok = env_ok and _has_real_value(value)
        sources["acpx_env"] = bool(env_seen and env_ok)
    if field.yaml_rules:
        yaml_ok = True
        yaml_seen = False
        for agent_name, yaml_path, _force_quote in field.yaml_rules:
            value = _yaml_value(repo_root, agent_name, yaml_path)
            yaml_seen = yaml_seen or value is not None
            yaml_ok = yaml_ok and _has_real_value(value)
        sources["agent_yaml"] = bool(yaml_seen and yaml_ok)

    weak_default = str(keys.get(field.key) or "").strip().lower() in {"changeme", "change-me"}
    return {
        "key": field.key,
        "label": field.label,
        "group": field.group,
        "kind": field.kind,
        "required": field.required,
        "note": field.note,
        "configured": any(sources.values()),
        "sources": sources,
        "weak_default": weak_default,
    }


def _command_status(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    from .acpx.agent_registry import DEFAULT_ACP_AGENTS, build_agent_registry
    from .acpx.config import load_acpx_config
    from .acpx.windows_spawn import is_executable_resolvable

    acpx_config = load_acpx_config(config)
    registry = build_agent_registry(acpx_config.agents, acpx_config.agents_env)
    configured_agents = (
        config.get("acpx", {}).get("agents", {})
        if isinstance(config.get("acpx"), dict)
        else {}
    )
    rows: List[Dict[str, Any]] = []
    for agent_id, spec in registry.items():
        configured = configured_agents.get(agent_id)
        has_override = isinstance(configured, dict) and bool(configured.get("command"))
        rows.append({
            "agent_id": agent_id,
            "description": spec.description,
            "command": spec.command,
            "default_command": DEFAULT_ACP_AGENTS.get(agent_id, spec).command,
            "has_override": has_override,
            "resolvable": is_executable_resolvable(spec.command),
        })
    return rows


def get_access_key_wizard_status() -> Dict[str, Any]:
    """Return the masked status payload consumed by the graphical wizard."""
    config_path = _config_path()
    repo_root = _repo_root_from_config(config_path)
    keys = _parse_keys_file(_data_keys_path(repo_root))
    config = load_config(force_reload=True)

    groups = []
    configured_count = 0
    total_fields = 0
    for group in WIZARD_GROUPS:
        field_rows = []
        for field in group.fields:
            row = _field_status(field, keys=keys, config=config, repo_root=repo_root)
            field_rows.append(row)
            configured_count += 1 if row["configured"] else 0
            total_fields += 1
        groups.append({
            "key": group.key,
            "title": group.title,
            "fields": field_rows,
        })

    return {
        "success": True,
        "config_path": str(config_path),
        "data_keys_path": str(_data_keys_path(repo_root)),
        "groups": groups,
        "commands": _command_status(config),
        "summary": {
            "configured_fields": configured_count,
            "total_fields": total_fields,
        },
    }


def _upsert_keys_file(path: Path, updates: Dict[str, str]) -> bool:
    if not updates:
        return False
    original = path.read_text(encoding="utf-8") if path.exists() else (
        "# Tlamatini secrets vault - managed by Access Keys Wizard\n"
        "# Format: KEY=VALUE. Never commit this file.\n"
    )
    lines = original.splitlines()
    seen: set[str] = set()
    out: List[str] = []
    key_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in lines:
        match = key_re.match(line)
        if match:
            key = match.group(1)
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    missing = [key for key in updates if key not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# Added by Tlamatini Access Keys Wizard")
        for key in missing:
            out.append(f"{key}={updates[key]}")
    new_text = "\n".join(out).rstrip() + "\n"
    if new_text == original:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _force_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _quote_yaml_scalar(value: str, *, force_quote: bool = False) -> str:
    if force_quote:
        return _force_quote(value)
    if value == "":
        return '""'
    if re.fullmatch(r"-?\d+", value):
        return value
    if re.fullmatch(r"-?\d+\.\d+", value):
        return value
    needs_quote = (
        value[0] in "!&*[]{}|>%@`#," or
        value.lower() in {"true", "false", "yes", "no", "on", "off", "null", "~"} or
        any(ch in value for ch in [":", "#", "\n", "\t"]) or
        value != value.strip()
    )
    return _force_quote(value) if needs_quote else value


_YAML_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:(?P<rest>.*)$")


def _patch_yaml_text(text: str,
                     updates: Dict[Tuple[str, ...], Tuple[str, bool]]) -> Tuple[str, bool]:
    if not updates:
        return text, False
    lines = text.splitlines(keepends=False)
    stack: List[Tuple[int, str]] = []
    changed = False
    out: List[str] = []
    for line in lines:
        match = _YAML_KEY_RE.match(line)
        if not match:
            out.append(line)
            continue
        indent = len(match.group("indent"))
        key = match.group("key")
        rest = match.group("rest")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        path = tuple(part for _depth, part in stack)
        update = updates.get(path)
        if update is None:
            out.append(line)
            continue
        value, force_quote = update
        comment_match = re.search(r"\s+#.*$", rest)
        comment = comment_match.group(0) if comment_match else ""
        new_line = (
            f"{match.group('indent')}{key}: "
            f"{_quote_yaml_scalar(value, force_quote=force_quote)}{comment}"
        )
        changed = changed or new_line != line
        out.append(new_line)
    new_text = "\n".join(out)
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, changed


def _patch_agent_yaml_files(repo_root: Path, updates: Dict[str, str]) -> List[str]:
    by_agent: Dict[str, Dict[Tuple[str, ...], Tuple[str, bool]]] = {}
    for key, value in updates.items():
        field = FIELD_BY_KEY.get(key)
        if not field:
            continue
        for agent_name, yaml_path, force_quote in field.yaml_rules:
            by_agent.setdefault(agent_name, {})[yaml_path] = (value, force_quote)

    changed_paths: List[str] = []
    for agent_name, path_updates in by_agent.items():
        path = _agent_yaml_path(repo_root, agent_name)
        if path is None:
            continue
        original = path.read_text(encoding="utf-8")
        new_text, changed = _patch_yaml_text(original, path_updates)
        if not changed:
            continue
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, path)
        changed_paths.append(str(path))
    return changed_paths


def _patch_config_json(updates: Dict[str, str],
                       command_updates: Dict[str, str]) -> Optional[str]:
    config = load_config(force_reload=True)
    patch: Dict[str, Any] = {}

    for key, value in updates.items():
        field = FIELD_BY_KEY[key]
        if field.json_key:
            patch[field.json_key] = value

    acpx = dict(config.get("acpx") if isinstance(config.get("acpx"), dict) else {})
    agents = dict(acpx.get("agents") if isinstance(acpx.get("agents"), dict) else {})

    touched_acpx = False
    for key, value in updates.items():
        field = FIELD_BY_KEY[key]
        for agent_id, env_key in field.acpx_env:
            agent = agents.get(agent_id)
            agent = dict(agent) if isinstance(agent, dict) else {}
            env = dict(agent.get("env") if isinstance(agent.get("env"), dict) else {})
            env[env_key] = value
            agent["env"] = env
            if "command" not in agent:
                from .acpx.agent_registry import DEFAULT_ACP_AGENTS
                default = DEFAULT_ACP_AGENTS.get(agent_id)
                if default is not None:
                    agent["command"] = default.command
            agents[agent_id] = agent
            touched_acpx = True

    if command_updates:
        from .acpx.agent_registry import DEFAULT_ACP_AGENTS
        known = set(DEFAULT_ACP_AGENTS) | set(agents)
        for agent_id, command in command_updates.items():
            if agent_id not in known:
                raise ValueError(f"unknown ACPX agent_id: {agent_id}")
            agent = agents.get(agent_id)
            agent = dict(agent) if isinstance(agent, dict) else {}
            agent["command"] = command
            agents[agent_id] = agent
            touched_acpx = True

    if touched_acpx:
        acpx["agents"] = agents
        patch["acpx"] = acpx

    if not patch:
        return None
    return save_config_updates(patch)


def _reset_acpx_runtime() -> None:
    try:
        from .acpx import runtime as runtime_mod
        with runtime_mod._runtime_lock:  # type: ignore[attr-defined]
            runtime_mod._runtime_singleton = None  # type: ignore[attr-defined]
    except Exception:
        pass


def _normalize_field_updates(raw_fields: Any, *, mirror_google_alias: bool) -> Dict[str, str]:
    if raw_fields is None:
        return {}
    if not isinstance(raw_fields, dict):
        raise ValueError("fields must be a JSON object")
    updates: Dict[str, str] = {}
    for key, value in raw_fields.items():
        if key not in FIELD_BY_KEY:
            raise ValueError(f"unknown key field: {key}")
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        trimmed = value.strip()
        if trimmed:
            updates[key] = trimmed
    if (
        mirror_google_alias
        and "GEMINI_API_KEY" in updates
        and "GOOGLE_API_KEY" not in updates
    ):
        updates["GOOGLE_API_KEY"] = updates["GEMINI_API_KEY"]
    return updates


def _normalize_command_updates(raw_commands: Any) -> Dict[str, str]:
    if raw_commands is None:
        return {}
    if not isinstance(raw_commands, dict):
        raise ValueError("commands must be a JSON object")
    updates: Dict[str, str] = {}
    for agent_id, value in raw_commands.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"command for {agent_id} must be a string")
        trimmed = value.strip()
        if trimmed:
            updates[str(agent_id)] = trimmed
    return updates


def save_access_key_wizard_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist wizard values. The response never contains secret values."""
    mirror_google_alias = bool(payload.get("mirror_google_alias", True))
    field_updates = _normalize_field_updates(
        payload.get("fields"), mirror_google_alias=mirror_google_alias,
    )
    command_updates = _normalize_command_updates(payload.get("commands"))

    config_path = _config_path()
    repo_root = _repo_root_from_config(config_path)
    data_keys = _data_keys_path(repo_root)

    changed_files: List[str] = []
    if _upsert_keys_file(data_keys, field_updates):
        changed_files.append(str(data_keys))

    config_written = _patch_config_json(field_updates, command_updates)
    if config_written:
        changed_files.append(config_written)

    changed_files.extend(_patch_agent_yaml_files(repo_root, field_updates))
    _reset_acpx_runtime()

    return {
        "success": True,
        "updated_keys": sorted(field_updates.keys()),
        "updated_commands": sorted(command_updates.keys()),
        "files_changed": sorted(set(changed_files)),
        "restart_required": bool(field_updates or command_updates),
        "status": get_access_key_wizard_status(),
    }
