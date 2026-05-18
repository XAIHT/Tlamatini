# Tlamatini — ACPX (Agent Communication Protocol eXtension)

This file is the authoritative reference for what **ACPX** means in Tlamatini, the mechanics it implements, and the contract every part of the system (LLM, planner, tools, frontend) honors. Whenever the user mentions "ACPX", "ACPX mechanics", "ACP child", "use ACPX to ...", "spawn an external CLI", "leg A → leg B", "multi-CLI relay", "hand off transcript", or anything semantically equivalent, route them through this surface — do not paraphrase, do not invent a workaround.

---

## Definition

**ACPX = Agent Communication Protocol eXtension.**

It is Tlamatini's runtime for spawning **external coding-agent CLIs** as out-of-process child processes, talking to them over stdin/stdout, persisting the conversation as an NDJSON transcript, and brokering the whole thing to the LLM as Tlamatini tools.

ACPX is a **Python port of OpenClaw's ACPX plugin** (`extensions/acpx/`). The surface is API-compatible: `agent_id` mapping, `permissionMode` vocabulary, and the `SKILL.md` frontmatter contract all match verbatim, so any acp-router skill written for OpenClaw runs unmodified on Tlamatini and vice versa.

### ACPX toolbar toggle (per-request enable/disable)

The chat toolbar exposes three checkboxes: **Multi-Turn**, **Exec Report**, and **ACPX**. The ACPX checkbox (`#acpx-enabled` in `agent/templates/agent/agent_page.html`) **defaults to unchecked** — both visually (the JS hydration in `agent_page_state.js::applyStoredAcpxState` falls back to `false` when sessionStorage has no prior value) and on the backend (every read site — `interface.py::ask_rag`, `factory.py`, `chains/unified.py` payload-rebuild whitelist, `mcp_agent.py::CapabilityAwareToolAgentExecutor.invoke`, `consumers.py::receive` and the `queue_llm_retrieval` signature — defaults `acpx_enabled` to `False`). The checkbox sends an `acpx_enabled` boolean on every WebSocket request, the planner / executor call `agent.acpx.filter_acpx_tools(tools, acpx_enabled)` to strip the entire ACPX/Skill tool surface (the 12 names listed below) from the bound tool list whenever the flag is `False`, and the result is that **the default request behaves exactly like the legacy pre-ACPX Multi-Turn flow** — no `acp_*` / `*_skill` tools are even visible to the planner. `bypass_prompt_validation` is computed as `multi_turn_enabled OR acpx_enabled`, so the system still skips prompt-shape validation when only ACPX is checked (which is the right behavior because ACPX flows are LLM-operator flows, not Q&A).

The 12 ACPX/Skill tool names live in `agent.acpx.ACPX_TOOL_NAMES` (a `frozenset`) and are also registered in `_EXEC_REPORT_TOOLS` (in `agent/mcp_agent.py`) under `agent_key="acpx"` for the spawn/send/wait/kill family and `agent_key="skill"` for `invoke_skill`, so the Exec Report still merges all spawn/send/wait/kill rows into one "List of ACPx Operations" table when the user re-enables ACPX. Adding a 13th LLM-facing ACPX tool requires updating BOTH `ACPX_TOOL_NAMES` AND the executor whitelist in `unified.py` — the same drop-on-rebuild bug class that bit `exec_report_enabled` once already.

---

## Supported external coding agents (the `agent_id` registry)

Defined in `agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS`. Each agent has a transport profile that controls how the runtime drives the child:

| `agent_id` | Default command | Transport | Prompt argv form | Default budgets (timeout / idle / grace) |
|---|---|---|---|---|
| `claude` | `claude` | `oneshot-prompt` | `claude -p "<task>"` | 180 s / 10 s / 2 s |
| `codex` | `codex` | `oneshot-prompt` | `codex exec "<task>"` | 180 s / 10 s / 2 s |
| `cursor` | `cursor-agent` | `oneshot-prompt` | `cursor-agent -p "<task>"` | 180 s / 10 s / 2 s |
| `gemini` | `gemini` | `oneshot-prompt` | `gemini -p "<task>"` | 180 s / 10 s / 2 s |
| `qwen` | `qwen-code` | `oneshot-prompt` | `qwen-code -p "<task>"` | 180 s / 10 s / 2 s |
| `tlamatini` | `python -m agent.acpx.self_acp_server` | `json-acp` | (stdin envelope) | 45 s / 6 s / 12 s |
| `kiro` | `kiro` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `kimi` | `kimi` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `iflow` | `iflow` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `kilocode` | `kilocode` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `opencode` | `opencode` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `pi` | `pi` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `droid` | `droid` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `copilot` | `copilot` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |

