<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini Agents — MCP connector

> Current release: **[v1.91.0](docs/changes/2026-10-23-v1.91.0.md)**. Dated records below retain their original evidence dates.

## v1.91.0 — Live Editor and Terminater configuration

**v1.91.0** is the current source version (2026-10-23). Its existing annotated tag
resolves to `a771d27c` and is present on origin. The catalog remains **86 workflow
agents, 67 wrapped chat agents and 110 built-in tools** (21 + 67 + 12 + 10), with
**29 skills and 220 migrations**. The frontend has **64 JS modules and 29 CSS
files** in the counted `static/agent/js` and `static/agent/css` directories.

**Config → Live Editor & Terminater** opens one dialog with Live Editor,
Terminater and Voice tabs, also available from the canvas and terminal Settings
buttons on the chat and control-panel surfaces. Saved account preferences control
real action pacing, teaching suggestions, shell defaults, manual Enter, waits and
narration; editor/terminal appearance stays local to the account and browser.
Presets and previews are drafts until Save; Stop, mute and tab access are immediate.

Migration **0220** stores account preferences and revisions. One TerminalHub applies
them across chat, ACP and Prompt Flow; legacy explicit flow values remain compatible.
Speech uses the shared browser queue, selects one focused tab and can wait for a
real completion receipt before typing. User interruption wins and private input is
not narrated. The offline editor bundle and runtime/source carriers include the new
UI and backend modules.

Source evidence on October 23: **17/17 visible browser checks passed; 929 of 931
regression tests passed**, with two existing README documentation assertions failing
before this documentation sweep. These are dated source results, not a new installed
package acceptance. No GitHub release for v1.91.0 was found during this sweep.
See the [release record](docs/changes/2026-10-23-v1.91.0.md) and
[settings guide](docs/interaction-settings.md).

## Carried from v1.90.0 — editable canvas and Interactor

The v1.90.0 source line had **86 workflow agents, 67 wrapped chat agents, 110 built-in tools (21 direct/module + 67 wrapped + 12 ACPX/Skills + 10 supervisors), and 219 migrations** after migration 0219. Interactor added a module/tool, not an Agent. The annotated tag resolves to `ebc5c3b4` and its GitHub release was published on 2026-10-22. Later commits in that line carried the account wizard’s local Notifier checkpoints. This section preserves v1.90.0 history; current configuration and counts are described above. Dated source and frozen runs remain separate.

- **Editor:** `agent_page_editing.js` owns the CodeMirror document, dirty baseline, encoding and save snapshot. `agent_page_canvas.js` owns load/refresh generation and cancellation. Markdown Preview and Source share the buffer; HTML/SVG remain inert source; PDF saving copies the original PDF. Never read a hidden compatibility element instead of the editor.
- **Native files:** `canvas_file_views.py` and `native_dialogs.py` provide local Save As/read/save. Authentication, CSRF, loopback-only host access, account/session-bound capabilities and full revision checks prevent a browser name from becoming an arbitrary host path. Existing Windows replacement preserves metadata; DB backup/restore mechanics are unchanged.
- **Interactor:** `agent/interactor/` connects the synchronous tool loop to the browser through session-authenticated `ws/interactor/`. Server-issued tab identity travels through ContextVar; bounded commands and receipts verify document/revision and full buffer. Browser messages acknowledge/access/stop; they cannot request arbitrary host-path commands.
- **Tutor:** read fresh unsaved text, type a small segment, guide the next field and end mutations for the turn. Continue begins a fresh chat/read. Prepared choices match locally, with no per-key model call. User input and Stop win; hidden tabs pause with bounded recovery rather than repeating edits.
- **Carriage:** migration 0218 seeds the Tool/catalog rows; `tool_gate_table()` supplies binding, Compact selection and cost labels. The offline editor bundle, Interactor browser files, frozen imports and source/static inventories must travel together.
- **Intent:** password input is not ownership of every command; a wizard email field or DONE reply is not notification consent. Preserve genuine user-runs tutorials. The catalog wizard uses createsuperuser and therefore creates an administrative account.

Contracts and evidence: [v1.90.0](docs/changes/2026-10-22-v1.90.0.md), [Canvas editing](docs/canvas-editing.md), [Interactor](docs/interactor.md), [Account wizard](docs/user-creation-wizard.md). Source/frozen rendering tests do not certify a rebuilt installed executable.



Exposes **every complete live Tlamatini agent directory (86 in v1.91.0, unchanged since Terminater arrived in v1.88.0;
85 in v1.87.0)** as MCP tools so an MCP client (Claude Code, etc.) can drive
them directly — Executer, Pythonxer, Croner, ACPXer, STM32er, ESP32er,
Arduiner, Shoter, Playwrighter, Kalier, MCP Doctor, NetSpeed-Calculator, and
the rest of the live catalog. It also exposes 7 management/skill tools and 10
ACPX tools: **103 root stdio MCP tools total in v1.91.0, unchanged since v1.88.0 (102 in v1.87.0)**. The server discovers agents
dynamically; these counts are a verified snapshot, not a hardcoded limit.

## Files

