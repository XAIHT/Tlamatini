import logging
from dataclasses import dataclass
from typing import Any, Iterable

from .capability_registry import (
    _RUN_CONTROL_TOOL_NAMES,
    _RUN_ID_RE,
    _normalize_text,
    _score_capability,
    _tokenize,
    build_tool_capabilities,
    select_context_capabilities_for_request,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GlobalPlanNode:
    node_id: str
    stage: str
    capability_type: str
    capability_key: str
    depends_on: tuple[str, ...] = ()
    parallel_group: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "stage": self.stage,
            "capability_type": self.capability_type,
            "capability_key": self.capability_key,
            "depends_on": list(self.depends_on),
            "parallel_group": self.parallel_group,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GlobalExecutionPlan:
    request_text: str
    planner_version: str
    execution_mode: str
    selected_contexts: tuple[str, ...]
    selected_tool_names: tuple[str, ...]
    selected_wrapped_agent_names: tuple[str, ...]
    selected_run_control_names: tuple[str, ...]
    notes: tuple[str, ...]
    nodes: tuple[GlobalPlanNode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_text": self.request_text,
            "planner_version": self.planner_version,
            "execution_mode": self.execution_mode,
            "selected_contexts": list(self.selected_contexts),
            "selected_tool_names": list(self.selected_tool_names),
            "selected_wrapped_agent_names": list(self.selected_wrapped_agent_names),
            "selected_run_control_names": list(self.selected_run_control_names),
            "notes": list(self.notes),
            "nodes": [node.to_dict() for node in self.nodes],
        }


def _reason_for_context(context_key: str) -> str:
    if context_key == "system_context":
        return "Prefetch system MCP context because the request references host state, resources, or runtime metrics."
    if context_key == "files_context":
        return "Prefetch files MCP context because the request references project files, paths, or source content."
    return "Prefetch MCP context selected by the global planner."


def _reason_for_tool(capability_kind: str, tool_name: str) -> str:
    if capability_kind == "wrapped_agent":
        return (
            f"Plan wrapped agent '{tool_name}' because the request asks for an isolated agent-backed action "
            "or long-running execution."
        )
    if capability_kind == "template_agent":
        return (
            f"Plan template-agent control tool '{tool_name}' because the request targets agent lifecycle management."
        )
    if capability_kind == "run_control":
        return (
            f"Plan run-control tool '{tool_name}' so wrapped agent runs can be monitored, inspected, or stopped."
        )
    return f"Plan tool '{tool_name}' because the request matches its capability hints."


def _select_planner_tool_names(
    request_text: str,
    tools: Iterable,
    *,
    selected_contexts: tuple[str, ...],
    max_selected: int = 50,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    tools_list = list(tools)
    if not tools_list:
        return (), (), (), ("No tool or agent capabilities are enabled for planning.",)

    capabilities = build_tool_capabilities(tools_list)
    normalized_request = _normalize_text(request_text)
    request_tokens = _tokenize(normalized_request)

    scored: list[tuple[int, int, Any]] = []
    for index, capability in enumerate(capabilities):
        score = _score_capability(capability, normalized_request, request_tokens)
        scored.append((score, index, capability))
        logger.info("[Planner._select] tool=%s kind=%s score=%d", capability.tool_name, capability.kind, score)

    positive = [item for item in scored if item[0] > 0]
    if not positive:
        notes = (
            "No tool or agent capability crossed the planner threshold; answer should rely on prefetched context and the base model.",
        )
        return (), (), (), notes

    positive.sort(key=lambda item: (-item[0], item[1], item[2].tool_name))

    # Run-control tools (list/status/log/stop) are auto-injected whenever
    # wrapped agents are selected, so they must NOT inflate top_score or
    # the dynamic floor — otherwise they crowd out the actual agent tools.
    non_control_positive = [
        item for item in positive
        if item[2].tool_name not in _RUN_CONTROL_TOOL_NAMES
    ]
    top_score = non_control_positive[0][0] if non_control_positive else positive[0][0]
    logger.info("[Planner._select] top_score=%d (excluding run-control)", top_score)

    threshold = 6 if selected_contexts else 2
    if top_score < threshold and not _RUN_ID_RE.search(normalized_request):
        notes = (
            "Context capabilities are sufficient for this request; the planner intentionally scheduled no tool or agent execution stage.",
        )
        return (), (), (), notes

    # Every tool that scored above the entry threshold is selected.
    # The old approach used a tight dynamic floor that aggressively
    # cut tools when another tool scored very high — this broke
    # multi-step requests where 4+ different agents were named
    # using natural language (scoring ~20-24) while monitoring
    # tools scored ~58.  Now we let scoring and the cap do the work.
    logger.info("[Planner._select] threshold=%d, max_selected=%d", threshold, max_selected)

    selected_names: list[str] = []
    for score, _index, capability in positive:
        if len(selected_names) >= max_selected:
            break
        # Skip run-control tools here; they are auto-injected below.
        if capability.tool_name in _RUN_CONTROL_TOOL_NAMES:
            continue
        if score < threshold:
            continue
        selected_names.append(capability.tool_name)
        logger.info("[Planner._select] SELECTED tool=%s score=%d", capability.tool_name, score)

    selected_wrapped_agent_names = tuple(
        capability.tool_name
        for _score, _index, capability in positive
        if capability.kind == "wrapped_agent" and capability.tool_name in selected_names
    )
    selected_run_control_names: list[str] = []

    if selected_wrapped_agent_names or _RUN_ID_RE.search(normalized_request):
        for control_name in _RUN_CONTROL_TOOL_NAMES:
            if any(tool.name == control_name for tool in tools_list):
                selected_run_control_names.append(control_name)
                if control_name not in selected_names:
                    selected_names.append(control_name)

    ordered_selected_names = tuple(
        tool.name for tool in tools_list
        if tool.name in set(selected_names)
    )
    notes = (
        f"Planner threshold={threshold}, top_tool_score={top_score}, selected_tools={len(ordered_selected_names)}.",
    )
    return (
        ordered_selected_names,
        selected_wrapped_agent_names,
        tuple(selected_run_control_names),
        notes,
    )


def build_global_execution_plan(
    request_text: str,
    tools: Iterable,
    *,
    system_enabled: bool,
    files_enabled: bool,
    max_selected_tools: int = 50,
) -> GlobalExecutionPlan:
    tools_list = list(tools)
    selected_contexts = select_context_capabilities_for_request(
        request_text,
        system_enabled=system_enabled,
        files_enabled=files_enabled,
    )
    (
        selected_tool_names,
        selected_wrapped_agent_names,
        selected_run_control_names,
        notes,
    ) = _select_planner_tool_names(
        request_text,
        tools_list,
        selected_contexts=selected_contexts,
        max_selected=max_selected_tools,
    )

    capability_map = {
        capability.tool_name: capability
        for capability in build_tool_capabilities(tools_list)
    }
    nodes: list[GlobalPlanNode] = []

    context_node_ids: list[str] = []
    for context_key in selected_contexts:
        node_id = f"prefetch:{context_key}"
        context_node_ids.append(node_id)
        nodes.append(GlobalPlanNode(
            node_id=node_id,
            stage="prefetch",
            capability_type="context",
            capability_key=context_key,
            depends_on=("request:start",),
            parallel_group="context_prefetch",
            reason=_reason_for_context(context_key),
        ))

    execution_dependency_ids = tuple(context_node_ids) or ("request:start",)
    execute_node_ids: list[str] = []
    wrapped_execute_node_ids: list[str] = []
    monitor_node_ids: list[str] = []

    for tool_name in selected_tool_names:
        if tool_name in selected_run_control_names:
            continue
        capability = capability_map.get(tool_name)
        capability_kind = getattr(capability, "kind", "tool")
        node_id = f"execute:{tool_name}"
        execute_node_ids.append(node_id)
        if capability_kind == "wrapped_agent":
            wrapped_execute_node_ids.append(node_id)
        nodes.append(GlobalPlanNode(
            node_id=node_id,
            stage="execute",
            capability_type=capability_kind,
            capability_key=tool_name,
            depends_on=execution_dependency_ids,
            parallel_group="tool_execution",
            reason=_reason_for_tool(capability_kind, tool_name),
        ))

    if selected_run_control_names:
        monitor_dependencies = tuple(wrapped_execute_node_ids) or tuple(execute_node_ids) or execution_dependency_ids
        for tool_name in selected_run_control_names:
            node_id = f"monitor:{tool_name}"
            monitor_node_ids.append(node_id)
            nodes.append(GlobalPlanNode(
                node_id=node_id,
                stage="monitor",
                capability_type="run_control",
                capability_key=tool_name,
                depends_on=monitor_dependencies,
                parallel_group="run_monitoring",
                reason=_reason_for_tool("run_control", tool_name),
            ))

    answer_dependencies = tuple(node.node_id for node in nodes) or ("request:start",)
    nodes.append(GlobalPlanNode(
        node_id="answer:final",
        stage="answer",
        capability_type="answer",
        capability_key="final_response",
        depends_on=answer_dependencies,
        parallel_group="",
        reason="Synthesize the final response from all prefetched MCP contexts, planned tool outputs, and agent run observations.",
    ))

    if selected_tool_names:
        execution_mode = "tool_augmented"
    elif selected_contexts:
        execution_mode = "context_only"
    else:
        execution_mode = "direct_model"

    return GlobalExecutionPlan(
        request_text=request_text,
        planner_version="phase3_global_dag_v1",
        execution_mode=execution_mode,
        selected_contexts=tuple(selected_contexts),
        selected_tool_names=tuple(selected_tool_names),
        selected_wrapped_agent_names=tuple(selected_wrapped_agent_names),
        selected_run_control_names=tuple(selected_run_control_names),
        notes=tuple(notes),
        nodes=tuple(nodes),
    )


def summarize_global_execution_plan(plan_like: dict[str, Any] | GlobalExecutionPlan) -> str:
    if isinstance(plan_like, GlobalExecutionPlan):
        plan = plan_like.to_dict()
    else:
        plan = dict(plan_like or {})

    lines = [
        f"Planner version: {plan.get('planner_version', 'unknown')}",
        f"Execution mode: {plan.get('execution_mode', 'unknown')}",
    ]

    selected_contexts = plan.get("selected_contexts", []) or []
    selected_tools = plan.get("selected_tool_names", []) or []
    if selected_contexts:
        lines.append("Selected MCP contexts: " + ", ".join(str(item) for item in selected_contexts))
    else:
        lines.append("Selected MCP contexts: none")

    if selected_tools:
        lines.append("Selected tools/agents: " + ", ".join(str(item) for item in selected_tools))
    else:
        lines.append("Selected tools/agents: none")

    nodes = plan.get("nodes", []) or []
    if nodes:
        lines.append("Planned DAG nodes:")
        for index, node in enumerate(nodes, start=1):
            stage = node.get("stage", "unknown")
            capability = node.get("capability_key", "")
            depends_on = node.get("depends_on", []) or []
            dependency_suffix = f" depends_on={','.join(depends_on)}" if depends_on else ""
            lines.append(f"{index}. [{stage}] {capability}{dependency_suffix}")

    notes = plan.get("notes", []) or []
    if notes:
        lines.append("Planner notes:")
        for note in notes:
            lines.append(f"- {note}")
    return "\n".join(lines)


def selected_contexts_from_plan(plan_like: dict[str, Any] | GlobalExecutionPlan) -> tuple[str, ...]:
    if isinstance(plan_like, GlobalExecutionPlan):
        return tuple(plan_like.selected_contexts)
    return tuple(plan_like.get("selected_contexts", []) or ())


def selected_tool_names_from_plan(plan_like: dict[str, Any] | GlobalExecutionPlan) -> tuple[str, ...]:
    if isinstance(plan_like, GlobalExecutionPlan):
        return tuple(plan_like.selected_tool_names)
    return tuple(plan_like.get("selected_tool_names", []) or ())
