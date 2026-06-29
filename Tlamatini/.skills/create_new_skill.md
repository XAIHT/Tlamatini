<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Creating a New Skill (SKILL.md package) in Tlamatini

Authoritative, step-by-step guide for authoring a new **Skill** — including
**ACPX skills**. A Skill is a markdown package (`SKILL.md`) discovered at
runtime by `agent/skills/registry.py` and invoked by the LLM through the two
always-on ACPX-surface tools `list_skills` / `invoke_skill`. It is **NOT** an
MCP, **NOT** a `Tool` row, **NOT** a `@tool` function, and **NOT** a workflow
agent.

> **Companion guides** (already auto-imported every session):
> - `Tlamatini/.mcps/create_new_mcp.md` → the "Skill Workflow (SKILL.md package)" section is the short version of this file.
> - `Tlamatini/.agents/workflows/create_new_agent.md` → for the *heavier* workflow-agent surface (do NOT confuse a Skill with an Agent).
>
> **Reference skills to read before you start** (all under `agent/skills_pkg/`):
> - `skill_creator/SKILL.md` — the bootstrap skill + its `scripts/quick_validate.py`.
> - `acp_router/SKILL.md` — the canonical **ACPX-orchestrating** skill (runtime `in-process`, drives `acp_spawn` / `acp_send` / `acp_kill`).
> - `setup_new_acpx_key/SKILL.md` — a long, real ACPX procedure with a full `permissions` / `inputs` / `outputs` contract.
> - `summarize/SKILL.md` — minimal in-process skill.
> - `flow_making/SKILL.md` — the canonical **in-process skill that shells out to shipped `scripts/*.py`** (objective → `.flw` by wrapping FlowCreator); shows a runbook that drives `execute_command` + `chat_agent_file_creator`, a deterministic converter, and a `references/` schema file.
> - `tlamatini_new_acp_agent/SKILL.md` — internal-tooling skill that operates ON the ACPX runtime.

---

## 0 · First decision: is a Skill even the right surface?

A Skill is the right choice when the capability is **procedural** — a runbook
the LLM follows — that *composes existing tools* (`acp_*`, `chat_agent_*`,
`execute_command`, MCP fetches) into a documented sequence.

| Want to… | Surface | Guide |
|---|---|---|
| Document a *procedure* the LLM follows by name | **Skill** | this file |
| Run new Python inline on demand | direct `@tool` | `create_new_mcp.md` |
| Spawn a long-running isolated subprocess | wrapped `chat_agent_*` | `create_new_mcp.md` |
| Inject prompt context before answering | MCP context provider | `create_new_mcp.md` |
| Add a drag-and-drop canvas workflow node | Agent | `create_new_agent.md` |

If you find yourself editing a migration, `tools.py`, `chat_agent_registry.py`,
`factory.py`, a JS file, or any HTML — **stop**. A Skill touches exactly one
file (its `SKILL.md`), plus optional `references/` and `scripts/` siblings.
No DB row, no UI checkbox markup, no chain rewiring.

---

## 1 · The two Skill runtimes (this is the core decision)

`metadata.tlamatini.runtime` selects how `SkillHarness` (`agent/skills/harness.py`)
executes the body. There are exactly two values, and the parser rejects any
other (`frontmatter.py` raises `SkillParseError`).

### `runtime: in-process` (default)

- The body is loaded as a **planning playbook**. The harness returns a
  structured *envelope* (`skill_runtime`, `body_excerpt`, `permissions`,
  `requires_tools`, `requires_mcps`, `guidance`) plus stub values shaped to the
  declared `outputs`. The calling unified-agent then **carries the plan
  forward using the tools listed in `requires_tools`**. The harness itself does
  NOT execute destructive actions in this revision (safe-by-default).
- **This is what an "ACPX skill" almost always is**: a skill whose body tells
  the LLM how to drive `acp_spawn` / `acp_send_and_wait` / `acp_relay` /
  `acp_kill` (and `acp_doctor` first). `acp-router` and `setup-new-acpx-key` are
  both `in-process` — they *orchestrate* the ACPX tools rather than *becoming* an
  ACPX child. **Prefer this for anything that picks an `agent_id`, relays
  between CLIs, or sets up ACPX.**

