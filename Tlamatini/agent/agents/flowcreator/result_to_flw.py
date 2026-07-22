#!/usr/bin/env python3
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
result_to_flw.py — convert FlowCreator's ``flow_result.json`` into a canonical
``.flw`` flow file that the Tlamatini ACP canvas loader (``loadDiagram`` in
``agent/static/agent/js/acp-file-io.js``) accepts.

Part of the ``flow-making`` skill. Stdlib-only (no ``agent.*`` import) so it runs
in any isolated runtime dir under either source or frozen Tlamatini.

Usage:
    python result_to_flw.py <flow_result.json> <out.flw> [flow_name]

Contract honored (verified against acp-file-io.js::loadDiagram):
- ``data.nodes[]`` each carry ``text`` (REQUIRED — the loader calls
  ``nodeData.text.toLowerCase()`` unconditionally), ``left``, ``top``,
  ``agentPurpose`` (optional), ``configData`` (dict or null).
- ``data.connections[]`` are keyed by INTEGER ``sourceIndex`` / ``targetIndex``
  (indices into the node list), plus ``inputSlot`` / ``outputSlot``.
- ``text`` is emitted as a hyphen-preserving Title-Case display name
  (``monitor_log`` -> ``Monitor-Log``). Every downstream consumer lowercases it
  again for class resolution + the connection-restoration ``switch``, so the
  casing is purely cosmetic AND always matches (``Monitor-Log`` -> matches the
  ``'monitor-log'`` case and the ``monitor-log`` classMap key).

Exit codes: 0 on success, non-zero on malformed input. The LAST stdout line is
``agent_count=<N> connection_count=<M> flw_path=<path>`` for the skill runbook
to parse.
"""
from __future__ import annotations

import json
import os
import re
import sys

# Cosmetic display-name overrides (mirrors
# agent/services/agent_paths.py::display_name_from_agent_type, but hyphen-joined
# so the lowercased form still matches the canvas classMap + connection switch).
# Anything not listed falls back to hyphen-preserving Title-Case.
_DISPLAY_OVERRIDES = {
    "and": "AND",
    "or": "OR",
    "acpxer": "ACPXer",
    "recmailer": "RecMailer",
    "ssher": "SSHer",
    "scper": "SCPer",
    "sqler": "SQLer",
    "pser": "PSer",
    "apirer": "APIrer",
    "pythonxer": "Pythonxer",
    "teletlamatini": "TeleTlamatini",
    "telegrammer": "Telegrammer",
    "whatsapper": "Whatsapper",
    "zavuerer": "Zavuerer",
    "flowcreator": "FlowCreator",
    "flowhypervisor": "FlowHypervisor",
    "flowbacker": "FlowBacker",
    "stm32er": "STM32er",
    "esp32er": "ESP32er",
}

# Agents that may exist only once on the canvas — their node id has no cardinal.
_SINGLETONS = {"flowcreator", "flowhypervisor"}


def _agent_type(text: str) -> str:
    """Normalize a node label to its canonical underscore agent type."""
    t = (text or "").strip()
    t = re.sub(r"\s*\(\d+\)\s*$", "", t)            # strip trailing " (2)"
    t = t.replace("-", "_").replace(" ", "_")
    t = re.sub(r"[^A-Za-z0-9_]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_").lower()
    return t


def _display_name(agent_type: str) -> str:
    if agent_type in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[agent_type]
    # Hyphen-preserving Title-Case: monitor_log -> Monitor-Log
    return "-".join(seg.capitalize() for seg in agent_type.split("_") if seg)


def _node_id(agent_type: str, counters: dict) -> str:
    hyphen = agent_type.replace("_", "-")
    if agent_type in _SINGLETONS:
        return hyphen
    counters[agent_type] = counters.get(agent_type, 0) + 1
    return f"{hyphen}-{counters[agent_type]}"


def _intish(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def convert(result: dict) -> dict:
    raw_nodes = result.get("nodes") or []
    raw_conns = result.get("connections") or []

    counters: dict = {}
    nodes = []
    ids = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("text") or raw.get("agentName") or raw.get("agent_name") or "")
        atype = _agent_type(label)
        if not atype:
            continue
        cfg = raw.get("configData")
        if cfg is None:
            cfg = raw.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
        node_id = str(raw.get("id") or "") or _node_id(atype, counters)
        ids.append(node_id)
        nodes.append({
            "id": node_id,
            "text": _display_name(atype),
            "left": str(raw.get("left") or "50px"),
            "top": str(raw.get("top") or "50px"),
            "agentPurpose": str(raw.get("agentPurpose") or raw.get("agent_purpose") or ""),
            "configData": cfg,
        })

    n = len(nodes)
    connections = []
    for raw in raw_conns:
        if not isinstance(raw, dict):
            continue
        si = _intish(raw.get("sourceIndex"), -1)
        ti = _intish(raw.get("targetIndex"), -1)
        # Allow id-keyed connections too (fall back when indices are absent).
        if not (0 <= si < n) and raw.get("sourceId") in ids:
            si = ids.index(raw["sourceId"])
        if not (0 <= ti < n) and raw.get("targetId") in ids:
            ti = ids.index(raw["targetId"])
        if not (0 <= si < n) or not (0 <= ti < n):
            continue
        connections.append({
            "sourceIndex": si,
            "targetIndex": ti,
            "sourceId": ids[si],
            "targetId": ids[ti],
            "inputSlot": _intish(raw.get("inputSlot"), 0),
            "outputSlot": _intish(raw.get("outputSlot"), 0),
        })

    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}

    return {
        "schemaVersion": 2,
        "nodes": nodes,
        "connections": connections,
        "artifacts": artifacts,
    }


def main(argv) -> int:
    if len(argv) < 3:
        print("usage: result_to_flw.py <flow_result.json> <out.flw> [flow_name]")
        return 2
    in_path, out_path = argv[1], argv[2]
    if not os.path.exists(in_path):
        print(f"[FAIL] input not found: {in_path}")
        return 1
    try:
        with open(in_path, "r", encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[FAIL] could not read/parse {in_path}: {e}")
        return 1
    if not isinstance(result, dict) or "nodes" not in result:
        # Some FlowCreator runs surface an error structure instead of a flow.
        status = result.get("status") if isinstance(result, dict) else None
        msg = result.get("message") if isinstance(result, dict) else None
        print(f"[FAIL] {in_path} is not a flow_result (status={status!r} message={msg!r})")
        return 1

    flw = convert(result)
    if not flw["nodes"]:
        print(f"[FAIL] no usable nodes in {in_path}")
        return 1

    if not out_path.lower().endswith(".flw"):
        out_path += ".flw"
    try:
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(flw, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAIL] could not write {out_path}: {e}")
        return 1

    print(f"[OK] wrote {out_path}")
    # Machine-readable summary on the LAST line (the runbook parses this).
    print(f"agent_count={len(flw['nodes'])} "
          f"connection_count={len(flw['connections'])} "
          f"flw_path={os.path.abspath(out_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
