<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini Agents — MCP connector

Exposes **every complete live Tlamatini agent directory (89 in the v1.65.4
release)** as MCP tools so an MCP client (Claude Code, etc.) can drive
them directly — Executer, Pythonxer, Croner, ACPXer, STM32er, ESP32er,
Arduiner, Shoter, Playwrighter, Kalier, MCP Doctor, NetSpeed-Calculator, and
the rest of the live catalog. It also exposes 7 management/skill tools and 10
ACPX tools: **105 root stdio MCP tools total**. The server discovers agents
dynamically; these counts are a verified snapshot, not a hardcoded limit.

## Files

| File | Role |
|---|---|
| `tlamatini_mcp_server.py` | The stdio MCP server. Self-contained (needs only `mcp` + `pyyaml`; `psutil` used for tree-kill if present). Does **not** import Django. |
| `.mcp.json` | Project-scoped registration so Claude Code shows it under `/mcp`. |

It resolves `Tlamatini/agent/agents/` relative to its own location, so the
client's working directory doesn't matter.

## Activate it

1. Reload Claude Code in this folder (`C:\Development\Tlamatini`). A project
   `.mcp.json` server must be **approved on first use** — run `/mcp`, pick
   `tlamatini`, approve it (or restart the session).
2. Verify offline anytime: `python tlamatini_mcp_server.py --list`
3. The tools then appear to Claude as `mcp__tlamatini__<agent>` (e.g.
   `mcp__tlamatini__executer`).

## How it runs an agent (per call)

The exact Tlamatini "launcher dance" — no shortcuts:

1. copy `agent/agents/<name>/` → `Temp/mcp_agent_runs/<name>__<runid>/` (gitignored)
2. deep-merge your args onto that copy's `config.yaml` (empty values are
   dropped, so template defaults survive)
3. run `python <name>.py` in the copied dir
4. read `<name>__<runid>.log` (where the agent writes its result) and return it

### `config_used` is echoed back — but BULKY values are truncated (v1.48.2)

Every result echoes the fully-resolved `config_used`, so you can see exactly what the
agent ran with. That is genuinely useful for a 20-character `pattern` — and actively
harmful for a 46 KB `content` (File-Creator) or a 10 KB `input_text` (LaTeXer), where
the echo alone can blow the caller's response budget and push out the run's **real
log**. So `_redact_bulky()` replaces any string longer than `_ECHO_VALUE_LIMIT`
(600 chars) with a truncated prefix plus an **honest** marker naming the true size:

```
"content": "The first 600 characters…... <redacted from echo: 46231 chars total>"
```

It recurses into dicts and lists (depth-capped at 6) and it affects **only the echo** —
the agent always receives the complete, unmodified value. Nothing is silently
misrepresented: the marker always states the real length. This is why long `new_string`
/ `content` arguments come back visibly shortened in the tool result.

## Calling agents

Each agent tool's parameters are **auto-derived from its `config.yaml`**, plus
three universal options:

- `wait` (bool) — wait for completion and return the full log. Default `true`,
  except known **long-running** agents (croner, flowhypervisor, teletlamatini,
  gatewayer, gateway_relayer, recmailer,
  monitor_log, monitor_netstat, node_manager) default `false`.
- `timeout_seconds` (int, default 180) — if the agent hasn't finished by then,
  it's left running in the background and a `run_id` is returned.
- `config` (object) — free-form overrides for nested/uncommon keys, or to set
  `source_agents`/`target_agents` wiring.

### Examples (conceptual args)

| Agent | Args |
|---|---|
| `executer` | `{ "script": "echo hello" }` |
| `pythonxer` | `{ "script": "print(sum(range(10)))" }` |
| `shoter` | `{}` (screenshot; renders on the real desktop) |
| `stm32er` | `{ "action": "bootstrap" }` then `{ "action": "validate" }` |
| `esp32er` | `{ "action": "scaffold_build_upload", "board": "esp32dev" }` |
| `arduiner` | `{ "action": "boards" }` (FQBN picks the MCU) |
| `acpxer` | `{ "agent_id": "claude", "task": "summarize README" }` |
| `croner` | `{ "trigger_time": "14:30" }` → returns a `run_id` (background) |
| `netspeed_calculator` | `{ "action": "validate" }` for reachability, or one approved `full` run (about 100-200 MB) |