### `runtime: acpx`

- The body **becomes the `task` text of an ACPX child session**, spawned with
  `metadata.tlamatini.acpx_agent` (a registered `agent_id` — claude / cursor /
  gemini / qwen / codex / tlamatini / kiro / kimi / iflow / kilocode / opencode /
  pi / droid / copilot). The harness collects events until `done` or the budget
  is exceeded, then returns `{answer, events}`.
- `acpx_agent` is **mandatory** for this runtime — the parser raises
  `runtime=acpx requires tlamatini.acpx_agent` otherwise.
- The body supports a tiny `${input.KEY}` substitution at spawn time
  (`SkillHarness._render_body`), so write the body as a prompt template that
  references its declared inputs, e.g. `Review the diff at ${input.repo_path}`.
- Use this **only** when the entire job is "hand this exact prompt to one
  external CLI and return its answer". If you need to branch, call multiple
  tools, or read transcripts between turns, use `in-process` and let the LLM
  drive the `acp_*` tools.

> Pick `acpx` when the skill *is* a single CLI prompt. Pick `in-process` when the
> skill *coordinates* the ACPX tools. When unsure, choose `in-process`.

---

## 2 · Where the file goes & how it's discovered

```
Tlamatini/agent/skills_pkg/<skill_name>/SKILL.md      # required
Tlamatini/agent/skills_pkg/<skill_name>/references/   # optional long playbooks
Tlamatini/agent/skills_pkg/<skill_name>/scripts/      # optional helper scripts
```

Discovery facts (from `registry.py`, do not fight them):

- The registry `rglob`s `SKILL.md` under each root — **nested subdirectories are
  allowed**, the filename must be exactly `SKILL.md`.
- The skill's `name` should match the **leaf directory name**; if the
  frontmatter `name` differs, **the frontmatter wins**. Keep them identical to
  avoid confusion.
- **Duplicate `name` is rejected by the linter** and the registry's "later wins"
  map silently shadows — never reuse an existing skill's `name`.
- A malformed `SKILL.md` is **skipped with a logger warning, never a crash** —
  so a broken skill is invisible, not loud. Always lint (step 5).
- The registry caches with a **30-second staleness window** (`reload_if_stale`).
  In a long-running server, disk edits show up within 30 s — or force it via the
  navbar **ACPX-Skills ▸ Reload Registry** (`boot_skills()` re-run), no restart.
- Frozen builds resolve `skills_pkg` from the install-dir copy, then the
  PyInstaller `_MEIPASS` bundle, then source. `build.py` ships the directory both
  ways, so a new skill is picked up in frozen builds after a rebuild.
- `name` is **kebab-case** (lowercase ASCII letters/digits/dashes). The directory
  name is conventionally `snake_case` (e.g. dir `acp_router`, name `acp-router`).

---

## 3 · The frontmatter contract (field by field)

Validated against `agent/skills_pkg/_meta/schema.json` and parsed by
`agent/skills/frontmatter.py`. **Only `name` is hard-required by the parser**;
everything else has a safe default. But the JSON schema and `quick_validate.py`
both expect `description`, and good skills declare the full contract.

