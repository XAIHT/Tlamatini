# ACPX & Skills in Tlamatini — A complete guide for dummies

**Document version:** 1.0
**Date:** 2026-04-29
**Status:** Implementation landed locally, NOT committed. The user reviews and decides whether to commit.
**Companion docs:** `CLAUDE.md`, `docs/claude/architecture.md`, `docs/claude/agents.md`, `docs/claude/multi-turn.md`, `TlamatiniVsOpenClaw.md`.

> **Current-state banner (Tlamatini 1.20.0, 2026-06-14).** This file is the original ACPX/Skills design walkthrough; its per-section numbers are an intentional **historical Phase-1 snapshot** (5 ACPX `@tool`s, 20 seed skills, 14 agent_ids, 57 visual agents). The system has since grown — the authoritative current counts are: **76 visual agent types**, **83 Multi-Turn tools** (20 base + 51 wrapped `chat_agent_*` + 12 ACPX/Skill), **27 skills**, and a **12-tool LLM-facing ACPX/Skill surface** (`acp_doctor`, `list_acp_agents`, `acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_kill`, `acp_transcript`, `acp_session_status`, `acp_list_sessions`, `acp_relay`, `list_skills`, `invoke_skill`). The `DEFAULT_ACP_AGENTS` agent_id registry remains **14** entries (§3.5). For the live surface read `CLAUDE.md` and `docs/claude/acpx.md`, not the historical numbers below.

---

## 0. Read this first

This document explains a feature that has just been added to Tlamatini and that you, the user, have **not yet committed**. The feature has two parts that work together:

1. **ACPX** — a runtime that lets Tlamatini spawn external coding-agent CLIs (Claude Code, Cursor, Codex, Gemini, Qwen, Pi, Kiro, Kimi, iFlow, Factory Droid, Kilocode, OpenCode) as child processes, send them turns, and tear them down — exposed to the unified-agent loop as four LangChain tools (`acp_spawn`, `acp_send`, `acp_kill`, `acp_doctor`, `list_acp_agents`).
2. **Skills** — a markdown-driven extension surface. You add a directory with a `SKILL.md` file under `agent/skills_pkg/<your-skill>/` and the LLM gains a new capability with declared inputs, outputs, permissions, and budget — invocable through the `invoke_skill` tool. 20 seed skills ship in this revision.

Both layers are designed to be **OpenClaw-compatible** so that:
- A skill written for Tlamatini can be dropped into OpenClaw with no changes.
- A skill written for OpenClaw is parseable by Tlamatini's registry.
- The `permissionMode` / `nonInteractivePermissions` vocabulary is identical in both projects.
- The agent_id mapping (`claude` → claude CLI, `qwen` → qwen-code CLI, etc.) is identical in both projects.

If you have ten minutes, read sections 1, 2, and 7. They give you the mental model and the day-one usage. Sections 3-6 are the engineering deep dive. Sections 8-12 are reference and runbook.

---

## 1. Why this exists (one paragraph)

Tlamatini already has 57 typed visual agents and a Multi-Turn unified-agent loop. Two gaps were called out in `TlamatiniVsOpenClaw.md`: there is no story for **delegating a sub-task to an external coding agent** (Claude Code, Cursor, Qwen, …) the way OpenClaw's ACPX does, and there is no story for **adding capabilities through a markdown file rather than a Python agent**. ACPX closes the first gap. The Skill catalog closes the second.

The intent is composability: when the LLM decides "this is a refactor that Cursor should handle", it can `acp_spawn(agent_id='cursor', task=...)` and pull the result back into the same chat. When the LLM decides "this looks like a Notion page-create", it can `invoke_skill('notion', ...)` and run a 600-byte playbook in a controlled harness with declared permissions.

---

## 2. Mental model — pictures over words

```
┌──────────────────────────────────────────────────────────────────────┐
│ Browser chat / ACP visual canvas                                      │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ WebSocket (Daphne / Channels)
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Tlamatini Django app                                                  │
│                                                                       │
│  agent/consumers.py ──► agent/rag/chains/unified.py ─►                │
│                              MultiTurnToolAgentExecutor               │
│                                       │                               │
│      (Layer 5: LangChain @tool calls)│                               │
│                                       ▼                               │
│  ┌──────────┐   ┌─────────────┐   ┌─────────────────────────┐        │
│  │tools.py  │   │chat_agent_*│   │ ACPX + Skills tools     │ NEW    │
│  │(legacy)  │   │(wrapped 32)│   │  acp_spawn  acp_send    │        │
│  │          │   │            │   │  acp_kill   acp_doctor  │        │
│  │          │   │            │   │  list_acp_agents        │        │
│  │          │   │            │   │  invoke_skill           │        │
│  │          │   │            │   │  list_skills            │        │
│  └──────────┘   └─────────────┘   └──────┬──────────┬──────┘        │
│                                          │          │                │
│                              ┌───────────┘          └────────────┐   │
│                              ▼                                   ▼   │
│                    ┌──────────────────┐               ┌────────────┐ │
│                    │ AcpxRuntime      │               │ Skill      │ │
│                    │  - probe         │               │ Registry   │ │
│                    │  - spawn child   │               │  + Harness │ │
│                    │  - send turn     │               │            │ │
│                    │  - kill          │               │            │ │
│                    │  - permission    │               │            │ │
│                    │    gate          │               │            │ │
│                    └─────────┬────────┘               └─────┬──────┘ │
└──────────────────────────────┼──────────────────────────────┼────────┘
                               │                              │
                               │ subprocess.Popen             │ in-process
                               │ (stdin/stdout JSON)          │ scoped loop
                               ▼                              │ OR delegate
                    ┌──────────────────┐                      │ to ACPX
                    │ External CLI     │                      ▼
                    │   claude / qwen  │           ┌─────────────────────┐
                    │   cursor / codex │           │ Tlamatini @tools    │
                    │   gemini / pi /… │           │ (scoped to skill's  │
                    └──────────────────┘           │  requires_tools)    │
                                                   └─────────────────────┘
```

Two key observations:

- **ACPX child processes are external programs.** The `claude` binary, the `cursor` binary, etc. — Tlamatini does not implement them. It just spawns them and brokers their I/O. If the binary isn't installed, the agent_id is unhealthy.
- **Skills are in-process by default.** A skill like `notion` or `summarize` runs *through* the existing unified-agent loop using the existing `chat_agent_*` tools. A skill can opt into ACPX by setting `runtime: acpx` and naming an `acpx_agent`.

---

## 3. The ACPX runtime — what it actually does

### 3.1 Files

```
Tlamatini/agent/acpx/
├── __init__.py              # public exports
├── config.py                # AcpxConfig + load_acpx_config(...)
├── agent_registry.py        # DEFAULT_ACP_AGENTS + build_agent_registry(...)
├── session_store.py         # FileSessionStore + AcpSessionRecord (reset-aware)
├── windows_spawn.py         # PATH search + .cmd/.bat handling for Windows
├── permissions.py           # PermissionGate (approve-reads / deny-all / approve-all)
├── runtime.py               # AcpxRuntime, AcpSession, AcpRuntimeError, get_acpx_runtime()
├── tools.py                 # @tool acp_spawn / acp_send / acp_kill / acp_doctor /
│                            # list_acp_agents / invoke_skill / list_skills
├── service.py               # boot_acpx() + boot_skills() — called from apps.py
└── tests.py                 # 23 unit tests, all green
```

### 3.2 Lifecycle of one ACP session

1. **Boot.** `agent/apps.py::AgentConfig.ready()` schedules `boot_acpx()` on a daemon thread. That call creates the singleton `AcpxRuntime`, runs `probe_availability()` once, and mirrors the registered agent_ids into the `AcpAgent` table.
2. **Spawn.** The LLM (or you, through the chat) calls `acp_spawn(agent_id='claude', task='...')`. The runtime:
   - Looks up the `AcpAgentSpec` (default registry + your `config.json` overrides).
   - Resolves the command on PATH using `windows_spawn.py` (handles `.cmd` / `.bat` / `.exe` suffix search).
   - Creates a `FileSessionStore` record with a fresh UUID (and marks it `mark_fresh()` so any stale on-disk JSON is ignored — the OpenClaw `ResetAwareSessionStore` semantics).
   - Spawns the child via `subprocess.Popen` with stdin/stdout/stderr piped, in `text=True` mode.
   - Sends an initial JSON envelope `{"task": "...", "mode": "session"}` on stdin.
   - Reads the child's stdout line-by-line as JSON; non-JSON lines are wrapped as `{"event":"log","text":"..."}`.
   - Appends every event to a per-session transcript file `<state_dir>/<session>.transcript.ndjson`.
   - Returns the last 32 events to the LLM (a tail summary; full transcript stays on disk).
3. **Follow-up.** `acp_send(session_id, "next turn text")` writes another envelope to the live child and reads more events. Each turn is bounded by `timeout_seconds` (default 120).
4. **Kill.** `acp_kill(session_id)` calls `proc.terminate()` (3-second grace), then `proc.kill()`, then marks the record `closed=True`.

### 3.3 Permissions — the security backbone

