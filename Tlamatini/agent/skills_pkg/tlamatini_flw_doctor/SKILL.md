---
name: tlamatini-flw-doctor
description: "Validate a .flw workflow file: check connection topology, terminal agents, Parametrizer single-lane queue, missing connectors, dangling target_agents."
metadata:
  openclaw:
    emoji: "🩺"
  tlamatini:
    runtime: in-process
    requires_tools: []
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 30
      max_tokens: 8000
    permissions:
      filesystem:
        read:  ["**/*.flw", "Tlamatini/agent/agents/**/*"]
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs:
      - { name: flw_path, type: string, required: true }
    outputs:
      - { name: ok,        type: boolean, required: true }
      - { name: problems,  type: array,   required: true }
      - { name: summary,   type: string,  required: true }
    triggers:
      keywords: [".flw doctor", "validate flow", "check flow", "lint flw"]
      file_globs: ["**/*.flw"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# .flw doctor

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Statically validate a `.flw` workflow against the **current** schema. This is a
read-only diagnostic: it reports findings and **never writes** a pool
`config.yaml`, never rewrites the flow, and exits cleanly even when the flow is
broken — the finding IS the deliverable.

## The schema you are validating (schemaVersion 2)

⚠️ **Do not look for `version` / `agents` / `from` / `to`.** That shape is
obsolete; `agent/services/flow_spec.py::normalize_flow_payload` is the
authority and it reads:

| key | meaning |
|---|---|
| `schemaVersion` | integer; **2** is current. Treat anything else as a NAMED finding (`unknown_schema_version`), not as a parse failure. |
| `nodes[]` | `id`, `text` (the agent display name), `left`, `top`, `agentPurpose`, `configData` |
| `connections[]` | `sourceId`/`targetId` **or** `sourceIndex`/`targetIndex`, plus `inputSlot` / `outputSlot` |
| `artifacts` | object; `artifacts.parametrizerMappings` is keyed by node id |

A connection may address its endpoints by **id or by index** — accept both.
An index outside `0..len(nodes)-1` is a finding (`bad_index`); a normalizer
would silently DROP that connection, which is exactly the class of defect
this doctor exists to surface.

A node's config may also carry `_parametrizer_mappings`; that and
`artifacts.parametrizerMappings` are two valid persistence shapes for the same
data (`acp-file-io.js::getSavedParametrizerMappings` accepts either).

## Checks

1. **Parse + shape.** JSON parses; `nodes` and `connections` are arrays.
   Report `schemaVersion` and flag an unknown one by name.
2. **Known agent types.** Resolve every node's `text` through
   `agent/agents/flowcreator/flow_catalog.json` (89 installed types; the
   generated catalog is the canonical name/slot/field source). Unknown ⇒
   `unknown_agent_type`.
3. **Reference integrity.** Every connection resolves to a real node by id or
   by index. Dangling ⇒ `dangling_reference`; out-of-range ⇒ `bad_index`.
4. **Slot validity.** `inputSlot` / `outputSlot` must exist on that agent's
   contract (`agent/services/agent_contracts.py` →
   `input_field_by_slot` / `output_field_by_slot`). A slot the contract does
   not define ⇒ `bad_slot`; the canvas would write it nowhere.
5. **Relationship kind — execution vs kill vs observation.** These are three
   different things and must not be conflated:
   - **execution** (`target_agents`) — "start this next".
   - **kill** (`Ender.target_agents`) — Ender's `target_agents` is a **KILL
     LIST**, and its `output_agents` is what it launches afterwards. An Ender
     edge is never a missing execution edge.
   - **observation** (`source_agents`) — "watch this agent's log". Never an
     execution edge.
   Contracts flagged `never_starts_targets` (Stopper, Cleaner) draw the edge
   but do not launch it. Declare Ender's input connections explicitly.
6. **Parametrizer.** Single-lane queue: **exactly one** source and **exactly
   one** target. Its mappings must be present and complete — every mapping
   names a source field the producing agent actually declares
   (`_PARAMETRIZER_OUTPUT_FIELDS` / the generated catalog) and a target field
   that exists in the destination's `config.yaml`. Missing or partial ⇒
   `incomplete_parametrizer_mapping`. ⚠️ Membership is **derived**; never
   check it against a hand-maintained producer list.
7. **Logic gates.** OR / AND take exactly 2 inbound sources; Barrier takes
   N ≥ 2; Asker / Forker have two outbound branches
   (`target_agents_a` / `target_agents_b`); Counter uses
   `target_agents_l` / `target_agents_g`. A Counter's source dependency does
   **not** choose its conditional output branch.
8. **Terminal agents.** Monitor-* / Emailer / Notifier / RecMailer have no
   outbound execution edge.

## Validating without writing

⛔ **If you confirm anything in the canvas GUI, it is a VISIBLE, HEADED
browser on Angela's real desktop — headless is FORBIDDEN**, and any script
that drives it runs in a VISIBLE FOREGROUND console, never
`run_in_background`.

To confirm the flow also COMPILES, use the supported dry-run path —
`POST /agent/compile_flow/` with `mode: "dry_run"` — which runs the same Agent
Contract validation the Start sequence uses **without** touching the session
pool. Never call it with `mode: "write"` from this skill.

## Output

Return `{ ok, problems: [{node_id, kind, message}, ...], summary }`.
`ok: false` with a populated `problems` list is a **successful** diagnostic
run, not a failure of this skill.