| Field | Required | Default | Notes |
|---|---|---|---|
| `name` | **yes** | — | kebab-case; unique across all skills; matches dir leaf |
| `description` | yes (schema) | `""` | one line; shown by `list_skills`; fed to the planner for scoring |
| `metadata.openclaw.emoji` | no | — | cosmetic; OpenClaw compatibility |
| `metadata.tlamatini.runtime` | no | `in-process` | `in-process` \| `acpx` only |
| `metadata.tlamatini.acpx_agent` | **iff runtime=acpx** | `""` | a registered `agent_id` (`list_acp_agents`) |
| `metadata.tlamatini.requires_tools` | no | `[]` | tool names the body calls (`acp_spawn`, `chat_agent_file_creator`, …) |
| `metadata.tlamatini.requires_mcps` | no | `[]` | e.g. `["Files-Search"]` |
| `metadata.tlamatini.budget.max_iterations` | no | `12` | schema range **1–256** |
| `metadata.tlamatini.budget.max_seconds` | no | `180` | schema range **1–7200** |
| `metadata.tlamatini.budget.max_tokens` | no | `30000` | schema range **1–1000000** |
| `metadata.tlamatini.permissions.filesystem.{read,write}` | no | `[]` | glob lists; supports `${input.X}` interpolation |
| `metadata.tlamatini.permissions.shell` | no | `[]` | exact allowed command prefixes |
| `metadata.tlamatini.permissions.network` | no | — | `"allow"` \| `"deny"` or array |
| `metadata.tlamatini.permissions.db` | no | — | `"allow"` \| `"deny"` \| `"read"` or array |
| `metadata.tlamatini.inputs[]` | no | `[]` | each item needs `name` + `type`; optional `required`/`default`/`values`/`description` |
| `metadata.tlamatini.outputs[]` | no | `[]` | each item needs `name` + `type`; validated by `io_contract` when present |
| `metadata.tlamatini.triggers.keywords` | no | `[]` | planner relevance signals |
| `metadata.tlamatini.triggers.file_globs` | no | `[]` | planner relevance signals |

Contract enforcement at invoke time (`harness.py` + `io_contract.py`):

- **Inputs** are validated and coerced *before* the body runs. A missing
  `required: true` input fails with `input_contract_violation`.
- **Outputs** are validated *after* the body runs, but **only when `outputs` is
  declared**. Declaring outputs you don't actually return causes
  `output_contract_violation` — so declare only what the skill genuinely yields.
- **Budget** is hard-enforced: `max_iterations`, `max_seconds`, `max_tokens`.
  Exceeding any returns `budget_exceeded`. Keep ACPX skills' `max_seconds`
  realistic — a slow CLI relay can need 120–300 s (and the ACPX child has its
  own timeout/idle budgets separate from this skill budget).

---

## 4 · Authoring scaffolds

### 4a. `in-process` ACPX-orchestrating skill (the common case)

```markdown
---
name: my-acp-skill
description: One-line statement of when the LLM should invoke this.
metadata:
  openclaw:
    emoji: "🧭"
  tlamatini:
    runtime: in-process
    requires_tools: ["acp_doctor", "acp_spawn", "acp_send_and_wait", "acp_relay", "acp_kill"]
    requires_mcps: []
    budget:
      max_iterations: 8
      max_seconds: 180
      max_tokens: 16000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   deny
      db:        deny
    inputs:
      - { name: harness, type: enum, required: true,
          values: ["claude","cursor","codex","gemini","qwen","tlamatini"] }
      - { name: task,    type: string, required: true }
    outputs:
      - { name: session_id,      type: string, required: true }
      - { name: transcript_path, type: string, required: true }
    triggers:
      keywords: ["spawn", "relay", "claude code", "gemini", "acp"]
---

# My ACP Skill

State the goal in one sentence.

## Procedure
1. Call `acp_doctor` first; branch on `details[].resolvable` for `${input.harness}`.
2. `acp_spawn(agent_id="${input.harness}", task="${input.task}")` — capture `session_id`.
3. `acp_send_and_wait(session_id, "...", until_idle_seconds=15, max_wait_seconds=180)`.
4. ALWAYS `acp_kill(session_id)` at the end.
5. Return `{session_id, transcript_path}`.

## Failure handling
- `AGENT_NOT_FOUND` → report the missing CLI, do NOT silently swap harness.
- `PERMISSION_DENIED` → runtime is `deny-all`; report, do not bypass.
```

### 4b. `runtime: acpx` skill (body IS the CLI prompt)

