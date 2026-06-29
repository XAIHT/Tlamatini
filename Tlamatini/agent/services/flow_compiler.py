# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from __future__ import annotations

import csv
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .agent_contracts import AgentContract, get_agent_contract, get_password_paths, resolve_agent_type
from .agent_paths import get_agents_root, get_session_pool_path, pool_name_to_agent_type
from .flow_spec import FlowNode, FlowSpec, normalize_flow_payload


class FlowCompileError(Exception):
    pass


class _QuotedStr(str):
    """String subclass marking a value that must be emitted with double quotes
    in YAML output. The `_AgentConfigYamlDumper` registers a representer that
    forces ``style='"'`` for any instance of this class, so e.g. an Emailer
    SMTP App Password is always written as ``password: "wvqt jved ymfm kexc"``
    no matter how PyYAML's default scalar logic would have rendered the raw
    string."""


class _AgentConfigYamlDumper(yaml.SafeDumper):
    """Per-call Dumper subclass so the str / _QuotedStr representers do NOT
    leak into PyYAML's global representer table (which would affect every
    other yaml.dump call site in the process — Django views, tests, agents'
    own offset/state files, etc.)."""


def _str_representer(dumper, value):
    if "\n" in value:
        if not value.endswith("\n"):
            value = value + "\n"
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


def _quoted_str_representer(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(value), style='"')


_AgentConfigYamlDumper.add_representer(str, _str_representer)
_AgentConfigYamlDumper.add_representer(_QuotedStr, _quoted_str_representer)


def _wrap_password_values(config: dict[str, Any], password_paths: tuple[str, ...]) -> dict[str, Any]:
    if not password_paths:
        return config
    result = deepcopy(config)
    for dotted in password_paths:
        parts = [part for part in dotted.split(".") if part]
        if not parts:
            continue
        parent: Any = result
        for part in parts[:-1]:
            if not isinstance(parent, dict):
                parent = None
                break
            parent = parent.get(part)
        if isinstance(parent, dict) and parts[-1] in parent:
            current = parent[parts[-1]]
            if current is None:
                parent[parts[-1]] = _QuotedStr("")
            elif isinstance(current, _QuotedStr):
                continue
            elif isinstance(current, str):
                parent[parts[-1]] = _QuotedStr(current)
            else:
                parent[parts[-1]] = _QuotedStr(str(current))
    return result


def dump_agent_config_yaml(
    config: dict[str, Any],
    path: Path,
    agent_type: str | None = None,
) -> None:
    """Write `config` to `path` as YAML. When `agent_type` matches an agent
    that declares `password_paths`, every value at those dotted paths is
    force-double-quoted via `_QuotedStr` + `_AgentConfigYamlDumper`. This is
    the single dump path used by the Flow Compiler (Start / Validate), the
    canvas item-dialog save endpoint, and the per-agent connection-update
    views — so a password set via any of those surfaces lands on disk
    embraced by `"`, exactly as the user requires.
    """
    pwd_paths = get_password_paths(agent_type) if agent_type else ()
    payload = _wrap_password_values(config, pwd_paths)
    with Path(path).open("w", encoding="utf-8") as handle:
        yaml.dump(
            payload,
            handle,
            Dumper=_AgentConfigYamlDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in updates.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _safe_yaml_dump(data: dict[str, Any], path: Path, agent_type: str | None = None) -> None:
    """Backwards-compatible alias for `dump_agent_config_yaml`. Internal-only
    callers (this module) pass `agent_type` so password fields get force-quoted;
    callers that don't know the agent type get the same multiline-aware dump
    behavior as before, just without the password-quoting layer."""
    dump_agent_config_yaml(data, path, agent_type)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _strip_internal_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if not str(key).startswith("_")}


def _ensure_list(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key)
    if not isinstance(value, list):
        value = []
        config[key] = value
    return value


def _add_unique(config: dict[str, Any], key: str, value: str) -> None:
    target = _ensure_list(config, key)
    if value and value not in target:
        target.append(value)


def _set_connection_field(config: dict[str, Any], key: str, value: str) -> None:
    # Dialog-edited values always win over canvas-derived wiring. Singleton
    # connection fields are filled only when the user has not set them; list
    # fields get the canvas-derived entry appended via `_add_unique`, which
    # is already a no-op when the entry is present.
    if key in {"source_agent", "target_agent", "source_agent_1", "source_agent_2"}:
        if not config.get(key):
            config[key] = value
    else:
        _add_unique(config, key, value)


