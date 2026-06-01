# `.flw` schema (schemaVersion 2) — the shape the canvas loader consumes

Source of truth: `agent/static/agent/js/acp-file-io.js::loadDiagram(data)` and
`agent/services/flow_spec.py::flow_spec_to_legacy_json`. The `flow-making` skill's
`scripts/result_to_flw.py` emits exactly this shape.

```json
{
  "schemaVersion": 2,
  "nodes": [
    {
      "id": "starter-1",
      "text": "Starter",
      "left": "50px",
      "top": "50px",
      "agentPurpose": "",
      "configData": { "target_agents": ["monitor_log_1"] }
    },
    {
      "id": "monitor-log-1",
      "text": "Monitor-Log",
      "left": "210px",
      "top": "50px",
      "agentPurpose": "",
      "configData": { "target.logfile_path": "app.log", "target_agents": ["ender_1"] }
    }
  ],
  "connections": [
    {
      "sourceIndex": 0,
      "targetIndex": 1,
      "sourceId": "starter-1",
      "targetId": "monitor-log-1",
      "inputSlot": 0,
      "outputSlot": 0
    }
  ],
  "artifacts": { "parametrizerMappings": {} }
}
```

## Hard rules the loader enforces

- **`nodes[].text` is REQUIRED** — `loadDiagram` calls `nodeData.text.toLowerCase()`
  unconditionally. It is the visible label AND, lowercased, selects the CSS class
  and the connection-restoration `switch`. Emit a hyphen-preserving display name
  (`monitor_log → Monitor-Log`): lowercased it matches both the `monitor-log`
  classMap key and the `'monitor-log'` switch case. Single-word agents → `Starter`,
  `Executer`, `Ender`, etc.
- **`connections[]` are keyed by INTEGER `sourceIndex` / `targetIndex`** (indices
  into `nodes`). `sourceId` / `targetId` are written for clean round-tripping but
  the loader ignores them. `inputSlot` / `outputSlot` default to 0; A/B branch
  outputs (Asker/Forker/Counter) use slots 1/2, OR/AND inputs use slots 1/2.
- `left` / `top` are CSS pixel strings (`"210px"`). `agentPurpose` is optional
  (falls back to `getAgentPurposeForName`). `configData` is the agent's
  `config.yaml` overrides, or `null` to deploy the template defaults.
- `artifacts.parametrizerMappings` (keyed by node id) carries Parametrizer
  mapping artifacts; omit/`{}` when unused.

## Connection-field semantics inside `configData`

- `target_agents: []` — downstream agents to START after this one finishes.
- `source_agents: []` — upstream agents whose logs this one MONITORS.
- `output_agents: []` — Stopper/Ender/Cleaner canvas wiring (not "start").
- Special slots: Asker/Forker → `target_agents_a` / `target_agents_b`; Counter →
  `target_agents_l` / `target_agents_g`; OR/AND → `source_agent_1` / `source_agent_2`.
- Pool names are cardinal-suffixed with underscores (`executer_1`, `monitor_log_2`).

FlowCreator already produces correct wiring; the converter only re-shapes its
`flow_result.json` into the above without altering the topology.
