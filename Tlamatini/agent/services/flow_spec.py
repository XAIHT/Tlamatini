from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agent_contracts import get_agent_contract, resolve_agent_type
from .agent_paths import display_name_from_agent_type, parse_canvas_agent_name, pool_name_from_canvas_id


@dataclass
class FlowNode:
    id: str
    text: str
    left: str = "0px"
    top: str = "0px"
    agent_purpose: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def agent_type(self) -> str:
        try:
            base, _ = parse_canvas_agent_name(self.id)
        except ValueError:
            base = resolve_agent_type(self.text)
        return resolve_agent_type(base)

    @property
    def pool_name(self) -> str:
        return pool_name_from_canvas_id(self.id)


@dataclass
class FlowConnection:
    source_id: str
    target_id: str
    input_slot: int = 0
    output_slot: int = 0


@dataclass
class FlowSpec:
    nodes: list[FlowNode]
    connections: list[FlowConnection]
    artifacts: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 2


def _intish(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _node_id_from_text(text: str, counters: dict[str, int]) -> str:
    agent_type = resolve_agent_type(text)
    contract = get_agent_contract(agent_type)
    if contract.singleton:
        return agent_type.replace("_", "-")
    counters[agent_type] = counters.get(agent_type, 0) + 1
    return f"{agent_type.replace('_', '-')}-{counters[agent_type]}"


def normalize_flow_payload(payload: dict[str, Any]) -> FlowSpec:
    raw_nodes = payload.get("nodes") or []
    raw_connections = payload.get("connections") or []
    artifacts = payload.get("artifacts") or {}

    counters: dict[str, int] = {}
    nodes: list[FlowNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or raw.get("agentName") or raw.get("agent_name") or "")
        node_id = str(raw.get("id") or "") or _node_id_from_text(text, counters)
        config = raw.get("configData")
        if config is None:
            config = raw.get("config")
        if not isinstance(config, dict):
            config = {}
        nodes.append(
            FlowNode(
                id=node_id,
                text=text or display_name_from_agent_type(node_id),
                left=str(raw.get("left") or "0px"),
                top=str(raw.get("top") or "0px"),
                agent_purpose=str(raw.get("agentPurpose") or raw.get("agent_purpose") or ""),
                config=dict(config),
            )
        )

    connections: list[FlowConnection] = []
    for raw in raw_connections:
        if not isinstance(raw, dict):
            continue
        source_id = raw.get("sourceId")
        target_id = raw.get("targetId")
        if source_id is None and raw.get("sourceIndex") is not None:
            idx = _intish(raw.get("sourceIndex"), -1)
            if 0 <= idx < len(nodes):
                source_id = nodes[idx].id
        if target_id is None and raw.get("targetIndex") is not None:
            idx = _intish(raw.get("targetIndex"), -1)
            if 0 <= idx < len(nodes):
                target_id = nodes[idx].id
        if not source_id or not target_id:
            continue
        connections.append(
            FlowConnection(
                source_id=str(source_id),
                target_id=str(target_id),
                input_slot=_intish(raw.get("inputSlot"), 0),
                output_slot=_intish(raw.get("outputSlot"), 0),
            )
        )

    return FlowSpec(
        nodes=nodes,
        connections=connections,
        artifacts=artifacts if isinstance(artifacts, dict) else {},
        schema_version=_intish(payload.get("schemaVersion"), 2),
    )


def flow_spec_to_legacy_json(spec: FlowSpec, *, redact: bool = False) -> dict[str, Any]:
    from .agent_contracts import redact_config_for_export

    node_index = {node.id: index for index, node in enumerate(spec.nodes)}
    nodes = []
    for node in spec.nodes:
        config = node.config
        if redact:
            config = redact_config_for_export(node.agent_type, config)
        nodes.append(
            {
                "id": node.id,
                "text": node.text,
                "left": node.left,
                "top": node.top,
                "agentPurpose": node.agent_purpose,
                "configData": config,
            }
        )

    connections = []
    for conn in spec.connections:
        if conn.source_id not in node_index or conn.target_id not in node_index:
            continue
        connections.append(
            {
                "sourceIndex": node_index[conn.source_id],
                "targetIndex": node_index[conn.target_id],
                "sourceId": conn.source_id,
                "targetId": conn.target_id,
                "inputSlot": conn.input_slot,
                "outputSlot": conn.output_slot,
            }
        )

    return {
        "schemaVersion": spec.schema_version,
        "nodes": nodes,
        "connections": connections,
        "artifacts": spec.artifacts,
    }
