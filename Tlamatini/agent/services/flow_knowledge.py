"""Export the installed agent contracts for standalone planning/monitoring agents.

Only field names and types are exported. Local template values (credentials,
paths, prompts, recipients) are never copied into the knowledge catalog.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml

from .agent_contracts import get_agent_contracts
from .agent_paths import get_agents_root


KNOWLEDGE_AGENTS = {"flowcreator", "flowhypervisor", "parametrizer"}


def config_schema(value):
    if isinstance(value, dict):
        return {str(key): config_schema(item) for key, item in value.items()}
    if isinstance(value, list):
        return "list"
    if value is None:
        return "nullable"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    return "str"


def build_catalog():
    root = get_agents_root()
    fallback_path = root / "flowcreator" / "flow_catalog.json"
    fallback = json.loads(fallback_path.read_text(encoding="utf-8")) if fallback_path.exists() else {"agents": {}}
    descriptions = {}
    for parent in root.parents:
        path = parent / "agents_descriptions.md"
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                match = re.match(r"\| \*\*(.*?)\*\* \| (.*?) \|", line)
                if match:
                    descriptions[re.sub(r"[^a-z0-9]", "", match[1].lower())] = match[2]
            break
    agents = {}
    contracts = get_agent_contracts()
    for folder in sorted(root.iterdir()):
        name = folder.name
        if not (folder / f"{name}.py").is_file() or not (folder / "config.yaml").is_file():
            continue
        contract = contracts[name]
        config = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8")) or {}
        if not isinstance(config, dict):
            raise ValueError(f"{name}: config.yaml must be a mapping")
        purpose = descriptions.get(re.sub(r"[^a-z0-9]", "", contract.display_name.lower()))
        purpose = purpose or fallback["agents"].get(name, {}).get("purpose", contract.display_name)
        schema = config_schema(config)
        # Canvas-managed connections may be absent from a minimal template.
        for field in sorted(set(contract.input_field_by_slot.values()) | set(contract.output_field_by_slot.values())):
            schema.setdefault(field, "str" if field in {"source_agent", "target_agent", "source_agent_1", "source_agent_2"} else "list")
        if name == "mouser":
            for field in ("ini_posx", "ini_posy", "end_posx", "end_posy"):
                schema[field] = "number"  # normalized coordinates are fractional
        agents[name] = {
            "display_name": contract.display_name,
            "aliases": list(contract.normalized_aliases),
            "purpose": purpose,
            "config_schema": schema,
            "output_fields": list(contract.parametrizer_fields),
            "output_slots": {str(k): v for k, v in contract.output_field_by_slot.items()},
            "input_slots": {str(k): v for k, v in contract.input_field_by_slot.items()},
            "connection_fields": list(contract.connection_fields),
            **{key: getattr(contract, key) for key in (
                "no_input", "no_output", "singleton", "long_running", "never_starts_targets", "special"
            )},
        }
    return {"schema_version": 1, "agents": agents}


def write_runtime_knowledge(destination, agent_type):
    """Refresh both new and existing pool/isolated runtimes before execution."""
    destination = Path(destination)
    # A main-script-only refresh must also carry its new local dependencies.
    helpers = {"mouser": ("mouser_coordinates.py",), "keyboarder": ("keyboarder_input.py",),
               "flowcreator": ("result_to_flw.py",)}
    for filename in helpers.get(agent_type, ()):
        source = get_agents_root() / agent_type / filename
        target = destination / filename
        destination.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
    if agent_type not in KNOWLEDGE_AGENTS:
        return
    destination.mkdir(parents=True, exist_ok=True)
    source = get_agents_root() / "flowcreator" / "flow_knowledge.py"
    target = destination / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    catalog = build_catalog()
    (destination / "flow_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Existing pool folders must receive corrected instructions as well.
    guide_name = {"flowcreator": "agentic_skill.md", "flowhypervisor": "monitoring-prompt.pmt"}.get(agent_type)
    if guide_name:
        source = get_agents_root() / agent_type / guide_name
        target = destination / guide_name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