### Transport modes

- **`oneshot-prompt`** — Each turn re-spawns the CLI with the prompt as a CLI argument behind `prompt_arg_flag` (or `prompt_subcommand_args` for codex), closes stdin, and captures stdout to EOF. This is the **only** transport that reliably captures responses from TUI agents (claude / gemini / cursor / qwen) on Windows: TUI CLIs detect the piped stdout and refuse to flush, so a long-lived stdin-fed child captures the outbound prompt only — never the answer. The fix is to call them in their own `-p`/`--print` mode where they print the answer to stdout and exit. There is no inter-turn session state inside the child process; conversation continuity must be carried in the next prompt by the caller.
- **`json-acp`** — Child speaks one JSON envelope per turn ending with `{"done": true}`. Strict ACP contract; the `tlamatini` self-host server uses it.
- **`tui-repl`** — Long-lived interactive REPL over stdin/stdout with the transport-aware idle rule. Used for CLIs whose one-shot flag is unknown to us yet — override per-agent in `config.json.acpx.agents.<id>` (set `transport: oneshot-prompt`, `prompt_arg_flag: "-p"`) once you confirm one.
- **`one-shot`** — Single-task-per-process via stdin (`python script.py < task`). Stdin closes after the first write; runtime waits for child exit.

User overrides go in `config.json`:

```json
{
  "acpx": {
    "agents": {
      "claude": { "command": "C:/Users/me/AppData/Roaming/npm/claude.cmd" },
      "cursor": { "command": "/usr/local/bin/cursor-agent" }
    }
  }
}
```

Custom `agent_id`s declared via overrides default to `tui-repl` with the fast-path defaults.

---

## The 12 ACPX/Skill tools (LLM-facing surface)

All tools return a JSON envelope. The LLM never raises — every error is `{"ok": false, "reason": "...", "code": "..."}`.

### Health & enumeration
- `acp_doctor()` — health probe + per-agent enumeration.
  - Returns `{ok, message, details:[{agent_id, command, description, resolvable, cli_version}], probe:{agent_id, stdout, stderr}}`.
  - **Always call first** when an ACPX flow starts so the LLM knows which `agent_id`s are resolvable on this host.
- `list_acp_agents()` — same enumeration without the version probe (cheaper).

### Session lifecycle
- `acp_spawn(agent_id, task, cwd="", mode="session", session_label="", timeout_seconds=0, idle_seconds=0, startup_grace_seconds=0, max_event_chars=0)`
  - Spawns a child for `agent_id`, dispatches `task`.
  - For TUI agents: returns sub-second with `spawned_immediately:true` and an empty `events` array. The drain happens on the next call.
  - For JSON-ACP agents: drains until `done:true` or the configured timeout.
  - Returns `{session_id, agent_id, transport, transcript_path, events, events_total, spawned_immediately}`.
- `acp_send(session_id, text, timeout_seconds=0, idle_seconds=0, startup_grace_seconds=0, max_event_chars=0)`
  - Send a follow-up turn to an existing session.
- `acp_send_and_wait(session_id, text, until_idle_seconds=10, max_wait_seconds=180, max_event_chars=0)`
  - Same as `acp_send` but blocks until the child settles (idle rule fires).
  - Returns `{events, events_total, settled}` — `settled=True` means the drain ended on the idle rule (clean), not the timeout backstop.
  - **Prefer this for "wait for the full answer" / "complete answer" / "settle" prompts.**
- `acp_kill(session_id)` — terminate the child process. Returns `{killed, transcript_path, agent_id, pid}`.

### Reads
- `acp_transcript(session_id, max_chars=8000, direction="all")` — read the on-disk transcript (`{events, text, total_size, truncated, transcript_path}`). `direction` ∈ `"all" | "in" | "out"`.
- `acp_session_status(session_id)` — `{alive, pid, transcript_size, last_event_at, closed}`.
- `acp_list_sessions()` — enumerate all live sessions in the runtime.

