---
name: tlamatini-agent-creation
description: The authoritative, exhaustive end-to-end runbook for creating a BRAND-NEW Tlamatini workflow agent — every surface, in order, with 530+ numbered steps across 26 phases. Invoke whenever Angela says "create a new agent", "add an agent", "make a <X>er agent", "I want a new canvas agent", or asks to wire any new pool agent across backend + frontend + Multi-Turn + Parametrizer + FlowCreator + FlowHypervisor + watchdog + config dialog + demo prompts + Python tests + Playwright harness tests + docs + packaging. Covers naming, coloring, the inputs/outputs connector contract in agentic_control_panel.html, the Multi-Turn (wrapped chat-agent) tool, Exec Report, the configuration dialog, automated unit tests AND Playwright tests in Claude's harness. Pairs with tlamatini-agent-naming (casing) and the @-imported create_new_agent.md / create_new_mcp.md.
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Tlamatini — Complete New-Agent Creation Runbook (700+ steps)

> **Audience:** Claude Code working ON the Tlamatini codebase for **Angela**.
> **Scope:** adding ONE brand-new workflow agent end-to-end across **every** surface
> Tlamatini touches — backend pool script, Django view/url, migration, Parametrizer,
> CSS coloring, all the frontend JS, the `agentic_control_panel.html` inputs/outputs
> connector contract, the configuration dialog, Multi-Turn (the wrapped chat-agent
> tool), the Exec Report, FlowCreator's `agentic_skill.md`, FlowHypervisor's
> `monitoring-prompt.pmt`, the command watchdog + orphan reaper, demo "Prompts
> example" creation, `requirements.txt`/`build.py` packaging, a full Python unit-test
> module, AND a Playwright regression in Claude's own harness — then docs, lint,
> migrate, and a **visible** dogfood run.
>
> **This skill is the master checklist.** The two `@`-imported guides
> (`Tlamatini/.agents/workflows/create_new_agent.md`, `Tlamatini/.mcps/create_new_mcp.md`)
> are the canonical mechanics for individual surfaces; this skill is the *superset* that
> also nails the things they leave implicit (watchdog, FlowHypervisor, config dialog,
> demo prompts, Python tests, Playwright tests, packaging). **Read both `@`-imports and
> the `tlamatini-agent-naming` skill first**, then execute the steps below in order.

---

## Placeholders used throughout (decide these in Phase 0, then NEVER drift)

| Token | Meaning | Example (`Pingerer`) |
|---|---|---|
| `<Display>` | exact-cased display name = DB `agentDescription` (single source of truth) | `Pingerer` |
| `<lower>` | `<Display>`.lower(), spaces→nothing for single-word; underscores for multi-word dir | `pingerer` |
| `<dash>` | `<Display>`.toLowerCase().replace(/\s+/g,'-') — CSS classMap key | `pingerer` |
| `<space>` | `<Display>`.toLowerCase() preserving spaces — JS connection checks | `pingerer` |
| `<Pascal>` | JS connector symbol fragment `update<Pascal>Connection` | `Pingerer` |
| `<CAPS>` | ALL-CAPS protocol token base — `INI_SECTION_<CAPS>` + `<CAPS> SPECIAL NOTES` | `PINGERER` |
| `<css>` | the canvas/exec-report CSS class root (== `<dash>` minus dashes for single-word, kept dashed for multi-word; equals `<lower>` for single-word) | `pingerer` |
| `N` | the agent's idAgent / migration sequence number | (next free) |

> **Worked multi-word example** (`Node Manager`): `<Display>=Node Manager`,
> `<lower>=node_manager` (dir/pool/file), `<dash>=node-manager` (CSS classMap key),
> `<space>=node manager` (connection checks), `<Pascal>=NodeManager`,
> `<CAPS>=NODE_MANAGER`, `<css>=node-manager` / `nodemanager-agent` (verify against an
> existing multi-word agent — historically some classMap values dropped the dash, e.g.
> `'node-manager': 'nodemanager-agent'`; COPY an existing sibling exactly).

---

# PHASE 0 — Preflight, scoping & naming (lock these before any code)

1. Confirm with Angela the agent's **purpose** in one sentence (what task it performs).
2. Decide whether the agent is **deterministic** (no LLM) or **LLM-powered** — this changes config keys and FlowHypervisor timing notes.
3. Decide whether the agent is **state-changing** (mutates files/DB/remote/GUI/sends messages) or **observational/read-only** (Shoter/Camcorder/Recorder/AudioPlayer/VideoPlayer/Monitor-*). This decides Exec-Report membership.
4. Decide whether the agent is **Active** (starts downstream via `target_agents`) or **Terminal/Monitoring** (does not).
5. Decide whether the agent **produces structured output** consumed by Parametrizer (emits `INI_SECTION_<CAPS>`).
6. Decide whether the agent should be **LLM-callable in Multi-Turn** (a wrapped `chat_agent_<lower>` tool) — most new agents should be.
7. Decide whether the agent is **long-running** (Monitor-style) or **short-lived**.
8. Decide whether the agent **scaffolds project directories** (firmware/engine style → defaults to `<app>/Templates`) or writes **scratch** (→ `<app>/Temp`).
9. Decide whether the agent **spawns console child processes** (relevant to the orphan reaper + command watchdog).
10. Decide whether the agent has a **singleton** constraint (only FlowCreator/FlowHypervisor are; a normal agent is not).
11. Lock the **`<Display>`** name with EXACT casing — this is `agentDescription` and the single source of truth.
12. **Invoke the `tlamatini-agent-naming` skill** and derive `<lower>`, `<dash>`, `<space>`, `<Pascal>`, `<CAPS>`, `<css>` from `<Display>` per its transform table.
13. NEVER let any non-identifier surface display a different casing of `<Display>` (Angela is emphatic — STM32er must never become STM32Er).
14. Pick the next free **idAgent / migration number** `N`: run `Glob` over `Tlamatini/agent/migrations/0*.py` and take `max+1`; confirm no `agentDescription='<Display>'` already exists.
15. Pick a reference sibling agent that most resembles the new one (e.g. Shoter for capture, Apirer for HTTP, Kalier for an API bridge, Camcorder/Recorder for media). You will COPY its structure.
16. Pick a **second** reference sibling that already does Multi-Turn + Parametrizer + Exec-Report so you can copy those wirings (Camcorder and Recorder are the most recent fully-wired examples).
17. Read the chosen sibling's `agent/agents/<sibling>/<sibling>.py` in full before writing anything.
18. Read the chosen sibling's `config.yaml` in full.
19. Read the sibling's `update_<sibling>_connection_view` in `views.py`.
20. Read the sibling's CSS block in `agentic_control_panel.css`.
21. Read the sibling's `ChatWrappedAgentSpec` in `chat_agent_registry.py`.
22. Read the sibling's `_PARAMETRIZER_OUTPUT_FIELDS` entry in `services/agent_contracts.py`.
23. Read the sibling's `_EXEC_REPORT_TOOLS` entry (if state-changing) in `mcp_agent.py`.
24. Read the sibling's `test_<sibling>_agent.py` in full — it is your test template.
25. Write down the **full list of `config.yaml` keys** the new agent needs (params + connection fields). This list is referenced by ~8 later surfaces; keeping it stable prevents silent drift.
26. Decide the agent's **connection-field shape**: `target_agents`+`source_agents` (normal), `target_agents_a/_b` (Asker/Forker), `target_agents_l/_g` (Counter), `source_agent_1/_2` (OR/AND), or `output_agents` (Stopper/Ender/Cleaner).
27. Decide the **INI_SECTION KV header fields** (what downstream agents can address) + whether there is a `response_body`.
28. Create a small scratch note (or a dated pivot file per `feedback_track_changes_pivot_file`) listing the verbatim request + every file you will touch, so a later "roll back just that change" is exact.

---

# PHASE 1 — Backend: the pool agent script + config.yaml