### PPTXer: create and verify styled slides

The existing `pptxer` agent is exposed by the connector (typically `mcp__tlamatini__pptxer`) and by `chat_agent_pptxer` in chat. Parameters continue to come from `config.yaml`. Select any of the 12 new visual styles through `nuance`; there are 36 named treatments overall. Empty `nuance` uses the original automatic classifier.

```json
{"action": "create", "nuance": "blueprint", "slide_size": "16:9", "input_text": "# Architecture review\n\n## Delivery plan\n- Explain the system and its next milestone."}
```

Brand color, background, font pairing, and density overrides remain available. Long text can continue across slides. The connector returns the agent log: inspect `INI_SECTION_PPTXER` fields `status`, `output_path`, `layout_clean`, `ground_truth`, `render_tier`, `overlaps`, and `text_overflows`. `created_with_findings` needs review; a saved deck alone does not establish native visual verification. Actions remain `create`, `outline`, `render`, `audit`, `info`, `fonts`, and `validate`. [Style catalogue and verification guide](Tlamatini/agent/agents/pptxer/STYLES.md).

### LaTeXer: discover and apply styles

The connector exposes the existing `latexer` agent (typically `mcp__tlamatini__latexer`); the running chat app calls the same agent as `chat_agent_latexer`. Its 30-style system is native to the agent and needs no external MCP registration. Parameters are derived from `config.yaml` as usual.

```json
{"action": "list_styles"}
```

This returns a JSON catalogue inside the agent's `response_body`, `status: listed`, `success: true`, `style_count: 30` and `distribution: not_probed`. The connector returns the agent log; no PDF is created and no TeX installation is needed for this action.

```json
{"action": "scaffold_compile", "template": "article", "style": "circuit_board", "title": "Signal notebook", "content": "A precise measurement begins with a clear question.", "style_mode": "print", "style_cover": false}
```

PDF compilation needs an installed engine (MiKTeX recommended). Other controls are `subtitle`, `style_decoration` and six-digit `predominant_color`. Send complex LaTeX as `content_b64` / `input_text_b64`; a valid base64 field takes precedence over its plain counterpart. Styles apply to generated source and bare fragments, not existing complete sources/projects. Canonical design fields are `style`, `style_family`, `style_mode`, `style_count`; operation success still comes from `status`/`success`. See the [style guide](Tlamatini/agent/agents/latexer/STYLES.md).

### Management and skill tools

- `tlamatini_list_agents()` — every agent + its parameters.
- `tlamatini_run_log(run_id, max_chars?)` — read a run's log.
- `tlamatini_run_status(run_id)` — alive / finished + return code.
- `tlamatini_run_stop(run_id)` — terminate a background run (process tree).
- `tlamatini_list_runs()` — all runs this session.
- `tlamatini_list_skills()` — list current runtime skills.
- `tlamatini_read_skill(name)` — read one skill's instructions.

The 10 ACPX tools are `acp_doctor`, `list_acp_agents`, `acp_spawn`, `acp_send`,
`acp_send_and_wait`, `acp_relay`, `acp_transcript`, `acp_session_status`,
`acp_list_sessions`, and `acp_kill`.

Typical long-running pattern: call the agent (gets `run_id`) →
`tlamatini_run_log(run_id)` to watch → `tlamatini_run_stop(run_id)` to end it.

## Notes

- **Python**: `.mcp.json` points at `C:\Program Files\Python312\python.exe`
  (the interpreter that already has `mcp` + `pyyaml`). Change it if you move
  to a venv.
- **Visible/desktop agents** (Shoter, Mouser, Keyboarder, headed Playwrighter,
  Executer with `execute_forked_window: true`) render on your real desktop —
  the MCP server runs as a normal user process, not sandboxed.
