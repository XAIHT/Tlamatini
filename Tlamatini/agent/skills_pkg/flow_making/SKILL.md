---
name: flow-making
description: Turn a natural-language objective into a downloadable .flw workflow by driving the FlowCreator engine (full 69-agent catalog), then emit a canvas-loadable .flw.
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
          description: "Absolute path to write the .flw file (e.g. C:\\tmp\\alert.flw)." }
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

# Flow-Making

Produce a canvas-loadable `.flw` from `${input.objective}` by wrapping the
**FlowCreator** engine — which already encodes the full 69-agent catalog,
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
