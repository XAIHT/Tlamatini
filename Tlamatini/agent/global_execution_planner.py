# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import logging
from dataclasses import dataclass
from typing import Any, Iterable

from .capability_registry import (
    ACPX_CO_SELECTION_RULES,
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


# ── Self-source intent (read / explain / modify YOUR OWN code) ───────────────
# When the user asks about Tlamatini's own source code, the file read+inspect
# toolset must ALWAYS be bound in Multi-Turn so she can actually open and reason
# about her code instead of answering only from her injected self-knowledge.
# These names are force-selected (bypassing scoring, the threshold, and the
# max_selected cap) whenever the request matches AND the tool is enabled.
_SELF_SOURCE_PHRASES: tuple[str, ...] = (
    "your source code", "your own source code", "your own source", "your source",
    "your code", "your own code", "your codebase", "your code base",
    "your implementation", "your internals", "your own files", "your files",
    "read your source", "read your code", "explain your code", "explain your source",
    "analyze your code", "analyse your code", "summarize your code", "summarise your code",
    "summary of your code", "summary of your source", "walk through your code",
    "how are you coded", "how you are coded", "how are you programmed",
    "how are you built", "how were you built", "how are you architected",
    "modify your", "modify yourself", "change your code", "change your source",
    "edit your code", "edit your source", "rewrite your", "tlamatini source code",
)

_SELF_SOURCE_EXPLORE_TOOLS: tuple[str, ...] = (
    "chat_agent_globber",
    "chat_agent_grepper",
    "chat_agent_file_interpreter",
    "chat_agent_file_extractor",
    "chat_agent_editor",
)


def _is_self_source_request(normalized_request: str) -> bool:
    """True when the user is asking about / to read / modify Tlamatini's OWN code."""
    return any(phrase in normalized_request for phrase in _SELF_SOURCE_PHRASES)


def _self_source_force_names(tools_list: list) -> tuple[str, ...]:
    """Self-source exploration tools that are actually enabled (registry order)."""
    available = {getattr(tool, "name", "") for tool in tools_list}
    return tuple(name for name in _SELF_SOURCE_EXPLORE_TOOLS if name in available)


def _external_mcp_force_names(normalized_request: str, tools_list: list) -> tuple[str, ...]:
    """External-MCP tools (named ``ext__<server>__<tool>`` by external_mcp_manager)
    to force-bind when the user references them — by naming the server (e.g.
    "redis mcp") or saying "mcp" / "external". Closes the "connected but not
    planner-bound" gap: once a server is live its tools are in tools_list, and
    naming it must reliably select them. Bounded so it can't flood the surface.
    Only ever forces tools that are actually present (i.e. the server connected).
    """
    supervisor = {
        "external_mcp_status",
        "external_mcp_reconnect",
        "external_mcp_doctor",
        "external_mcp_list_tools",
        "external_mcp_call",
        "external_mcp_import",
        "external_mcp_set_active",
        "external_mcp_wait",
    }
    available = {getattr(t, "name", "") for t in tools_list}
    ext_names = [
        getattr(t, "name", "") for t in tools_list
        if getattr(t, "name", "").startswith("ext__")
    ]
    supervisor_names = [name for name in supervisor if name in available]
    if not ext_names and not supervisor_names:
        return ()
    tokens = set(normalized_request.split())
    generic = bool(tokens & {"mcp", "mcps", "external", "roblox", "studio"})
    by_server: dict[str, list[str]] = {}
    for name in ext_names:
        parts = name.split("__")
        server = parts[1] if len(parts) > 2 else ""
        by_server.setdefault(server, []).append(name)

    named_servers: list[str] = []
    for server in by_server:
        server_words = server.replace("-", " ").replace("_", " ").lower().strip()
        named = bool(server_words) and (
            server.lower() in normalized_request
            or server_words in normalized_request
            or any(w in tokens for w in server_words.split())
        )
        if named:
            named_servers.append(server)

    forced: list[str] = []
    if generic or named_servers:
        forced.extend(supervisor_names)

    direct_limit_per_server = 128
    if named_servers:
        for server in named_servers:
            forced.extend(by_server.get(server, [])[:direct_limit_per_server])
    elif generic and len(by_server) == 1:
        # If there is only one active external MCP server, generic "use the MCP"
        # means that server. For many active servers, keep the prompt sane and
        # rely on external_mcp_list_tools + external_mcp_call as the dispatcher.
        only_server = next(iter(by_server))
        forced.extend(by_server[only_server][:direct_limit_per_server])

    return tuple(dict.fromkeys(forced))


def _select_planner_tool_names(
    request_text: str,
    tools: Iterable,
    *,
    selected_contexts: tuple[str, ...],
    max_selected: int = 20,
    chat_history_text: str = "",
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    tools_list = list(tools)
    if not tools_list:
        return (), (), (), ("No tool or agent capabilities are enabled for planning.",)

    capabilities = build_tool_capabilities(tools_list)
    normalized_request = _normalize_text(request_text)
    request_tokens = _tokenize(normalized_request)

    # When the current message is short (e.g. "continue", "go ahead"),
    # score tools against the recent chat history as well so that
    # follow-up messages carry forward tool relevance from prior turns.
    history_boost_tokens: set[str] = set()
    history_boost_text: str = ""
    is_short_followup = len(request_tokens - {"continue", "go", "ahead", "proceed", "yes", "ok", "do"}) < 4
    if is_short_followup and chat_history_text:
        history_boost_text = _normalize_text(chat_history_text)
        history_boost_tokens = _tokenize(history_boost_text)

    scored: list[tuple[int, int, Any]] = []
    for index, capability in enumerate(capabilities):
        score = _score_capability(capability, normalized_request, request_tokens)
        # Apply history boost for short follow-up messages
        if history_boost_tokens:
            history_score = _score_capability(capability, history_boost_text, history_boost_tokens)
            # Use half of the history score as a boost (capped at 15)
            score += min(history_score // 2, 15)
        scored.append((score, index, capability))
        logger.info("[Planner._select] tool=%s kind=%s score=%d", capability.tool_name, capability.kind, score)

    # Self-source intent: when the user asks to read / explain / analyze /
    # modify YOUR OWN source code, force-bind the file read+inspect toolset so a
    # Multi-Turn run can ALWAYS go read the real code instead of answering only
    # from self-knowledge. These bypass scoring + threshold + the max_selected
    # cap on purpose (same idea as run-control / ACPX-sibling auto-injection);
    # only tools that are actually enabled (present in tools_list) are forced.
    forced_self_source_names = (
        _self_source_force_names(tools_list)
        if _is_self_source_request(normalized_request) else ()
    )
    # External-MCP intent: when the user references an active external MCP server,
    # force-bind its ext__* tools so naming it ("using redis mcp …") reliably
    # selects them once it has connected and exposed tools.
    forced_external_mcp_names = _external_mcp_force_names(normalized_request, tools_list)
    forced_names = tuple(dict.fromkeys(forced_self_source_names + forced_external_mcp_names))

    positive = [item for item in scored if item[0] > 0]
    if not positive and not forced_names:
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
    top_score = (
        non_control_positive[0][0] if non_control_positive
        else (positive[0][0] if positive else 0)
    )
    logger.info("[Planner._select] top_score=%d (excluding run-control)", top_score)

    threshold = 6 if selected_contexts else 2
    if (top_score < threshold and not _RUN_ID_RE.search(normalized_request)
            and not forced_names):
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
    # Force-bind the self-source exploration tools FIRST (bypass score + cap).
    for forced in forced_names:
        if forced not in selected_names:
            selected_names.append(forced)
            logger.info("[Planner._select] FORCE-SELECTED tool=%s reason=self_source_intent", forced)

    for score, _index, capability in positive:
        if len(selected_names) >= max_selected:
            break
        # Skip run-control tools here; they are auto-injected below.
        if capability.tool_name in _RUN_CONTROL_TOOL_NAMES:
            continue
        if score < threshold:
            continue
        if capability.tool_name in selected_names:
            continue
        selected_names.append(capability.tool_name)
        logger.info("[Planner._select] SELECTED tool=%s score=%d", capability.tool_name, score)

    capability_by_name = {capability.tool_name: capability for capability in capabilities}
    selected_wrapped_agent_names = tuple(
        name for name in selected_names
        if capability_by_name.get(name) is not None
        and capability_by_name[name].kind == "wrapped_agent"
    )
    selected_run_control_names: list[str] = []

    if selected_wrapped_agent_names or _RUN_ID_RE.search(normalized_request):
        for control_name in _RUN_CONTROL_TOOL_NAMES:
            if any(tool.name == control_name for tool in tools_list):
                selected_run_control_names.append(control_name)
                if control_name not in selected_names:
                    selected_names.append(control_name)

    # ACPX co-selection: if a primary ACPX tool made the cut, pull in
    # its operational siblings (e.g. acp_spawn → acp_doctor + acp_kill,
    # acp_relay → acp_transcript + acp_kill). The siblings bypass the
    # max_selected cap on purpose — they are operationally required, not
    # additional candidates. Same shape as run-control auto-injection.
    available_names = {tool.name for tool in tools_list}
    for primary, siblings in ACPX_CO_SELECTION_RULES.items():
        if primary in selected_names:
            for sibling in siblings:
                if sibling in available_names and sibling not in selected_names:
                    selected_names.append(sibling)
                    logger.info("[Planner._select] CO-SELECTED tool=%s reason=acpx_sibling_of:%s",
                                sibling, primary)

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
    max_selected_tools: int = 20,
    chat_history_text: str = "",
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
        chat_history_text=chat_history_text,
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