Three modes (mirrors OpenClaw's `ACPX_PERMISSION_MODES`):

| Mode             | What it does                                                     | When to use |
|---               |---                                                                |---          |
| `approve-reads`  | Reads auto-approved; writes / shell / network need a prompt.      | **Default.** Safe for unattended runs because the non-interactive policy then kicks in. |
| `approve-all`    | Everything auto-approved.                                          | Flagged **dangerous** in `permissions.is_dangerous_config()`. Only opt in for trusted local automation. |
| `deny-all`       | Hard wall on every action including spawn.                         | Audit / lockdown mode. Useful when you want to inspect the runtime without letting it do anything. |

Plus a non-interactive policy:

| Policy | Behavior in unattended runs |
|---    |---                            |
| `deny` | Action denied; LLM gets a `PERMISSION_DENIED` envelope and can decide what to do. **Default.** |
| `fail` | Whole skill / spawn fails hard with an error. |

The gate is at `agent/acpx/permissions.py::PermissionGate.decide(action, interactive=...)` and returns a `PermissionDecision(allowed, reason, needs_prompt)`. There is exactly one place in the codebase where these decisions are made; no skill or runtime caller bypasses it.

### 3.4 Configuration

ACPX reads its config from a top-level `acpx` block in `Tlamatini/agent/config.json`. This block is **OpenClaw-compatible verbatim** — you can copy a working `acpx` block from an OpenClaw deployment and it parses unchanged.

Example:

```json
{
  "acpx": {
    "cwd": "C:/Development",
    "stateDir": "C:/Users/angel/.tlamatini/acpx-state",
    "probeAgent": "claude",
    "permissionMode": "approve-reads",
    "nonInteractivePermissions": "deny",
    "timeoutSeconds": 180,
    "pluginToolsMcpBridge": false,
    "openClawToolsMcpBridge": false,
    "mcpServers": {
      "files": {
        "command": "python",
        "args": ["-m", "agent.mcp_files_search_server"]
      }
    },
    "agents": {
      "claude": { "command": "C:/Users/angel/AppData/Roaming/npm/claude.cmd" },
      "cursor": { "command": "C:/Program Files/Cursor/cursor-agent.exe" }
    }
  }
}
```

If you do not add an `acpx` block, the defaults kick in:

- `cwd` = current working directory of the Django process.
- `stateDir` = `~/.tlamatini/acpx-state/`.
- `permissionMode` = `approve-reads`.
- `nonInteractivePermissions` = `deny`.
- `timeoutSeconds` = 120.
- `pluginToolsMcpBridge` = `false` (Tlamatini @tools NOT exposed to ACP children).
- `agents` = built-in registry only.

### 3.5 The built-in agent registry

`DEFAULT_ACP_AGENTS` in `agent/acpx/agent_registry.py` ships with 14 entries; the agent_id keys match the OpenClaw acp-router skill exactly:

| agent_id    | command       | description                              |
|---          |---            |---                                       |
| `claude`    | claude        | Anthropic Claude Code CLI                 |
| `cursor`    | cursor-agent  | Cursor agent CLI                          |
| `codex`     | codex         | OpenAI Codex (ACP path)                   |
| `copilot`   | copilot       | GitHub Copilot CLI                        |
| `gemini`    | gemini        | Google Gemini CLI                         |
| `qwen`      | qwen-code     | Alibaba Qwen Code CLI                     |
| `pi`        | pi            | Pi assistant CLI                          |
| `droid`     | droid         | Factory Droid CLI                         |
| `iflow`     | iflow         | iFlow CLI                                 |
| `kilocode`  | kilocode      | Kilocode CLI                              |
| `kimi`      | kimi          | Kimi CLI                                  |
| `kiro`      | kiro          | Kiro CLI                                  |
| `opencode`  | opencode      | OpenCode CLI                              |
| `tlamatini` | sys.executable -m agent.acpx.self_acp_server | Tlamatini-as-ACP-server (self-host); reserved slot |

You can override any command and add new agent_ids through `acpx.agents` in `config.json`.

---

## 4. The Skill system — what it actually does

### 4.1 Files

```
Tlamatini/agent/skills/                 # the runtime (parser, registry, harness)
├── __init__.py
├── frontmatter.py                      # parse_skill_md(), find_skill_files()
├── registry.py                         # SkillRegistry singleton (skill_registry)
├── io_contract.py                      # validate_inputs / validate_outputs
└── harness.py                          # SkillHarness, Budget, SkillAuditLog

Tlamatini/agent/skills_pkg/             # the *content* (SKILL.md packages)
├── _meta/
│   ├── schema.json                     # JSON-Schema for SKILL.md frontmatter
│   └── lint.py                         # standalone validator
├── hello_world/SKILL.md                # smoke-test skill
├── skill_creator/                      # bootstrap a new skill
│   ├── SKILL.md
│   └── scripts/quick_validate.py
├── acp_router/SKILL.md                 # picks an agent_id for ACPX
├── tlamatini_new_acp_agent/SKILL.md    # scaffold a new visual agent
├── tlamatini_flow_from_objective/SKILL.md
├── tlamatini_flw_doctor/SKILL.md
├── tlamatini_exec_report_row_adder/SKILL.md
├── tlamatini_planner_trace_replay/SKILL.md
├── tlamatini_allowed_hosts_tighten/SKILL.md
├── tlamatini_csrf_exempt_audit/SKILL.md
├── tlamatini_static_version_bumper/SKILL.md
├── github/SKILL.md                     # OpenClaw-format port
├── notion/SKILL.md
├── jira/SKILL.md
├── slack/SKILL.md
├── gmail/SKILL.md
├── todoist/SKILL.md
├── trello/SKILL.md
├── summarize/SKILL.md
└── weather/SKILL.md
```

The split — runtime in `agent/skills/`, content in `agent/skills_pkg/` — is intentional. The skills_pkg directory is purely data; you can drop new skills in there and they appear in `list_skills` without restarting Django (the registry has a 30-second staleness cap and reloads on demand).

### 4.2 The SKILL.md contract

Every SKILL.md is YAML frontmatter + a markdown body. Minimum required fields:

```markdown
---
name: my-skill                      # kebab-case, unique across the catalog
description: One-line description.   # used by list_skills / planner triggers
---

# Body
The body is the playbook the LLM follows when this skill is invoked.
Body must stay under 8 KiB or the linter rejects it.
```

Full optional shape (everything Tlamatini-specific lives under `metadata.tlamatini`):

```markdown
---
name: example
description: Example skill.
metadata:
  openclaw:                          # kept for OpenClaw compatibility
    emoji: "✨"
    requires:
      bins: ["gh"]
      env:  ["GITHUB_TOKEN"]
    primaryEnv: "GITHUB_TOKEN"
  tlamatini:
    runtime: in-process              # or: acpx
    acpx_agent: claude               # required iff runtime=acpx
    requires_tools: ["chat_agent_executer"]
    requires_mcps:  ["Files-Search"]
    budget:
      max_iterations: 12
      max_seconds: 180
      max_tokens: 30000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/**/*"]
        write: ["Tlamatini/${input.target_dir}/**/*"]
      shell:   ["python -m ruff check **/*.py"]
      network: deny                  # or: allow, or array of host globs
      db:      deny                  # or: allow, read, or array
    inputs:
      - { name: target_dir, type: string,  required: true }
      - { name: max_lines,  type: integer, required: false, default: 100 }
      - { name: mode,       type: enum, values: ["fast","careful"], required: false }
    outputs:
      - { name: changed_files, type: array,  required: true }
      - { name: summary,       type: string, required: true }
    triggers:
      keywords:   ["refactor","cleanup","rewrite"]
      file_globs: ["**/*.py"]
---

# Body of the skill — markdown playbook…
```

### 4.3 The harness — what happens when `invoke_skill('my-skill', {...})` runs

1. **Registry lookup.** `skill_registry.reload_if_stale()` (cheap, refreshes if 30s old). Then `skill_registry.get('my-skill')`. If missing, the tool returns `{"ok": false, "code": "UNKNOWN_SKILL"}`.
2. **Input validation.** `io_contract.validate_inputs(skill.inputs, args)` coerces & checks types (string / number / integer / boolean / enum / array / object). Missing required inputs → failure envelope with `reason="input_contract_violation"`. Defaults are applied for missing optional inputs.
3. **Audit open.** `SkillAuditLog` opens `~/.tlamatini/skill-audit/<YYYY-MM>/<epoch>_<skill>_<id8>.ndjson` and writes an `audit_open` event. Every later event in the run is appended.
4. **Dispatch.** Two runtimes:
   - **`in-process`** (default): the harness builds an *envelope* describing the skill's body, args, requires_tools, permissions, and a `body_excerpt`, plus stub values matching the declared `outputs`. This envelope is what the unified-agent reads next; the calling agent then carries forward through the existing tool palette to actually execute the steps. **This deliberate design keeps the first revision safe-by-default**: no new shell paths and no new file-write paths are introduced through `invoke_skill` alone. Promotion to a real scoped Multi-Turn loop is a follow-up phase, gated on a manual smoke test (the lesson from the Living-Canvas regression).
   - **`acpx`**: the harness calls `runtime.spawn(agent_id=skill.acpx_agent, task=<rendered body>)`, drains events into the audit log, then `runtime.kill(session_id)`. A short `${input.KEY}` template substitution renders any `${input.x}` in the body before sending it.
5. **Output validation.** When the skill declares `outputs`, the harness runs `io_contract.validate_outputs(...)`. A violation produces a failure envelope with `reason="output_contract_violation"` and the offending output included for debugging.
6. **Audit close.** A successful invocation returns:
   ```json
   {
     "ok": true, "skill": "my-skill", "runtime": "in-process",
     "output": {...validated outputs...},
     "iterations_used": 1, "tokens_used": 0,
     "elapsed_seconds": 0.00X, "audit_id": "<32-hex>"
   }
   ```

The `audit_id` lets you locate the per-invocation NDJSON file later.

### 4.4 Budget enforcement

```python
@dataclass
class Budget:
    max_iterations: int   # raises BudgetExceeded when iterations > cap
    max_seconds: float    # raises BudgetExceeded when elapsed > cap
    max_tokens: int       # raises BudgetExceeded when running token total > cap
```

Every harness loop tick calls `budget.tick_iteration()` which checks both iteration count and wall-clock. ACP children push token counts back through `budget.add_tokens()` when their event stream includes a `tokens` field. Exceeding any cap is a clean failure (`reason="budget_exceeded"`), never a hang.

---

## 5. The catalog (20 seed skills)

> **Historical revision snapshot.** The numbers in this section (and the verification log below) reflect the original ACPX port. The catalog has since grown — **27 skills as of 2026-06-01** (added: `code-review`, `security-audit`, `kali-pentest`, `create-new-agent`, `create-new-mcp`, `tlamatini-flow-from-objective`, **`flow-making`**). See `CLAUDE.md` / `README.md` §3.12 for the current list; run `python agent/skills_pkg/_meta/lint.py` for the live count.

| # | Skill name | Runtime | Purpose |
|---|---|---|---|
| 1 | `hello-world` | in-process | Smoke test the harness |
| 2 | `skill-creator` | in-process | Bootstrap a new SKILL.md package |
| 3 | `acp-router` | in-process | Pick the right ACP agent_id and `acp_spawn` it |
| 4 | `tlamatini-new-acp-agent` | in-process | Scaffold a new visual ACP agent end-to-end (8 steps) |
| 5 | `tlamatini-flow-from-objective` | in-process | Turn an objective into a `.flw` workflow file |
| 6 | `tlamatini-flw-doctor` | in-process | Validate a `.flw` (topology, terminal agents, gates) |
| 7 | `tlamatini-exec-report-row-adder` | in-process | Add a tool to `_EXEC_REPORT_TOOLS` + matching CSS |
| 8 | `tlamatini-planner-trace-replay` | in-process | Replay & explain the latest planner trace from the log |
| 9 | `tlamatini-allowed-hosts-tighten` | in-process | Replace `ALLOWED_HOSTS=['*']` with a whitelist + backup |
| 10 | `tlamatini-csrf-exempt-audit` | in-process | Classify every `@csrf_exempt` view in views.py |
| 11 | `tlamatini-static-version-bumper` | in-process | Bump `STATIC_VERSION` to bust frontend cache |
| 12 | `github` | in-process | Use `gh` CLI for issues / PRs / runs / releases |
| 13 | `notion` | in-process | Notion API — pages, data sources, blocks |
| 14 | `jira` | in-process | Jira REST API v3 — issues, comments, transitions |
| 15 | `slack` | in-process | Slack Web API — post, reply, history, react, upload |
| 16 | `gmail` | in-process | Gmail API — search, get, send, reply, label |
| 17 | `todoist` | in-process | Todoist REST API v2 — tasks and projects |
| 18 | `trello` | in-process | Trello API — boards, cards, comments |
| 19 | `summarize` | in-process | Compress text to a target word count, faithfully |
| 20 | `weather` | in-process | Open-Meteo current + hourly forecast (no key) |

This is the seed; the catalog is meant to grow to 100+ over the phased rollout described in section 11. Adding skill #21 means dropping a new directory under `agent/skills_pkg/` — no Python edits required.

---

## 6. Visual canvas integration

Two new node types on the ACP canvas:

| Node | CSS class | Gradient | Maps to |
|---|---|---|---|
| **Skill** | `.canvas-item.skill-agent` | purple → indigo → cyan → teal | `invoke_skill(name, args)` |
| **ACPx** | `.canvas-item.acpx-agent` | fire-orange → coral → violet → black | `acp_spawn(agent_id, task, …)` |

Both are registered in the `AGENT_TYPE_CLASS_MAP` of `agent/static/agent/js/acp-canvas-core.js` (the canonical classMap location) so the existing icon-style cache, sidebar tooltip, and applyAgentTypeClass paths pick them up automatically. Their gradients live in `agent/static/agent/css/agentic_control_panel.css` next to the existing 57-agent gradient block; the **ACPx gradient is intentionally loud** (deep red → coral → violet → black) because spawning an external CLI is a security-relevant action and the visual identity should make that obvious.

The full visual integration (right-click menu wiring, configuration dialog populated from `list_acp_agents` / `list_skills`, .flw load/save round-trip, undo/redo coverage) is the visible-canvas Phase 5 of the rollout — not in this commit. The classMap + gradient ground laid here is what Phase 5 builds on.

---

## 6.5 The ACPX-Skills admin menu (added 2026-05-17)

The Phase-5 visual surface is still future work, but the **operator-facing** surface for the skill catalog has landed. The chat navbar has a fourth dropdown, **ACPX-Skills**, between **Agents** and **Config**, with four entries:

| Entry | Backing | What it does |
|---|---|---|
| **Browse Skills** | `GET /agent/skills/` + `GET /agent/skills/<name>/` | Two-pane modal: search-filterable skill list + detail pane (frontmatter, requires, inputs/outputs, permissions, body). Pure read. |
| **Configure Skills** | WebSocket `set-skills` (mirrors `set-mcps` / `set-agents` / `set-tools`) | Checkbox-grid modal toggling `Skill.enabled`. Disabled skills are filtered from `list_skills` and rejected by `invoke_skill` with `{"ok":false,"code":"SKILL_DISABLED"}`. |
| **Diagnostics** | `GET /agent/skills/_/diagnostics/` | Cross-check report: missing tool/MCP deps (against disabled `Tool` / `Mcp` rows), unknown `acpx_agent` values, orphan `Skill` rows. |
| **Reload Registry** | `POST /agent/skills/_/reload/` | Re-runs `agent/acpx/service.py::boot_skills()` — rescans `agent/skills_pkg/`, refreshes Skill rows, prunes orphans. No server restart needed; `enabled` toggles preserved. |

### What it changes about §7 (day-one) and §10 (runbook)

- §7.5 (smoke-test `hello-world`): instead of typing into the chat, you can now hit **Browse Skills** to confirm `hello-world` is loaded, then **Configure Skills** to verify it's enabled. The chat `list_skills` + `invoke_skill` flow still works exactly the same.
- §10.2 ("a skill is failing"): **Diagnostics** is now the first place to check before opening the audit NDJSON. Most failures (disabled `requires_tools`, missing MCP, unknown `acpx_agent`) show up there before they show up in the audit log.

### The constraint that matters most

The `Skill` DB row already existed in this commit (the `Skill` model in `agent/models.py` and migration `0071_acpx_skills.py` are both pre-existing). The admin UI **only ever writes `Skill.enabled`** — every other column (`description`, `runtime`, `acpx_agent`, `frontmatter_json`, `body_sha256`) is owned by `boot_skills()` and refreshed from the SKILL.md on disk on every reload. The disk is the only source of truth for permissions, budgets, and body. **Do not extend the dialog to override SKILL.md fields from the browser** — the rule is "DB only for enumeration and enable/disable like MCPs/Agents". If you want to change a permission, edit the SKILL.md and click Reload.

### Files touched (incremental on top of the original commit)

- `agent/views.py` — `list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`
- `agent/urls.py` — 4 new routes
- `agent/consumers.py` — `skill_establishment()`, `get_all_skills()`, `save_skill()`, `set-skills` handler, establishment loops in both rebuild paths
- `agent/acpx/tools.py` — `_disabled_skill_names()` helper + gating clauses in `list_skills` / `invoke_skill` (fails OPEN on DB exception)
- `agent/templates/agent/agent_page.html` — navbar dropdown + 3 dialog containers + asset includes
- `agent/static/agent/js/skills_dialog.js` — 4 dialogs in ~360 lines
- `agent/static/agent/js/{agent_page_state,agent_page_init,agent_page_chat}.js` — `skills` global + entry points + `type:'skill'` system-message handler
- `agent/static/agent/css/skills_dialog.css` — styling
- `eslint.config.mjs` — 11 new globals
- Coverage: 14 tests in `agent/tests.py` (`SkillsAdminEndpointTests`, `SkillsToolSurfaceGatingTests`, `SkillsNavbarTemplateContractTests`)

---

## 7. Day-one usage walkthrough (for dummies)

### 7.1 Install one external coding-agent CLI

The ACPX runtime is happy with any of the 13 supported CLIs. The simplest is Anthropic's:

```
npm install -g @anthropic-ai/claude-code      # installs `claude` on PATH
claude --version                              # confirm
```

(If you don't install any CLI, ACPX still works — but `acp_doctor` returns unhealthy and `acp_spawn` will fail with `AGENT_NOT_FOUND`. The skill catalog and the in-process harness work fine even with zero ACP CLIs installed.)

### 7.2 Apply the new migration

```
python Tlamatini/manage.py migrate
```

That creates `AcpAgent`, `Skill`, `AcpSession`, `SkillInvocation`, and seeds 7 new `Tool` rows for the new tools.

### 7.3 Lint the skill catalog

```
python Tlamatini/manage.py acpx_lint
```

You should see 20 skills passing. If any fail, fix the SKILL.md before continuing — a malformed skill is silently skipped at runtime.

### 7.4 Start Tlamatini in source mode

```
python Tlamatini/manage.py runserver --noreload
```

In the log (`Tlamatini/tlamatini.log`) you should see:

```
[ACPX] mirrored 14 agents into AcpAgent table
[skills] reload: 20 skills loaded
[ACPX] mirrored 20 skills into Skill table
```

If you see those three lines, the runtime is alive.

### 7.5 Try the smoke-test skill

In the chat, with Multi-Turn enabled and the seven new tool toggles ON, ask:

```
Use list_skills to confirm 'hello-world' is registered, then invoke it with who='angel'.
```

You should see the LLM call `list_skills` → `invoke_skill('hello-world', '{"who":"angel"}')` and return a JSON envelope with `ok: true` and `output.greeting` set.

### 7.6 Health-probe ACPX

In the chat:

```
Run acp_doctor and tell me what it reports.
```

Expected `ok: true` if `claude` (or whichever your `probeAgent` is) is on PATH; `ok: false` with a clear `details` array otherwise.

### 7.7 Spawn an ACP child

```
Spawn claude in cwd='C:/Development/Tlamatini' with the task 'list the immediate children of agent/' using acp_spawn.
```

You should see a returned `session_id`, the last 32 events of the child's response, and a `transcript_path` you can open later for the full record.

If you want to follow up:

```
Send 'now show the agents/ folder' to that session via acp_send.
```

When done:

```
Kill the session via acp_kill.
```

### 7.8 Author a new skill

The fastest way:

```
Use the skill-creator skill to bootstrap a new skill named 'my-first-skill'
that runs in-process and just echoes its inputs.
```

The LLM follows the skill-creator playbook, writes `agent/skills_pkg/my_first_skill/SKILL.md`, runs `python Tlamatini/agent/skills_pkg/_meta/lint.py`, and returns the result. Your new skill is immediately visible to `list_skills`.

---

## 8. Day-two usage — building real flows

### 8.1 Drag-and-drop a Skill into a `.flw`

(Phase-5 visual; ground laid in this commit. You can already pre-populate a `.flw` JSON manually:)

```json
{
  "version": 1,
  "agents": [
    { "id": 1, "type": "starter", "x": 50,  "y": 50, "config": {} },
    { "id": 2, "type": "skill",   "x": 250, "y": 50,
      "config": { "skill_name": "summarize", "args": { "text": "...", "target_words": 80 } } },
    { "id": 3, "type": "notifier","x": 450, "y": 50, "config": {} }
  ],
  "connections": [
    { "from": 1, "to": 2, "kind": "target_agents" },
    { "from": 2, "to": 3, "kind": "target_agents" }
  ]
}
```

When Phase 5 ships, this loads visually with the new gradient nodes.

### 8.2 Mix Skill + ACPx in one flow

Recommended pattern for "delegate the heavy lifting to Cursor, then notify":

```
Starter → ACPx(cursor, task='refactor file X to async') → Skill(summarize) → Emailer
```

The ACPx node spawns Cursor as a child and waits; the Skill node summarizes its transcript; the Emailer ships the digest.

### 8.3 The acp-router skill

When the user types "run this in qwen", the LLM should reach for `acp-router` instead of guessing. acp-router knows the AgentId mapping and the unhealthy-fallback recovery procedure. It's a tiny skill but it's the difference between "claude" → claude and "Claude Code" → still claude (the LLM does this kind of disambiguation poorly without a skill body to consult).

---

## 9. Internals deep dive

### 9.1 Why a separate `skills_pkg/` directory?

Python imports `agent.skills` (the runtime). The skill *content* must NOT be a Python package because:
- A SKILL.md filename collides with no Python; a `__init__.py` in `agent/skills/` would, however, be confusing if it imported skill contents.
- `agent.skills_pkg` keeps content discovery purely file-system based — the registry calls `Path.rglob("SKILL.md")`, never `importlib`.
- A future plugin distribution that ships skills as zip packages can drop them into `skills_pkg/` without touching anything else.

### 9.2 Reset-aware session store

OpenClaw's `createResetAwareSessionStore` adds a `markFresh(sessionId)` method that makes the next `load(sessionId)` return None even if the on-disk file exists. Tlamatini ports the same semantics (see `agent/acpx/session_store.py::FileSessionStore.mark_fresh`). The reason is exactly what the OpenClaw runtime explains: a freshly-spawned session must NOT inherit the previous session's transcript, so when we reuse a session_id slot we mark it fresh and the first `load()` returns None until the first `save()` lands.

### 9.3 The Windows spawn quirks

`agent/acpx/windows_spawn.py::resolve_command` mirrors OpenClaw's `applyWindowsSpawnProgramPolicy`. Three rules:

1. If the command has a path separator and the file ends in `.cmd` or `.bat`, return it with `use_shell=True` so Windows actually invokes the shim.
2. If the command is a bare name, search PATH across `cmd / cmd.cmd / cmd.bat / cmd.exe` (in that order) using `shutil.which`.
3. Returning the command unchanged is a valid "let it fail loudly" path — `subprocess.Popen` will raise `FileNotFoundError` and `AcpSession.spawn_child()` translates that into `AcpRuntimeError("AGENT_NOT_FOUND")`.

This all matters because `claude` on Windows is typically `claude.cmd`, and `npm install -g` puts it in `%APPDATA%/npm/`. Without the suffix search, the runtime would never find it.

### 9.4 The transcript file format

Per-session NDJSON in `<state_dir>/<session>.transcript.ndjson`. Each line is a JSON object:

```json
{"direction": "out", "text": "<task>", "ts": 1761800000.123}
{"direction": "in",  "raw":  "<line>", "ts": 1761800000.456}
```

Direction `out` is what we wrote to the child's stdin; direction `in` is what we read back. Re-replaying a transcript is straightforward; the ndjson format is intentional so existing tools (jq, Python `json.loads` per line, log shippers) work directly.

### 9.5 Tool toggle pattern reuse

ACPX tools follow the existing `Tool` toggle convention exactly:

- Each tool has a row in the `Tool` table seeded by migration 0071 (`acpx-spawn`, `acpx-send`, `acpx-kill`, `acpx-doctor`, `acpx-list-agents`, `acpx-invoke-skill`, `acpx-list-skills`).
- Each row has a `toolDescription` whose normalized form (`acpx-spawn`) becomes the gating key `tool_acpx-spawn_status` in `global_state`.
- `get_mcp_tools()` checks each gate (default `'enabled'`) and adds the tool only if enabled.
- The existing `tools_dialog.js` UI surfaces the toggles automatically.

This means: zero new UI work to expose the seven new tools to operator-level enable/disable.

### 9.6 Mirroring vs source-of-truth

Three new tables (`AcpAgent`, `Skill`, `AcpSession`) and one audit table (`SkillInvocation`).

- `AcpAgent` is **mirrored** from disk: `service.boot_acpx()` reconciles rows with `runtime.list_agents()` on every Django boot. Disk is source of truth; the table is the UI / toggle surface.
- `Skill` is **mirrored** from disk the same way (`service.boot_skills()`).
- `AcpSession` is **runtime state**: each row corresponds to a real (or recently-real) child process. The `FileSessionStore` JSON is the source of truth; the DB row is for the admin / future UI.
- `SkillInvocation` is the **audit trail**: append-only, never reconciled.

### 9.7 What `boot_skills` and `boot_acpx` do NOT do

They never:
- Spawn an ACP child during Django startup. (Probing is `--version`, not a session.)
- Block the ASGI worker. (They run on a daemon thread.)
- Raise on import errors of the skill content. (Malformed SKILL.md files log a warning and are skipped.)
- Auto-rebuild the registry without prompting. (30-second stale check; explicit `reload()` is a one-liner.)

---

## 10. Operator runbook — five common situations

### 10.1 "ACPX feels broken — nothing happens when I call acp_spawn"

1. `python Tlamatini/manage.py shell` → `from agent.acpx import get_acpx_runtime; r=get_acpx_runtime(); r.probe_availability(); print(r.doctor())`. The `details` array names the probe agent and the failure mode.
2. Confirm the named agent CLI is on PATH from the shell Tlamatini runs in: `where claude` (Windows) or `which claude` (POSIX).
3. If the binary lives somewhere unusual, override it in `config.json`:
   ```json
   "acpx": { "agents": { "claude": { "command": "C:/full/path/to/claude.cmd" } } }
   ```
4. Restart Tlamatini, re-run `acp_doctor`.

### 10.2 "A skill is failing with input_contract_violation and I don't know which input"

Open `~/.tlamatini/skill-audit/<YYYY-MM>/<...>.ndjson` for the matching `audit_id`. The `args_validated` event records the args that survived coercion; the `skill_failed` event records the reason. The LLM also gets the same detail in the JSON envelope, so asking "what was the validation error?" surfaces it back.

### 10.3 "I want to see what an ACP child actually said"

`<state_dir>/<session_id>.transcript.ndjson`. Default state_dir is `~/.tlamatini/acpx-state/`. One line per event, both directions. Use `jq` or `Get-Content` with a tail-follow for live debugging.

### 10.4 "I want to lock down the runtime entirely"

In `config.json`:

```json
"acpx": { "permissionMode": "deny-all" }
```

`acp_spawn` will refuse with `code: PERMISSION_DENIED`. The skill harness will reject any non-trivial skill action. `acp_doctor` still works (probing is read-only).

### 10.5 "I want to add a skill that needs a tool that doesn't exist yet"

The Tlamatini contract is: skills can only `requires_tools` a tool that is registered in `agent/tools.py`. The current registered set is the legacy tools + the 42 wrapped chat-agents + the 12 ACPX/Skill tools listed in §9.5. If your skill needs a brand-new tool, add the `@tool` first (per the existing tool-creation guide in `Tlamatini/.mcps/create_new_mcp.md`), then write the skill that requires it. `acpx_lint` will be extended in a follow-up phase to cross-check `requires_tools` against `get_mcp_tools()` automatically.

---

## 11. Phased rollout (where this revision sits)

| Phase | What lands | Status |
|---|---|---|
| **1** | ACPX runtime skeleton: AcpxRuntime, FileSessionStore, agent_registry, permissions, windows_spawn, the 4+1 @tool functions, acp_doctor, migration | **DONE in this revision** |
| **2** | First spawn end-to-end (`acp_spawn` works against a real installed CLI), transcript persistence | **Manual smoke test gates this** — user runs §7.7 once with `claude` installed |
| **3** | Skill skeleton: SkillRegistry, SkillHarness with budget + IO contract, hello-world + skill-creator + 18 more seed skills | **DONE in this revision** |
| 4 | Planner integration: skills' `triggers` scored in `global_execution_planner.py`; tier-2 surfacing | Pending |
| 5 | Visual canvas: full Skill / ACPx node config dialogs, .flw save/load round-trip, undo/redo. (CSS + classMap groundwork is DONE here.) | Pending |
| 6 | Catalog buildout: skills 21–105+ in 8–10 thematic PRs | Pending |
| 7+ | Real-time hook UI surface (the Living-Canvas-style theater for ACP/Skill activity) — separately gated | Pending |

Each future phase ships only with a manual smoke test recorded in the commit message, mirroring the lesson from the dropped Living Canvas v0. **The rule is: the agent's commit message must describe a real instance run, not a green test count.**

---

## 12. Reference

### 12.1 Public Python surface

```python
# Runtime
from agent.acpx import (
    AcpxConfig, PERMISSION_MODES, NON_INTERACTIVE_POLICIES, DEFAULT_TIMEOUT_SECONDS,
    load_acpx_config,
    AcpAgentSpec, DEFAULT_ACP_AGENTS, build_agent_registry,
    FileSessionStore, AcpSessionRecord,
    AcpxRuntime, AcpSession, AcpRuntimeError, get_acpx_runtime,
)

# LLM-facing tools
from agent.acpx import (
    acp_spawn, acp_send, acp_kill, acp_doctor, list_acp_agents,
    invoke_skill, list_skills,
)

# Skill side
from agent.skills import skill_registry, Skill, SkillHarness, SkillRuntimeError, BudgetExceeded
```

### 12.2 Tool input/output envelope shapes

| Tool | Input args | Success envelope keys |
|---|---|---|
| `acp_spawn` | agent_id, task, cwd?, mode?, session_label? | session_id, agent_id, transcript_path, events |
| `acp_send` | session_id, text, timeout_seconds? | events |
| `acp_kill` | session_id | killed |
| `acp_doctor` | (none) | message, details |
| `list_acp_agents` | (none) | agents [{agent_id, command, description, resolvable}] |
| `invoke_skill` | skill_name, args_json | skill, runtime, output, iterations_used, tokens_used, elapsed_seconds, audit_id |
| `list_skills` | filter_keywords? | skills [{name, description, runtime, acpx_agent}] |

Failure envelope is always `{ok: false, reason, code, [extras]}`.

### 12.3 Files added or modified by this revision

**New files (no commits made):**

- `Tlamatini/agent/acpx/__init__.py`
- `Tlamatini/agent/acpx/config.py`
- `Tlamatini/agent/acpx/agent_registry.py`
- `Tlamatini/agent/acpx/session_store.py`
- `Tlamatini/agent/acpx/windows_spawn.py`
- `Tlamatini/agent/acpx/permissions.py`
- `Tlamatini/agent/acpx/runtime.py`
- `Tlamatini/agent/acpx/tools.py`
- `Tlamatini/agent/acpx/service.py`
- `Tlamatini/agent/acpx/tests.py`  (23 tests, all green)
- `Tlamatini/agent/skills/__init__.py`
- `Tlamatini/agent/skills/frontmatter.py`
- `Tlamatini/agent/skills/registry.py`
- `Tlamatini/agent/skills/io_contract.py`
- `Tlamatini/agent/skills/harness.py`
- `Tlamatini/agent/skills_pkg/_meta/schema.json`
- `Tlamatini/agent/skills_pkg/_meta/lint.py`
- `Tlamatini/agent/skills_pkg/<20 SKILL.md packages>`
- `Tlamatini/agent/migrations/0071_acpx_skills.py`
- `Tlamatini/agent/management/commands/acpx_lint.py`
- `ACPX.md`  (this file, at repo root)

**Modified files:**

- `Tlamatini/agent/apps.py` — boot ACPX + Skills on the existing background-thread path.
- `Tlamatini/agent/models.py` — adds `AcpAgent`, `Skill`, `AcpSession`, `SkillInvocation`.
- `Tlamatini/agent/tools.py` — registers the 7 new ACPX tools in `get_mcp_tools()`.
- `Tlamatini/agent/static/agent/js/acp-canvas-core.js` — adds `'skill'` and `'acpx'` to `AGENT_TYPE_CLASS_MAP`.
- `Tlamatini/agent/static/agent/css/agentic_control_panel.css` — adds the two new gradient blocks.

### 12.4 Verification checklist (what was actually run)

| Check | Result |
|---|---|
| `python -m unittest agent.acpx.tests -v` | **23 tests passed, 0 failed** |
| `python agent/skills_pkg/_meta/lint.py` | **20 SKILL.md packages valid, 0 invalid** |
| `python manage.py acpx_lint` | **20 valid, exit 0** |
| `python manage.py makemigrations agent --check --dry-run` | **No changes detected** (migration 0071 is a complete schema delta) |
| `python manage.py test agent.tests.ExecReportCaptureTests agent.tests.LoadedContextFallbackTests` | **12 existing tests still pass** |
| End-to-end import smoke: load registry, invoke hello-world, list ACP agents, list skills | **20 skills loaded, 14 ACP agents registered (4 resolvable on this PATH), `hello-world` returns ok=true** |

### 12.5 What was NOT done (intentional)

- **No commits.** The user explicitly said "DON'T COMMIT ANYTHING." All edits live in the working tree only.
- **No real ACP child spawn was attempted.** That requires a CLI to be installed; the manual smoke-test gate in §7.7 is for the user to run after reviewing the code.
- **No real-time UI / Living-Canvas-style theater.** The Living-Canvas regression of 2026-04-29 taught us that hooks defined but unconsumed is the right shape for a first revision; the hook-broadcasting code path is intentionally absent.
- **No automatic skill-author loop.** `skill-creator` guides a human through authoring; it does not autonomously commit new skills.
- **No sandboxing model.** The OpenClaw `Dockerfile.sandbox` story is a parallel workstream, called out separately in TlamatiniVsOpenClaw.md.
- **No follow-up Phase-2-style integration tests** that depend on a real CLI being installed. Those land after the user confirms the manual smoke test passes.

---

## 13. Frequently asked questions

**Q: Can a skill call another skill?**
A: Yes — through the harness's tool surface. If the calling skill has `invoke_skill` in `requires_tools`, the LLM can chain. The harness will create separate audit records for each invocation.

**Q: Can ACPX call back into Tlamatini?**
A: Yes via the `pluginToolsMcpBridge` flag (default OFF). When ON, the runtime injects an MCP server that exposes Tlamatini @tools to the ACP child. Off-by-default because exposing every tool to a less-trusted runtime is a security choice; opt in deliberately.

**Q: What happens if two `acp_spawn` calls race?**
A: Each gets its own session_id; the FileSessionStore writes are atomic (temp file + os.replace). Two concurrent sessions for the same agent_id is fine. The runtime singleton's `_sessions` dict tracks them by id.

**Q: How is this safer than the existing `execute_command` tool?**
A: ACPX adds a permission gate that `execute_command` lacks. With `permissionMode: deny-all`, ACPX cannot spawn anything. With `approve-reads`, it can still spawn (the spawn itself is read-class) but every write/shell action *inside* the child requires either an interactive prompt or fails per the non-interactive policy. `execute_command` has no such layer. The TlamatiniVsOpenClaw report flagged that as a security debt; the natural follow-up is a skill `tlamatini-execute-command-permission-bridge` (in the roadmap) that wraps the legacy tool in the same gate.

**Q: Is OpenClaw required to use Tlamatini ACPX?**
A: No. ACPX is a Python implementation living in `agent/acpx/`; it talks to ACP-compatible CLIs directly. OpenClaw is one such consumer/producer of the same protocol but Tlamatini does not import it.

**Q: How does this interact with the existing 57 visual agents?**
A: It doesn't — they're orthogonal. Skills are a *new* node type, not a replacement. Existing flows are unchanged. The Phase-5 visual integration will add Skill / ACPx as 58th and 59th typed nodes; until then they exist on the runtime side only.

**Q: Will this slow down Django startup?**
A: No. The boot is on a daemon thread, the probe is bounded to 5 seconds, and skill registry reload is a directory scan over ~20 files. On a cold start the visible cost is below 200 ms; on hot starts it's negligible.

**Q: Can I disable ACPX entirely?**
A: Two ways. (a) Set every `tool_acpx-*_status` to `'disabled'` through the existing tool toggle UI — the unified-agent stops seeing the tools but the runtime stays alive. (b) `permissionMode: deny-all` — the runtime is alive but every action is blocked; useful for audit. There is no environment variable to turn off the import; the runtime singleton is lazy and never spawns anything until `acp_spawn` is called.

---

## 14. Closing note

This is a substantial change set: 11 new Python files, 1 modified migration path, 4 modified existing files, 20 SKILL.md packages, 1 admin command, and a new visual-canvas surface ground laid for Phase 5.

It is also explicitly **uncommitted**. The user's standing rule — and the lesson learned the hard way from the 2026-04-29 Living-Canvas episode — is that nothing ships without an end-to-end manual smoke test in a running source-mode instance, demonstrated by the user.

That smoke test for ACPX is §7.7. The smoke test for the skill harness is §7.5. They take three minutes total once a CLI is installed and they prove the boundary that the unit tests cannot prove.

If both pass, the work is ready to commit. If they don't, **drop the changes** — `git checkout -- .` and `git clean -fd Tlamatini/agent/acpx Tlamatini/agent/skills Tlamatini/agent/skills_pkg ACPX.md` will return the tree to the last commit. There is no ambiguity here: a feature that does not animate in a real instance does not ship.

Welcome to ACPX. It is built to be small at the boundary, large at the catalog, and safe by default.