| File | Role |
|---|---|
| `tlamatini_mcp_server.py` | The stdio MCP server. Self-contained (needs only `mcp` + `pyyaml`; `psutil` used for tree-kill if present). Does **not** import Django. |
| `.mcp.json` | Project-scoped registration so Claude Code shows it under `/mcp`. |

It resolves `Tlamatini/agent/agents/` relative to its own location, so the
client's working directory doesn't matter.

## Activate it

1. Reload Claude Code in this folder (`C:\Development\XAIHT\Tlamatini`). A project
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
  recmailer,
  monitor_log, monitor_netstat) default `false`.
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

### Terminater: a visible terminal (new in v1.88.0)

The connector exposes the `terminater` agent (typically `mcp__tlamatini__terminater`); the running chat calls the same agent as `chat_agent_terminater`. It types a command into a real CMD / PowerShell terminal that the user watches in Tlamatini's **Terminals** area (see [docs/terminater.md](docs/terminater.md)).

```json
{"action": "run", "kind": "powershell", "text": "Get-Date", "typing_wpm": 50}
```

The result is the agent log with an `INI_SECTION_TERMINATER` block (`status`, `exit_code`, `typed`, `user_part`, `response_body` = the command's output). Things an MCP client must know:

* **It needs a running Tlamatini to be visible.** The agent finds the hub through `TLAMATINI_TERMINATER_URL` / `TLAMATINI_TERMINATER_TOKEN` or `<app>/Temp/.terminater_hub.json`. With `mode: auto` and no reachable hub it runs **standalone** (its own terminal, which dies with the run and which nobody watches); set `mode: hub` to be refused instead.
* **A call is slow by design.** Every key is typed at `typing_wpm` (default 50): about 15 s for 60 characters, plus the command itself, so allow for it in the client's timeout.
* A command that exits non-zero is `command_failed` and one that goes quiet for `hang_seconds` is `hung`; both are failures for a Forker even though the terminal worked. A `<<USER:hint>>` hand-over waits for a person (up to `user_wait_seconds`, default 300).

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

Parametrizer derives its parser registry from current contracts and validates complete typed mappings. FlowCreator selects from all 86 installed agents and validates the generated graph before publishing; FlowHypervisor separates execution, kill and observation relationships and uses current desktop receipts/timing. GUI-Manager remains design only.

See [configuration, examples and limitations](docs/desktop-input-and-flow-contracts.md), the [complete generated coverage inventory](docs/agent-coverage.md), and the [GUI-Manager design](docs/GUI-Manager-design.md).

## Video-Analyzer content analysis

Video-Analyzer supports `analysis_type: robotics` (default), `transcription`, and `summary`. Robotics preserves the deterministic motion gate and dual-vision/merge verdict, with `PASS_OK` only on two explicit independent passes. Transcription reads selected video audio tracks (`audio_tracks: all` or `0,1`) using Whisperer's local faster-whisper backend, GPU auto/CPU fallback and timestamped segments; it never opens a microphone. Summary combines speech with two independent visual observers over frame batches spanning the whole clip, then synthesizes an overview, chronology, readable screen text, facts, steps, decisions, action items and limitations. Content modes accept static scenes, bypass the motion gate, and emit `TLM_ANALYSIS::` tokens rather than robotics verdicts. Missing audio/speech and partial failures are explicit. Each content run saves transcript, segments, report and full analysis artifacts. Parametrizer and wrapped chat results expose `analysis_type`, `analysis_token`, `transcript`, `summary`, `audio_status`, timestamped `segments_json` and artifact paths; the body remains `response_body`. Input remains a file, wildcard, newest video in a folder or Camcorder pool name, or a web link (YouTube and other sites): Video-Analyzer downloads it itself (one item; sound only for transcription), joins picture and sound with PyAV when ffmpeg is absent, keeps a self-updating private yt-dlp, names every download failure, and adds `source_url`/`source_title` to its result. Always starts downstream agents; sampled perception is not exhaustive.

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

## Image/video error reporting and recovery (2026-09-26)

Image/video model failures accumulate in one shared, themed, non-modal fatal-error dialog with an audible notification. Tlamatini keeps running: preserve its retry/tactic ladder, cancellation controls and configured flow recovery routes. Keep the configured model identities; never report a surviving observer or raw concatenation as successful analysis. Dismiss hides the dialog while retaining its history; new failures reopen it. See [the shared behavior and verification contract](docs/visual-analysis-errors.md).

## Direct microphone input is not an MCP tool (2026-09-27)

Config → Mic is the last chat Config entry. It chooses automatic submission or
an editable draft for manual Send, and saves per-browser capture preferences.
Neither the settings dialog nor draft-only transcription invokes an MCP tool.
Model orchestration starts only after the resulting text is actually submitted.

The chat button beside Send uses authenticated same-origin `/ws/chat-voice/`
and an internal resident Whisperer worker. It does not need an External MCP,
ACPX, a model tool decision or a newly registered agent. The transcript returns
to the browser's composer, which either submits with current options or keeps
an editable draft according to Config → Mic.
Existing Whisperer workflow/MCP tools keep their own contracts. See
[the microphone guide](docs/chat-microphone-design.md).