def _snapshot_managed_connections(config: dict[str, Any], contract: AgentContract) -> dict[str, Any]:
    snapshot = {}
    for field_name in contract.connection_fields:
        if field_name not in config:
            continue
        snapshot[field_name] = deepcopy(config[field_name])
    return snapshot


def _template_config(agent_type: str) -> dict[str, Any]:
    return _read_yaml(get_agents_root() / agent_type / "config.yaml")


def _node_by_id(spec: FlowSpec) -> dict[str, FlowNode]:
    return {node.id: node for node in spec.nodes}


def _connection_graph(spec: FlowSpec) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    forward: dict[str, list[str]] = {}
    reverse: dict[str, list[str]] = {}
    for conn in spec.connections:
        forward.setdefault(conn.source_id, []).append(conn.target_id)
        reverse.setdefault(conn.target_id, []).append(conn.source_id)
    return forward, reverse


def _collect_upstream(start_id: str, reverse: dict[str, list[str]]) -> list[str]:
    result = []
    seen = set()
    stack = [start_id]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        result.append(node_id)
        stack.extend(reverse.get(node_id, []))
    return result


def _compiled_configs(spec: FlowSpec) -> tuple[dict[str, dict[str, Any]], list[str]]:
    warnings: list[str] = []
    configs: dict[str, dict[str, Any]] = {}
    preserved: dict[str, dict[str, Any]] = {}

    for node in spec.nodes:
        contract = get_agent_contract(node.agent_type)
        merged = _deep_merge(_template_config(node.agent_type), _strip_internal_config(node.config))
        # Snapshot connection fields BEFORE the canvas-wiring pass mutates
        # `merged`. The snapshot is used by the Ender kill-list special case
        # below to detect a user-edited `target_agents` and keep it verbatim.
        # We deliberately do NOT clear the fields anymore: dialog edits win,
        # canvas wires only contribute via `_add_unique` / "fill if empty".
        preserved[node.id] = _snapshot_managed_connections(merged, contract)
        configs[node.id] = merged

    nodes = _node_by_id(spec)
    _, reverse = _connection_graph(spec)

    for conn in spec.connections:
        source = nodes.get(conn.source_id)
        target = nodes.get(conn.target_id)
        if not source or not target:
            warnings.append(f"Skipped connection with missing endpoint: {conn.source_id} -> {conn.target_id}")
            continue

        source_contract = get_agent_contract(source.agent_type)
        target_contract = get_agent_contract(target.agent_type)

        output_field = source_contract.output_field_by_slot.get(
            conn.output_slot,
            source_contract.output_field_by_slot.get(0, "target_agents"),
        )
        if output_field:
            _set_connection_field(configs[source.id], output_field, target.pool_name)

        input_field = target_contract.input_field_by_slot.get(
            conn.input_slot,
            target_contract.input_field_by_slot.get(0, "source_agents"),
        )
        if input_field:
            _set_connection_field(configs[target.id], input_field, source.pool_name)

    # Ender has a special kill-list contract: direct input is graphical,
    # target_agents is every upstream runtime agent except cleaners. With
    # "dialog edits always win", a user-populated `target_agents` is kept
    # verbatim — the kill-list derivation only fires when the field was
    # empty BEFORE the canvas pass touched it.
    for node in spec.nodes:
        if node.agent_type != "ender":
            continue
        user_targets = preserved.get(node.id, {}).get("target_agents")
        if isinstance(user_targets, list) and user_targets:
            configs[node.id]["target_agents"] = user_targets
            continue
        incoming = [conn.source_id for conn in spec.connections if conn.target_id == node.id]
        if not incoming:
            if isinstance(user_targets, list):
                configs[node.id]["target_agents"] = user_targets
            continue
        kill_list: list[str] = []
        for incoming_id in incoming:
            for upstream_id in _collect_upstream(incoming_id, reverse):
                upstream = nodes.get(upstream_id)
                if not upstream or upstream.id == node.id or upstream.agent_type == "cleaner":
                    continue
                if upstream.pool_name not in kill_list:
                    kill_list.append(upstream.pool_name)
        configs[node.id]["target_agents"] = kill_list

    for node in spec.nodes:
        if node.agent_type != "parametrizer":
            continue
        config = configs[node.id]
        sources = config.get("source_agents")
        targets = config.get("target_agents")
        if isinstance(sources, list) and len(sources) == 1:
            config["source_agent"] = sources[0]
        if isinstance(targets, list) and len(targets) == 1:
            config["target_agent"] = targets[0]
        if isinstance(sources, list) and len(sources) > 1:
            warnings.append(f"{node.pool_name} has {len(sources)} sources; Parametrizer expects exactly one.")
        if isinstance(targets, list) and len(targets) > 1:
            warnings.append(f"{node.pool_name} has {len(targets)} targets; Parametrizer expects exactly one.")

    for node in spec.nodes:
        if node.agent_type == "monitor_log":
            target = configs[node.id].setdefault("target", {})
            if isinstance(target, dict):
                target["logfile_path"] = f"{node.pool_name}.log"

    return configs, warnings