```markdown
---
name: my-cli-prompt
description: Hand a fixed prompt to one external coding-agent CLI and return its answer.
metadata:
  tlamatini:
    runtime: acpx
    acpx_agent: claude          # REQUIRED for runtime=acpx; a registered agent_id
    budget:
      max_iterations: 6
      max_seconds: 300
      max_tokens: 16000
    inputs:
      - { name: repo_path, type: string, required: true }
    outputs:
      - { name: answer, type: string, required: true }
    triggers:
      keywords: ["review my repo", "claude review"]
---

# Repo Reviewer (CLI)

You are reviewing the repository at ${input.repo_path}.
Read the diff, list the top 5 correctness risks, and end with a one-line verdict.
```

> Body authoring rules: keep it a **procedure**, not documentation. The body cap
> is **8 KiB** (linter `[FAIL]` above that). Long playbooks go in
> `references/<file>.md` inside the skill dir and are *referenced* from the body,
> not inlined.

---

## 5 · Validate (mandatory before you call it done)

Two validators ship with the project:

```bash
# Whole-catalog lint — checks: parseable, non-empty body, body <= 8 KiB,
# no duplicate names. Exits non-zero on any failure. This is the gate.
python Tlamatini/agent/skills_pkg/_meta/lint.py

# Single-package quick check — name+description present, file <= 12 KiB.
python Tlamatini/agent/skills_pkg/skill_creator/scripts/quick_validate.py \
    Tlamatini/agent/skills_pkg/<skill_name>
```

A skill that fails to parse is **silently skipped** at load — so "it doesn't show
up in `list_skills`" almost always means a lint failure. Always run the linter.

---

## 6 · Verify discovery & invocation end-to-end

1. Either restart Django (`manage.py runserver --noreload`) **or** use the chat
   navbar **ACPX-Skills ▸ Reload Registry** (re-runs `boot_skills()` — no
   restart) **or** just wait out the 30-second staleness window.
