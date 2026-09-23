---
name: flow-making
description: Turn a natural-language objective into a downloadable .flw workflow by driving the FlowCreator engine (full 89-agent catalog), then emit a canvas-loadable .flw.
metadata:
  openclaw:
    emoji: "🌊"
  tlamatini:
    runtime: in-process
    requires_tools: ["execute_command", "chat_agent_file_creator"]
    requires_mcps: []
    budget:
      max_iterations: 10
      max_seconds: 900
      max_tokens: 16000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/agents/flowcreator/**/*", "Tlamatini/agent/skills_pkg/flow_making/**/*"]
        write: ["${input.out_path}"]
      shell:
        - "python agent/skills_pkg/flow_making/scripts/make_flow.py"
        - "python agent/skills_pkg/flow_making/scripts/result_to_flw.py"
      network: deny
      db: deny
    inputs:
      - { name: objective, type: string, required: true,
          description: "One-sentence high-level goal for the flow." }
      - { name: out_path,  type: string, required: true,
          description: "Absolute path to write the .flw file. If the user gives no folder, default it under the Tlamatini Templates directory (TLAMATINI_TEMPLATES, e.g. <Templates>/alert.flw) — never C:\\Temp / %TEMP%." }
      - { name: flow_name, type: string, required: false,
          description: "Logical flow name FlowCreator records (defaults to the out_path basename)." }
      - { name: llm_model, type: string, required: false,
          description: "Ollama model FlowCreator queries (defaults to the FlowCreator template's model)." }
      - { name: llm_host,  type: string, required: false,
          description: "Ollama host URL (default http://localhost:11434)." }
    outputs:
      - { name: flw_path,         type: string,  required: true }
      - { name: agent_count,      type: integer, required: true }
      - { name: connection_count, type: integer, required: true }
    triggers:
      keywords: ["flow-making","make a flow","build a flow","create a flow","create flow file","flow file",".flw","flow from objective","scaffold a flow"]
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

# Flow-Making

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

> **Related (2026-07-22):** FlowCreator is now ALSO a plain **wrapped chat-agent**,
> `chat_agent_flowcreator` — a Multi-Turn tool (no ACPX needed) that takes
> `prompt=` + `flow_filename=` and writes the `.flw` itself. This skill is the
> heavier, ACPX/`invoke_skill`-surface path that shells out to `scripts/make_flow.py`;
> the wrapped tool is the lighter one-call path. **Both convert `flow_result.json`
> → `.flw` with the SAME `result_to_flw.py` logic** — this skill's
> `scripts/result_to_flw.py` and the copy vendored at
> `agent/agents/flowcreator/result_to_flw.py` (so the pool subprocess can carry it)
> must be kept in sync. For a simple "make me a .flw from this sentence" ask, prefer
> `chat_agent_flowcreator`; use this skill when you need the scripted pipeline.

Produce a canvas-loadable `.flw` from `${input.objective}` by wrapping the
**FlowCreator** engine — which already encodes the full 89-agent catalog,
connection contracts, and design rules in `agentic_skill.md`. Do NOT hand-author
the `.flw` JSON yourself: you do not carry the agent catalog/config-key contracts
in context, so a hand-written flow hallucinates agent types and will not load.

## Primary path — one deterministic call

Run the shipped driver with `execute_command`. It copies the FlowCreator
template to an isolated runtime dir, writes its `config.yaml`, runs FlowCreator
(which queries the configured Ollama model), and converts the result to a `.flw`:

```
python agent/skills_pkg/flow_making/scripts/make_flow.py \
  --objective "${input.objective}" \
  --out "${input.out_path}" \
  --flow-name "${input.flow_name}" \
  --model "${input.llm_model}" \
  --host "${input.llm_host}"
```

- The path is relative to the chat process's working directory (the Tlamatini
  app root, where `manage.py` runs — same cwd `execute_command` uses for
  `python manage.py ...`). If a relative call ever reports "can't open file",
  retry with the repo-root prefix `Tlamatini/agent/skills_pkg/...`.