def _ensure_pool_agent(node: FlowNode, pool_path: Path) -> Path:
    source_dir = get_agents_root() / node.agent_type
    if not source_dir.exists():
        raise FlowCompileError(f"Source agent not found: {node.agent_type}")

    pool_dir = pool_path / node.pool_name
    if not pool_dir.exists():
        shutil.copytree(source_dir, pool_dir)
        return pool_dir

    source_script = source_dir / f"{node.agent_type}.py"
    if source_script.exists():
        shutil.copy2(source_script, pool_dir / source_script.name)

    return pool_dir


def _parametrizer_mappings_for_node(spec: FlowSpec, node: FlowNode) -> list[dict[str, Any]]:
    mappings = node.config.get("_parametrizer_mappings")
    if isinstance(mappings, list):
        return mappings

    artifacts = spec.artifacts or {}
    candidates = [
        artifacts.get("parametrizerMappings"),
        artifacts.get("parametrizer_mappings"),
        artifacts.get("parametrizerSchemes"),
        artifacts.get("parametrizer_schemes"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        value = candidate.get(node.id) or candidate.get(node.pool_name)
        if isinstance(value, list):
            return value
    return []


def _write_parametrizer_scheme(pool_dir: Path, mappings: list[dict[str, Any]]) -> int:
    scheme_path = pool_dir / "interconnection-scheme.csv"
    saved = 0
    with scheme_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_field", "target_param", "target_marker"])
        writer.writeheader()
        for mapping in mappings:
            source_field = str(mapping.get("source_field", "")).strip()
            target_param = str(mapping.get("target_param", "")).strip()
            target_marker = str(mapping.get("target_marker", "")).strip().strip("{}").strip()
            if not source_field or not target_param:
                continue
            writer.writerow(
                {
                    "source_field": source_field,
                    "target_param": target_param,
                    "target_marker": target_marker,
                }
            )
            saved += 1
    return saved


def compile_flow_spec(
    spec: FlowSpec,
    *,
    request=None,
    session_id: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    configs, warnings = _compiled_configs(spec)
    agents = []

    pool_path = get_session_pool_path(request=request, session_id=session_id)
    if write:
        pool_path.mkdir(parents=True, exist_ok=True)

    for node in spec.nodes:
        contract = get_agent_contract(node.agent_type)
        config = configs[node.id]
        if write:
            pool_dir = _ensure_pool_agent(node, pool_path)
            _safe_yaml_dump(config, pool_dir / "config.yaml", node.agent_type)
            if node.agent_type == "parametrizer":
                count = _write_parametrizer_scheme(pool_dir, _parametrizer_mappings_for_node(spec, node))
                if count:
                    warnings.append(f"Saved {count} Parametrizer mapping(s) for {node.pool_name}.")

        if not contract.exclude_from_validation:
            agents.append(
                {
                    "folder_name": node.pool_name,
                    "agent_type": node.agent_type,
                    "config": config,
                }
            )

    return {
        "success": True,
        "write": write,
        "pool_path": str(pool_path),
        "agents": agents,
        "warnings": warnings,
    }


def compile_flow_payload(payload: dict[str, Any], *, request=None, write: bool = False) -> dict[str, Any]:
    spec = normalize_flow_payload(payload)
    return compile_flow_spec(spec, request=request, write=write)


def list_pool_agents_for_validation(request) -> list[dict[str, Any]]:
    pool_path = get_session_pool_path(request=request)
    if not pool_path.exists():
        return []
    agents = []
    for folder_name in sorted(os.listdir(pool_path)):
        folder_path = pool_path / folder_name
        if not folder_path.is_dir():
            continue
        if folder_name == "_chat_runs_":
            continue
        agent_type = resolve_agent_type(pool_name_to_agent_type(folder_name))
        contract = get_agent_contract(agent_type)
        if contract.exclude_from_validation:
            continue
        agents.append(
            {
                "folder_name": folder_name,
                "agent_type": agent_type,
                "config": _read_yaml(folder_path / "config.yaml"),
            }
        )
    return agents
