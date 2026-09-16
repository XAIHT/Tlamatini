"""Standalone contract-aware flow planning helpers; no Django or application imports."""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path


def load_catalog():
    catalog = json.loads(Path(__file__).with_name("flow_catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not catalog.get("agents"):
        raise ValueError("Missing or unsupported installed-agent catalog; redeploy this agent")
    return catalog["agents"]


def normalize(value):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", str(value).strip().lower())).strip("_")


def resolve(value, catalog):
    key = normalize(value)
    for name, spec in catalog.items():
        if key == name or key in spec["aliases"]:
            return name
    raise ValueError(f"Unknown/uninstalled agent type: {value}")


def roster_prompt(catalog):
    rows = [f"{name}: {spec['purpose'][:360]}" for name, spec in catalog.items()]
    return (
        "Select the installed agents needed for the user's objective, including control, "
        "data-mapping and verification steps. Return ONLY a JSON array of canonical type strings. "
        "This is capability selection, not a flow. GUI-Manager is a design, not an installed agent.\n"
        + "\n".join(rows)
    )


def select_types(response, catalog):
    text = response.strip()
    start, end = text.find("["), text.rfind("]")
    chosen = json.loads(text[start:end + 1])
    if not isinstance(chosen, list) or not chosen or not all(isinstance(x, str) for x in chosen):
        raise ValueError("Capability selection must be a nonempty JSON array of agent types")
    # Lifecycle and value mapping are always available to the design stage.
    return sorted({resolve(x, catalog) for x in chosen} | {"starter", "ender", "parametrizer"})


def guide_sections(guide, catalog):
    result = {}
    reference = guide.split("## Available Agents", 1)[1].split("## Output Format", 1)[0]
    chunks = re.split(r"(?m)^### (?:\d+[a-z]?\. )?", reference)
    for chunk in chunks[1:]:
        title = chunk.splitlines()[0].strip().strip("*")
        key = re.sub(r"[^a-z0-9]", "", title.lower())
        for name, spec in catalog.items():
            aliases = [name, spec["display_name"], *spec["aliases"]]
            if any(key == re.sub(r"[^a-z0-9]", "", alias.lower()) for alias in aliases):
                result[name] = "### " + chunk.strip()
    return result


def design_prompt(guide, catalog, selected):
    details = guide_sections(guide, catalog)
    missing = set(catalog) - set(details)
    if missing:
        raise ValueError("Agent guide coverage missing: " + ", ".join(sorted(missing)))
    # Keep global rules and examples; include detailed reference only for selected agents.
    prefix, rest = guide.split("## Available Agents", 1)
    _, suffix = rest.split("## Output Format", 1)
    schemas = {name: catalog[name] for name in selected}
    return (
        prefix + "\n## Selected agent references\n" + "\n\n".join(details[n] for n in selected)
        + "\n## Output Format" + suffix
        + "\n## Authoritative installed contracts\n"
        + "These current field types, slots and lifecycle flags override older examples. "
        "Use only the selected types below; unsupported or uncertain requirements must not be invented. "
        "Fields marked nullable have no inferred scalar type. Credentials and local values are deliberately omitted.\n"
        + json.dumps(schemas, ensure_ascii=False, separators=(",", ":"))
    )


def _check_config(value, schema, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    for key, item in value.items():
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"{path}.{key} must be finite")
        if key == "_parametrizer_mappings":
            if path != "parametrizer" or not isinstance(item, list):
                raise ValueError(f"{path}.{key} must be a list")
            continue
        if key not in schema:
            raise ValueError(f"Unknown config field: {path}.{key}")
        expected = schema[key]
        if isinstance(expected, dict):
            # Empty dictionaries are extension maps (HTTP headers, tool params, etc.).
            if expected and key not in {"headers", "params", "tool_arguments", "tool_args", "arguments", "env"}:
                _check_config(item, expected, f"{path}.{key}")
            elif not isinstance(item, dict):
                raise ValueError(f"{path}.{key} must be an object")
        elif expected != "nullable":
            valid = {"list": isinstance(item, list), "bool": isinstance(item, bool),
                     "int": type(item) is int, "number": type(item) in (int, float),
                     "str": isinstance(item, str)}[expected]
            if not valid:
                raise ValueError(f"{path}.{key} must have type {expected}")


def _slots(spec, direction):
    result = {}
    for slot, field in spec[direction + "_slots"].items():
        # 0 is a compatibility alias for branch/input slot 1.
        result[field] = max(result.get(field, 0), int(slot))
    return result


def build_flow(agents, catalog):
    if not isinstance(agents, list) or not agents:
        raise ValueError("A flow must contain agent definitions")
    nodes, names, counts, definitions = [], {}, {}, []
    for i, agent in enumerate(agents):
        if not isinstance(agent, dict):
            raise ValueError("Every agent definition must be an object")
        name = resolve(agent.get("agent_type", ""), catalog)
        spec = catalog[name]
        config = copy.deepcopy(agent.get("config", {}))
        _check_config(config, spec["config_schema"], name)
        counts[name] = counts.get(name, 0) + 1
        if spec["singleton"] and counts[name] > 1:
            raise ValueError(f"Only one {name} is allowed")
        pool_name = name if spec["singleton"] else f"{name}_{counts[name]}"
        names[pool_name] = i
        definitions.append((name, spec, config, pool_name))
        nodes.append({"text": spec["display_name"], "left": f"{50 + i % 5 * 160}px",
                      "top": f"{50 + i // 5 * 100}px", "configData": config})

    def refs(config, field):
        value = config.get(field, [])
        if value in (None, ""):
            return []
        values = value if isinstance(value, list) else [value]
        if not all(isinstance(x, str) and x in names for x in values):
            raise ValueError(f"Dangling or invalid reference in {field}: {values}")
        return values

    connections = set()
    # Validate every reference, including kill lists and data dependencies.
    for _, spec, cfg, _ in definitions:
        for field in spec["connection_fields"]:
            refs(cfg, field)

    def add(source, target, output):
        target_type, target_spec, target_cfg, _ = definitions[target]
        if definitions[source][1]["no_output"] or target_spec["no_input"]:
            raise ValueError("A no-input/no-output system agent cannot be wired")
        slots = [slot for field, slot in _slots(target_spec, "input").items()
                 if definitions[source][3] in refs(target_cfg, field)]
        if target_type in {"and", "or"} and not slots:
            raise ValueError(f"{target_type} requires explicit source_agent_1/source_agent_2")
        for slot in slots or [0]:
            connections.add((source, target, slot, output))

    for i, (_, spec, cfg, _) in enumerate(definitions):
        for field, slot in _slots(spec, "output").items():
            for ref in refs(cfg, field):
                add(i, names[ref], slot)
        # Source fields express dependencies. Never invent a branch from these.
        fields = set(spec["input_slots"].values()) | {"source_agent"}
        for field in fields:
            for ref in refs(cfg, field):
                source = names[ref]
                if any(c[0] == source and c[1] == i for c in connections):
                    continue
                source_spec = definitions[source][1]
                if len(_slots(source_spec, "output")) > 1:
                    # Resolve in the final consistency pass once all outputs exist.
                    continue
                add(source, i, next(iter(_slots(source_spec, "output").values())))
        if spec["special"] == "parametrizer":
            for ref in refs(cfg, "target_agent"):
                add(i, names[ref], 0)

    for i, (_, spec, cfg, _) in enumerate(definitions):
        for field in set(spec["input_slots"].values()) | {"source_agent"}:
            for ref in refs(cfg, field):
                if not any(c[0] == names[ref] and c[1] == i for c in connections):
                    raise ValueError(f"Branch to {definitions[i][3]} must specify its output field")
        if spec["special"] == "parametrizer":
            for singular, plural in (("source_agent", "source_agents"), ("target_agent", "target_agents")):
                if refs(cfg, singular) and refs(cfg, plural) and refs(cfg, singular) != refs(cfg, plural):
                    raise ValueError(f"Parametrizer {singular}/{plural} disagree")
            sources = refs(cfg, "source_agent") or refs(cfg, "source_agents")
            targets = refs(cfg, "target_agent") or refs(cfg, "target_agents")
            if len(sources) != 1 or len(targets) != 1:
                raise ValueError("Parametrizer requires exactly one source and one target")
            source_spec = definitions[names[sources[0]]][1]
            target_schema = definitions[names[targets[0]]][1]["config_schema"]
            mappings = cfg.get("_parametrizer_mappings", [])
            if not mappings:
                raise ValueError("Parametrizer requires _parametrizer_mappings in the generated plan")
            for mapping in mappings:
                if not isinstance(mapping, dict) or mapping.get("source_field") not in source_spec["output_fields"]:
                    raise ValueError("Parametrizer mapping references an unsupported source field")
                current = target_schema
                for part in str(mapping.get("target_param", "")).split("."):
                    if not isinstance(current, dict) or part not in current:
                        raise ValueError("Parametrizer mapping references an unknown target field")
                    current = current[part]
    return {"nodes": nodes, "connections": [
        {"sourceIndex": s, "targetIndex": t, "inputSlot": inp, "outputSlot": out}
        for s, t, inp, out in sorted(connections)
    ]}


def execution_matrix(agents, configs, catalog):
    index = {name: i for i, name in enumerate(agents)}
    matrix = [[0] * len(agents) for _ in agents]
    for name, cfg in configs.items():
        base = re.sub(r"_\d+$", "", name)
        spec = catalog.get(base)
        if name not in index or not spec or spec["never_starts_targets"] or spec["no_output"]:
            continue
        fields = set(spec["output_slots"].values())
        if spec["special"] == "parametrizer":
            fields.add("target_agent")
        for field in fields:
            values = cfg.get(field, [])
            for target in values if isinstance(values, list) else [values]:
                if isinstance(target, str) and target in index:
                    matrix[index[name]][index[target]] = 1
    return matrix


def monitoring_contract_context(agents, configs, catalog):
    rows = ["CURRENT CONTRACT FACTS (override generic timing heuristics):"]
    for name in agents:
        base = re.sub(r"_\d+$", "", name)
        spec, cfg = catalog.get(base), configs.get(name, {})
        if not spec:
            rows.append(f"{name}: unknown installed contract; do not infer execution semantics")
            continue
        flags = [key for key in ("long_running", "never_starts_targets", "no_output") if spec[key]]
        rows.append(f"{name}: lifecycle={','.join(flags) or 'ordinary'}; output_fields={','.join(spec['output_fields'])}")
        dependencies = {field: cfg[field] for field in ("source_agents", "source_agent", "source_agent_1", "source_agent_2") if cfg.get(field)}
        if dependencies:
            rows.append("  log/data dependencies: " + json.dumps(dependencies, ensure_ascii=False))
        if base == "ender":
            rows.append("  kill targets (not execution edges): " + json.dumps(cfg.get("target_agents", [])))
        if base == "mouser":
            rows.append(f"  movement_type={cfg.get('movement_type', 'random')}; total_time={cfg.get('total_time', 30)}s for random mode")
        if base == "keyboarder":
            rows.append(f"  mode={cfg.get('input_mode', 'sequence')}; stride_delay={cfg.get('stride_delay', 100)}ms; typing_interval_ms={cfg.get('typing_interval_ms', 10)}; literal_text_length={len(str(cfg.get('text', '')))}")
    rows.append(
        "Mouser/Keyboarder input_sent means input delivery only, never verified application success. "
        "observed is an inspection result. error may follow partial input; do not recommend automatic replay. "
        "Check foreground/window identity and fresh UI evidence before continuing. "
        "Shoter coordinate_space must be screen with valid geometry before mapping screenshot pixels; unknown is unusable. "
        "Use configured duration and text/key delays; these agents do not have a universal five-second deadline. "
        "A stopped PID or a downstream trigger is not proof of successful work."
    )
    return "\n".join(rows)


def desktop_outcomes(pool_path, agents):
    """Reread bounded tails so a structured error is not forgotten next cycle."""
    rows = ["LATEST DESKTOP RECEIPTS (from current log tails; not UI verification):"]
    for name in agents:
        base = re.sub(r"_\d+$", "", name)
        if base not in {"mouser", "keyboarder", "shoter"}:
            continue
        path = Path(pool_path) / name / f"{name}.log"
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                handle.seek(max(0, path.stat().st_size - 131072))
                tail = handle.read().decode("utf-8", errors="replace")
        except OSError:
            rows.append(f"{name}: receipt unavailable during log rotation/cleanup")
            continue
        tag = base.upper()
        blocks = re.findall(r"INI_SECTION_" + tag + r"<<<\s*\n(.*?)\n\s*>>>END_SECTION_" + tag, tail, re.S)
        if not blocks:
            rows.append(f"{name}: no complete structured receipt in current tail")
            continue
        header = re.split(r"\r?\n[ \t]*\r?\n", blocks[-1], maxsplit=1)[0]
        # Do not repeat free-form output/body, file paths or typed content.
        fields = dict(re.findall(r"(?m)^([a-z_]+):[ \t]*(.*?)\r?$", header))
        keys = ("action_status", "status", "verification", "characters_sent", "commands_sent", "window_handle", "coordinate_space")
        rows.append(name + ": " + json.dumps({key: fields[key] for key in keys if key in fields}))
    return "\n".join(rows)