- **Temp**: runtime copies live under the gitignored repo-root `Temp/` per the
  2026-06-02 temp policy.
- This connector is **separate** from Tlamatini's own running app — it drives
  the agent templates straight from disk and needs neither the Django server
  nor a browser.
- Agent execution is under the caller/user's jurisdiction. The plain-Python
  templates are auditable and editable, but the caller remains responsible
  for permissions, credentials, authorized targets, metered traffic, hardware,
  and downstream effects.

## Desktop control and flow contracts — 2026-09-15

Mouser now resolves explicit physical, window and screenshot coordinates; Keyboarder binds Unicode/key delivery to a verified window; Shoter publishes capture geometry. `input_sent` is delivery evidence, not application success, and a failed or interrupted input segment must be observed before replay.

Parametrizer derives its parser registry from current contracts and validates complete typed mappings. FlowCreator selects from all 89 installed agents and validates the generated graph before publishing; FlowHypervisor separates execution, kill and observation relationships and uses current desktop receipts/timing. GUI-Manager remains design only.

See [configuration, examples and limitations](docs/desktop-input-and-flow-contracts.md), the [complete generated coverage inventory](docs/agent-coverage.md), and the [GUI-Manager design](docs/GUI-Manager-design.md).

## Video-Analyzer content analysis

Video-Analyzer supports `analysis_type: robotics` (default), `transcription`, and `summary`. Robotics preserves the deterministic motion gate and dual-vision/merge verdict, with `PASS_OK` only on two explicit independent passes. Transcription reads selected video audio tracks (`audio_tracks: all` or `0,1`) using Whisperer's local faster-whisper backend, GPU auto/CPU fallback and timestamped segments; it never opens a microphone. Summary combines speech with two independent visual observers over frame batches spanning the whole clip, then synthesizes an overview, chronology, readable screen text, facts, steps, decisions, action items and limitations. Content modes accept static scenes, bypass the motion gate, and emit `TLM_ANALYSIS::` tokens rather than robotics verdicts. Missing audio/speech and partial failures are explicit. Each content run saves transcript, segments, report and full analysis artifacts. Parametrizer and wrapped chat results expose `analysis_type`, `analysis_token`, `transcript`, `summary`, `audio_status`, timestamped `segments_json` and artifact paths; the body remains `response_body`. Input remains a file, wildcard, newest video in a folder or Camcorder pool name. Always starts downstream agents; sampled perception is not exhaustive.

See [configuration, routing, Parametrizer mappings and limitations](Tlamatini/agent/agents/video_analyzer/README.md).

The existing `video_analyzer` MCP tool discovers these config fields automatically; pass `analysis_type="transcription"` or `analysis_type="summary"` and `video_pathfilenames`. Nested `transcription` options remain an object. No new MCP server or tool count is introduced.

## Model configuration for tools and MCPs (2026-09-20)

The central `agent/agents/model_settings.py` registry owns the built-in model,
engine and voice fields (38 settings, 21 model-backed agents). Add a metadata
entry and a real consumer when introducing another configurable built-in model;
do not add a disconnected selector or hardcoded tag. Wrapped chat seeds globals
before explicit tool arguments. Standalone `tlamatini_mcp_server.py` resolves
missing/`"@config"` template fields before applying invocation overrides and
carries `model_settings.py` plus `CONFIG_PATH` into isolated child runtimes.
Literal YAML choices remain standalone overrides. Credentials and provider URLs
remain separate; external MCP/ACPX providers keep their own model configuration.

Use compiled imports in frozen web services and `get_agents_root()` for portable
assets. Never read loose source relative to a frozen service's `__file__`, and
never require a self-modify source tree just to execute a tool. Preserve inheritance
in Parametrizer/flow mappings. Run the source/frozen `check_agent_runtimes` gate
and targeted wrapper tests, then both inclusion sweeps. The full field map,
validation API, optional values and lifecycle rules are in [model configuration](docs/model_configuration.md).