### Hand-off
- `acp_relay(session_id_src, session_id_dst, transform="last_assistant_text", prefix="", suffix="", until_idle_seconds=10, max_wait_seconds=180, max_event_chars=0)`
  - Single-call hand-off: reads the source transcript, extracts the assistant text (or `transform="full_transcript"`), wraps with optional `prefix`/`suffix`, sends to the destination session, waits for it to settle.
  - **One tool call replaces a 3-step dance** (`acp_transcript` → string-manipulate → `acp_send`). Always prefer it on relay/hand-off prompts.

### Skills
- `list_skills(filter_keywords="")` — list registered SKILL.md packages.
- `invoke_skill(skill_name, args_json)` — run a skill inside the SkillHarness. The skill `acp-router` is the canonical companion: it picks the best `agent_id` for an intent.

---

## Canonical ACPX flows the LLM must recognize

### 1. Spawn-and-go (single agent)
```
acp_doctor
  → acp_spawn(agent_id, initial_task)
    → acp_send_and_wait(session_id, follow_up_question)
      → acp_kill(session_id)
```

### 2. Multi-CLI relay (leg A → leg B)
```
acp_doctor
  → acp_spawn(leg_a_id, task_a)
    → acp_send_and_wait(session_a, ...)         # let A produce its answer
      → acp_spawn(leg_b_id, prompt_template_b)  # B's prompt template
        → acp_relay(session_a, session_b)       # ONE call: hand off A's text to B
          → acp_kill(session_a)
            → acp_kill(session_b)
```

A single `acp_relay` replaces the otherwise-required `acp_transcript` → string-manipulate → `acp_send` sequence.

### 3. Harvest transcript & report
```
... do the work via acp_spawn / acp_send_and_wait ...
  → acp_transcript(session_id)
    → invoke_skill('summarize', {text, target_words})   # compress
      → chat_agent_file_creator(filepath, content)      # write report
        → chat_agent_notifier(title, message)           # signal done
          → acp_kill(session_id)
```

### 4. Skill-driven agent routing
```
list_skills
  → invoke_skill('acp-router', {intent: '...', prefer: 'gemini'})
    → acp_spawn(<returned agent_id>, task)
      → ...
```

---

## Required behavior (contract the LLM honors)

1. **Always call `acp_doctor` first** on an ACPX flow so the LLM knows which `agent_id`s are resolvable. Branch on `details[].resolvable`.
2. **Capture `session_id` on every `acp_spawn`** — every follow-up tool call needs it.
3. **Always call `acp_kill` at the end of each session you spawned.** Sessions left alive count against the runtime's session cap.
4. **Use the dedicated ACPX tool, never an `execute_command` workaround.** Reading a transcript via `type` / `cat` is wrong — use `acp_transcript`.
5. **Honor named `agent_id`s.** If the user says "pin leg A to gemini", pass exactly `agent_id="gemini"`. If gemini isn't resolvable, announce the fallback in one short line and pick another resolvable id.
6. **For "complete answer" / "wait for full answer" / slow REPL prompts**: prefer `acp_send_and_wait` with `until_idle_seconds=15, max_wait_seconds=180`, or pass `timeout_seconds=120, idle_seconds=15` to `acp_send`. The default TUI 8 s timeout is tuned for "session stays alive cheaply", not "produce a full essay".
7. **For relay/hand-off prompts**: always `acp_relay`, never the manual transcript-and-send dance.
8. **Operational siblings** of every ACPX flow:
   - `chat_agent_file_creator` — write the report.
   - `chat_agent_notifier` — signal completion.
   - `invoke_skill` — for `summarize` / `acp-router` skills.

---

## Runtime mechanics (what happens inside the box)

### `oneshot-prompt` (claude / gemini / cursor / qwen / codex)

`agent/acpx/runtime.py::AcpSession._oneshot_send_turn` runs each turn as a fresh process invocation:

1. **Persist outbound prompt** to the NDJSON transcript with `direction:"out"` and `transport:"oneshot-prompt"` so a crash before the spawn still leaves evidence.
2. **Resolve command** via `windows_spawn.resolve_command`. If unresolvable, yield an `error` event + `command_not_found` synthetic done.
3. **Build argv**: `[exe, *extra_args, *spec.args, *spec.prompt_subcommand_args, spec.prompt_arg_flag, "<task>"]` (the flag is omitted when None/empty so codex's `["exec", "<task>"]` works).
4. **Spawn** with stdin=PIPE, stdout=PIPE, stderr=PIPE; `text=True, encoding=utf-8`; `shell=resolved.use_shell` (Windows .cmd/.bat).
5. **Close stdin immediately** — most non-interactive CLIs need EOF to start producing output.
6. **`proc.communicate(timeout=deadline)`** captures stdout and stderr to EOF; on `TimeoutExpired` the child is killed and a final `communicate(timeout=5)` collects whatever was buffered.
7. **Persist captured output** as one transcript line per non-empty channel (`stdout`, `stderr`).
8. **Yield events**: one `assistant_message` event with `role:"assistant"` and the captured stdout in `text` (so `extract_last_assistant_text` picks it up verbatim and `trim_event_payload` can cap it for the LLM payload), one `log` event with `channel:"stderr"` if stderr was non-empty, then a synthetic `done` (`child_exited` or `timeout`) carrying `exit_code` and `elapsed_seconds`.

### `json-acp` / `tui-repl` / `one-shot` (long-lived child)

`agent/acpx/runtime.py::AcpSession.send_turn` is the heart. Per turn:

1. **Write `{"task":"...","mode":"session"}\n` to child stdin** (and `close()` for `transport="one-shot"`).
2. **Daemon reader thread** drains child stdout into a `queue.Queue` line-by-line. Cross-platform; needed because Windows `readline()` on a pipe cannot be interrupted.
3. **Drain loop** wakes every 100 ms (queue `get(timeout=0.1)`) and checks four completion conditions, in order:
   1. The child emits a JSON line with `"done": true` (strict ACP).
   2. The child closes stdout (process exit) — reader pushes a `None` sentinel.
   3. `timeout_seconds` elapsed (hard backstop) — yields `{done:true, _synthetic:"timeout", events_seen, transport}`.
   4. **Idle rule** fires — yields `{done:true, _synthetic:"idle", idle_seconds, events_seen, transport}`. The transport-aware variant of this rule is the real fix for slow ACPX execution:
      - `transport="json-acp"`: idle rule arms only after `event_count > 0` AND `now - last_event_at >= idle_seconds` AND `now - started_at >= startup_grace_seconds`. (A JSON-ACP child contractually emits at least one event per turn.)
      - `transport="tui-repl"` / `"one-shot"`: idle rule arms after `now - started_at >= startup_grace_seconds + idle_seconds` **even with zero events**. A silent TUI is, by definition, finished; the previous code waited the full timeout because it required `event_count > 0`.

4. **Every line received and the outbound task itself are appended to the per-session NDJSON transcript** at `<state_dir>/<session_id>.transcript.ndjson`. The transcript is what `acp_transcript` and `acp_relay` read from.

`acp_spawn` honors `spawn_returns_immediately`: for TUI agents it returns the `session_id` sub-second without draining; the drain happens on the next `acp_send` / `acp_send_and_wait` / `acp_transcript`. The LLM can override with `timeout_seconds>0` to force a drain on spawn.

---

## Permission model

`agent/acpx/permissions.py::PermissionGate` enforces three modes (matching OpenClaw's vocabulary verbatim):

- `approve-reads` (default) — read actions are auto-approved; write actions go through the gate.
- `approve-all` — flagged dangerous; auto-approves everything.
- `deny-all` — blocks all spawns. `acp_spawn` raises `PERMISSION_DENIED`.

`non_interactive` policy is `deny | fail` for unattended runs.

---

## ACPXer — the visual canvas counterpart

The 12 tools above are the **LLM-facing** ACPX surface. **ACPXer** is the **canvas-facing** counterpart: a workflow agent (one of the 62 in the visual ACP designer) that drives ONE ACPX session lifecycle from a drag-and-drop node.

- **Lives at**: `agent/agents/acpxer/acpxer.py` + `config.yaml`. Self-contained — does NOT import `agent.acpx.runtime`, so it works identically in source and frozen builds (the agent pool runs as separate Python subprocesses with no path back into the Django app). It mirrors the runtime's transport-aware drain rule and `agent_id` registry inline.
- **What it does, in order**: read `config.yaml` → resolve `agent_id` → command + transport + budgets via the registry mirror → spawn the child via `subprocess.Popen` → write task envelope (`{"task":..., "mode":"session"}\n` for `json-acp`, raw `task\n` for `tui-repl`) → drain stdout via daemon reader thread + 100-ms tick + 4-rule completion (json `done:true` / child exit / hard timeout / transport-aware idle) → extract last-assistant text → kill child → emit `INI_SECTION_ACPXER<<<` block → trigger `target_agents`.
- **Transcript format**: writes `<agent_dir>/transcript.ndjson` with the SAME `{"direction": "in"|"out", "text", "raw", "ts"}` lines that the in-process runtime writes — the two formats are interchangeable, so a future tool could read an ACPXer transcript via the existing `read_transcript` helper without modification.
- **Output contract** (consumed by Parametrizer, registered in `views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS['acpxer']`): KV header `agent_id`, `session_id`, `transport`, `settle`, `transcript_path`; body = `response_body` (= last-assistant text). This means the canonical visual relay flow is:
  ```
  Starter → ACPXer(claude) → Parametrizer → ACPXer(gemini) → Parametrizer → ACPXer(cursor) → File-Creator → Ender
  ```
  Each Parametrizer copies the previous ACPXer's `response_body` into the next ACPXer's `task` — three different LLMs argue back and forth in a fully visual, fully unattended pipeline.
- **Relationship to the 12 tools**: same `agent_id` registry (claude / cursor / gemini / qwen / codex = `oneshot-prompt`; tlamatini = `json-acp`; kiro / kimi / iflow / kilocode / opencode / pi / droid / copilot = `tui-repl`); same transport-aware drain rule for legacy paths; same fresh-process-per-turn capture path for `oneshot-prompt`; same NDJSON transcript format; same default budgets per transport. **The two surfaces produce interchangeable artefacts**.
- **When to use which**:
  - LLM operator in this chat ("spawn claude and relay to gemini") → use the 12 tools (`acp_spawn` / `acp_send_and_wait` / `acp_relay` / `acp_kill`).
  - Visual / .flw / Croner-scheduled / unattended flows → use ACPXer nodes on the canvas. FlowCreator (the AI flow designer) knows the patterns.
- **CSS gradient (Aurora Conduit)**: `.canvas-item.acpxer-agent { linear-gradient(135deg, #0B1F3A 0%, #5A1FB8 33%, #EC4899 66%, #22D3EE 100%) }` — cosmic-navy → electric-violet → luminous-magenta → cyan-radiance. Distinct from `.acpx-agent` (the LLM-driven exec-report row, fire-orange) so the user can tell at a glance which surface is in play.

---

## Files involved

- `agent/acpx/agent_registry.py` — `DEFAULT_ACP_AGENTS`, `AcpAgentSpec` (transport, defaults, `spawn_returns_immediately`), `build_agent_registry`.
- `agent/acpx/runtime.py` — `AcpxRuntime`, `AcpSession`, daemon reader thread, transport-aware idle rule, doctor, list_sessions, session_status, read_transcript, kill (returns record), event trimming, last-assistant extraction.
- `agent/acpx/tools.py` — the 12 LangChain `@tool` functions.
- `agent/acpx/session_store.py` — `FileSessionStore`, reset-aware semantics.
- `agent/acpx/permissions.py` — permission gate.
- `agent/acpx/config.py` — config schema mirror of OpenClaw's plugin.json.
- `agent/acpx/windows_spawn.py` — Windows-aware command resolution.
- `agent/acpx/tests.py` — 60 unit tests covering every tool + the redesigned drain.
- `agent/capability_registry.py` — `_EXTRA_HINTS_BY_TOOL_NAME` ACPX entries, `_ACPX_SIGNAL_TOKENS` boost, `ACPX_CO_SELECTION_RULES` (sibling auto-injection).
- `agent/global_execution_planner.py` — applies `ACPX_CO_SELECTION_RULES` so e.g. selecting `acp_spawn` auto-co-selects `acp_doctor` + `acp_kill`.
- `agent/mcp_agent.py` — `_EXEC_REPORT_TOOLS` registers ACPX rows under `agent_key="acpx"` so spawn / send / send_and_wait / kill / relay merge into one Exec Report table.
- `agent/prompt.pmt` rule 12 — the LLM-facing version of this contract.
- `agent/agents/acpxer/acpxer.py` + `config.yaml` — the **visual ACPXer** workflow agent (canvas counterpart of the 12 tools). Self-contained subprocess that mirrors the runtime's transport-aware drain in ~120 lines, writes interchangeable NDJSON transcripts, emits Parametrizer-compatible `INI_SECTION_ACPXER<<<` blocks.
- `agent/agents/parametrizer/parametrizer.py` — `SECTION_AGENT_TYPES` includes `'acpxer'` so Parametrizer can pipe ACPXer output into a downstream node's config.
- `agent/views.py` — `PARAMETRIZER_SOURCE_OUTPUT_FIELDS['acpxer']` lists the 6 fields downstream agents can address: `agent_id`, `session_id`, `transport`, `settle`, `transcript_path`, `response_body`.
- `agent/agents/flowcreator/agentic_skill.md` — entry #58 documents ACPXer for the AI flow-designer (FlowCreator); it includes the four canonical flow patterns (single-shot CLI run, visual multi-CLI relay, scheduled audit, branching on CLI failure).
- `agent/agents/flowhypervisor/monitoring-prompt.pmt` — `ACPXER SPECIAL NOTES` block tells the watchdog to NOT flag long-running drains, NOT flag a `settle=timeout` line as an error, and NOT flag content of `INI_SECTION_ACPXER<<<` blocks; it DOES flag `Command not resolvable on PATH` as a real error.

---

## ACPX-Skills admin menu (chat navbar dropdown)

Added 2026-05-17. The chat navbar has a fourth dropdown — **ACPX-Skills** — that admins every SKILL.md package under `agent/skills_pkg/`. Position is between **Agents** and **Config** in `agent/templates/agent/agent_page.html`.

Four entries:

| Entry | Backing | What it does |
|---|---|---|
| **Browse Skills** | `GET /agent/skills/` (list) + `GET /agent/skills/<name>/` (detail) | Search-filterable list pane + detail pane showing frontmatter, requires, inputs/outputs, permissions, body. Pure read; no DB writes. |
| **Configure Skills** | WebSocket `set-skills` channel (mirrors `set-mcps` / `set-agents` exactly) | Checkbox grid toggling `Skill.enabled` per row. Payload encoding: comma-separated `name=description=true/false`. |
| **Diagnostics** | `GET /agent/skills/_/diagnostics/` | Cross-checks every skill's `requires_tools` / `requires_mcps` against disabled `Tool` / `Mcp` rows; flags `runtime:acpx` skills whose `acpx_agent` isn't in the registry; surfaces orphan DB rows (Skill row exists, SKILL.md gone). |
| **Reload Registry** | `POST /agent/skills/_/reload/` | Re-runs `agent/acpx/service.py::boot_skills()` — rescans `agent/skills_pkg/`, refreshes Skill rows, prunes deleted ones. No server restart needed. |

### Persistence shape (DB stays at "enumeration + enable/disable" only)

The `Skill` model was pre-existing from migration `0071_acpx_skills.py` and is auto-seeded by `boot_skills()` from `apps.AgentConfig.ready()` on a background thread. The admin UI **only ever writes `Skill.enabled`** via `consumers.AgentConsumer.save_skill(name, enabled)`. The cached fields (`description`, `runtime`, `acpx_agent`, `frontmatter_json`, `body_sha256`) are owned by `boot_skills()` and refreshed from SKILL.md on every reload — the disk is the only source of truth for permissions, budgets, body. Browse / Diagnostics read fresh from `skill_registry`, not from those cached columns.

### Tool-surface gating

When `Skill.enabled = False`:
- `list_skills` (`agent/acpx/tools.py`) filters the row out of its return value.
- `invoke_skill` returns `{"ok": false, "code": "SKILL_DISABLED"}`.

Implemented via `_disabled_skill_names()` in `agent/acpx/tools.py` — **fails open** (empty set on any DB exception) so a broken admin layer never silently hides skills from the LLM. The ACPX toolbar checkbox is the orthogonal global gate; both must allow the skill for the LLM to see it.

### WebSocket wiring (mirrors Mcps/Agents/Tools verbatim)

- `consumers.skill_establishment(name, description, enabled)` sends one `type:'skill'` system message per Skill row on connect (both the rebuild path and the session-restore path).
- Frontend `agent_page_chat.js` catches those and pushes into the module-level `skills = []` array (declared in `agent_page_state.js`).
- The Configure dialog (`skills_dialog.js::preRenderSkillsConfigureDialog`) reads from that array; Continue dispatches `set-skills` via `sendChatSocketMessage`.
- Backend `set-skills` handler in `consumers.receive()` parses the payload and calls `save_skill(name, enabled)` — touches only `Skill.enabled`.

### Naming convention (no `<prefix>-N` shim for Skills)

`Skill` rows are keyed on `name` (the SKILL.md frontmatter `name`, e.g. `acp-router`) directly. There is NO `skill-N` ID-prefix transformation like the `mcp-N` / `tool-N` / `agent-N` pattern uses — the SKILL.md `name` is already unique. The `_normalize_toggle_record_name('skill', ...)` helper in `consumers.py` does NOT apply.

### Files

- Backend: `agent/views.py` (`list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`); `agent/urls.py` (4 routes); `agent/consumers.py` (`skill_establishment`, `get_all_skills`, `save_skill`, `set-skills` handler, establishment loops in both rebuild paths); `agent/acpx/tools.py` (`_disabled_skill_names()` + gating in `list_skills` / `invoke_skill`).
- Frontend: `agent/templates/agent/agent_page.html` (navbar dropdown + 3 dialog containers + asset includes); `agent/static/agent/js/skills_dialog.js` (jQuery-UI dialogs for all 4 entries); `agent/static/agent/js/agent_page_init.js` (`OpenSkillsXyzDialog` + `ReloadSkillRegistry` entry points); `agent/static/agent/js/agent_page_chat.js` (`type:'skill'` system-message handler); `agent/static/agent/js/agent_page_state.js` (`let skills = []` global); `agent/static/agent/css/skills_dialog.css` (styling).
- Lint: `eslint.config.mjs` (11 new globals: `skills`, `computeCheckboxGridLayout`, `OpenSkills*Dialog`/`preRender`/`render`/`open`/`reload` family).
- Coverage: 14 tests in `agent/tests.py` — `SkillsAdminEndpointTests` (7), `SkillsToolSurfaceGatingTests` (3), `SkillsNavbarTemplateContractTests` (4). The template-contract class pins the dropdown HTML so a careless edit doesn't silently drop the menu.

---

## When the user says "ACPX" (decision matrix)

| User says... | You do... |
|---|---|
| "Use ACPX to ..." / "ACPX mechanics" / "ACP child" | Recognize as an ACPX request. Run a canonical flow per the prompt's steps. |
| "Spawn a child" / "external coding agent" | `acp_doctor` → `acp_spawn`. |
| "Wait for the full answer" / "complete answer" | `acp_send_and_wait` with longer `until_idle_seconds`. |
| "Harvest the transcript" / "cite the transcript" | `acp_transcript`. |
| "Hand off" / "leg A → leg B" / "relay" / "multi-CLI" | `acp_relay`. |
| "Pin leg A to gemini" | `agent_id="gemini"` exactly. Fallback only if not resolvable. |
| "Is the session alive?" / "session status" | `acp_session_status`. |
| "List sessions" / "what's running" | `acp_list_sessions`. |
| "Kill the session" / "terminate" / "graceful kill" | `acp_kill`. |
| "Pick the best agent for ..." | `invoke_skill('acp-router', {intent, prefer})`. |
| "Summarize the transcript" | `acp_transcript` → `invoke_skill('summarize', {...})`. |
| "Build a visual flow that uses ACPX" / "Draw a multi-CLI relay" / ".flw with ACPX" / "scheduled multi-CLI" / "Croner-driven ACPX" | This is the **ACPXer canvas surface**, not the 12 tools. Hand the request to FlowCreator (or describe the canvas wiring): `Starter → ACPXer(<id>) → Parametrizer → ACPXer(<id>) → ... → Ender`. Do NOT use `acp_spawn` here. |
| Anything not in this table but mentioning ACPX | Run `acp_doctor` first to ground yourself, then pick the closest flow. |