29. Create directory `Tlamatini/agent/agents/<lower>/`.
30. Create `Tlamatini/agent/agents/<lower>/config.yaml`.
31. In `config.yaml`, add a top comment `# <Display> Agent Configuration`.
32. Add each functional param key with a sensible default value (from your Phase-0 key list).
33. Add the connection fields that apply: `target_agents: []` if Active.
34. Add `source_agents: []` if it monitors upstream logs.
35. Use `output_agents: []` INSTEAD of `target_agents` ONLY for Stopper/Ender/Cleaner-style agents.
36. For OR/AND use scalar `source_agent_1: ""` / `source_agent_2: ""`.
37. For Asker/Forker use `target_agents_a: []` / `target_agents_b: []`.
38. For Counter use `target_agents_l: []` / `target_agents_g: []`.
39. Leave any credential/secret field as an **empty string** default (never hardcode a key — `regen_secrets.py` / Flow-Compiler redaction depends on this).
40. If a param is numeric, default it to a real number (not a string) so `yaml.safe_load` yields the right type.
41. If the agent has nested config, model it as a nested mapping (e.g. `llm:` block with `base_url`/`model`/`temperature`) mirroring the sibling.
42. Create `Tlamatini/agent/agents/<lower>/<lower>.py`.
43. Copy the FULL boilerplate from the reference sibling's `.py` (module preamble + all helpers + `main()` shape). DO NOT hand-roll helpers.
44. Make `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` the FIRST statement after `import os, sys`.
45. Keep the standard helpers verbatim: `load_config`, `get_python_command`, `get_user_python_home`, `get_agent_env`, `get_pool_path`, `get_agent_directory`, `get_agent_script_path`, `is_agent_running`, `wait_for_agents_to_stop`, `start_agent`, `write_pid_file`, `remove_pid_file`.
46. Ensure the log file name is exactly `{directory_name}.log` (the canvas reads this; any other name breaks LED/log surfacing).
47. Compute `CURRENT_DIR_NAME` and `LOG_FILE_PATH` the same way the sibling does.
48. Keep the top-of-module `subprocess.Popen.__init__` monkey-patch (`_chg_guarded_init`) that defaults `creationflags` to `CREATE_NO_WINDOW` — this is the orphan seatbelt; do not remove it.
49. Implement the agent's **core logic** between `logging.info("🚀 <CAPS> AGENT STARTED")` and the target-trigger block.
50. Use a distinctive emoji + `<Display>`-cased phrase in the STARTED log line (FlowHypervisor markers key off these — see Phase 18).
51. Wrap external/hardware/network calls in try/except so a missing device/host produces a logged error, not a crash.
52. For any numeric `config.get(...)` that could arrive as a wrapped-parser string (e.g. `"5 from the default mic"`), coerce via a `_coerce_int`/`_coerce_float` helper that extracts the leading number and never raises (see the Recorder fix — this caught a real incident).
53. Write the PID file immediately at the top of `main()` via `write_pid_file()`.
54. Remove the PID file in a `finally:` block via `remove_pid_file()`.
55. Add a short `time.sleep(0.4)` before `remove_pid_file()` to keep the LED green briefly (sibling pattern).
56. End `main()` with `sys.exit(0)`.
57. If Active, place the target-trigger block at the END of the work: `if target_agents: wait_for_agents_to_stop(target_agents)` then a `for target in target_agents: start_agent(target)` loop.
58. The concurrency guard `wait_for_agents_to_stop(target_agents)` MUST come BEFORE the `start_agent` loop (prevents duplicate spawns in looping flows).
59. If state-changing, ensure `target_agents` are triggered REGARDLESS of success/failure (so a downstream Forker can branch on the outcome) — match the "ALWAYS triggers target_agents" contract used by Kalier/Unrealer/STM32er/Camcorder.
60. Do NOT trigger `target_agents` from a Terminal/Monitoring agent (Emailer/Notifier/Monitor-*) — those leave `target_agents` as canvas-only metadata.
61. Add a final completion log line `logging.info("🏁 <Display> agent finished.")` before the `finally`.
62. Do NOT import anything from `agent.*` (the `agent` Django package) inside the pool script — pool subprocesses have no `sys.path` back into it (`ModuleNotFoundError`). Port any needed runtime mechanics inline (~100–200 lines) as ACPXer does.
63. Resolve any bundled asset path for BOTH frozen (`os.path.dirname(sys.executable)`) and source (`os.path.dirname(os.path.abspath(__file__))`) modes.
64. If the agent needs a third-party lib (e.g. `opencv-python`, `sounddevice`), import it lazily inside the function that uses it and report a clean message if it is absent (do not crash at import time).
65. Keep `main()` callable under `if __name__ == "__main__": main()`.
66. Verify `config.yaml` round-trips: `python -c "import yaml; print(yaml.safe_load(open(r'...config.yaml')))"`.
67. Confirm the script has no top-level side effects beyond the documented `os.chdir`/`logging.basicConfig` that the test harness saves+restores.
68. Confirm there is no top-level `def` placed above the imports (that trips ruff E402) — if you need a module-top guard (temp policy), make it an `if`-block, not a `def`.
69. Re-read the whole `.py` once and diff it mentally against the sibling to ensure no helper was accidentally dropped.

---

# PHASE 2 — Reanimation & lifecycle (pause/resume correctness)

70. Right after `LOG_FILE_PATH` is set and BEFORE `logging.basicConfig(...)`, add `_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'`.
71. Immediately after, add `if not _IS_REANIMATED: open(LOG_FILE_PATH, 'w').close()` (truncate only on a fresh start).
72. NEVER truncate the log when `_IS_REANIMATED` is true (resume appends).
73. In `main()`, when `_IS_REANIMATED`, log `🔄 <Display> REANIMATED (resuming from pause)` as the first line.
74. If the agent persists restart state (file offsets, counters, checkpoints), store it in files named `reanim*` (e.g. `reanim.pos`) so Ender can reset them on stop.
75. If the agent polls a source log, implement `save_reanim_offset(offset)` / `get_reanim_offset(...)` using `reanim.pos` (or `reanim_<source>.pos` per source).
76. Load the offset at startup and call `save_reanim_offset` after each read.
77. Confirm the agent is idempotent under resume: resuming produces the same behavior as if never interrupted.
78. Confirm the agent does NOT delete its own `reanim*` files (only Ender clears them on Stop).
79. Confirm a Counter-style agent uses `reanim.counter`; a Gatewayer-style uses `reanim_queue.json`/`reanim_dedup.json`; a registry agent uses `reanim_registry.json` (only if applicable).
80. Verify the three lifecycle modes mentally: Fresh start (no env var → truncate → STARTED), Reanimation (`AGENT_REANIMATED=1` → no truncate → REANIMATED → load reanim files), Stop (Ender clears reanim files).
81. Confirm pressing Start while PAUSED acts as Resume (no special code needed — the ACP handles it).
82. Confirm the agent does not assume it is always a fresh start anywhere in its logic.

---

# PHASE 3 — Structured output (INI_SECTION — Parametrizer producer)

83. If the agent feeds Parametrizer, define the section in the unified format: `INI_SECTION_<CAPS><<<` … `>>>END_SECTION_<CAPS>`.
84. Use `<CAPS>` = the UPPERCASE base name (single ALL-CAPS token convention — do NOT mixed-case it).
85. Put the KV header (one `key: value` per line) BEFORE the first blank line.
86. Put the multi-line body AFTER the first blank line (it becomes `response_body`).
87. If there is no body, omit the blank line (KV-only section).
88. Emit each section in a SINGLE atomic `logging.info(...)` call (concurrent writes interleave and corrupt otherwise).
89. Emit N separate sections for N results (one section per result/response).
90. Choose KV header field names that downstream agents will address (e.g. `output_path`, `status`, `url`, `return_code`, `success`).
91. Include `response_body` in the header field list ONLY if the section has a body.
92. Build the section string with explicit `\n` joins exactly like the sibling (do not use f-string multiline that swallows indentation).
93. Confirm the section start/end tokens match exactly (`INI_SECTION_<CAPS><<<` and `>>>END_SECTION_<CAPS>`).
94. If the agent ALWAYS emits the section even on failure (recommended for routable branching), document that in the section body (e.g. `status: error`).
95. Verify a round-trip parse: feed a sample log line through Parametrizer's `_parse_section_content` mentally or with a quick test (Phase 22 covers the real test).

---

# PHASE 4 — Temp & Templates directory policy (2026-06-02)

96. If the agent writes TEMPORARY/scratch files, route them under `<app>/Temp` — NEVER `C:\Temp`, `%TEMP%`, or a bare `tempfile.gettempdir()`.
97. Copy the module-top temp guard from `executer.py` verbatim: `if (os.environ.get('TLAMATINI_TEMP') or '').strip(): import tempfile as _tlt_tempfile; _tlt_tempfile.tempdir = os.environ['TLAMATINI_TEMP'].strip(); …`.
98. Keep that guard as an `if`-block (NOT a top-level `def`) so it sits above the imports without tripping ruff E402.
99. If the agent SCAFFOLDS a project/template directory (firmware/engine style), default its parent to `<app>/Templates` (`TLAMATINI_TEMPLATES`) unless Angela supplies a path.
100. Use `agent/path_guard.py` resolvers conceptually (`get_app_temp_root` / `get_app_templates_root`) — but remember the pool script can't import `agent.*`, so rely on the inherited `TLAMATINI_TEMP` / `TLAMATINI_TEMPLATES` env vars (the parent exports them).
101. Confirm `Temp` = throwaway scratch; `Templates` = deliverable project trees (never via `tempfile`).
102. Confirm no path the agent writes escapes the Tlamatini app root.
103. If you add an in-process `@tool` instead (rare), route its scratch through `path_guard.get_app_temp_root()` / `resolve_temp_path()` directly.
104. Note that `prompt.pmt` Rules 15/16 inject the absolute `{temp_directory}`/`{templates_directory}` for the LLM — you do not edit those unless the policy itself changes.

---

# PHASE 5 — Watchdog & orphan-reaper properties

105. If the agent spawns console child processes (`cmd`/`powershell`/external CLI), understand it is subject to the **command watchdog** (`agent/command_watchdog.py`).
106. Know the watchdog kills only console interpreters + descendants that make NO PROGRESS (CPU-seconds + IO bytes across the whole subtree) for N idle ticks past `hang_grace_seconds` — it is progress-based, NOT duration-based.
107. Ensure the agent's children make observable progress (CPU or IO) while working so the watchdog never kills a long-but-working job.
108. If the agent legitimately runs a long quiet external job, document expected behavior and consider that `command_watchdog_*` config keys are tunable (do not weaken the watchdog contract for one agent).
109. Confirm the agent never relies on a child that blocks on stdin with zero CPU+IO for the full grace window (that is exactly the hang class the watchdog targets — feed `DEVNULL`/EOF to children).
110. For an in-process `@tool` that runs a command, use the bounded `_run_command_bounded` pattern (Popen + stdin=DEVNULL + `communicate(timeout=...)` + whole-tree kill), not a naive `subprocess.run` (which is a fake guarantee for `shell=True` grandchildren).
111. Understand the **orphan reaper** (`agent/orphan_reaper.py`) Tier 1/2/3: if the new agent spawns console children via a NEW tool name, either add that tool name to `_PROCESS_SPAWNING_TOOL_NAMES` in `mcp_agent.py` (Tier-1 reap after it) or rely on Tier-2's pool-cmdline scan.
112. Confirm the agent's children carry the `CREATE_NO_WINDOW` default (the `_chg_guarded_init` monkey-patch handles this automatically — verify it is present from Phase 1).
113. Confirm the reaper/watchdog can never be tripped into killing the agent's OWN long-running python runtime (those are python, not console interpreters; the watchdog scopes to `cmd/powershell/pwsh` + descendants only).
114. For a VISIBLE/desktop agent (a window the user must SEE) that you launch yourself during dogfooding, recall the reaper protects ancestors + console-window owner + main PID — but the agent runs as its own subprocess, so it is reaped only if genuinely orphaned.
115. Note: the watchdog + reaper changes take effect in a frozen build only after `python build.py` — flag this to Angela if she runs the frozen `C:\Tlamatini` install.