- Omit `--flow-name` / `--model` / `--host` when the corresponding input is
  empty (the driver has sensible defaults).
- Use forward slashes in `--out` even on Windows (e.g.
  `C:/Users/you/Desktop/Flows/alarm.flw`); the driver creates the folder if it
  is missing.

## Reading the result

On success the **last stdout line** is machine-readable:

```
agent_count=<N> connection_count=<M> flw_path=<absolute path>
```

Parse it and return `{ flw_path, agent_count, connection_count }`. Tell the user
to open it on the ACP designer via **Open ▸ select the `.flw`** (it auto-deploys
the agents and draws the connections).

## Failure handling

If the driver exits non-zero, its last stdout line begins with `ERROR `. Surface
that message verbatim and act on the common causes — do NOT silently fabricate a
`.flw`:

- `ERROR FlowCreator timed out` / `Cannot reach Ollama` — Ollama is not running
  or the model is not pulled. Ask the user to start Ollama / pull the model, or
  pass a different `--model`.
- `ERROR FlowCreator: ...` — the model returned an unparseable flow; retry once,
  then report.
- `ERROR could not locate the FlowCreator template dir` — pass `--template
  <dir>` (the `agent/agents/flowcreator` folder) or set
  `TLAMATINI_FLOWCREATOR_DIR`.

## Fallback — manual two-step (only if the driver is unavailable)

1. Use `chat_agent_file_creator` to write a `config.yaml` (JSON is valid YAML)
   into a **copy** of `agent/agents/flowcreator/` with
   `{ "prompt": "${input.objective}", "flow_filename": "...", "llm": {"host": "...", "model": "..."} }`,
   then `execute_command: python flowcreator.py` in that copy.
2. Convert its `flow_result.json` to the final `.flw`:
   `python agent/skills_pkg/flow_making/scripts/result_to_flw.py <runtime>/flow_result.json "${input.out_path}"`
   and read the same `agent_count=… connection_count=… flw_path=…` summary line.

## Notes

- The `.flw` schema this produces is the schemaVersion-2 nodes/connections shape
  the canvas loader consumes; see `references/flw_schema.md`.
- Never mutate the FlowCreator template in place — always run from an isolated
  copy (the driver does this for you).

## Current installed-agent contract — 2026-09-15

Use `agent/agents/flowcreator/flow_catalog.json` for canonical names, current config schemas, output/input slots, lifecycle flags and structured fields for all 89 installed types. GUI-Manager is design only. After changing a template/contract/reference, run `python scripts/update_flow_catalog.py` and its `--check` mode in the repository. Deployment refreshes runtime snapshots.

FlowCreator selects capabilities before detailed design, validates the generated plan, and uses bounded repair. Declare Ender input connections explicitly; Ender `target_agents` is a kill list. Counter uses L/G slots; source dependencies do not choose a conditional output branch. Generated Parametrizers require valid `_parametrizer_mappings`, one source and one target. Do not maintain a separate hardcoded Parametrizer producer list.

For desktop flows, use explicit physical/screenshot geometry and verified target windows. `input_sent` is input delivery only; errors may be partial and must not be blindly replayed. Read `docs/desktop-input-and-flow-contracts.md` and `docs/agent-coverage.md` for the full contract and verification scope.

## Model choices in generated flows

Preserve quoted `"@config"` and missing registered model fields so generated agents
follow Config → Models. Keep a literal model/engine/voice only when an explicit
override is intended; never fill inheritance with a guessed tag. The registry in
`agent/agents/model_settings.py` maps all 21 model-backed agents to 38 global
settings. Wrapped-chat globals are seeded before explicit tool arguments, so do
not manufacture model arguments when translating a request into a flow. Optional
empty Whisperer cloud model and LaTeXer repair model values have distinct meanings.
Video `analysis_type` remains a per-agent task choice; its local audio model is
separate from Whisperer's engine. See `docs/model_configuration.md` and the current
generated flow catalog for exact field paths and defaults.