2. In the chat, enable **Multi-Turn + ACPX** (both — `list_skills` / `invoke_skill`
   live on the ACPX tool surface; with ACPX unchecked they're filtered out).
3. Ask: *"List the available skills."* → `list_skills` must include your new
   `name`, `description`, `runtime`.
4. Ask: *"Invoke the `<skill_name>` skill with `<args>`."* → the LLM calls
   `invoke_skill(skill_name, args_json)`; the harness validates inputs against
   your `inputs` contract, runs the body, and returns the envelope/outputs.
5. (Optional) Confirm it's enabled in **ACPX-Skills ▸ Configure Skills** — the
   `Skill.enabled` boolean is the only DB-backed knob. When disabled,
   `list_skills` hides it and `invoke_skill` returns `{"ok": false, "code":
   "SKILL_DISABLED"}` (fails open on DB error).

---

## 7 · What you must NOT do

- **No migration.** Skills are auto-seeded into the `Skill` table by
  `agent/acpx/service.py::boot_skills()` (called from `apps.AgentConfig.ready()`
  on a background thread). You never write a migration for a skill.
- **No `Tool` / `Mcp` row, no checkbox HTML, no JS.** The only DB field the admin
  UI ever writes is `Skill.enabled`; every other column (`description`,
  `runtime`, `acpx_agent`, `frontmatter_json`, `body_sha256`) is owned by
  `boot_skills()` and refreshed from disk on each reload.
- **No `chat_agent_registry.py` / `_EXEC_REPORT_TOOLS` entry.** Those are for
  wrapped chat-agents, a different surface.
- **No edits outside `agent/skills_pkg/<skill_name>/`** (plus its `references/` /
  `scripts/`). If you're touching anything else, you've misclassified the work.

---

## 8 · ACPX-specific gotchas (read if your skill touches ACPX)

- **`list_skills` / `invoke_skill` are ACPX-surface tools.** They are filtered
  out when the toolbar **ACPX** checkbox is off (`agent.acpx.filter_acpx_tools`).
  Your skill is invisible to the planner unless ACPX is enabled — there is no
  separate "skills" toggle on the toolbar; the per-skill `Skill.enabled` flag is
  the orthogonal gate and **both** must allow.
- **`runtime: acpx` `acpx_agent` must be resolvable**, not just spelled right.
  An unresolved CLI surfaces as `AGENT_NOT_FOUND` at spawn — the skill body
  should say so rather than silently swapping harnesses. Confirm with
  `list_acp_agents` / `acp_doctor`.
- **Budget vs ACPX child budget are two different clocks.** The skill's
  `max_seconds` caps the whole `invoke_skill` call; the ACPX child has its own
  `timeout_seconds` / `idle_seconds` / `startup_grace_seconds` from the registry.
  For a slow relay, raise the skill `max_seconds` AND pass longer ACPX budgets in
  the body's `acp_send_and_wait` / `acp_send` calls.
- **`oneshot-prompt` agents (claude / cursor / gemini / qwen / codex) have no
  in-child session memory** — each `acp_send` re-spawns the CLI. If your skill
  needs continuity, carry context forward in the next prompt (or use `acp_relay`
  to hand a transcript from leg A to leg B). See `docs/claude/acpx.md`.
- **Keep the skill body in sync with the ACPX tool names.** A renamed `acp_*`
  tool or a new required arg silently breaks a runbook — the
  `tlamatini_new_acp_agent` / `tlamatini_*` skills are especially sensitive
  because they operate on the ACPX runtime itself.

---

## 9 · Summary checklist

```
[ ] 0. Confirmed a Skill (not a tool/MCP/agent) is the right surface.
[ ] 1. Chose runtime: in-process (orchestrates acp_* tools) vs acpx (body IS the CLI prompt).
       acpx => acpx_agent set to a registered, resolvable agent_id.
[ ] 2. Created Tlamatini/agent/skills_pkg/<skill_name>/SKILL.md
       (kebab-case name == dir leaf; long playbooks in references/).
[ ] 3. Frontmatter: name + description + runtime + budget within schema ranges
       (iter 1-256, sec 1-7200, tokens 1-1e6); requires_tools lists every acp_*/
       chat_agent_* the body calls; declared outputs match what the body returns.
[ ] 4. Body is a PROCEDURE, <= 8 KiB; uses ${input.X} where it references inputs.
[ ] 5. python agent/skills_pkg/_meta/lint.py  => [OK] for the new skill, exit 0.
       (+ quick_validate.py on the package dir.)
[ ] 6. Reloaded (restart OR ACPX-Skills > Reload OR 30s) and verified via
       list_skills + invoke_skill with Multi-Turn + ACPX both enabled.
[ ] 7. NO migration, NO Tool/Mcp row, NO JS/HTML, NO chat_agent_registry entry.
```

---

## Appendix · Files that define the Skill contract (read the source, not just this)

| Path | Role |
|---|---|
| `agent/skills/frontmatter.py` | `parse_skill_md` — the real parser + defaults; only `name` is hard-required; `runtime` enum + `acpx_agent` rule live here |
| `agent/skills/registry.py` | discovery (`rglob SKILL.md`), 30 s staleness cache, frozen-path resolution, `summary()` / `planner_record()` |
| `agent/skills/harness.py` | `SkillHarness` — budget, audit NDJSON, `_run_in_process` (plan envelope) vs `_run_acpx` (spawn child, `${input.X}` render) |
| `agent/skills/io_contract.py` | `validate_inputs` / `validate_outputs` |
| `agent/skills_pkg/_meta/schema.json` | JSON-schema for the frontmatter (budget ranges, network/db enums) |
| `agent/skills_pkg/_meta/lint.py` | catalog linter — body non-empty, ≤ 8 KiB, no dup names |
| `agent/skills_pkg/skill_creator/SKILL.md` | the bootstrap skill (minimal scaffold) + `scripts/quick_validate.py` |
| `agent/acpx/service.py::boot_skills()` | seeds/refreshes `Skill` rows from disk at startup + on Reload |
| `agent/acpx/tools.py` | `list_skills` / `invoke_skill` + `_disabled_skill_names()` enable-gating (fails open) |
| `docs/claude/acpx.md` | the ACPX tool surface + transports the body of an ACPX skill drives |
| `docs/claude/mcp-tools.md` | the short "Skill Workflow" section + ACPX-Skills admin menu |