---

# PHASE 6 — Backend: Django connection-update view + urls.py

116. Open `Tlamatini/agent/views.py`.
117. Copy `update_<sibling>_connection_view` and rename it `update_<lower>_connection_view`.
118. Keep the `@csrf_exempt` + `@require_POST` decorators.
119. Parse `data = json.loads(request.body.decode('utf-8'))`.
120. Read `target_agent`, `action` (default `'add'`), and `connection_type` (default `'target'`).
121. Return a 400 JSON error if `target_agent` is missing.
122. Normalize the agent id `<lower>-N` → pool name `<lower>_N` (split on `-`, pop trailing digit as cardinal, join base with `_`).
123. Reject path-traversal in the pool name (`'..'`, `'/'`, `'\\'`) with a 400.
124. Build `config_path = os.path.join(get_pool_path(request), pool_name, 'config.yaml')`; 404 if missing.
125. Load the config with `yaml.safe_load(...) or {}`.
126. Normalize the `target_agent` id → target pool name the same way.
127. Choose the list key: `source_agents` if `connection_type=='source'` else `target_agents` (or the agent's special connection field per Phase 0).
128. Ensure the list exists (`if not isinstance(config.get(list_name), list): config[list_name] = []`).
129. On `action=='add'`, append the target pool name if not present.
130. On `action=='remove'`, remove it if present.
131. **Omit-if-empty rule:** never write an empty string into a connection field (the deep-merge in `save_agent_config_view` would destroy a template default).
132. Write the config back with `yaml.dump(..., default_flow_style=False, allow_unicode=True, sort_keys=False)`.
133. Return `{"success": True, ...}` JSON.
134. Wrap the whole body in try/except returning a 500 JSON on error.
135. If the agent uses a special connection shape (Asker/Forker/Counter/OR/AND/Ender), copy that sibling's view instead — those write `target_agents_a/_b`, `target_agents_l/_g`, `source_agent_1/_2`, or `output_agents`.
136. Open `Tlamatini/agent/urls.py`.
137. Add `path('update_<lower>_connection/<str:agent_name>/', views.update_<lower>_connection_view, name='update_<lower>_connection'),`.
138. Confirm the route name is unique and matches the connector fetch URL you will write in Phase 10.
139. If the agent needs any extra backend endpoint (rare), add it to both `views.py` and `urls.py` now and note it for the docs sweep.
140. Re-read the view once to confirm it matches the producer/consumer shape (a target-only producer like Shoter/Camcorder has no `source` branch usage in practice but should still accept `connection_type`).

---

# PHASE 7 — Database migration (seed the Agent row)

141. Find the highest existing migration with `Glob` `Tlamatini/agent/migrations/0*.py`.
142. Create `Tlamatini/agent/migrations/<NNNN>_add_<lower>.py` (next sequential number).
143. Implement `add_<lower>_agent(apps, schema_editor)` that gets the `Agent` model via `apps.get_model('agent','Agent')`.
144. Guard against duplicates: `if Agent.objects.filter(agentDescription='<Display>').exists(): return`.
145. Compute `next_id = (max idAgent or 0) + 1`.
146. Create the row: `Agent.objects.create(idAgent=next_id, agentName=f'agent-{next_id}', agentDescription='<Display>', agentContent='true')`.
147. Use the EXACT `<Display>` casing in `agentDescription` (this is THE source of truth).
148. Implement `remove_<lower>_agent` reverse that deletes the row by `agentDescription`.
149. Set `dependencies = [('agent', '<previous_migration_name>')]`.
150. Add `operations = [migrations.RunPython(add_<lower>_agent, remove_<lower>_agent)]`.
151. Do NOT edit `0002_populate_db.py` — always add a new migration.
152. If the agent is Multi-Turn-callable, you will ALSO create a SECOND migration in Phase 14 that seeds the `Tool` row for `chat_agent_<lower>` — note it now.
153. Run `python Tlamatini/manage.py makemigrations --check --dry-run` to confirm no model drift was introduced.
154. Do not run `migrate` yet (batch it in Phase 24 with the Tool-row migration), or run it now and re-run after Phase 14 — either is fine, just end Phase 24 with a clean migrate.

---

# PHASE 8 — Parametrizer registration (make the agent a usable source)

155. Open `Tlamatini/agent/agents/parametrizer/parametrizer.py`.
156. Add `'<lower>'` to the `SECTION_AGENT_TYPES` list (the generic parser handles the rest — no per-agent parser code).
157. Open `Tlamatini/agent/views.py` and add the field list to `PARAMETRIZER_SOURCE_OUTPUT_FIELDS['<lower>']` = the KV header fields + `response_body` (if present).
158. Open `Tlamatini/agent/services/agent_contracts.py` and add `'<lower>': (...)` to `_PARAMETRIZER_OUTPUT_FIELDS` with the same field tuple (this is the registry the Flow-Compiler reads).
159. Keep the three field lists IDENTICAL across `parametrizer.py` (membership), `views.py` (`PARAMETRIZER_SOURCE_OUTPUT_FIELDS`), and `agent_contracts.py` (`_PARAMETRIZER_OUTPUT_FIELDS`).
160. Add the agent to the **Supported Source Agents** table in `README.md` (Phase 20 sweep, but note the field list now).
161. If the agent is NOT a Parametrizer source (no INI_SECTION), SKIP 155–160 entirely.
162. Confirm `get_agent_contract('<lower>')` will resolve (alias-normalized) — if the agent has an alias spelling, add it to the contract's `aliases` (override in `agent_contracts.py` builtin overrides if needed).
163. Decide the agent's `AgentContract` flags if it needs non-default behavior: `singleton`, `long_running`, `never_starts_targets`, `exclude_from_validation`, `no_input`, `no_output`, `special`. A normal agent needs none (synthesized default works).
164. If you add a builtin contract override, set `input_field_by_slot` / `output_field_by_slot` to match the agent's connection shape (slot 2 → `target_agents_b` for Forker, etc.).
165. Add `secret_paths` to the contract for any `config.yaml` dotted path holding a credential (so `.flw` export redacts it).
166. Confirm `connection_fields` on the contract covers every connection key the agent uses (so stale wiring is cleared on recompile).
167. Re-read the Parametrizer "strict single-lane queue" rule — one source, one target, one-at-a-time — to confirm the agent's section granularity (N results = N sections) matches that model.
168. Confirm the agent's `display_name` resolves through `agent_paths.display_name_from_agent_type` to exactly `<Display>` (centralized capitalization quirks live there).

---

# PHASE 9 — Frontend: CSS coloring (the gradient)

169. Open `Tlamatini/agent/static/agent/css/agentic_control_panel.css`.
170. Scan the WHOLE file for existing 4-color gradients to avoid a visual collision.
171. Choose a UNIQUE 4-stop gradient (`0% / 33% / 66% / 100%`) visually distinct from every existing agent.
172. Add the rule `.canvas-item.<css>-agent { background-color: #c1; background: linear-gradient(135deg, #c1 0%, #c2 33%, #c3 66%, #c4 100%); color: white; font-size: smaller; }`.
173. Add the hover rule `.canvas-item.<css>-agent:hover { background: linear-gradient(135deg, #c1l 0%, #c2l 33%, #c3l 66%, #c4l 100%); box-shadow: 0 6px 15px rgba(r,g,b,0.5); }`.
174. The gradient must live ONLY in CSS — never type a gradient string in JS.
175. Ensure the sidebar icon inherits the gradient via `applyAgentToolIconStyle(iconDiv, '<Display>')` (Phase 10) — no per-agent JS branch.
176. Confirm the CSS class root `<css>` matches the JS classMap value you will set (`<dash>': '<css>-agent'`).
177. Pick a memorable name for the gradient theme (e.g. "Deep-Ocean Teal") and note it for the memory + commit message.
178. If the agent is state-changing, you will MIRROR this gradient in the Exec-Report caption CSS in Phase 15 — keep the primary colors handy.
179. Verify the gradient renders by eye after deployment (Phase 25) for BOTH a freshly dragged node and a `.flw`-loaded node.
180. Confirm no existing selector accidentally also matches `.canvas-item.<css>-agent` (search for the class root).

---

# PHASE 10 — Frontend JS: connector + `acp-canvas-core.js` (6 locations)

181. Open `Tlamatini/agent/static/agent/js/acp-agent-connectors.js`.
182. Add `async function update<Pascal>Connection(agentId, targetAgentId, action, type = 'target') { ... }` modeled on the sibling connector.
183. Inside it, `fetch('/agent/update_<lower>_connection/${agentId}/', { method:'POST', headers:{'Content-Type':'application/json', ...getHeaders()}, credentials:'same-origin', body: JSON.stringify({ target_agent: targetAgentId, action, type }) })`.
184. Log a `console.error` on a non-ok response and on a thrown error (sibling pattern).
185. Open `Tlamatini/agent/static/agent/js/acp-canvas-core.js`.
186. **Location 1 — classMap** (`applyAgentTypeClass()`, ~line 32): add `'<dash>': '<css>-agent',` (KEY is the hyphenated form, VALUE is the CSS class).
187. **Location 2 — `AGENTS_NEVER_START_OTHERS`** (~line 94): add `'<dash>'` ONLY if the agent does NOT start downstream (Terminal/Monitoring). Skip for Active agents.
188. **Location 3 — `populateAgentsList()`** (~line 830): confirm it uses the shared `applyAgentToolIconStyle(iconDiv, description)` — do NOT add a per-agent gradient branch.
189. **Location 4 — `removeConnection()`** (~line 600): add SPACED-form branches `if (targetAgentName.toLowerCase() === '<space>') update<Pascal>Connection(targetId, sourceId, 'remove', 'source');` and the symmetric `sourceAgentName` branch with `'remove','target'`.
190. **Location 5 — `removeConnectionsFor()`** (~line 740): add SPACED-form branches with the deletion guards (`!targetBeingDeleted` / `!sourceBeingDeleted`).
191. **Location 6 — mouseup handler** (~line 1200): add SPACED-form branches with `'add'` instead of `'remove'`.
192. Use the HYPHENATED form ONLY in the classMap (Location 1) and `AGENTS_NEVER_START_OTHERS` (Location 2).
193. Use the SPACED form (`name.toLowerCase()`) in Locations 4, 5, 6 (connection handlers).
194. Confirm the connector symbol `update<Pascal>Connection` is referenced identically in all locations (case-exact identifier).
195. If the agent has a special connection shape, mirror the sibling that shares that shape (Forker for A/B, Counter for L/G, etc.) at every location.
196. Do NOT forget any of the 6 locations — missing one silently breaks creation, removal, undo, redo, or `.flw` load.
197. Confirm `applyAgentTypeClass` is what the canvas calls to set the node's CSS class (so the gradient applies).
198. Confirm the new branches do not shadow an existing agent whose name is a substring (use exact `===`, not `includes`).
199. Re-read the 6 edits as a group to confirm name-form correctness per location.
200. Note the connector symbol for the `/* global */` declarations in Phase 11.

---

# PHASE 11 — Frontend JS: undo/redo, .flw load, globals

201. Open `Tlamatini/agent/static/agent/js/acp-canvas-undo.js`.
202. Find an existing `update<Sibling>Connection` reference and mirror it in the UNDO section (SPACED form, `'add'` action).
203. Mirror it again in the REDO section (SPACED form, `'remove'` action).
204. Open `Tlamatini/agent/static/agent/js/acp-file-io.js`.
205. In `restoreAgentConnection`'s SOURCE-side switch, add `case '<space>': await update<Pascal>Connection(sourceId, targetId, 'add', 'target'); break;`.
206. In `restoreAgentConnection`'s TARGET-side switch, add `case '<space>': await update<Pascal>Connection(targetId, sourceId, 'add', 'source'); break;`.
207. If the agent persists Parametrizer mappings or other artifacts, confirm `acp-file-io.js` re-hydrates them on `.flw` load (only relevant if the agent is a Parametrizer node — normal agents need nothing extra).
208. Add `update<Pascal>Connection` to the `/* global ... */` declaration at the top of `acp-canvas-core.js`.
209. Add it to the `/* global ... */` declaration at the top of `acp-canvas-undo.js`.
210. Add it to the `/* global ... */` declaration at the top of `acp-file-io.js`.
211. Open `Tlamatini/eslint.config.mjs` and add `update<Pascal>Connection` to the `globals` block so the linter knows it.
212. If the agent introduces any other new global JS symbol, add it to `eslint.config.mjs` too.
213. Confirm the `.flw` load path calls `updateCanvasContentSize()` after restoring positions (it does generically — just don't break it).
214. Confirm no JS edit appends a node to `#submonitor-container` instead of `#canvas-content` (coordinate-frame contract).
215. Re-read all undo/redo/file-io edits as a group for name-form (all SPACED) and action correctness.

---

# PHASE 12 — `agentic_control_panel.html`: the inputs/outputs connector contract

216. Open `Tlamatini/agent/templates/agent/agentic_control_panel.html` and read how agent nodes render (the palette is server-injected from the `Agent` rows; the label comes from `agentDescription` verbatim via `consumers.agent_establishment`).
217. Confirm the sidebar label will render exactly `<Display>` (it reads the DB row — no HTML edit needed for the label).
218. Confirm the node's hover tooltip + canvas Description dialog come from `agents_descriptions.md` (the `## Workflow Agents` table) parsed into `agent_purpose_map` — you will add that row in Phase 20.
219. Understand the **inputs/outputs** model: a node's INPUT connectors accept arrows FROM upstream agents (writing into `source_agents`), its OUTPUT connectors start arrows TO downstream agents (writing into `target_agents`).
220. Decide the agent's input/output cardinality and ensure it matches the connection-field shape from Phase 0/6: most agents = 1 input + 1 output; OR/AND = 2 inputs + 1 output; Asker/Forker = 1 input + 2 outputs; Counter = 1 input + 2 outputs (L/G); Starter = 0 input + N outputs; Ender = N inputs + output_agents.
221. Confirm the canvas DOM contract: every `.canvas-item`, the SVG `#connections-layer`, and `#selection-box` live inside `#canvas-content` (the content layer), NOT `#submonitor-container` (the viewport).
222. Confirm coordinate math for the node uses `canvasContent.getBoundingClientRect()` (already generic — do not special-case the new agent).
223. Confirm the node's connector dots/handles are produced by the generic canvas-item renderer keyed off the CSS class — a normal agent needs NO bespoke HTML.
224. If the agent needs a NON-standard connector layout (e.g. a third output), study how Forker/Counter render their A/B/L/G handles and mirror that EXACTLY (this is the only case that touches connector rendering JS/HTML).
225. Verify the node is draggable from the sidebar palette after the migration runs (the palette is populated from `Agent` rows at page load).
226. Verify the node's output connector, when dragged to a target, fires the `update<Pascal>Connection(..., 'add', ...)` path (Phase 10, Location 6).
227. Verify the node's input connector, when receiving an arrow, writes into the correct list (`source_agents`) via the view.
228. Confirm `AGENTS_NEVER_START_OTHERS` correctly suppresses the OUTPUT-starts-downstream behavior for a Terminal agent (the canvas still draws the wire as metadata).
229. Confirm the node renders inside the scrollable canvas and the canvas grows (no upper clamp) when the node is placed far right/bottom.
230. Confirm right-click on the node opens the contextual menu (generic `contextual_menus.js`) and the Description entry shows the `agent_purpose_map` text.
231. Confirm double-click / the config entry opens the configuration dialog (Phase 13).
232. Do NOT add the agent to any hardcoded HTML list — the palette is dynamic from the DB; only MCP checkboxes are hardcoded (irrelevant here).
233. If the new agent must appear in a specific palette CATEGORY/section grouping in the sidebar, check whether `agentic_control_panel.html`/its JS groups by category and add the mapping if such grouping exists; otherwise it lists generically.

---

# PHASE 13 — The configuration dialog (canvas node settings)

234. Open `Tlamatini/agent/static/agent/js/canvas_item_dialog.js` and read how a node's config dialog is built.
235. Confirm the dialog is GENERIC: it reads the node's `config.yaml` (via the save/load endpoints) and renders a field per key — most agents need NO bespoke dialog code.
236. Confirm each `config.yaml` key from Phase 1 appears as an editable field with its default pre-filled.
237. Confirm nested config (e.g. `llm.model`) renders with dotted-key fields the dialog understands.
238. Confirm boolean fields render as checkboxes / true-false controls (match the sibling).
239. Confirm the dialog's Save posts to `save_agent_config_view`, which DEEP-MERGES the posted JSON over the template `config.yaml` — so empty fields must be omitted, not written as `''` (or they destroy defaults).
240. If the agent needs a SPECIAL dialog widget (a dropdown of enum actions, a file picker, a Parametrizer mapping UI), find the sibling that has it and mirror it; otherwise rely on the generic renderer.
241. If the agent is a Parametrizer, wire `acp-parametrizer-dialog.js` (only for Parametrizer itself — not a normal new agent).
242. Confirm the dialog shows the connection fields as read-only/managed (connections are set by dragging wires, not typed in the dialog).
243. Confirm credential fields render as empty inputs (never pre-filled with a secret).
244. Confirm the dialog title shows `<Display>` (it reads the node label).
245. Verify the dialog round-trips: open → edit a value → Save → reopen shows the new value (Phase 25 live check).
246. Confirm Save does not clobber a connection field that was set by wiring (deep-merge + omit-empty protects this).
247. If you added a bespoke dialog control, add any new JS global it introduces to `eslint.config.mjs` and the `/* global */` header.

---

# PHASE 14 — Multi-Turn enablement (the wrapped chat-agent tool)

248. Decide YES (recommended) to make the agent LLM-callable in Multi-Turn — this is "enable the agent to be Multi-turn".
249. Open `Tlamatini/agent/chat_agent_registry.py`.
250. Append a `ChatWrappedAgentSpec(...)` to `WRAPPED_CHAT_AGENT_SPECS`.
251. Set `key="<lower>"`.
252. Set `template_dir="<lower>"` (MUST match `agent/agents/<lower>`).
253. Set `tool_name="chat_agent_<lower>"` (MUST start with `chat_agent_`).
254. Set `tool_description="Chat-Agent-<Display>"`.
255. Set `display_name="<Display>"` (MUST equal the DB `agentDescription`).
256. Set `purpose="..."` — a crisp sentence telling the LLM WHEN to use it.
257. Set `example_request="Run <Display> with param1='...', param2='...'"` using the EXACT `config.yaml` key names (the wrapped parser maps `key=value` → config overrides).
258. Set `aliases=("<lower>", "<space>", ...)` for natural-language matching.
259. Set `security_hints=(...)` with keywords that help capability scoring select it.
260. Set `poll_window_seconds=N` only if the default 8 is wrong (short agents can lower it).
261. Set `long_running=True` only for watch-loop agents.
262. Confirm the spec is picked up via `WRAPPED_CHAT_AGENT_BY_TOOL_NAME` — no edits needed in `mcp_agent.py`/`tools.py` for the launcher itself.
263. Create a SECOND migration `Tlamatini/agent/migrations/<NNNN+1>_add_chat_agent_<lower>_tool.py` that seeds the `Tool` row (mirror the sibling's Tool migration; the Tool toggles the dynamic tool UI).
264. In that migration, set the Tool's description to `Chat-Agent-<Display>` consistently with the spec.
265. Confirm the wrapped agent's `config.yaml` keys exactly match the `example_request` field names (mismatch = silent default fallback).
266. Add `<lower>` to `tools.py::_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR` if you want a section field (e.g. `output_path`) surfaced at the top level of the wrapped tool's JSON result (Camcorder/Recorder do this).
267. Understand the **payload whitelist gotcha**: `acpx_enabled`, `exec_report_enabled`, `ask_execs_enabled`, `conversation_user_id`, `multi_turn_enabled` must stay in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist — you are NOT adding a new payload flag, so just don't disturb it.
268. Understand **Ask Execs is automatic**: if the wrapped tool is state-changing, the Multi-Turn executor prompts Proceed/Deny before it runs — no wiring needed.
269. If the wrapped tool is READ-ONLY/polling and should NOT be prompted, add its name to `_MANAGEMENT_TOOLS` and/or `_TOOL_QUOTA_EXEMPT` in `mcp_agent.py` (and it is likely already absent from `_EXEC_REPORT_TOOLS`).
270. Confirm the wrapped tool returns JSON with `run_id`, `status`, `log_excerpt`, `runtime_dir`, `log_path`.
271. Confirm launching creates a runtime copy under `agents/pools/_chat_runs_/<lower>_<N>_<id>/`.
272. If the agent runs a desktop/visible GUI when launched from chat, recall the dogfooding rule: foreground + `dangerouslyDisableSandbox` (Phase 25), but the wrapped tool itself runs headless/background by default in Multi-Turn.
273. **DUAL ENABLE-GATE (2026-06-07 — do NOT bypass):** `get_mcp_tools()` binds your `chat_agent_<lower>` for the LLM ONLY when BOTH (a) the wrapper Tool row `Chat-Agent-<Display>` is enabled (Configure Mcps/Tools, the migration from step 263) AND (b) the Agent row `<Display>` is enabled (Configure Agents). Disabling EITHER makes the agent INVISIBLE to the LLM (reported as unknown). Both gates fail OPEN (no row → defaults enabled). This is exactly why step 255's `display_name` MUST equal the DB `agentDescription` — the agent gate is keyed on `agent_<display>_status`. VERIFY: uncheck the agent in Configure Agents (or the wrapper in Configure Mcps), ask the LLM to use it, confirm it is reported unavailable. Do NOT add the agent to the `Tool` table twice or to MCP context rows.
274. Confirm the `_infer_execution_shell(tool_name, args)` in `mcp_agent.py` returns a sensible shell for the Ask-Execs dialog; add a branch if the agent runs through an unusual interpreter.
275. Confirm capability scoring will surface the tool — the `security_hints` + `purpose` feed `capability_registry.py`; add an `_EXTRA_HINTS_BY_TOOL_NAME` entry only if scoring under-selects it.

---

# PHASE 15 — Exec Report (MANDATORY for EVERY Multi-Turn agent)

> ⚠️ **MANDATORY DIRECTIVE — NON-NEGOTIABLE (Angela, 2026-06-07):** EVERY agent that can run in Multi-Turn (anything wired with a wrapped `chat_agent_<lower>` tool in Phase 14) **MUST be captured and shown in the Exec Report** — **observational/output agents** (Talker, Shoter, Camcorder, Recorder, AudioPlayer, VideoPlayer) and **read-only LLM agents** (Crawler, Prompter, Summarizer, File/Image interpreters, Monitor-*, Recmailer, …) **INCLUDED**, and every newly-created agent. A Multi-Turn agent that produces NO Exec-report row (Exec report ON) is a defect — that was the Talker bug. The old "state-changing only / SKIP if observational" rule is **REVOKED**.

276. **Capture is AUTOMATIC** — `mcp_agent.py::_resolve_exec_report_spec` captures ANY wrapped `chat_agent_*` (except `_MANAGEMENT_TOOLS` helpers) by deriving `agent_key`/display from the registry. If you did Phase 14, your agent is ALREADY captured with **no** Exec-report code. Do NOT skip the agent just because it is observational.
277. **(MANDATORY) VERIFY** capture: run the agent in Multi-Turn with **Exec report ON** and confirm a `List of <Display> Operations` table appears; and ensure `agent.tests.ExecReportCaptureTests.test_every_multiturn_agent_is_capturable_including_observational` stays green (it fails if any wrapped agent resolves to no row).
278. **OPTIONAL refinement (nicer styling / shared keys only):** open `Tlamatini/agent/mcp_agent.py` and add `"chat_agent_<lower>": ("<css>", "<Display>"),` to `_EXEC_REPORT_TOOLS` — do this to merge a direct `@tool` with its wrapped launch under one `agent_key`, or to fix the display casing the generic fallback derives. Otherwise skip it; the registry display name + default caption are used.
279. If you add the entry and the agent also has a direct `@tool`, give both the SAME `agent_key` so rows merge into one table.
280. Confirm the `agent_key` (`<css>`) matches the canvas CSS class root so a per-agent gradient feels native.
281. (Optional CSS) Open `Tlamatini/agent/static/agent/css/agent_page.css`.
282. Add `.exec-report-caption-<css> { background: linear-gradient(135deg, #c1 0%, #c2 100%); color: #ffffff; }` mirroring the canvas gradient — purely cosmetic; without it the readable default `.exec-report-caption` background applies.
283. Add `.exec-report-<css> .exec-report-cmd { border-left: 3px solid #c1; }` accent.
284. If the caption background is DARK, add `<css>` to the dark-header `thead th { color:#f5f5f5; background:rgba(0,0,0,0.55) }` selector list.
285. Confirm capture is unconditional in `_invoke_tool` (it ignores the per-request flag) — you add nothing there.
286. Confirm `_extract_exec_report_command(tool_input, tool_name)` produces a sensible command string for the agent; add a tool-name-aware branch only if the default is unhelpful.
287. Confirm the row verdict uses the existing `call_success` logic — do NOT add a separate classifier.
288. Confirm the Exec-Report table caption will read `List of <Display> Operations`.
289. Confirm the `EXEC_REPORT_BOUNDARY` sentinel stays byte-identical in `response_parser.py` and `agent_page_chat.js` (you are not editing it — just don't).
290. Run `python Tlamatini/manage.py test agent.tests.ExecReportCaptureTests` later (Phase 24) — it is generic (incl. the all-agents audit); no per-agent exec-report test needed.

---

# PHASE 16 — Flow-Generator mapping (Create-Flow from a Multi-Turn answer)

291. If the agent is NOT Multi-Turn-callable, SKIP this phase.
292. Open `Tlamatini/agent/static/agent/js/agent_page_chat.js`.
293. Find `_mapToolArgsToAgentConfig(canonicalName, rawArgs, _toolName)`.
294. Add a branch `} else if (lower === '<space>') { ... }`.
295. Inside it, use the `set(key, value)` helper for each field (it refuses empty strings, protecting template defaults).
296. Field names MUST match `config.yaml` keys EXACTLY (mismatch = silent default fallback).
297. For dotted nested keys (e.g. `smtp.host`), use `collectDotted('smtp')` and assign the object only if non-empty.
298. NEVER set `config.target_agents` / `config.source_agents` here — `_generateAndDownloadFlow` adds cardinal-suffixed pool names.
299. Confirm the generated `.flw` node for the agent carries populated config fields (not empty defaults) after a Create-Flow.
300. Confirm the mapping handles every advertised `example_request` field from Phase 14.
301. Re-read the branch against the `config.yaml` keys to confirm 1:1 coverage.

---

# PHASE 17 — FlowCreator specification (`agentic_skill.md`)

302. Open `Tlamatini/agent/agents/flowcreator/agentic_skill.md`.
303. Add a numbered agent entry under **Available Agents** (use the next number; the entries are numbered #1..#N).
304. Include `- **Purpose**:` one line.
305. Include `- **Used for**:` a sentence of context.
306. Include `- **Aimed at**:` the design intent.
307. Include `- **Application example**:` a concrete flow scenario.
308. Include `- **Pool name pattern**: \`<lower>_<n>\``.
309. Include `- **Starts other agents**: YES/NO` per the Active/Terminal decision.
310. Include `- **Config parameters**:` listing EVERY `config.yaml` key with default + one-line description.
311. List `source_agents`/`target_agents` (or the special fields) in the config-parameters block with their semantics.
312. Add the agent to the **Quick-Reference: Agent Capabilities at a Glance** table (`| **<lower>** | what it does | Starts Others | Category |`).
313. Add the agent to the **Agent Categories** lists (Active agents OR Terminal/Monitoring agents).
314. If the agent has a special connection shape, document it in the **Connection Rules** section.
315. If the agent emits structured output, note it in the **Output Format Rules** / Parametrizer-source context.
316. If the agent is a good fit for a **Common Task Pattern**, add or extend a pattern example showing it in a flow.
317. If the agent should be PREFERRED over Pythonxer/Executer for its task, add a row to the **Agent Selection Priority Rules** table.
318. Confirm the entry's `agent_type` token used by FlowCreator's JSON output equals `<lower>` exactly.
319. Confirm the FlowCreator output-format example would emit `{"agent_type":"<lower>","config":{...}}` with the agent's keys.
320. Bump any "FlowCreator is agent #X" cross-reference if the numbering shifts.
321. Re-read the entry against the real `config.yaml` to confirm parameter parity (FlowCreator generates configs from this text).

---

# PHASE 18 — FlowHypervisor monitoring (`monitoring-prompt.pmt`)

322. Open `Tlamatini/agent/agents/flowhypervisor/monitoring-prompt.pmt`.
323. Add `<Display>` to the **SHORT-LIVED** list (Section 3) if it starts/does-work/exits quickly.
324. OR add it to the **LONG-RUNNING** list if it runs for the whole flow (Monitor-style).
325. If the agent has nuanced behavior (zero-config bootstrap, long first run, observational capture, structured-output-on-failure, external window, REPL/transport timing), add a dedicated `<CAPS> SPECIAL NOTES:` block modeled on the STM32er/Kalier/Camcorder notes.
326. In the SPECIAL NOTES, state whether it is SHORT-LIVED/LONG-RUNNING and ACTIVE/terminal.
327. State the typical duration and the threshold beyond which silence = stuck (e.g. "do NOT flag before ~5 min" for an LLM/build agent).
328. State that its `INI_SECTION_<CAPS><<<` block is NORMAL — never flag it as an error even when the body looks like a tool error (it is routable content for a downstream Forker).
329. State which conditions ARE legitimate errors to flag (e.g. "Command not resolvable on PATH", "Cannot reach <server>", "Failed to start agent").
330. Add the agent's STARTED marker (the emoji + `<Display>` phrase from Phase 1, step 50) to the **STARTUP markers** list in Section 4.
331. Add the agent's completion phrase (e.g. `🏁 <Display> agent finished.`) consistency to Section 4 if it differs from the generic "finished"/"exiting".
332. Add `<CAPS>` to the structured-output-section producer list in Section 4 if it emits INI_SECTION.
333. Add the agent to the **TYPICAL TIMING** list (Section 3 bottom) with its expected duration window.
334. If observational (Camcorder/Recorder-style), add it to the observational-capture SPECIAL NOTES and the "THINGS THAT ARE NORMAL (DO NOT FLAG)" list (Section 6).
335. If it has a fail-safe REFUSAL stage (preflight), state that a `stage: preflight` REFUSED section is the agent working as DESIGNED, not a flow error.
336. If its first run downloads a large toolchain, add the "do NOT flag a long FIRST build while Downloading/Installing progress keeps appearing" caveat.
337. Keep `<CAPS> SPECIAL NOTES` headers ALL-CAPS (the protocol convention — do not mixed-case).
338. Confirm none of the new notes would make the watchdog flag the agent's NORMAL structured output or normal long silence.
339. Re-read the additions against Section 5 (diagnostic checklist) to ensure no contradiction (e.g. a long-running agent must not trip CHECK 3's 5-minute stuck rule).

---

# PHASE 19 — Demo "Prompts example" creation (the prompts catalog)

> ⚠️ **MANDATORY DIRECTIVE — NON-NEGOTIABLE (Angela, 2026-06-07):** if the agent is **Multi-Turn-capable** (it has a wrapped `chat_agent_<lower>` tool from Phase 14), you **MUST** create **at least ONE** example prompt for it in the **Catalog of Prompts** (the `#prompts-catalog`, seeded via a `Prompt`-model migration). This is a hard completion gate, NOT optional: a Multi-Turn agent shipped **without** at least one catalog prompt is an **INCOMPLETE** agent and the task is **not done**. (Canvas-only agents with no Multi-Turn tool are exempt — but every Multi-Turn agent needs its catalog prompt.) Do NOT skip this phase for a Multi-Turn agent under any circumstance.

340. **(MANDATORY for Multi-Turn agents)** Seed **at least one** demo prompt (1 simple is the REQUIRED minimum; tiered basic/medium/hard like STM32er #63/#64/#65 is the gold standard). Skipping this for a Multi-Turn-capable agent is a defect — the agent is not considered finished until it has a catalog prompt.
341. Read the prompts-catalog CONTIGUITY contract (relaxed to fallback-only in v1.38.1): the primary load is ONE `GET /agent/list_prompts/` call returning ALL prompts grouped by `category`; the legacy probe-loop fallback is gap-tolerant, order = `promptName` suffix, `idPrompt` stays contiguous. **Since migration 0181 (2026-07-20) the DISPLAY ORDER inside a section is `sort_rank`, NOT `idPrompt`** — the view orders by (category rank, `sort_rank`, `idPrompt`). So APPEND at max(id)+1 as always AND set `sort_rank` to the slot your prompt belongs in (ranks step by 10; rank 10 is RESERVED for the section's Step-by-Step opener; 0 = unranked and sorts LAST). Sections must read least-complex → most-complex, prerequisites first. Without a `sort_rank` your new prompt is visible but pinned to the END of its section.
342. Find the current highest `idPrompt` and the next free slot (read the latest prompt-seeding migration; the catalog cap is `MAX_PROMPTS=256` in `tools_dialog.js`).
343. Create a migration `Tlamatini/agent/migrations/<NNNN+k>_add_<lower>_demo_prompts.py` that seeds rows into the prompts model.
344. Each demo prompt should drive the new agent (via `chat_agent_<lower>` if Multi-Turn) with a realistic, SAFE task.
345. Make the prompts SAFE to run repeatedly (the daily chat test may execute them) — no destructive operations.
346. Style the prompt banner to MIRROR a recent demo (e.g. ST-blue for STM32er; pick a theme matching the agent's CSS gradient) — copy the HTML banner pattern from the sibling's prompt migration.
347. Set each prompt's mode expectation correctly: Multi-Turn ON for operator prompts; the prompt-catalog mode badges (one-shot/multi-turn/ACPX) auto-set the toolbar toggles, so phrase the prompt so the classifier infers the right modes (scrub any "do NOT use acp_spawn" clause that would confuse the classifier).
348. Keep `idPrompt` and `promptName` suffix contiguous and gap-free with the existing catalog.
349. Implement the reverse migration to delete the seeded prompts.
350. Set `dependencies` on the previous migration.
351. Run a quick round-trip: `makemigrations --check` clean + a `sqlmigrate` mental check that rows insert.
352. If inserting BEFORE existing prompts (to keep grouping), shift the existing `idPrompt`+`promptName` suffixes accordingly (the catalog is order-sensitive).
353. Document the new catalog range (e.g. "catalog now 1–66") for the memory + docs.
354. Confirm the prompts appear in the `#prompts-catalog` modal after migrate (Phase 25 live check).
355. Confirm each prompt's title/description clearly names the agent so Angela can find it.

---

# PHASE 20 — Documentation sweep (every doc surface)

356. Open `agents_descriptions.md` (repo root) and add a row to the appropriate `## Workflow Agents` table — `| **<Display>** | <Description / Purpose> | <config hint> |`.
357. The `Description` cell becomes BOTH the sidebar tooltip AND the canvas Description dialog text — write it for that audience.
358. Open `README.md` and increment the agent count in ALL the places it appears (Overview, Key Features → Visual Workflow Designer, Workflow Agents header).
359. Add the agent to the README **Project Structure** tree (`│   │   │   ├── <lower>/  # <brief>`).
360. Add the agent to the README **Agent Architecture** Deterministic OR LLM-powered list.
361. Add a README **Workflow Agents table** row in the right category with the `Purpose` cell.
362. Add a README **Glossary** entry `| **<Display>** | <one-line definition> |`.
363. Prepend a README **Changelog / Recent Updates** entry `- **Added <Display> Agent** - <brief>`.
364. Add the README **Connection Endpoints API** row `| /update_<lower>_connection/<agent_name>/ | POST | Update <lower> connections |`.
365. If the agent is a Parametrizer source, add it to the README **Supported Source Agents** table (the field list from Phase 8).
366. If Multi-Turn, bump the README "Multi-Turn tools" / "wrapped agents" counts.
367. Open `CLAUDE.md` and add the agent to the `agents/` structure tree comment block (the long inline list of agent dirs).
368. Open `docs/claude/agents.md` and add the agent to the **All Workflow Agent Types** catalog under the right category with its full description.
369. Bump the "74 total" style counts in `CLAUDE.md` and `docs/claude/agents.md`.
370. If the agent is a media/observational sibling, update the relevant family descriptions (Shoter/Camcorder/Recorder/AudioPlayer/VideoPlayer prose) so the family stays consistent.
371. If the agent is state-changing, confirm `docs/claude/exec-report.md` does not need a new note (it is generic — only add if behavior is unusual).
372. Bump `package.json` "version" to the release version Angela targets (per `feedback_package_json_version_bump`) — only running-example/current-state strings, not historical changelog refs.
373. Update any `BookOfTlamatini.md` "Recent Updates" narrative entry if Angela maintains it for releases.
374. Confirm `agents_descriptions.md` is shipped by `build.py` next to the exe (it is — just don't break it) so tooltips work in frozen mode.
375. Re-grep the repo for the OLD agent count to catch any stray count you missed.
376. Confirm every doc uses the EXACT `<Display>` casing (run the naming-skill quick-check grep).

---

# PHASE 21 — Dependencies & packaging (`requirements.txt` + `build.py`)

377. If the agent needs a new third-party lib, add a PINNED version to `Tlamatini/requirements.txt` (e.g. `opencv-python==4.13.0.92`).
378. Add the lib to `build.py`'s `_agent_libs` verify list so the build fails loudly if it's missing.
379. If the lib bundles binaries (ffmpeg/SDL via ffpyplayer), add the needed `--collect-all <lib>` to `build.py`.
380. Confirm `build.py` ships the new `agent/agents/<lower>/` directory (the agent-pool tree is bundled — verify the glob/add-data covers it).
381. Confirm `build.py` installs `requirements.txt` into BOTH the build python AND the carried `PYTHON_HOME` (pool agents run under the carried python — the lib must be there).
382. If the agent ships a template project tree (firmware/engine), confirm `build.py` bundles that scaffold directory.
382b. **Self-modify snapshot (`copy_source_assets.py`, repo root)** — the agent's source files flow into the `TlamatiniSourceCode/` snapshot automatically (denylist: all text/source types are included by default; `build.py --self-modify` generates the snapshot fresh). Only act if the agent introduces (a) a NEW heavy binary asset type → add its extension to `EXCLUDED_EXTENSIONS` and, if a rebuild needs it, an entry in `RESTORE_FROM_INSTALL`; or (b) a NEW secret field name in its `config.yaml` whose key suffix isn't already matched by `_SECRET_KEY_RE` → extend the redaction pattern. See `docs/claude/recent-fixes.md` (2026-06-12).
383. Add a static contract test to `test_build_scripts.py` if the agent introduces a new bundled asset (mirror the existing "agents ship / assets referenced+exist" tests).
384. Confirm the new agent's imports are pinned in the build's import-verify list if `test_build_scripts.py` checks per-agent imports.
385. Note in the final summary that the frozen `C:\Tlamatini` install needs `python build.py` + reinstall for the agent to appear there.
386. Do NOT run `build.py` casually — it is ~18 min and there is a `.build.lock` PID guard; never run a background build while Angela may also build (they collide). Only build when Angela asks.
387. Confirm `.gitignore` already covers any generated artifacts the agent might create at runtime (Temp/Templates are ignored).
388. If the agent adds a new sound/icon asset, place it under `static/agent/` and reference it from the build's data files.

---

# PHASE 22 — Python unit tests (`test_<lower>_agent.py`)

389. Create `Tlamatini/agent/test_<lower>_agent.py`.
390. Write a module docstring describing what the agent does and what the test covers (mirror `test_camcorder_agent.py`).
391. Load the pool script via `importlib.util.spec_from_file_location` (it lives outside the `agent` package).
392. Save+restore cwd AND logging handlers around the import (the module's top-level `os.chdir`/`open(LOG_FILE_PATH)`/`logging.basicConfig` side effects must not leak).
393. If the agent uses hardware/external libs, inject a FAKE pure-Python stand-in into `sys.modules` (like the fake `cv2`/`sounddevice`) so REAL code paths run deterministically with no device.
394. Test each helper: config load, output-dir resolution (default vs honored), unique-path/collision-proof naming, any `_coerce_int`/`_coerce_float` robustness (feed it `"5 from the mic"` and assert it yields 5).
395. Test the core capability against the fake backend (file written / request shaped / command built correctly).
396. Test `emit_parametrizer_section`: the atomic `INI_SECTION_<CAPS>` block round-trips through Parametrizer's parser.
397. Test `main()` end-stage: the section is emitted AND `target_agents` is triggered (even on the failure path, if that's the contract).
398. Test the failure path: a missing device/host/lib is REPORTED, not crashed.
399. Test reanimation: with `AGENT_REANIMATED=1` the log is NOT truncated and the REANIMATED line is logged.
400. Write **registry-integration** tests (Django `SimpleTestCase`): assert the `ChatWrappedAgentSpec` exists with the right `tool_name`/`display_name`.
401. Assert the agent contract + `_PARAMETRIZER_OUTPUT_FIELDS['<lower>']` fields match the section header.
402. Assert Exec-Report MEMBERSHIP (state-changing) or ABSENCE (observational) of `chat_agent_<lower>` in `_EXEC_REPORT_TOOLS`.
403. Assert the `config.yaml` defaults parse and contain every documented key.
404. Assert the CSS gradient class `.canvas-item.<css>-agent` exists and is UNIQUE (no duplicate gradient).
405. Assert the URL route `update_<lower>_connection` resolves.
406. Assert the view `update_<lower>_connection_view` exists and handles add/remove.
407. Assert `parametrizer.py::SECTION_AGENT_TYPES` contains `'<lower>'` (if a source).
408. Assert the migrations exist and `makemigrations --check` is clean.
409. Assert `requirements.txt` pins the new lib (if any).
410. Assert the JS wiring exists by reading the JS files and grepping for `update<Pascal>Connection` in connectors + canvas-core (classMap) + undo + file-io (a static contract test like the build tests).
411. Make the tests HARD per `feedback_hard_real_scenario_tests`: errors + clean + overflow cases, drive REAL code (don't mock the thing under test), reproduce any real incident byte-faithfully.
412. Do NOT mock the module's `time` in real-client tests (it breaks timing-sensitive paths — known gotcha).
413. Use a raw-string for any fake-server source written to a temp `.py` subprocess (escaping gotcha).
414. Run `python Tlamatini/manage.py test agent.test_<lower>_agent` and get it fully green.
415. Run the related suites too (the registry tests touch shared maps — confirm no cross-agent regression): the sibling's test + `ExecReportCaptureTests`.
416. Run `python -m ruff check Tlamatini/agent/test_<lower>_agent.py` and fix all.
417. Confirm the test count + green status for the final summary.

---

# PHASE 23 — Playwright tests in Claude's harness (the daily-chat-test)

418. Open `.claude/skills/tlamatini-daily-chat-test/harness/` and read `config.py`, `run_test.py`, `questions.py`, `wrapped_questions.py`, `qualify.py`.
419. Understand the harness contract: it drives REAL Chrome via Playwright, logs into `agent_page.html`, asks curated questions one-by-one, waits for completion, scrapes + qualifies the answer.
420. Understand the answer-complete signal: input stops being `readOnly` AND `#wait-spinner` is removed from `#chat-log`.
421. Add KNOWLEDGE questions about the new agent to `harness/questions.py` (safe, introspective: "What does the <Display> agent do?", "Which agents capture <X>?") — these run with Multi-Turn ON, ACPX/Ask-Execs/Exec-Report OFF.
422. Add a WRAPPED-TOOL execution question to `harness/wrapped_questions.py` so `--bank wrapped --select <lower>` exercises the live `chat_agent_<lower>` tool.
423. Set the wrapped question's `id`, `category` (`wrapped:<lower>`), wrapped `key` (`<lower>`), and `display name` (`<Display>`) so `--select` matching works (id/category/key/name, case-insensitive, substring, aliases).
424. Add any alias mapping (e.g. `pinger`→`<lower>`) to the harness alias table if Angela uses a colloquial name.
425. Make the wrapped question SAFE to execute repeatedly (the bank may run 1000×/day) — benign, idempotent task.
426. Add expected keywords to the question so the heuristic qualifier can PASS a correct answer.
427. If the agent is observational/desktop, keep the wrapped question's action harmless (a single capture to the default folder, not a long video).
428. Confirm the test's pinned toggles match the harness default: Multi-Turn ON, ACPX OFF, Ask-Execs OFF, Exec-Report OFF, Internet OFF (per `feedback_test_toggle_state` — set AND verify, clear history first).
429. Run a focused FOREGROUND check first: `python run_test.py --bank wrapped --select <lower>` against a LIVE server (the single-select run is short).
430. Use `--bank wrapped --list` to confirm the new `--select` token is discoverable.
431. Verify the server is up at `http://127.0.0.1:8000` first (`curl` the root); if down, ask Angela to start it — never start a second instance (single-bound ports).
432. Get credentials from Angela (installer default `user`/`changeme` is usually wrong on the dev box) via env `TLAMATINI_USER`/`TLAMATINI_PASS` or `harness/.creds.env`.
433. On first-time harness setup, `pip install -r requirements.txt` + `python -m playwright install chrome` in the harness dir.
434. Confirm the question PASSES (answered, no error banner, expected keywords present); if WEAK/FAIL, read the report's heuristic reason + judge verdict and fix the agent or the question.
435. Add the new wrapped key to the harness README's list of selectable agents if it maintains one.
436. Do a small `--count 10` smoke of the knowledge bank to confirm the new knowledge questions don't regress.
437. Run the harness's own `ruff check` (the harness has a `.ruff_cache`) and keep it clean.
438. Confirm `results.jsonl` + `summary.json` + `report.md` are written under `harness/reports/run_<timestamp>/` for the run.
439. Report the focused-run outcome (asked/pass/weak/fail, pass-rate, avg time) to Angela.
440. Do NOT add destructive prompts to either bank (the daily run executes them with Multi-Turn ON).
441. If the chat UI selectors changed because of your work, fix `harness/config.py` (selectors + ready/started JS) and re-verify with `--count 2` before trusting a full run.

---

# PHASE 24 — Lint, migrate, full verification

442. Run `python -m ruff check` over the repo and fix ALL issues (E402 from a top-level def above imports is the classic one).
443. Run `npm run lint` and fix ERRORS (warnings can stay) — the missing `/* global */` or `eslint.config.mjs` global is the classic JS lint failure.
444. Run `python Tlamatini/manage.py makemigrations --check --dry-run` — must be clean (all rows seeded via your RunPython migrations, no model drift).
445. Run `python Tlamatini/manage.py migrate` and confirm the Agent row + Tool row + demo-prompt rows apply.
446. Run the new test module green: `python Tlamatini/manage.py test agent.test_<lower>_agent`.
447. Run `python Tlamatini/manage.py test agent.tests.ExecReportCaptureTests` (state-changing) — generic, must stay green.
448. Run the sibling's test + any shared-registry test to confirm no cross-agent regression.
449. Run `python Tlamatini/manage.py test agent.test_build_scripts` if you touched build/packaging.
450. Verify `get_agent_contract('<lower>')` returns a contract with the right `display_name` and `parametrizer_fields` (quick shell check).
451. Verify the wrapped tool is exposed: confirm `WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_<lower>']` resolves and `get_mcp_tools()` includes a tool named `chat_agent_<lower>`.
452. Grep the repo for the old agent count to confirm every count was bumped.
453. Run the naming-skill quick-check grep to confirm no mis-cased `<Display>` slipped in.
454. Confirm `python -c "import yaml; yaml.safe_load(open('...config.yaml'))"` still parses.
455. Confirm `eslint` recognizes the new global (no `no-undef` for `update<Pascal>Connection`).
456. Confirm the migration numbering has no gaps/duplicates with `Glob`.
457. Confirm the prompts catalog is contiguous (no gap that would break the dropdown).
458. Re-read your scratch/pivot note and tick every file you intended to touch.

---

# PHASE 25 — Live deploy, VISIBLE dogfood, and handoff

459. If Angela's server is the SOURCE instance, restart it (or confirm a `--noreload` instance) so the migration + new code load.
460. Open `agent_page.html` and confirm the new agent appears in the sidebar palette with the correct `<Display>` label and gradient icon.
461. Drag the agent onto the canvas and confirm the node renders with the gradient + correct input/output connectors.
462. Wire it to a Starter and an Ender; confirm the connection-update view writes `target_agents`/`source_agents` correctly (check the pool `config.yaml`).
463. Right-click the node → confirm the Description dialog shows the `agents_descriptions.md` text.
464. Open the node's configuration dialog → confirm every config key is editable with defaults → Save → reopen and confirm persistence.
465. Save the flow as a `.flw`, reload it, and confirm the node + connections + config restore (exercises `acp-file-io.js`).
466. Press Start on a tiny flow and confirm the agent runs (LED green), writes its `<lower>.log`, emits its `INI_SECTION_<CAPS>` (if a source), and triggers downstream.
467. If the agent is VISIBLE/desktop (a window the user must SEE), and Angela asked to use Tlamatini's agents, launch it FOREGROUND with `dangerouslyDisableSandbox: true` so the window renders on her real desktop (the Bash sandbox hides GUIs; `run_in_background` detaches them) — per `feedback_run_tlamatini_agents_visible`.
468. To dogfood via Tlamatini's pool (not Claude's own tools): copy the agent to an isolated runtime dir, write a tailored `config.yaml`, run `python <lower>.py`, then read `<lower>.log` for the result.
469. In chat with Multi-Turn ON, ask the LLM to run the agent (`Run <Display> with ...`) and confirm `chat_agent_<lower>` fires and returns the JSON result.
470. If state-changing, toggle Exec Report ON and confirm the `List of <Display> Operations` table renders with the correct gradient.
471. If state-changing, toggle Ask Execs ON and confirm the Proceed/Deny prompt appears before the tool runs.
472. Run the new demo prompt(s) from the catalog and confirm they execute end-to-end.
473. Confirm the FlowHypervisor (start it on a flow with the agent) does NOT falsely flag the agent's normal output/timing.
474. Confirm the command watchdog does not kill the agent's legitimate long-but-working run (if applicable).
475. Confirm the orphan reaper leaves no `conhost.exe` survivors after the agent finishes (check Task Manager / the Tier-2/3 logs).
476. Write/update a memory file `project_<lower>_agent.md` summarizing what was added, files touched, test counts, and the "frozen needs build.py / not committed" status — and add a one-line pointer to `MEMORY.md`.
477. Per `feedback_track_changes_pivot_file`, record the verbatim request + before/after of any `prompt.pmt`/registry/`config.yaml` default changes in a dated pivot note.
478. Do NOT commit or push unless Angela explicitly asks (per the standard workflow + secret-leak caution — run `regen_secrets.py` before any commit).
479. If a commit IS requested, branch first if on `main`, scrub secrets, and end the commit message with the required Co-Authored-By line.
480. Tell Angela explicitly: the SOURCE instance reflects the change now; the FROZEN `C:\Tlamatini` install needs `python build.py` + reinstall.
481. Give Angela the final per-surface checklist (the summary below) so she can verify nothing was skipped.

---

# Master per-surface checklist (every box must be ticked)

482. ☐ `agent/agents/<lower>/<lower>.py` (boilerplate, `_IS_REANIMATED` before `basicConfig`, PID, concurrency guard, target trigger, INI_SECTION, temp guard, no `agent.*` import).
483. ☐ `agent/agents/<lower>/config.yaml` (all params + connection fields, empty-string secrets, real numeric types).
484. ☐ `views.py::update_<lower>_connection_view` + `urls.py` route.
485. ☐ Migration `<NNNN>_add_<lower>.py` (Agent row, exact `<Display>` casing).
486. ☐ Migration `<NNNN+1>_add_chat_agent_<lower>_tool.py` (Tool row) — if Multi-Turn.
487. ☐ `parametrizer.py::SECTION_AGENT_TYPES` + `views.py::PARAMETRIZER_SOURCE_OUTPUT_FIELDS` + `agent_contracts.py::_PARAMETRIZER_OUTPUT_FIELDS` (identical field lists) — if a source.
488. ☐ `agentic_control_panel.css` unique gradient (normal + hover).
489. ☐ `acp-agent-connectors.js` connector `update<Pascal>Connection`.
490. ☐ `acp-canvas-core.js` × 6 (classMap HYPHEN, NEVER_START HYPHEN, populateAgentsList shared helper, removeConnection/removeConnectionsFor/mouseup SPACED).
491. ☐ `acp-canvas-undo.js` undo + redo (SPACED).
492. ☐ `acp-file-io.js` both switches (SPACED).
493. ☐ `/* global */` in 3 JS files + `eslint.config.mjs` global.
494. ☐ `agentic_control_panel.html` inputs/outputs connector cardinality correct (only special-shape agents touch rendering).
495. ☐ Config dialog (`canvas_item_dialog.js`) renders all keys (generic — bespoke only for special widgets).
496. ☐ `chat_agent_registry.py::ChatWrappedAgentSpec` (key/template_dir/tool_name/display_name/purpose/example_request/aliases/security_hints) — if Multi-Turn.
497. ☐ `tools.py::_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR` — if surfacing a section field.
498. ☐ `mcp_agent.py::_EXEC_REPORT_TOOLS` + `agent_page.css` caption/accent — if state-changing.
499. ☐ `agent_page_chat.js::_mapToolArgsToAgentConfig` branch — if Multi-Turn.
500. ☐ `flowcreator/agentic_skill.md` entry + capability table + categories + selection-priority.
501. ☐ `flowhypervisor/monitoring-prompt.pmt` SHORT/LONG list + SPECIAL NOTES + markers + TYPICAL TIMING + DO-NOT-FLAG.
502. ☐ Demo-prompt migration (contiguous catalog, safe prompts, mode badges) + banner styling.
503. ☐ Docs: `agents_descriptions.md`, `README.md` (counts/tree/tables/glossary/changelog/API), `CLAUDE.md`, `docs/claude/agents.md`, `package.json` version.
504. ☐ `requirements.txt` pin + `build.py` `_agent_libs`/`--collect-all`/bundle — if new dep.
505. ☐ `test_<lower>_agent.py` (helpers, fake backend, INI round-trip, main end-stage, reanimation, registry integration, JS contract) — green + ruff clean.
506. ☐ Playwright harness: `questions.py` knowledge Qs + `wrapped_questions.py` execution Q + `--select` token — focused run PASS.
507. ☐ `ruff check` clean + `npm run lint` errors clean + `makemigrations --check` clean + `migrate` applied.
508. ☐ Live verify: palette → drag → wire → dialog → .flw round-trip → run → INI_SECTION → target trigger → Exec Report → Ask Execs → demo prompt → FlowHypervisor sane → reaper clean.
509. ☐ Memory `project_<lower>_agent.md` + `MEMORY.md` pointer + pivot note; "frozen needs build.py / not committed" stated.

---

# Pitfalls index (the silent-failure traps — re-read before declaring done)

510. **Naming drift** — `agentDescription` is the only source of truth; CSS classMap (HYPHEN), connection handlers (SPACED), connector symbol (PascalCase), INI token (CAPS) each transform it differently. Fix it in the migration FIRST.
511. **Empty-string overwrites** — writing `config.field=''` (view, flow-generator, dialog) destroys the template default via the deep-merge. Always omit-if-empty / use the `set()` helper.
512. **Pool-name cardinal mismatch** — emit `<lower>_N` (underscore + cardinal), never bare `<lower>` or `<lower>-N`, into connection lists, or the Starter fails on the first hop.
513. **Forgetting `_IS_REANIMATED`** — without the marker before `basicConfig`, the log truncates on every resume.
514. **Missing concurrency guard** — `wait_for_agents_to_stop` must precede `start_agent` in looping flows.
515. **`_EXEC_REPORT_TOOLS` miss** — a state-changing agent without the map entry shows no table (silent data loss); an observational agent wrongly added shows a spurious table.
516. **Flow-Generator miss** — Multi-Turn-callable agent without a `_mapToolArgsToAgentConfig` branch produces a `.flw` node with empty config.
517. **6 JS edit locations** — `acp-canvas-core.js` touches connections in 6 places; missing one breaks creation/removal/undo/redo/.flw-load.
518. **CSS gradient duplicated in JS** — never type a gradient in JS; use `applyAgentToolIconStyle`.
519. **Importing `agent.*` from a pool subprocess** — `ModuleNotFoundError` at runtime; port inline.
520. **Temp/Templates outside Tlamatini** — scratch → `<app>/Temp`, scaffold → `<app>/Templates`; never `C:\Temp`/`%TEMP%`/bare `tempfile`.
521. **Payload whitelist** — don't disturb `UnifiedAgentChain.invoke`'s rebuild whitelist (`acpx_enabled`/`exec_report_enabled`/`ask_execs_enabled`/`conversation_user_id`/`multi_turn_enabled`).
522. **Parametrizer field-list drift** — the three lists (parametrizer.py, views.py, agent_contracts.py) must be identical.
523. **Catalog contiguity** — a gap in `idPrompt` breaks the prompts dropdown at the first missing slot.
524. **FlowHypervisor false positives** — a long-running/observational/structured-output agent without its SPECIAL NOTES gets wrongly flagged as stuck or errored.
525. **Watchdog** — keep child processes making progress and fed EOF on stdin; never block with zero CPU+IO.
526. **Frozen vs source** — source instance reflects edits immediately; frozen `C:\Tlamatini` needs `python build.py` + reinstall. State this every time.
527. **Build collisions** — never run a background `build.py` while Angela may build (`.build.lock`, ~18 min, they clobber shared dirs).
528. **Test softness** — make tests HARD (real code, real incident, error+clean+overflow); soft happy-path tests miss real bugs.
529. **Test toggles** — automated chat tests set AND verify Multi-Turn ON / Exec-Report per intent / Ask-Execs OFF, and clear history first.
530. **Secret leak** — run `regen_secrets.py` before any commit; config carries live keys in dev.

---

# Quick mental model (the one-paragraph version)

531. A new Tlamatini agent is a **self-contained Python pool subprocess** (`agent/agents/<lower>/<lower>.py` + `config.yaml`) that the canvas can drag, wire, configure, start, and monitor; that the Multi-Turn LLM can launch as `chat_agent_<lower>`; that Parametrizer can read as a source; that FlowCreator can design into a `.flw`; that FlowHypervisor watches; that the watchdog/reaper keep clean; and that is surfaced in CSS (gradient), the connection views, a migration (Agent + Tool rows), demo prompts, docs, packaging, a hard Python test module, and a Playwright harness question. Decide the name and shape ONCE (Phase 0), then propagate the SAME identity across all ~30 surfaces without drift. When in doubt, copy the most recent fully-wired sibling (Camcorder / Recorder) verbatim and change only the identity tokens.
