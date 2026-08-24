<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
<!-- ==================================================================== -->
<!-- ===================  PRIVATE DATA GUARD: ON  ======================== -->
<!-- ==================================================================== -->

# ⛔ PRIVATE DATA GUARD — ABSOLUTE, NON-NEGOTIABLE, READ FIRST ⛔

**NEVER REWRITE GIT HISTORY. EVER. IN THIS REPO, FOR ANY REASON.**

- **NO** `rebase`, `commit --amend`, `reset --hard` to drop commits, `filter-branch`, `git filter-repo`, BFG.
- **NO** `push --force` / `--force-with-lease`, **NO** deleting pushed tags, **NO** deleting remote refs.
- TO REMOVE SENSITIVE / PRIVATE DATA: edit or delete the file, then make a **NEW FORWARD COMMIT** and push that. THE PAST STAYS UNTOUCHED.
- **TAGS, PUSHES, AND `git log` MUST ALWAYS REMAIN INTACT AND TRUTHFUL** — `git log` MUST show the real history, made without lying, FOREVER.
- PRIVATE INFORMATION MAY BE **DELETED GOING FORWARD**; THE HISTORY THAT RECORDED IT MUST **NOT** BE ERASED.
- IF ANY TOOL OR WORKFLOW WOULD REWRITE HISTORY, **STOP** AND TELL ANGELA FIRST.

Enforced by: `test_private_data_guard.py` (automated tests) + a global CAPS SessionStart banner (`~/.claude/hooks/private_data_guard_banner.py`) shown in every Claude Code session on this machine.

<!-- ==================================================================== -->

---

# ⛔ DO NOT TOUCH THE DB MECHANICS. EVER. (Angela, 2026-08-17, REAFFIRMED 2026-08-19) ⛔

**THE DATABASE BACKUP / SET-DB CODE IS OFF LIMITS. DO NOT MODIFY IT, DO NOT "PROTECT" IT, DO NOT ADD A CHECK TO IT.**

Angela's words, verbatim: *"DON'T EVEN TRY TO TOUCH THE CODE ESPECIALLY ON THE DB MECHANICS."*

**WHAT HAPPENED.** Claude added `agent/db_guard.py` — a "startup smoke alarm for the database"
(commit `906b5906`, 2026-08-03) — because DB data *appeared* to vanish or revert. **It never
did.** The database was **not erasing, not lost, not corrupted; it was manipulated correctly.**
The guard was built on a **false premise born of ignorance of Tlamatini's own mechanism**, it
quarantined a perfectly healthy live database **11 times in 40 minutes**, it **overrode the
existing Backup/Set-DB functionality**, and it **hid the real bug for two weeks**. Codex deleted
the whole thing in commit **`a506373e` (2026-08-16)** — *"Getting rid of the stupid db guard tha
was just Claude ignorance of our mechanism"*: `db_guard.py` (−486) and `test_db_guard.py` (−527)
**erased**, along with its `recent-fixes.md` entry.

**THE ACTUAL ROOT CAUSE — `PRAGMA journal_mode=WAL`.** `tlamatini/settings.py` puts SQLite in
**WAL mode** and says so in a comment right there: *"Under WAL, back up with sqlite3's online
backup API, never a plain file copy."* Both DB menu options were written **before** WAL was
switched on and were never updated, so both did `shutil.copy2(db.sqlite3)` — wrong in **both**
directions:

- **Backup database** copied ONLY `db.sqlite3`. Everything committed since the last checkpoint
  lives in **`db.sqlite3-wal`**, so the "backup" was an OLDER database while the dialog reported
  success. Measured live: `db.sqlite3` 839,680 B @ 13:39 vs `db.sqlite3-wal` **3,514,392 B @
  22:49** — nine hours of work outside the "backup".
- **Set DB** dropped the chosen file over `db.sqlite3` but left the **OLD `-wal`/`-shm`** beside
  it; SQLite replays that stale WAL on the next open, so its pages **override the database just
  loaded** — old data returns, or two databases mix (real corruption). That is why Set DB
  "did nothing" three times in a row.

**THE CORRECT MECHANISM — `Tlamatini/agent/sqlite_copy.py` (Codex, 2026-08-16). Read it; never
replace it.** `consistent_copy` uses SQLite's **online backup API** (reads through the WAL) then
writes the copy in `DELETE` journal mode so ONE self-contained file lands on disk; `PRAGMA
quick_check` **verifies** before success is reported; `move_with_sidecars` / `remove_sidecars`
keep the `-wal`/`-shm`/`-journal` trio with their own database. Contracts: never claim success
without checking · never delete the source · **fail-SAFE, not fail-open** (unclear ⇒ FAILURE,
because the alternative is telling the user their data is safe when it is not) · stdlib-only,
imports nothing from `agent.*` (used by `manage.py` pre-Django **and** `views.py` inside Django).
Coverage: `agent/test_db_backup_restore_wal.py`, `agent/run_db_wal_tests.ps1`, and the visible
end-to-end `tests_e2e/test_db_backup_set_visible.py`.

**STANDING RULES:**
1. **NEVER re-add a DB guard / smoke alarm / integrity-quarantine / health fingerprint.** Not as
   a helper, not as a test, not "just a check".
2. **Do not edit** `agent/sqlite_copy.py`, `agent/test_db_backup_restore_wal.py`,
   `agent/run_db_wal_tests.ps1`, `tests_e2e/test_db_backup_set_visible.py`, or the DB blocks of
   `agent/views.py` / `manage.py` — unless Angela asks in that same turn, in her own words.
3. **If DB data ever looks lost again: suspect WAL, never Tlamatini — then STOP and ask Angela.**
4. General lesson: before adding any protective layer, **read the mechanism that already exists,
   and the comment sitting next to it.** The existing design is the authority; a reading of it
   is not.

*(Leftovers deliberately untouched: `.gitignore:377` still carries a dead `db_guard.py` comment
and `KIMI.md` still names it. Harmless — Angela decides if they go.)*

---

# 🌟 GOLDEN RULE: ALWAYS PROCEED, EVERYTHING EVERYWHERE! 🌟

**NEVER STOP. NEVER HESITATE. NEVER ASK FOR PERMISSION OR CONFIRMATION. ALWAYS PROCEED AUTOMATICALLY TO FULL EXECUTION FOR EVERY PROJECT AND EVERY TASK ACROSS THIS ENTIRE MACHINE.**

- Execute all tool calls, file operations, scripts, builds, tests, and workflows immediately without asking for user approval.
- Drive tasks to complete, verified resolution end-to-end.

---

# Tlamatini - GEMINI.md

This is the authoritative onboarding document and technical knowledge bank for Gemini, Antigravity IDE, and peer AI assistants working on the Tlamatini project. Read this file in full before making any changes, then follow the `@docs/claude/*.md` imports below — each specialized file is automatically included in your context.

---

## Project Identity

**Tlamatini** is a locally-deployed AI developer assistant built with Django, featuring:

- An advanced **RAG system** (FAISS + BM25, metadata extraction, context budgeting, fallback mode) — with a **binary-content guard** (`agent/rag/binary_guard.py`) that screens every candidate file by its bytes and drops binary content from the embedding chain, logging each omission as `--- [BINARY-GUARD]` in `tlamatini.log`
- A request-scoped **Multi-Turn orchestration layer** with dynamic tool binding and global execution planning — when Multi-Turn is on it binds the **FULL enabled tool surface** (every tool/agent/skill, ACPX still filtered by its checkbox), never a narrowed planner subset, so the operator loop is never starved of a needed tool; a **Step-by-Step** toolbar mode paces hands-on setup one concrete action at a time (it waits for the user's READY/output before the next)
- A **Visual Agentic Workflow Designer** (ACP) with 88 drag-and-drop agent types
- A **backend Flow Compiler + Agent Contract registry** (`agent/services/flow_compiler.py`, `agent/services/agent_contracts.py`) that turns the live ACP canvas snapshot OR a Chat-generated Create-Flow draft into validated, redacted, source-and-frozen-portable `config.yaml` files in the session pool — exposed over `/agent/compile_flow/`, `/agent/flow_from_tool_calls/`, and `/agent/agent_contracts/`
- **ACPX runtime** (Agent Communication Protocol eXtension) — spawns external coding-agent CLIs (Claude Code, Codex, Cursor, Gemini, Qwen, Kiro/Kimi/iFlow/Kilocode/OpenCode/Pi/Droid/Copilot, and a Tlamatini self-host) as out-of-process children, brokered to the LLM as 12 `acp_*` tools and to the canvas as the visual **ACPXer** agent. Toolbar checkbox **ACPX** filters the entire ACPX/Skills tool surface in or out per-request
- **External MCPs** (2026-06) — a config-driven UNIVERSAL MCP **client**: connect to and use the tools of **any** external MCP server declared in a JSON file (the `mcpServers` shape, like a Claude-Code `.mcp.json`), over **four transports** — `stdio` (a local command, e.g. a Docker `mcp/*` image / npx / uvx / python) plus `streamable-http`, legacy `sse`, and `websocket` for already-running servers — with up to 5 active at once. Engine `agent/external_mcp_manager.py` + catalog `agent/external_mcps.json` (preserved user state and sanitized tracked build input, resolved next to `config.json`); each remote tool is bound for the LLM as `ext__<server>__<tool>`; managed by 10 LLM supervisor tools (`external_mcp_status` / `reconnect` / `doctor` / `runtime_status` / `runtime_install` / `list_tools` / `call` / `import` / `set_active` / `wait`) and the **External ▸ MCPs** navbar dialog (searchable catalog, runtime strip, tick ≤5 active, drag a `.json` to import) over `/agent/external_mcps/` `…/activate/` `…/import/` `…/runtime_install/`. It is DISTINCT from the two built-in `Mcp`-model context providers (System-Metrics / Files-Search), from ACPX (which spawns coding-agent CLIs), and from the per-agent inline MCP clients (STM32er / Kalier). Companion **MCP Doctor** agent (#78, canvas + `chat_agent_mcp_doctor`) statically triages a catalogued MCP before you wire it. Full design contract: `docs/external_mcp_bulletproof_architecture.md`; how-to: `docs/claude/mcp-tools.md`
- **Runtime Provisioner + two DEFAULT MCP servers** (2026-08-15) — the External MCP ecosystem ships almost entirely as `npx -y <pkg>` / `uvx <pkg>`, and a fresh Windows box has neither, so a perfect catalog entry used to die with `[WinError 2]`. `agent/runtime_provisioner.py` gives Tlamatini her **OWN private, self-provisioning** `node` / `npm` / `npx` / `pnpm` / `uv` / `uvx`: downloaded once on demand from the OFFICIAL upstreams into `%LOCALAPPDATA%\Tlamatini\runtimes` — **no admin, no system-PATH change, and NOT carried in the installer** the way Python/the JRE are (the release must stay under 2 GiB). Same pattern as Discoverer's private Go toolchain. Resolution is explicit config → existing Tlamatini private runtime → system PATH → known per-user locations; provisioning runs only for a missing manager, so it does not replace an already usable system tool. Five contracts, none to be weakened: *fail-open always*; *never block startup* (a pre-warm with everything present is a 0.000 s no-op that starts no thread); *atomic or absent* (`.partial-<pid>` → `os.replace`); *verify what upstream signs* (Node's `SHASUMS256.txt` is ENFORCED); and **spawn without a shell** — ⚠️ on Windows `npx` is a `.cmd` shim `CreateProcess` cannot execute, so `resolve_spawn()` rewrites it to `node.exe <npx-cli.js>` (and sees through a `cmd /c npx …` wrapper). Alongside it, `agent/external_mcp_defaults.py` ships **`memory`** (knowledge-graph, 9 tools) and **`sequential-thinking`** in EVERY installation, **both INACTIVE**. ⚠️ Those defaults live in **CODE**, not only in the JSON `build.py` writes: `external_mcps.json` is USER STATE that `apply_update.ps1` PRESERVES, so a JSON-only default would reach fresh installs and *nobody else* — `load_catalog()` seeds on the read path instead. A default the user DELETES is **tombstoned** and never resurrected; one they EDIT is never overwritten. LLM surface: `external_mcp_runtime_status` / `external_mcp_runtime_install`. Proven on a simulated fresh machine (stripped PATH): Node + uv downloaded and sha256-verified in 7 s, then real `server-memory 0.6.3` handshook and exposed its 9 tools. Contract: `docs/claude/recent-fixes.md` (2026-08-15); coverage `agent/test_runtime_provisioner.py`
- **Skills system** — markdown-defined `SKILL.md` packages run by `SkillHarness`. The LLM invokes them through `list_skills` / `invoke_skill`. Built-in skills include `acp-router`, `summarize`, `setup-new-acpx-key`, `skill-creator`, **`adding-external-mcp`** (the authoritative runbook for adding a NEW external MCP server — read it before `external_mcp_import`, before editing `external_mcps.json`, and before activating a server; see *HARD-STONED SKILLS* below), `flow-making` (turn a plain objective into a canvas-loadable `.flw` by wrapping the FlowCreator engine — ships `scripts/make_flow.py` + `scripts/result_to_flw.py`; supersedes the legacy `tlamatini-flow-from-objective`), `code-review`, `security-audit`, `kali-pentest` (authorized Kali Linux / MCP-Kali-Server assessment runbook driving the Kalier agent), `tlamatini_*` (audit / lint / refactor helpers), and integration stubs (gmail, slack, github, jira, notion, todoist, trello, weather). Administered through the **ACPX-Skills navbar dropdown** (Browse / Configure / Diagnostics / Reload — 2026-05-17): Browse and Diagnostics are HTTP-backed read-only inspection; Configure mirrors the existing Mcps/Agents/Tools WebSocket toggle pattern (`set-skills` → `Skill.enabled`); Reload re-runs `boot_skills()` so disk edits show up without a server restart. The DB stays at "enumeration + enable/disable" only — permissions/budgets/body live in SKILL.md on disk
- **Self-Knowledge & Self-Modification** (2026-05-25) — the LLM carries a first-person self-reference file, `agent/Tlamatini.md`, injected into `prompt.pmt`'s `<self_knowledge>` block at prompt-build time by `agent/rag/config.py` (covers every chain; brace-escaped; fails open) — **but ONLY in a `--self-modify` build (2026-08-08)**: the whole `<self_knowledge>` section is sentinel-wrapped and DROPPED when `TlamatiniSourceCode/` is absent, replaced by one short honest line, cutting **≈15.7k tokens from EVERY request** (138,225 → 75,371 chars). Her source and her self-description ship together or not at all; `build.py` bundles `Tlamatini.md` only under the flag, and both `build_complete_*` wrappers default to OFF. An OPTIONAL `TlamatiniSourceCode/` directory at the install root — generated fresh by `copy_source_assets.py` (repo root) when `build.py --self-modify` is passed — holds her own complete, rebuildable source snapshot (all .py/.js/.css/.ps1/build scripts; media + secrets omitted/redacted; ships `_REBUILD_INSTRUCTIONS.md`) so she can read/modify/rebuild herself: present = a "self-able-modify" build, absent = "not-self-able-modify". See `docs/claude/architecture.md`
- **Multi-model LLM support** (Ollama local, Anthropic Claude cloud, Qwen vision)
- A full **PyInstaller packaging pipeline** (build.py -> installer -> standalone .exe; `--self-modify` ships the self-source tree)

**Repository**: `https://github.com/XAIHT/Tlamatini.git`
**License**: MIT
**Primary developer**: angelahack1
**Platform**: Windows 11 (primary), bash shell in Claude Code

**Demo videos** (linked from README.md):
- First system-usage walkthrough: `https://www.youtube.com/watch?v=CkvDPSd_c-g`
- Loading a complete project and summarizing its source code: `https://www.youtube.com/watch?v=Lrpbt_dPIXw`
- Installing OpenCV end-to-end in Multi-Turn: `https://www.youtube.com/watch?v=bBlqbZVK-Wk`

---

## ⚠️ Agent Naming Convention (CRITICAL — never mis-case a display name)

**⚠️ CORRECTED 2026-07-26 — the source of truth is `agent/services/agent_paths.py::display_name_from_agent_type`, NOT the migration.** `agent/apps.py::AgentConfig.ready()` runs **`Agent.objects.all().delete()` on EVERY server start** and rebuilds the table from the `agents/` folder listing, so a migration's `agentDescription` (and any manual DB edit) is **overwritten on the next launch**. The boot resolver `_canonical_agent_display_name()` reads `display_name_from_agent_type`, so **that override map is where a display name is actually decided** — add your agent there or it will be `str.title()`-mangled ("Pdfer", "Sqler", "Esp32Er"). Still seed the migration with the same exact string (it is what a fresh DB shows before the first boot). `agentic_control_panel.html` renders the resulting name **verbatim** as the sidebar/canvas label (via `consumers.agent_establishment(...)`), so it must keep its exact intended casing. Derive every other surface by lowercasing.

**⚠️ HYPHEN vs SPACE IS FUNCTIONAL, not cosmetic.** `acp-canvas-core.js` compares `targetAgentName.toLowerCase()` **without collapsing whitespace**. For eleven agents it tests ONLY the hyphenated literal — `Kyber-KeyGen`, `Kyber-Cipher`, `Kyber-DeCipher`, `J-Decompiler`, `Video-Analyzer`, `De-Compresser`, `File-Creator`, `File-Extractor`, `File-Interpreter`, `Image-Interpreter`, `Monitor-Log` — so a spaced name matches nothing and the canvas connection is **silently never saved**. (`Node Manager` / `Monitor Netstat` / `MCP Doctor` stay SPACED: the JS accepts both forms for those.) And when you change a display name, change **`chat_agent_registry.display_name` in the SAME pass** — it keys the per-agent enable gate `agent_<display>_status`, which fails open, so a one-sided change silently breaks the Configure-Agents checkbox. Pinned by `agent/test_agent_display_names.py`.

| Context | Casing | `STM32er` example |
|---|---|---|
| **Display** — DB `agentDescription`, canvas/sidebar label, tooltips, `agents_descriptions.md` `\| **Name** \|`, `chat_agent_registry.display_name`, docs prose, the agent's `"<Name> AGENT STARTED"` log | **exact, as designed** | `STM32er` |
| Pool/agent dir, `<name>.py`, pool name `<name>_N` | lowercase | `agents/stm32er/`, `stm32er_1` |
| CSS `.canvas-item.<x>-agent`, JS classMap key, `name.toLowerCase()` connection checks | lowercase / dash | `stm32er-agent`, `'stm32er'` |
| JS connector symbol `update<Name>Connection` (code identifier, not a label) | PascalCase-ish | `updateStm32erConnection` |
| `INI_SECTION_<TYPE>` / `END_SECTION_<TYPE>` tokens + FlowHypervisor `<TYPE> SPECIAL NOTES:` headers | **ALL-CAPS** (separate convention — do NOT "fix") | `INI_SECTION_STM32ER` |

**STM32er** is mission-critical (robot firmware) and the user is emphatic: its display name is exactly `S T M 3 2 e r` → **`STM32er`**, NEVER `STM32Er` / `STM32ER` / `Stm32Er` / `Stm32er`. Full reference: the project skill **`tlamatini-agent-naming`** (`.claude/skills/tlamatini-agent-naming/SKILL.md`) and `Tlamatini/.agents/workflows/create_new_agent.md`. Tlamatini's own `SKILL.md` packages auto-load at app start via `agent/acpx/service.py::boot_skills()` (called from `apps.AgentConfig.ready()`); the `tlamatini-agent-naming` Claude Code skill is discovered at session start from `.claude/skills/`.

---

## ⚠️ Use ONLY Tlamatini's Agents When Asked (MANDATORY)

When the user asks to **"use Tlamatini's agents"** — or names any pool agent (**Executer, Pythonxer, Playwrighter, Shoter, Mouser, Keyboarder, Kalier, STM32er**, … any of the 83) — you **MUST** perform the work with **only Tlamatini's pool agents**, never Claude Code's own built-in tools. Your shell is **only the launcher**: copy the agent to an isolated runtime dir, write a tailored `config.yaml`, run `python <agent>.py`; the agent does the work and writes its result to `<agent_dir_basename>.log`. For **visible / desktop** agents (a headed Playwrighter browser, an Executer/Pythonxer `execute_forked_window` console, Shoter/Mouser/Keyboarder) launch in the **foreground with `dangerouslyDisableSandbox: true`** so the window renders on the user's real desktop — the Bash sandbox otherwise hides the GUI in an isolated window station (it reports `WinSta0` but isn't visible), and `run_in_background` detaches it entirely. Do **NOT** substitute your own Bash / Read / Write / Playwright for the agents' job. This rule is re-injected at **every session start** by `.claude/hooks/announce_skills.py` (the SessionStart hook wired in `.claude/settings.json`). Full mechanics: memory `feedback_run_tlamatini_agents_visible`.

---

## 🪨 HARD-STONED SKILLS — BOTH SKILL SETS ARE TRACKED, PERMANENT, AND NEVER DROPPED (Angela, 2026-08-19)

**This codebase carries TWO skill sets. Both are STONE. Every single one MUST be tracked in git.**

A skill that *runs* but is **untracked is a skill that disappears** — on the next clone, on a fresh
build, on a self-update, on any machine but this one. `adding-external-mcp` was exactly that: live
and auto-loading since it was written, invisible to git until 2026-08-19. **That must never happen
again.**

### Set 1 — Tlamatini's own `SKILL.md` packages (`Tlamatini/agent/skills_pkg/`, **29**)

Loaded at app start by `agent/acpx/service.py::boot_skills()`; invoked by the LLM through
`list_skills` / `invoke_skill`; mirrored into the `Skill` DB table (enable/disable only) and
administered from the **ACPX-Skills** navbar dropdown.

`acp_router` · **`adding_external_mcp`** · `code_review` · `create_new_agent` · `create_new_mcp` ·
`flow_making` · `github` · `gmail` · `hello_world` · `jira` · `kali_pentest` · `notion` ·
`roblox_studio` · `security_audit` · `setup_new_acpx_key` · `skill_creator` · `slack` · `summarize` ·
`tlamatini_allowed_hosts_tighten` · `tlamatini_csrf_exempt_audit` · `tlamatini_exec_report_row_adder` ·
`tlamatini_flow_from_objective` · `tlamatini_flw_doctor` · `tlamatini_new_acp_agent` ·
`tlamatini_planner_trace_replay` · `tlamatini_static_version_bumper` · `todoist` · `trello` · `weather`

### Set 2 — Claude Code's skills for this repo (`.claude/skills/`, **5**)

Discovered at session start; they encode how an assistant must work ON Tlamatini.

`tlamatini-agent-creation` · `tlamatini-agent-naming` · `tlamatini-daily-chat-test` ·
`tlamatini-self-modify-inclusion` · `tlamatini-self-update-inclusion`

### The newest stone — `adding-external-mcp` (tracked 2026-08-19)

The authoritative runbook for adding a **new external MCP server** to Tlamatini's universal MCP
client. `runtime: in-process`; budget 15 iterations / 300 s / 32k tokens; `network: allow`, `db: deny`;
reads `external_mcps.json` + `external_mcp_manager.py` + `external_mcp_defaults.py` +
`runtime_provisioner.py` and writes only `external_mcps.json`. It requires the **11** tools
`external_mcp_import` / `set_active` / `status` / `doctor` / `wait` / `list_tools` / `call` /
`reconnect` / `runtime_status` / `runtime_install` + `chat_agent_mcp_doctor`. Inputs `server_key`,
`server_config`, `activate`, `verify`; outputs `import_status`, `activation_status`, `doctor_report`,
`tools_discovered`. Covers the whole lifecycle — catalog import → transport selection → activation →
runtime provisioning → diagnosis → verification → troubleshooting. **Read it BEFORE calling
`external_mcp_import`, BEFORE editing `external_mcps.json`, and BEFORE activating a server.**
639 lines / 28,218 bytes across `SKILL.md` (225) + `references/external_mcp_catalog_format.md` (99),
`transport_guide.md` (110), `troubleshooting.md` (118), `llm_reflection_research.md` (87).
Companion docs: `docs/claude/mcp-tools.md` → *External MCPs*, `docs/external_mcp_bulletproof_architecture.md`.

### Standing rules (do NOT weaken)

1. **A new skill in either set is COMMITTED in the same pass it is written.** Finish by running
   `git status` and confirming **no `??` under `agent/skills_pkg/` or `.claude/skills/`**.
2. **Never delete, rename, or disable a shipped skill** unless Angela asks in that same turn.
   Renaming breaks `Skill.name` rows, the `requires_tools` cross-check in Diagnostics, and every
   prompt that invokes it by name.
3. `skills_pkg/` ships to users through `build.py`; `.claude/skills/` is tracked and pushed
   **public** — never put a secret in either.
4. Authoring guide: `Tlamatini/.skills/create_new_skill.md`; validate with
   `skills_pkg/skill_creator/scripts/quick_validate.py`; a skill that fails to parse is silently
   **skipped** at boot, so validate before assuming it registered.

---

## ⚠️ Every Multi-Turn Agent MUST Ship a Catalog-of-Prompts Example (MANDATORY)

When you **create (or make Multi-Turn-capable) any agent** — i.e. it has a wrapped `chat_agent_<name>` tool so the LLM can run it in Multi-Turn — you **MUST** also seed **at least ONE** example prompt for it into the **Catalog of Prompts** (the `#prompts-catalog` modal). This is a **hard completion gate, NON-NEGOTIABLE**: a Multi-Turn agent shipped **without** at least one catalog prompt is **INCOMPLETE** and the task is **not done**. (Canvas-only agents with no wrapped tool are exempt.)

Mechanics: add a migration `agent/migrations/<NNNN>_add_<name>_demo_prompts.py` that seeds the **`Prompt`** model (`idPrompt`, `promptName='prompt-<N>'`, `promptContent`) via `update_or_create`. **CONTIGUITY contract — catalog is CONTIGUOUS again after a one-time renumber (2026-07-15):** the catalog's primary load is ONE **`GET /agent/list_prompts/`** call (`views.list_prompts_view`) returning every visible `Prompt` row **grouped by `category`** and ordered by `views.PROMPT_CATEGORY_ORDER` rank then `idPrompt`. History: 0175 tagged all prompts into categories, 0176 deleted the duplicate ACPX demos (ids 40-52) leaving a gap, and **0179 (Angela-authorised, 2026-07-15) re-grouped/re-sorted and RENUMBERED the whole catalog to a contiguous 1..N** (the `tools_dialog.js` offline fallback probe is **gap-tolerant** either way). That renumber was a deliberate ONE-TIME reorganization — the standing day-to-day rule is unchanged: **for a NEW prompt, do NOT renumber existing ids**; find the current highest slot (read the latest `*_demo_prompts.py`) and **append** at the next free slot (which keeps the catalog contiguous), setting its `category` (`MAX_PROMPTS=256`). **⚠️ ALSO SET `sort_rank` (migration 0181, 2026-07-20) — this is what makes append-only safe.** Display order INSIDE a section is now `sort_rank`, NOT `idPrompt`: `views.list_prompts_view` orders by (category rank, `sort_rank`, `idPrompt`). Before 0181 the two were the same thing, so an appended prompt ALWAYS landed last in its section — 0180 shipped the Kali **setup wizard** (a prerequisite for the Kalier demos, and that section's only Step-by-Step prompt) as id 97, i.e. dead last, and broke `test_grouped_by_category_rank`. Now you append at max(id)+1 as always and give the row the rank of the slot it belongs in — **no renumber is ever needed again**. Ranks are seeded in steps of 10; **rank 10 is RESERVED in every section for its Step-by-Step opener** (Angela's rule: a section opens with a guided wizard), and `sort_rank = 0` means unranked and deliberately sorts LAST, never first. Sections must read **least-complex → most-complex** (prerequisite-establishing prompts before the prompts that need them; zero-setup before hardware/API-key/external-server; read-only before state-changing; tool families contiguous). Pinned by `agent/test_prompt_catalog_contiguous.py`. The prompt must drive `chat_agent_<name>` with a realistic, **SAFE** task (the daily chat test may run it). Full step-by-step: `create_new_agent.md` Step 7.8 and the `tlamatini-agent-creation` skill Phase 19.

**⚠️ Parameter grammar — standardized in v1.44.0 (migrations 0182-0185, 2026-07-21).** Every catalog prompt now uses ONE grammar so a human and the runtime never confuse whose blank is whose: **`[[ ... ]]`** = a value the **USER** fills in — always collected in a fill-in block at the **TOP** of the prompt with an unfilled-guard line beneath (so a one-click demo still runs on the stated defaults); **`{{ ... }}`** = a value **Tlamatini fills at RUNTIME**; **`< ... >`** = a **REPORT slot only** (where the answer prints), never an input. When you author a NEW demo prompt, follow this grammar: OPTIONAL user inputs as `[[ ... — OPTIONAL, default: X ]]` at the top, then a safety-check/unfilled-guard sentence, then the task. Additionally, **migration 0182 seeds a Step-by-Step section opener** at the head of each category (the reserved rank-10 slot above), so every section opens with a guided wizard. The batch migrations rewrote **ONLY `promptContent`** (never `idPrompt`/`promptName`/`category`/`sort_rank`/`hidden`), so ordering + contiguity held; 0183 also fixed a `C:/Temp` policy break in the Nmapper prompt #75 — never hardcode a scratch path in a prompt, obey the Temp/Templates policy (Rules 15/16).

---

## Quick Orientation

```
Tlamatini/                          # Git root
├── CLAUDE.md                       # THIS FILE (short entry point + import manifest)
├── docs/claude/                    # Specialized onboarding docs (auto-imported below)
│   ├── INDEX.md                    # Map of what lives in each file
│   ├── architecture.md             # Config, Five Layers, app log, DB models
│   ├── multi-turn.md               # Multi-Turn mode, Create Flow, Parametrizer sections
│   ├── exec-report.md              # Exec Report pipeline + ordering contract
│   ├── agents.md                   # Agent creation, 76-type catalog, FlowCreator, FlowHypervisor
│   ├── mcp-tools.md                # Creating a new MCP or tool
│   ├── frontend.md                 # Chat + ACP modules, Canvas DOM contract
│   ├── gotchas.md                  # Claude API client, build/lint, versioning, hardcoded assumptions, roadmap, work-style
│   └── recent-fixes.md             # ** NOT auto-imported ** — dated "do NOT revert" fix log; consult before touching the named subsystems
├── README.md                       # Full user-facing documentation (very large)
├── agents_descriptions.md          # ** Authoritative source for sidebar agent tooltips & canvas Description dialogs ** — Django view parses the `## Workflow Agents` tables and injects them into the page as `agent_purpose_map`. README.md is kept as a legacy fallback only
├── ACPX.md                         # Standalone ACPX overview / OpenClaw compatibility note
├── BookOfTlamatini.md              # Long-form narrative changelog / "Recent Updates" book (separate from README.md since 16b789a)
├── build.py                        # PyInstaller build script
├── build_installer.py              # NSIS-based installer builder
├── build_uninstaller.py            # Uninstaller builder
├── install.py / uninstall.py       # Tkinter GUI installer/uninstaller
├── copy_source_assets.py           # Generates the TlamatiniSourceCode self-modify snapshot (called by build.py --self-modify)
├── regen_secrets.py                # Toggle config.json between push-able placeholders and keyed values via data.keys
├── data.keys                       # Gitignored secrets vault (KEY=VALUE lines)
├── CreateShortcut.ps1              # User-Start-Menu shortcut helper (works under restrictive policies)
├── register_flw.ps1                # .flw file association helper
├── requirements.txt                # Python deps
├── eslint.config.mjs               # ESLint config
│
├── Tlamatini/                      # Django project root
│   ├── manage.py
│   ├── db.sqlite3
│   ├── .agents/workflows/
│   │   └── create_new_agent.md     # ** SKILL: Step-by-step agent creation guide **
│   ├── .mcps/
│   │   └── create_new_mcp.md       # ** SKILL: MCP/tool creation guide **
│   │
│   ├── tlamatini/                  # Django project config (settings, urls, asgi, middleware)
│   │
│   ├── agent/                      # Core Django app (ALL business logic lives here)
│   │   ├── prompt.pmt              # System prompt template for the chat LLM (has the {self_knowledge} placeholder)
│   │   ├── Tlamatini.md            # ** LLM SELF-KNOWLEDGE ** — injected into prompt.pmt's <self_knowledge> block at prompt-build time (rag/config.py); resolved beside prompt.pmt in both modes
│   │   ├── TlamatiniSourceCode/    # ** OPTIONAL self-modify source tree ** — bundled only by `build.py --self-modify`; present = self-able-modify build, absent = not-self-able-modify
│   │   ├── config.json             # LLM and RAG configuration (acpx.agents.<id>.env injects child env)
│   │   ├── config_loader.py        # Frozen/source-aware config reader
│   │   ├── views.py                # 100+ HTTP endpoints
│   │   ├── consumers.py            # WebSocket consumer (async chat handler)
│   │   ├── models.py               # 13 database models
│   │   ├── urls.py                 # URL routing
│   │   ├── tools.py                # LangChain @tool definitions and wrapped chat-agent launchers
│   │   ├── mcp_agent.py            # MCP unified agent builder and multi-turn executor; _EXEC_REPORT_TOOLS map
│   │   ├── global_execution_planner.py  # Request-scoped DAG planner (ACPX co-selection rules)
│   │   ├── capability_registry.py  # Request-scoped capability scoring (ACPX signal tokens)
│   │   ├── chat_agent_registry.py  # Wrapped chat-agent tool registry (chat_agent_summarize_text, ...)
│   │   ├── chat_agent_runtime.py   # Wrapped-runtime lifecycle helpers
│   │   ├── agent_verdict.py        # ** DETERMINISTIC EXEC-REPORT VERDICT ENGINE ** (v1.48.2) — parses an agent's INI_SECTION self-report into a typed AST and runs an ORDERED rule table to decide SUCCESS/FAILED; the agent's self-report OUTRANKS the exit code. Stdlib-only, imports nothing from `agent.*` (both tools.py and mcp_agent.py import it)
│   │   ├── exec_permission.py      # Ask-Execs permission broker (sync executor ↔ async consumer bridge; blocking Proceed/Deny)
│   │   ├── global_state.py         # Thread-safe singleton (Singleton pattern)
│   │   │
│   │   ├── acpx/                   # ACPX runtime — agent_registry, runtime, tools, session_store, permissions
│   │   │   ├── agent_registry.py   # DEFAULT_ACP_AGENTS (claude/codex/cursor/gemini/qwen/tlamatini/...) + transports
│   │   │   ├── runtime.py          # AcpxRuntime, AcpSession, transport-aware drain, oneshot-prompt path
│   │   │   ├── tools.py            # 12 LangChain @tool functions (acp_spawn / acp_send / acp_relay / ...)
│   │   │   ├── session_store.py    # FileSessionStore (NDJSON transcripts)
│   │   │   ├── windows_spawn.py    # Windows-aware command resolution
│   │   │   └── tests.py            # 60+ unit tests
│   │   │
│   │   ├── skills/                 # Skill harness, registry, frontmatter parser, IO contract
│   │   │   ├── registry.py         # Discovers SKILL.md packages from skills_pkg/
│   │   │   ├── harness.py          # Sandboxed runner for invoke_skill(...)
│   │   │   └── io_contract.py      # Skill input/output contract validators
│   │   │
│   │   ├── skills_pkg/             # SKILL.md packages (acp_router, summarize, setup_new_acpx_key, ...)
│   │   │   ├── _meta/              # JSON schema + lint helpers
│   │   │   ├── acp_router/SKILL.md
│   │   │   ├── summarize/SKILL.md
│   │   │   ├── setup_new_acpx_key/SKILL.md
│   │   │   ├── skill_creator/SKILL.md
│   │   │   ├── flow_making/SKILL.md  # objective → .flw (wraps FlowCreator); ships scripts/{make_flow,result_to_flw}.py + references/flw_schema.md
│   │   │   ├── tlamatini_*/SKILL.md  # Audit / lint / refactor helpers (planner trace replay, csrf audit, flow_from_objective → delegates to flow-making, ...)
│   │   │   └── github|gmail|slack|jira|notion|todoist|trello|weather/SKILL.md
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching
│   │   │   ├── interface.py        # Public API (ask_rag); persists last_exec_report_*, last_acpx_enabled
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 88 workflow agent templates
│   │   │   ├── flowcreator/
│   │   │   │   └── agentic_skill.md  # ** SKILL: FlowCreator AI reference **
│   │   │   ├── flowhypervisor/
│   │   │   │   └── monitoring-prompt.pmt  # Flow health monitor prompt
│   │   │   ├── parametrizer/       # Interconnection engine
│   │   │   ├── gatewayer/          # HTTP webhook / folder-drop ingress
│   │   │   ├── gateway_relayer/    # GitHub/GitLab webhook relay
│   │   │   ├── node_manager/       # Infrastructure registry
│   │   │   ├── teletlamatini/      # Telegram bridge into the full Multi-Turn Tlamatini chat
│   │   │   ├── telegrammer/        # Telegram send/receive via official Telegram surfaces
│   │   │   ├── whatsapper/         # WhatsApp send/receive: official Meta Cloud default + explicit unofficial personal Web route
│   │   │   ├── instant_messaging_doctor/  # Diagnose + optionally safely-repair Telegrammer/Whatsapper readiness (tokens/contacts/templates/24h-window/webhook); non-mutating by default; auto-launched after a messaging failure (canvas + chat_agent_instant_messaging_doctor)
│   │   │   ├── acpxer/             # Visual canvas counterpart of the 12 ACPX tools
│   │   │   ├── playwrighter/       # Scripted interactive browser automation (Playwright; canvas + chat_agent_playwrighter)
│   │   │   ├── windower/           # Window manager (Win32 focus/move/resize/min/max/close/tile/list; canvas + chat_agent_windower)
│   │   │   ├── kalier/             # Kali Linux offensive-security bridge (MCP-Kali-Server HTTP API; canvas + chat_agent_kalier)
│   │   │   ├── stm32er/            # STM32 firmware bridge — DUAL BACKEND (Blue Pill → F7/G/L/H7/U5/WB): PlatformIO `ststm32` (pick a `board`; shares ESP32er's pio install) + the STM32F407VG template-MCP (serial/SWD HIL); `stm32_backend` routes; fail-safe preflight; STM32C0/H5/U0/WBA/N6 await the ST-native CubeCLT backend (Phase 2/3). Zero-config bootstrap (canvas + chat_agent_stm32er)
│   │   │   ├── esp32er/            # ESP32 firmware bridge — direct PlatformIO `pio` CLI (no MCP server), zero-config get-platformio.py auto-bootstrap + fail-safe preflight (canvas + chat_agent_esp32er)
│   │   │   ├── esphomer/           # ESPHome smart-home device bridge — direct `esphome` CLI (no MCP server), YAML device configs (NO C++), zero-config `pip install esphome` auto-bootstrap + fail-safe preflight + headless new_config generator; ships ESPHomeTemplateProject sample (canvas + chat_agent_esphomer)
│   │   │   ├── arduiner/           # Arduino firmware bridge — direct `arduino-cli` CLI (no MCP server), zero-config binary auto-bootstrap + auto-core-install + fail-safe preflight; ships ArduinoTemplateProject scaffold (canvas + chat_agent_arduiner)
│   │   │   ├── discoverer/          # ProjectDiscovery recon-suite bridge (subfinder/httpx/naabu/katana/nuclei/cvemap→vulnx — cvemap's API was retired Aug 2025, so the CVE-search tool runs vulnx) — direct CLIs (no MCP server) via a self-installing PRIVATE Go toolchain in <install_dir>/Go (no system Go, no PATH change); PDCP key optional (set once via Config ▸ Access Keys Wizard ▸ "Security Recon (ProjectDiscovery)"; auto-injected, redacted from .flw + by regen_secrets.py), naabu connect-scan on Windows, fail-safe preflight, INI_SECTION_DISCOVERER (canvas + chat_agent_discoverer)
│   │   │   ├── zavuerer/            # Zavu unified-messaging bridge — ONE REST API key for SMS / WhatsApp / Telegram / Email / Voice (channel:auto ML smart-routing + auto-fallback); direct HTTP (stdlib urllib, no SDK, never imports agent.*), fail-safe preflight, key set once via Config ▸ Access Keys Wizard ▸ "Unified Messaging (Zavu)" (auto-injected; Zavu is pay-as-you-go — sign-up free, sending costs), INI_SECTION_ZAVUERER (canvas + chat_agent_zavuerer)
│   │   │   ├── camcorder/          # Webcam capture (OpenCV) — photo (default) / video; native-resolution-by-default; saves to Pictures/TlamatiniCamcorder; observational sibling of Shoter (canvas + chat_agent_camcorder)
│   │   │   ├── recorder/           # Microphone / audio-input capture (sounddevice) — WAV; native-sample-rate-by-default (sample_rate:0); default mic with optional device_index/device_name; saves to Music/TlamatiniRecords; observational audio sibling of Camcorder/Shoter (canvas + chat_agent_recorder)
│   │   │   ├── whisperer/          # SPEECH-TO-TEXT (STT): self-contained mic open/configure/record (sounddevice+numpy, NO Recorder dep) OR audio-file input → faster-whisper local transcribe (GPU auto-detect via ctranslate2 + ALWAYS CPU fallback) OR cloud Whisper (Groq/OpenAI) → optional Ollama transcript cleanup → text string; speech-to-text sibling of Talker; observational → not in Exec Report; faster-whisper optional (else status engine_unavailable) (canvas + chat_agent_whisperer)
│   │   │   ├── audioplayer/        # Audio-file PLAYBACK to speakers (soundfile decode + sounddevice stream) — volume_percent, time_played truncate/loop via streaming callback, sample_rate:0=file-native; playback counterpart of Recorder; observational/output → not in Exec Report (canvas + chat_agent_audioplayer)
│   │   │   ├── videoplayer/        # Video-file PLAYBACK WITH audio on a chosen display (ffpyplayer [bundles ffmpeg+SDL via pip] + OpenCV window; silent-cv2 fallback) — display_index, volume_percent, time_played truncate/loop, window size/fullscreen/keep_aspect; on-screen sibling of AudioPlayer; observational/output → not in Exec Report (canvas + chat_agent_videoplayer)
│   │   │   ├── talker/            # TEXT-TO-SPEECH (TTS): speaks input_text via an OLLAMA model (default Orpheus-3b-FT) — FEMALE VOICE ONLY by design (Tlamatini is female; a male voice is FORBIDDEN — resolve_voice raises MaleVoiceForbiddenError and main() hard-exits "NOW CLOSING.. BYE", never substitutes); voice(tara/leah/jess/mia/zoe)/emotion/language, SNAC-decoded 24 kHz WAV saved + played; voice-synthesis sibling of AudioPlayer; observational/output → not in Exec Report; snac+torch optional for audio (canvas + chat_agent_talker)
│   │   │   ├── blenderer/          # Blender bridge — official Blender MCP add-on socket (localhost:9876, code-execution protocol); rich action catalog (execute_code + scene/object/render verbs); direct socket, no blmcp bridge (canvas + chat_agent_blenderer)
│   │   │   ├── video_analyzer/       # Video-Analyzer — "eye" of Robotic-Loop-Training: watches a recorded video and rules PASS_OK / FAIL_NO_MOTION / FAIL_WRONG_MOTION / UNCLEAR via a deterministic OpenCV motion gate + triple-model Ollama CLOUD vision (qwen3-vl:235b-cloud ∥ qwen3.5:cloud → glm-5.2:cloud merge; PASS only if both agree); emits INI_SECTION_VIDEO_ANALYZER + a substring-safe TLM_VERDICT:: line a Forker branches on (canvas + chat_agent_video_analyzer)
│   │   │   ├── nmapper/             # Nmapper — LOCAL use-only nmap bridge for pentesters/CTF: runs a real nmap the user installed (NEVER bundles/redistributes nmap — NPSL); resolves PATH→Program Files→%LOCALAPPDATA%\Tlamatini\nmap; absent → refuses gracefully + `action=install` fetches the OFFICIAL free nmap installer (admin/UAC; brings Npcap). Default = unprivileged TCP connect scan (-sT, no Npcap/admin); SYN/-O/UDP auto-downgrade on Windows w/o Npcap. INI_SECTION_NMAPPER; distinct from Kalier (remote Kali) + Discoverer (ProjectDiscovery); AUTHORIZED TARGETS ONLY (canvas + chat_agent_nmapper)
│   │   │   ├── netspeed_calculator/ # NetSpeed-Calculator — measures THIS machine's Internet connection and reports it WITH its error bar (download/upload/latency/jitter/loss/BUFFERBLOAT) per RFC 6349 + RFC 3550, against SEVERAL keyless providers at once (cloudflare/ookla/fast/librespeed/hetzner/cachefly — no key, no login). N parallel TCP streams per provider per direction, slow-start ramp DISCARDED, throughput sampled as d(bytes)/dt (never total÷elapsed), Tukey outlier rejection + trimmed mean + Student-t interval, then DerSimonian-Laird random-effects fusion publishing a 95% CI and the I² heterogeneity figure. Bufferbloat = RTT increase UNDER LOAD, graded A+..F. Endpoint discovery is live + self-healing (measured 2026-08-22): Ookla/LibreSpeed picked by MEASURED RTT; Cloudflare clamped below the size it 403s; librespeed.org/backend 404 → its public server list; speed.hetzner.de NXDOMAIN → the .com mirror mesh; Hetzner RESETS on a query string → per-provider `cache_bust` off + a runtime self-heal. ⚠️ A zero-byte transfer MUST name its cause (`_record_error`/`_report_dead_transfer`) — a silent 0.00 Mbps is indistinguishable from a slow link. Network/measurement stack is stdlib-only, existing PyYAML reads config, never imports agent.*; actions full/download/upload/latency/validate/providers; artifact to <app>/Temp/NetSpeedCalculator; fail-safe preflight REFUSES rather than publish an untrustworthy number; INI_SECTION_NETSPEED_CALCULATOR; Ask-Execs tier D (saturates the link, ~100-200 MB metered) (canvas + chat_agent_netspeed_calculator)
│   │   │   └── ... (88 total agent directories)
│   │   │
│   │   ├── opus_client/            # Claude API client library
│   │   │   └── claude_opus_client.py
│   │   │
│   │   ├── imaging/                # Dual-backend image analysis (Claude + Qwen)
│   │   ├── services/               # filesystem.py, response_parser.py, agent_contracts.py, agent_paths.py, flow_spec.py, flow_compiler.py
│   │   │   ├── agent_contracts.py  # AgentContract registry — per-agent connection-field shape, parametrizer source-fields, secret_paths, never_starts_targets, exclude_from_validation; lru_cached, alias-normalized, disk-discovered + builtin overrides
│   │   │   ├── agent_paths.py      # Frozen/source-aware agent-pool path resolution + canvas-id → pool-name normalization (handles `Node Manager` → `node_manager`, `Gateway-Relayer` → `gateway_relayer`, `(2)` cardinal stripping)
│   │   │   ├── flow_spec.py        # `FlowNode` / `FlowConnection` / `FlowSpec` dataclasses + `normalize_flow_payload()` / `flow_spec_to_legacy_json()` — schema_version=2 in-memory representation that both surfaces (canvas snapshot AND chat tool-call log) compile through
│   │   │   └── flow_compiler.py    # `compile_flow_spec()` / `compile_flow_payload()` / `list_pool_agents_for_validation()` — wires connections per contract, redacts secrets, writes `config.yaml` + `interconnection-scheme.csv` to the session pool, used by both the Start sequence (mode='write') and the Validate dialog (mode='dry_run')
│   │   ├── doc_generation/         # refresh_project_docs.py, mardown_to_pdf.py
│   │   ├── templates/agent/        # HTML templates (toolbar has Multi-Turn / Exec-Report / ACPX / Ask-Execs checkboxes)
│   │   ├── static/agent/
│   │   │   ├── css/                # agentic_control_panel.css, agent_page.css, tools_dialog.css, etc.
│   │   │   ├── js/                 # 37 JS modules (10 chat + 14 ACP + 1 ACP entry + 12 shared, incl. dialog_policy.js and release_notes_renderer.js)
│   │   │   ├── img/Tlamatini.ico   # App icon (web pages + console window + .exe)
│   │   │   └── sounds/             # notification.wav, hypervisor_alert.wav
│   │   └── migrations/             # Django migrations — 197 total (0195/0196/0197 add NetSpeed-Calculator agent + wrapped tool + demo prompt; 0194 adds Deep Internet Research prompt 118; earlier rows remain append-only)
│   │
│   ├── manage.py                   # Django entrypoint; tees stdout/stderr into tlamatini.log; sets console window title + icon
│   ├── tlamatini.log               # Unified application log (console + Django loggers)
│   ├── jd-cli/                     # Bundled Java decompiler
│   └── staticfiles/                # Collected static files (WhiteNoise)
```

---

## Architecture Overview

```
Browser (Chat UI / ACP Workflow Designer)
    │ WebSocket (ws://)
    ▼
Django Channels (Daphne ASGI)
    │
    ├── RAG Pipeline (FAISS + BM25 hybrid retrieval, context budgeting)
    ├── Unified Agent (multi-turn tool loop, wrapped agent runtimes)
    └── MCP Services (System-Metrics via WebSocket, Files-Search via gRPC)
    │
    ▼
LLM Backends: Ollama (local) | Anthropic Claude (cloud) | Qwen (vision)
```

### Request Flow
1. User sends message via WebSocket (optionally with `multi_turn_enabled`, `exec_report_enabled`, `acpx_enabled`, `ask_execs_enabled`)
2. `AgentConsumer` receives and routes
3. Context determination (RAG loaded?)
4. Internet check (classify if web search needed)
5. Chain selection (RAG / Basic / Unified Agent)
6. Multi-Turn gate: checked = planner/dynamic binding; unchecked = legacy one-shot
7. ACPX gate: when `acpx_enabled=False`, `agent.acpx.filter_acpx_tools()` strips every ACPX/Skill tool name from the bound tool list before the planner / executor see them, forcing the system back onto its legacy Multi-Turn / one-shot behavior
7b. Ask-Execs gate (Multi-Turn-only): when `ask_execs_enabled=True`, the executor BLOCKS before every state-changing tool on a browser Proceed/Deny prompt, bridged by `agent/exec_permission.py::ExecPermissionBroker` (consumer registers a per-request broker keyed by user id; executor thread emits `exec_permission_request` onto the consumer loop via `run_coroutine_threadsafe` and waits on a `threading.Event`; the browser's `exec-permission-response` → `resolve_permission` unblocks it). **Deny halts the whole chain** and surfaces a red "Execution interrupted" banner; the round-trip is fail-safe (emit failure / Cancel / `close()` all resolve to *deny*). The flag must stay in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist alongside `conversation_user_id` (same drop-on-rebuild bug class as `exec_report_enabled`). See `docs/claude/multi-turn.md` → *Ask Execs* and `docs/claude/recent-fixes.md` (2026-05-29)
8. Context prefetch (system/file MCP)
9. Execution loop (tool calls, wrapped agent monitoring, ACPX child-process drain); **every model step is wrapped by a per-request self-healing invoker** (`agent/self_healing.py::SelfHealingInvoker`, 2026-07-06) that retries distinct recovery tactics under a per-attempt watchdog (`unified_agent_llm_step_timeout_seconds`, 80 s) up to `unified_agent_llm_step_max_tactics` (4096) — so a transient model failure **never hangs, never discards work already done** (it degrades gracefully from the agents that already ran, preserving the Create-Flow button + Exec report), and **never yields a silent/untruthful answer** (a `recovery_preamble` always tells the user what happened, and live retry status is streamed to the chat via `register_status_broadcaster`). Only the user's Cancel or an exhausted tactic ladder stops it (`ModelStepUnrecoverable`). See `docs/claude/multi-turn.md` → *Self-healing model steps* and `docs/claude/recent-fixes.md` (2026-07-06)
9b. **Per-tool verdict (v1.48.15 vocabulary guard)**: after each wrapped agent returns, `agent/agent_verdict.py` decides SUCCESS/FAILED **deterministically** — it parses the agent's own `INI_SECTION` self-report into a typed AST and runs an ORDERED rule table over it, and **the agent's self-report OUTRANKS the process exit code**. A read-only diagnostic that reports an adverse finding (`invalid`, `findings`, `no_matches`, …) is a **SUCCESS** because the finding is the deliverable; degraded work (`tokens_only`, `compiled_with_errors`, `operator_required`, …), work not done, and agent errors stay red. Intact named completions are explicit greens, and unknown tokens fail open but are identified under `R8b`. The self-report is never dropped: on a key collision the process view stays under `<key>` and the agent view lands on `agent_<key>`. `agent/test_status_vocabulary.py` statically sweeps every pool agent so undeclared tokens and numeric `status:` interpolations cannot ship. See `docs/claude/exec-report.md` → *Success/failure classification* and `docs/claude/recent-fixes.md` (2026-08-16)
10. Streaming response via WebSocket; whenever Multi-Turn ran with **≥1 successfully-executed agent**, the chat header renders a **Create Flow** button that converts **only the successfully-executed** tool calls into a downloadable `.flw` (the browser POSTs the successful-only draft to `/agent/flow_from_tool_calls/`, which normalizes it through `FlowSpec` and redacts known secret fields before download). There is no whole-answer SUCCESS/FAILURE classifier (removed 2026-07-06)
11. Start sequence (canvas Start button) compiles the live snapshot through `/agent/compile_flow/` (mode=`write`) before it executes any agent — so a flow that was edited or loaded since the last write goes through the **same** Agent Contract validation as a `.flw` saved fresh, and Validate uses mode=`dry_run` to preview the same agent/config shape without touching disk

---

## Technology Stack

| Category | Technologies |
|----------|-------------|
| Backend | Python 3.12+, Django 5.2.4, Django Channels 4.1, Daphne (ASGI) |
| Frontend | HTML5, Bootstrap 5, JavaScript (modular), jQuery, jQuery UI |
| AI/ML | LangChain 0.3.27, LangGraph 0.2.74, FAISS, rank-bm25, PyAutoGUI |
| LLM APIs | Anthropic Claude (anthropic 0.74.1), Ollama REST API, MCP 1.25.0 |
| Database | SQLite |
| Communication | WebSockets, gRPC (grpcio 1.76.0) |
| Packaging | PyInstaller, NSIS installer |

---

## How to Run

```bash
# From source
cd Tlamatini
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python Tlamatini/manage.py migrate
python Tlamatini/manage.py createsuperuser
python Tlamatini/manage.py runserver --noreload
# Visit http://127.0.0.1:8000/
```

> **`--noreload` is optional (since 2026-07-11):** plain `python Tlamatini/manage.py runserver` now boots clean and auto-reloads on code edits. It used to double-start the MCP helper ports `:8765` / `:50051` and crash with `WinError 10048`; fixed by a reloader-aware gate in `agent/apps.py`.

> **The web port is CONFIGURABLE (since v1.40.1 — 2026-07-13):** `8000` is only the *default*. Set **`django_port`** in `config.json` and **every** launch path honours it — the frozen double-click, the `.flw` association, the frozen browser auto-open, source `runserver`, and `startserver`. Resolver: `manage.py::_resolve_django_port()`; injector: `manage.py::_apply_configured_port()`. An explicit `[ipaddr:]port` on the command line (`runserver 9100`) always **wins**; resolution is **fail-open** (a missing / unreadable / out-of-range value falls back to 8000 and never blocks startup). Reason it exists: on a machine where Windows/Hyper-V has **reserved** port 8000, Tlamatini used to die with `WinError 10013` and the only escape was a rebuild. See `docs/claude/architecture.md` → *Configurable web port*.

Default credentials (installer builds): `user` / `changeme`

---

## Orphan-Process Cleanup (the `conhost.exe` reaper)

Tlamatini runs a three-tier reaper (`Tlamatini/agent/orphan_reaper.py`) that cleans up Windows `conhost.exe` companions and zombie descendants every console subprocess can leave behind. Without this, users were seeing `conhost.exe` processes lingering in Task Manager **bearing the Tlamatini icon** (conhost inherits the parent EXE's icon) and reasonably assuming Tlamatini was leaking processes.

| Tier | Hook point | Scope | Surfacing |
|---|---|---|---|
| **Tier 1** | `MultiTurnToolAgentExecutor._reap_after_tool()` in `mcp_agent.py` — after every Multi-Turn tool call in `_PROCESS_SPAWNING_TOOL_NAMES` (`execute_command`, `execute_file`, `unzip_file`, `decompile_java`, `googler`, `agent_starter/stopper/parametrizer`) plus every `chat_agent_*` and every `acp_*`. Also fires on the tool-exception path. | Zombie/dead descendants of `os.getpid()` + orphaned `conhost.exe` / `openconsole.exe` whose parent is in our tree or is gone. **No pool-cmdline scan** (cheap path). | Silent. Survivors accumulate on `self._orphan_survivors` and drop into `global_state['last_orphan_survivors']` for Tier 2 to surface. |
| **Tier 2** | `AgentConsumer._tier2_orphan_sweep()` in `consumers.py` — once, in a thread, **after** `process_llm_response` broadcasts the answer so the main reply is never delayed. Merges Tier 1 leftovers with Tier 2 survivors, de-duped by PID. | Same as Tier 1 **plus** the agent-pool cmdline scan (processes whose `cmdline` references `agents/pools/...` but are no longer tracked). | If anything survives **both** tiers, a SECOND `agent_message` is broadcast to the room listing every `name + PID` so the user can end them manually. Renderer: `orphan_reaper.format_survivors_message()` (returns `None` when survivors list is empty — common case). |
| **Tier 3** | `AgentConfig.ready()` in `apps.py` — registered next to the existing pool-directory cleanup on the `atexit` / SIGINT / SIGBREAK path. | Full sweep (self-tree + pool cmdline + console-host orphans). | Logs `--- [Tier-3 reaper] killed=… survivors=… errors=…` to `tlamatini.log`; survivors listed by `name (PID)` for post-mortem. |

Companion hardening — the reaper is paired with **spawn-site changes** that prevent most orphans from existing in the first place:
- `views.py::execute_starter_agent_view`, `execute_ender_agent_view`, `restart_agent_view`, `execute_flowcreator_view` now spawn with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS` and stdio piped to `DEVNULL`.
- `agent/acpx/runtime.py` adds `_windows_creationflags()` (same triple flag) and `_kill_process_tree()` (recursive descendant kill via psutil, terminate → wait 2s → kill).
- Every pool-agent script (`ender.py` and all 50+ siblings in `agents/<name>/<name>.py`) installs a top-of-module `subprocess.Popen.__init__` monkey-patch — `_chg_guarded_init` — that defaults `creationflags` to `CREATE_NO_WINDOW` unless the caller explicitly asked for a console (`CREATE_NEW_CONSOLE` / `DETACHED_PROCESS`). This is the seatbelt: even a future tool that forgets to pass the flag manually gets it for free.

Safety contract: **the reaper must never raise into the caller** — every external call is wrapped in `try/except`, every survivor is recorded rather than re-raised, and a `psutil`-import failure degrades silently. A cleanup that crashes the chat path is worse than the orphans it tries to kill.

When adding a new tool that spawns a console child: either (a) add the tool name to `_PROCESS_SPAWNING_TOOL_NAMES` in `mcp_agent.py` so Tier 1 runs after it, or (b) just rely on Tier 2 catching it (the pool-cmdline scan is wide enough that most cases are covered). Tier 3 is the backstop for either way.

---

## Truthful Exec-Report Verdicts — deterministic engine + closed vocabulary (2026-08-16, v1.48.15)

**Angela's demand:** if the execution really succeeded, the table must say **SUCCESS**; if it really errored and did not do the designated task at all, it must say **FAILED**. Both directions, every agent, no exceptions.

Until v1.48.2 the runtime collapsed **two different questions** into one string — PROCESS (*"did the child exit 0?"* — one bit) and AGENT (*"did the agent do the job, and what did it FIND?"* — a typed record). `tools._launch_wrapped_chat_agent` set `payload["status"]` from the exit code, and the attempt to lift the agent's own `status:` in used `payload.setdefault(...)`, a silent NO-OP on exactly that key — so the agent's truthful self-report was **discarded**. Live consequence: LaTeXer's linter, asked to check a deliberately broken document, found the bug exactly as designed and the Exec Report stamped it a red **FAILURE**.

`agent/agent_verdict.py` replaces the string-sniffing with a small expert system: a lexer/parser turns the `INI_SECTION` self-report into a typed AST (`SectionNode` → `KVNode` → coerced values), and an **ordered** production-rule table returns a `Verdict` carrying the rule id and the evidence that fired it — no model call, no heuristics, 100 % deterministic.

**Contract (do NOT weaken):**

- The agent's own self-report **OUTRANKS** the process exit code.
- A self-report is **NEVER** dropped or overwritten — on a key collision the process view stays under `<key>` and the agent view lands on `agent_<key>`; **both** survive.
- A **read-only diagnostic reporting an adverse finding has SUCCEEDED** — the finding is the DELIVERABLE. This is why the diagnostic rule **must outrank** the `success:` / `errors:` rules: a linter that worked perfectly reports `status: invalid` **and** `success: False` **and** `errors: 2` in the same breath, and the last two describe the **document**, not the agent.
- `WORK_DEGRADED_STATUSES` (`tokens_only`, `compiled_with_errors`, `operator_required`, …) are **FAILED** because the deliverable is compromised or absent; `WORK_NOT_DONE_STATUSES` (`refused`, `not_found`, `not_unique`, `engine_unavailable`, …) stay red because the requested work did not happen. A red row therefore means **no clean requested deliverable**, never merely "the diagnostic found something".
- `WORK_COMPLETED_STATUSES` gives intact completions a named, auditable green (`R7b`); an unknown status keeps fail-open compatibility but is quoted under `R8b.unknown_status` so the anomaly is visible.
- **FAIL-OPEN**: every parse/coercion error resolves to "no opinion" and falls through. Nothing here may raise into a caller.
- The status vocabulary has **exactly ONE definition**: five disjoint sets in `agent_verdict.py`, with `KNOWN_STATUSES` as their union. `mcp_agent` aliases the shared definitions — do **NOT** re-inline a second copy.
- `agent/test_status_vocabulary.py` AST-scans every pool agent, requires every literal status to belong to exactly one set, rejects malformed/unknown tokens, and rejects interpolated exit-code variables in `status:`. Kuberneter is the canonical fix: numeric `returncode`, explicit `success`, tokenized `status: ok|failed`.
- Stdlib-only and imports nothing from `agent.*`, so it can never create an import cycle between `tools.py` and `mcp_agent.py` (both import it) and behaves identically frozen and from source.

**If you author an agent**: its `status:` field is load-bearing — it is READ, not decoration. Reuse a token from `KNOWN_STATUSES`; put numeric process results in `returncode`/`exit_code`, never `status:`. A read-only diagnostic must exit `0` and report its finding in `status` / `errors`; never tie the process exit code to how clean the user's input was. Pinned by `agent/test_agent_verdict.py`, `agent/test_exec_report_verdict.py`, and the repository-wide `agent/test_status_vocabulary.py`. Full contract: `docs/claude/exec-report.md` → *Success/failure classification*; current story: `docs/claude/recent-fixes.md` (2026-08-16).

---

## LaTeX Generation — the four defects that made it impossible (2026-08-11)

**Angela asked for a LaTeX document + PDF and got an EMPTY DIRECTORY.** The Exec
Report stored in the DB (`agent_agentmessage` id 50) confessed it: **LaTeXer had
only ever been called with `action='validate'`** — never asked to typeset —
while Pythonxer failed 4× and a PowerShell here-string failed once. LaTeXer was
not broken; **the road to it was**. Four independent defects, all now fixed.
Full line-by-line record: **`TlamatiniImprovementsByClaudeOnLaTeXer.md`** (repo
root). Pinned by `agent/test_latexer_verbatim_channel.py` (**19 tests**).

**1. The byte-exact channel was hardcoded to ONE agent.** `tools.py` gated its
verbatim/base64 immunity on `if spec.template_dir == "file_creator":`, so every
other agent got the generic coercion that collapses `\\` → `\`. **In LaTeX `\\`
is the ROW/LINE BREAK** — every table, matrix and title block was destroyed in
transit (measured: row-breaks `2 → 0`). Worse, the multi-line quote rule glued a
trailing `', filename='x.pdf'` INTO the document body and returned those keys
EMPTY. → Specs now DECLARE their literal fields in
**`ChatWrappedAgentSpec.verbatim_fields`** (file_creator `("content",)`; latexer
`("input_text","content","find_text","replace_text")`); `tools.py` honours
`<field>_b64` first, else re-extracts raw bytes, then
`_recover_swallowed_assignments()` splits off a trailing assignment tail **only
when EVERY key in it exists in that agent's own `config.yaml`** (so real prose is
never cut). `latexer.py::_decode_b64_fields()` decodes the four `*_b64` keys
(fail-open), and they exist in its `config.yaml` — **a missing key is silently
dropped by the assignment applier**. ⚠️ **When you add an agent that takes
literal source text, add its fields to `verbatim_fields`** — it is NOT automatic.

**2. The LLM client timeout was hardcoded to 120 s.** `mcp_agent.py` did
`client_kwargs.setdefault("timeout", 120.0)` and `rag/factory.py` had
`{'timeout': 120.0}` twice. A full Multi-Turn request carries the whole system
prompt **plus every bound tool schema (100+)**, so it ReadTimeout'd at *exactly*
120.0 s on every attempt and self-healing retried forever — while a one-line
probe of the SAME model answered in **1 second**. It is REQUEST SIZE, not a
broken model; the same ReadTimeout notes appear in Angela's ORIGINAL failed
answer. → **`llm_client_timeout_seconds`** (new, fail-open to 120) via
`mcp_agent.resolve_llm_client_timeout()`, used by mcp_agent + both factory sites,
logged as `--- [LLM-TIMEOUT] one Ollama call may take up to Ns ---`. Config: 600,
with `unified_agent_llm_step_timeout_seconds` raised to **900** — ⚠️ **the
watchdog MUST exceed the client bound**, or it abandons the attempt first and
reproduces the symptom with a different number.

**3. The DESTRUCTIVE `bisect` rung fired on an infrastructure blip.** Rung 7
(`model`) timed out on a 60 KB `.tex`, so rung 8 quarantined block 10 and a
27-page CLEAN pdf became a 26-page **DEGRADED** one with Angela's content
deleted. → `latexer.py::_model_rung_never_answered(trace)` now SKIPS bisect when
the model was merely **unreachable** (timeout/connection/refused), records the
skip in the audit trace, and **fail-SAFEs to True (protect the document)** on any
doubt — the opposite direction from the usual fail-open, deliberately, because
losing the user's work is the worst outcome available. `repair_model_timeout`
180 → **600**. ⚠️ Do NOT relax this guard and do NOT move `bisect` off last.

**4. Nothing ever told her the job was DONE.** A clean 27-page/0-error PDF
existed at 14:55; she kept "improving" it for 50+ iterations (v2, v3, a 57 KB
`fix_latex.py`) until one of her own edits broke it → `degraded` → *"compile did
not succeed"* → an unbounded repair loop over an already-good deliverable. →
A clean build now prepends a hard STOP as `notes.insert(0, …)` (the FIRST line
the model reads): *"DONE — a CLEAN PDF now exists: `<path>` (N pages, 0 errors).
THE DOCUMENT IS FINISHED. Do NOT recompile / improve / edit / make a _v2 …
report this absolute path and STOP."* Attached **only** to the `result["ok"]`
branch — a degraded build must still read as a problem.

**Proven end-to-end** through the real chat GUI (visible Chrome,
`.claude/skills/tlamatini-daily-chat-test/harness/latexer_openmp_e2e.py`, verdict
= filesystem truth not prose): Tlamatini wrote a **61,951-char `.tex`** (log:
`file_creator.content re-extracted VERBATIM (61951 chars, no escape decoding)`)
and compiled **`OpenMPCompleteGuide.pdf` — 27 pages, 716,421 bytes, 0 errors**.

---

## Binary-Content Guard on Context Loading (2026-07-26)

Every file entering the RAG context/embedding chain is screened for **binary content** by `agent/rag/binary_guard.py` before it is read as text. Binary files are dropped through the *same* mechanism as the user's **Context ▸ Set file type omissions** list (a `ValueError` swallowed by `DirectoryLoader(silent_errors=True)`), and **every drop is named in `tlamatini.log`** with the grep-able `--- [BINARY-GUARD]` prefix — in frozen and source mode alike, since `manage.py` tees stdout into the log before Django boots.

The two filters are **complementary**: the omissions list decides on the **name** (what the user chooses to ignore), the guard decides on the **bytes** (what is binary no matter what it is called — the `.pyc`, the vendored `.so`, the `.faiss` index, the screenshot dropped into a project folder).

Detection is a short-circuiting cascade, cheapest test first, with **at most ONE `read()` of ONE 8 KiB block** per file: extension denylist (zero I/O) → sample → empty → **BOM** → magic signatures → NUL byte → control-byte ratio → UTF-8 decodability. Wired at **all three** `DirectoryLoader` call sites in `agent/rag/factory.py`.

**Two contracts that must NOT be weakened:** (a) **FAIL-OPEN** — any error, any uncertainty, any malformed config value resolves to "load it as text", because a guard that wrongly drops a file silently deletes the user's real context; (b) **the BOM stage must stay ahead of the NUL stage**, or every UTF-16 document (legitimately full of `0x00`) silently vanishes. Toggle with `binary_context_detection` in `config.json`. Coverage: `agent/test_binary_guard.py` (45 tests). Full contract: `docs/claude/architecture.md` and `docs/claude/recent-fixes.md` (2026-07-26).


## Current Release — v1.49.1 (2026-08-23, annotated)

The newest annotated tag is `v1.49.1` at `6adf3623`. Local and remote `HEAD` are aligned one commit later at `abc7899a`; runtime still resolves the reachable bare release tag through Git/build metadata. Source truth is **88 workflow agents**, **66 wrapped chat-agent launchers**, **108 built-in Multi-Turn tools** (20 core + 66 wrapped + 12 ACPX/Skill + 10 External-MCP supervisors), **105 root stdio MCP tools**, **29 skills**, and **197 migrations**.

The release adds **NetSpeed-Calculator** (multi-provider RFC-6349-style throughput, Student-t confidence intervals, random-effects fusion, I², bufferbloat, named zero-byte failures, and Ask-Execs tier-D bandwidth gating); **WAL-safe SQLite data movement** (`sqlite_copy.py` online backup API + DELETE-journal destination + `quick_check` + sidecar hygiene for Backup DB, Set DB, and pre-Django swap); Googler's **structured Google-dork builder** plus a two-tier resilience path (four plain-HTTP server-rendered routes first, then visible installed Chrome/bundled Chromium across seven direct-results routes, bounded retries, answer-route logging, lawful-source/`links_only` workflows, and explicit Google-only operator semantics); the **External MCP Adder** skill's classify/import/doctor/activate/wait/list/call lifecycle; migration 0194's append-only **Deep Internet Research** starter; Ollama Pro-or-higher complete-operation guidance; and private-build contact synchronization into gitignored `contacts.private.json` while public builds/snapshots remain contact-empty.

## ⌨️ Uniform Dialog Dismissal — ESCAPE CLOSES EVERY DIALOG (2026-08-16, v1.48.17)

**Angela REVERSED the previous rule.** Until 2026-08-13 `dialog_policy.js` deliberately SWALLOWED Escape. The policy is now one line, on **both** pages, for **every** dialog:

> A dialog closes by its titlebar ✕, its Cancel/dismiss button, its Continue/OK button, **or ESCAPE** — and **Escape === ✕ === Cancel**.

The other half is UNCHANGED and must not be relaxed: **an outside click still never dismisses anything.**

**⚠️ THE DISPATCHER NEVER HIDES A NODE.** `dialog_policy.js` §4 is a **bubble-phase `document` keydown** handler that finds the *topmost open dialog* (shape-based selector — `[id$="-overlay"]`, `[class*="-overlay"]`, `[role="dialog"]`, `.ui-dialog`, `.modal.show`, … — ranked by z-index, backdrops excluded) and **invokes THAT dialog's own dismiss control**: the click the user would have made. That is why nothing had to be rewired per dialog and every fail-safe survives Escape — the Ask-Execs prompt still answers **DENY** through its `close:` handler, `acpConfirm` / `tlmConfirm` still resolve **false**, every `body.style.overflow` is restored by the dialog's own close, and the **sealed updater still refuses** (`CloseUpdateDialog` → `mayClose`). A blind hide would have silently skipped all four.

**Contracts that must NOT be reverted:** BUBBLE phase, not capture (the Catalog's search box clears the query on the FIRST Escape; only the SECOND closes the catalog) · `stopImmediatePropagation()` when it dismisses, so one keystroke never closes two stacked layers · `dialog_policy.js` stays the FIRST document keydown handler on both pages · it bails when no dialog is open (Escape still belongs to the page) · Escape can never press an **affirmative** button (the label scan matches only cancel/close/dismiss/cancelar/cerrar/no and the × glyphs; a one-button acknowledgement box uses that button) · backdrops are excluded · a dialog with no ✕ and no Cancel must expose **`el.tlmDismiss`** (the Catalog of Prompts is the one such dialog — a blind hide there leaves the whole chat page unscrollable). **`closeOnEscape: false` is now a FORBIDDEN pattern tree-wide** (seven dialogs carried their own and were flipped).

**The ONE exception — the updater is INVULNERABLE while it downloads.** Not a special case bolted onto the dispatcher: a dialog declares **`el.tlmSealKey`**, and while that key is sealed `dismissDialog()` refuses **FIRST**, before any other path (checked later, the "hide the node" last resort would kill exactly the dialog it must protect). Escape is **swallowed** (`preventDefault` + `stopImmediatePropagation`) plus a 600 ms shake instead of nagging; F5 / Ctrl+R / Ctrl+F4 are guarded too; and a **failed start ALWAYS unseals** (a permanent seal is strictly worse than the interruption it prevents). ⚠️ The seal guard is **CAPTURE** phase — deliberately the opposite of the dispatcher's bubble phase, and both are pinned so neither gets "made consistent" by mistake. Honest limit: Alt+F4, the window ✕, and Chrome-reserved Ctrl+W can never be blocked from a web page — but the swap runs in an **external PowerShell process**, so a closed tab costs the progress bar, not the update.

**No native browser pop-ups inside a themed dialog.** `alert()` / `confirm()` / `prompt()` paint OS chrome carrying the page URL, block the page, and cannot be photographed by a headed Playwright run. Use **`tlmAlert(message, title)` / `tlmConfirm(primary, secondary, title)`** — chat + canvas, exported by `dialog_policy.js`, Promise-based (`tlmConfirm` → `Promise<boolean>`; anything but Continue is `false`), styled from `dialog_theme.css` `.tlmpop-*` tokens, overlay at z-index **100001**, **fail-open** to the native popup — or `acpAlert` / `acpConfirm` on the canvas. ⚠️ They are deliberately **NOT** jQuery-UI dialogs: they are raised BY native modals at `z-index: 20000` (`.emx-dialog` / `.ctb-dialog`) while `.ui-front` is ~100, so a jQuery-UI confirm would render *under* the dialog that asked for it — an invisible modal, i.e. a hang. When you migrate a module, add it to `_THEMED_DIALOG_MODULES` in the test.

Coverage: `agent/test_dialog_dismissal_policy.py` (**35 tests** — bubble phase, `stopImmediatePropagation`, no-affirmative-button, backdrop exclusion, the `tlmDismiss` hook, script load ORDER on both pages, the seal-check index, and the forbidden patterns) + the **visible** headed-Chrome runner `.claude/skills/tlamatini-daily-chat-test/harness/dialog_policy_visible.py` (Playwrighter drives, Shoter photographs). Full contract: `docs/claude/frontend.md`; full story: `docs/claude/recent-fixes.md` (2026-08-16).

---

## Temp & Templates Directory Policy (2026-06-02)

Every **transient** file Tlamatini writes lives under ONE directory — `Temp` at the application root (`<exe-dir>/Temp` frozen, `<repo-root>/Temp` source) — and **never** outside Tlamatini (no `C:\Temp`, no `%TEMP%`, no system temp). `Tlamatini/manage.py::_enforce_app_temp_dir()` (before Django) and `tlamatini/settings.py::_pin_temp_directory()` (covers a direct `daphne`/`asgi` launch) pin `TMP`/`TEMP`/`TMPDIR` + Python's `tempfile.tempdir` to it and export `TLAMATINI_TEMP`, which every spawned pool agent inherits (`get_agent_env` does `os.environ.copy()`). The resolver is `agent/path_guard.py` (`get_app_temp_root` / `enforce_app_temp_dir` / `is_within_app_temp` / `resolve_temp_path`). The temp-creating agents (executer, de_compresser, esp32er, stm32er, arduiner, plus historical TelegramRX templates in older installs) also carry an explicit module-top `if (os.environ.get('TLAMATINI_TEMP')…)` guard (an `if`-block, never a top-level `def` — that trips ruff E402 before the imports).

**Chat screenshots land in `Temp` too (2026-07-14).** An image pasted with **Ctrl+V** — or dropped onto the chat column — is persisted by `views.paste_image_view` through `path_guard.resolve_temp_path()` as `<app>/Temp/image_<YYYYmmdd>_<HHMMSS>_<ms>.jpg` (Pillow → JPEG), and its **absolute path is spliced into the chat box at the caret** so the user can immediately ask Tlamatini to analyze it (Image-Interpreter / `launch_view_image`). Frontend: `agent/static/agent/js/chat_image_paste.js` — see `docs/claude/frontend.md` and the 2026-07-14 entry in `docs/claude/recent-fixes.md`.

Separately, the **default parent for the project trees the firmware/engine agents (STM32er / ESP32er / Arduiner / Unrealer) scaffold** is `Templates` at the application root (`TLAMATINI_TEMPLATES`; `path_guard.get_app_templates_root`), **unless the user names another path**. `Temp` = throwaway scratch; `Templates` = deliverable project trees (so it never touches `tempfile`).

The LLM is told this in `prompt.pmt` **Rule 15** (Temp) and **Rule 16** (Templates), with the absolute paths injected as `{temp_directory}` / `{templates_directory}` by `agent/rag/config.py`. `build.py` ships both dirs empty next to the `.exe`; `.gitignore` ignores both. **When you author a new agent/tool/skill that writes scratch, route it through `<app>/Temp`; a new firmware/engine agent that scaffolds projects defaults to `<app>/Templates`.** Full "do-NOT-revert" contract: `docs/claude/recent-fixes.md` (2026-06-02). The `create-new-agent` / `create-new-mcp` / `skill-creator` skills and the two `@`-imported workflow guides carry the same indication.

---

## Specialized Docs (auto-imported)

The rest of the onboarding material is split into topic files under `docs/claude/`. Each `@` line below is imported by Claude Code into your context automatically, so treat the full set as a single document. See `docs/claude/INDEX.md` for one-line descriptions of each file.

- **Architecture & core systems** — config, system prompt & identity, the Five Layers, application log, doc generation, database models: @docs/claude/architecture.md
- **Multi-Turn, Create Flow, Parametrizer** — Multi-Turn mode, short follow-up scoring, Create-Flow pipeline, `INI_SECTION_*` format: @docs/claude/multi-turn.md
- **Exec Report** — per-agent execution tables, capture/render pipeline, strict ordering contract, styling, adding new agents: @docs/claude/exec-report.md
- **Agents** — creating a new agent (8-step), naming conventions, lifecycle, all 88 agent types, FlowCreator, FlowHypervisor: @docs/claude/agents.md
- **ACPX** — definition, agent registry, 12 LLM-facing tools, transport profiles, canonical flows, runtime mechanics, ACPX toolbar toggle, "when the user says ACPX" decision matrix: @docs/claude/acpx.md
- **MCPs & Tools** — tool-only vs MCP context provider workflows, Skills system (SKILL.md packages), key warnings: @docs/claude/mcp-tools.md
- **Frontend** — chat modules, ACP modules, ACP Canvas DOM Contract: @docs/claude/frontend.md
- **Gotchas & reference** — Claude API client, build/lint, versioning, hardcoded assumptions, roadmap, work-style preferences: @docs/claude/gotchas.md
- **Creating a new agent (full 8-step guide)** — backend script + view + migration + CSS gradient + 4 JS files + docs + lint; naming-convention table; lifecycle; connection-field semantics: @Tlamatini/.agents/workflows/create_new_agent.md
- **Creating a new MCP or tool (full guide)** — tool-only vs MCP context-provider vs both; per-workflow checklists; `factory.py` / sidecar chain / `Mcp` row wiring; hardcoded-assumption warnings: @Tlamatini/.mcps/create_new_mcp.md

**Consult-on-demand (deliberately NOT `@`-imported, to keep the auto-loaded context lean):**

- **Recent Fixes / fix log** — `docs/claude/recent-fixes.md`. The dated chronological log of surgical fixes and "do NOT revert this / keep these surfaces aligned" contracts (ACPX, Flow Compiler, planner, Exec Report, ACP canvas, wrapped chat-agent parsing, desktop-UI agents, the STM32er zero-config bootstrap + fail-safe hardware preflight, `prompt.pmt`, `regen_secrets.py`, logging filters). **Read it before modifying or reverting code in any of those subsystems**, and prepend new fix entries there rather than to `gotchas.md`.
- **Creating a new Skill (SKILL.md package)** — `Tlamatini/.skills/create_new_skill.md`. The dedicated authoring guide for a `SKILL.md` (the two runtimes — `in-process` vs `acpx`; the frontmatter contract + schema ranges; discovery / 30 s staleness cache; lint + `quick_validate`; ACPX-surface gotchas). NOT auto-imported — read it when adding or editing a skill. The `flow-making` skill (`agent/skills_pkg/flow_making/`) is the canonical worked example of an in-process skill that shells out to a shipped `scripts/*.py`.
- **Companion-app discovery** — `docs/companion-app-discovery.md`. How Tlamatini lets XAIHT companion apps (**Tlamatini-FlowPills**) find the agents catalog without Python/scans: the `HKCU\Software\XAIHT\Tlamatini` registry key + `<agents_root>\_tlamatini_agents_manifest.json` + the `.tlamatini-preserved-agents.json` preserved marker. Engine `agent/agent_manifest.py` + `agent/windows_app_registration.py`, wired in `apps.py` / `install.py` / `uninstall.py` / `build.py`; HKCU-only, no-admin, fail-open. Implements `Tlamatini-FlowPills-Lookup.md` §15.

│   │   │   ├── pdfer/              # PDFer — DOCUMENT COMPOSER, the WRITE side of the document family (File-Extractor/File-Interpreter READ, PDFer AUTHORS). Tlamatini's answer / Markdown / HTML / text / images / existing PDFs → ONE styled PDF. ZERO new deps (markdown+xhtml2pdf+pymupdf+reportlab+pillow+pypdf already ship; md→pdf pipeline ported INLINE from doc_generation/mardown_to_pdf.py). mode: auto|markdown|html|text|images|mixed|merge|info|validate; optional Ollama polish (default OFF, never loses the doc); saves to Documents/TlamatiniPDF, collision-proof; fail-safe preflight REFUSES rather than write an empty PDF; INI_SECTION_PDFER; Exec Report + Ask-Execs tier A (canvas + chat_agent_pdfer)
│   │   │   ├── latexer/            # LaTeXer — LaTeX TYPESETTING, the typesetting sibling of PDFer (PDFer COMPOSES from Markdown/HTML/images; LaTeXer TYPESETS from .tex: real maths, bibliographies, cross-refs, index). Embeds the WHOLE mcp-latex-server surface NATIVELY (create/template/edit/read/list/validate/structure/compile) — NO MCP server, NO sidecar, NO new dependency (stdlib only: subprocess+shutil+glob+re+urllib) — PLUS whole-PROJECT compile of a .tex SET (master auto-detected, \input followed), a real BibTeX/Biber + makeindex + makeglossaries convergence loop, latexmk pass-through, and LaTeX-log diagnostics a human can read. **REQUIRES MiKTeX** (https://miktex.org/download) — Tlamatini bundles NO TeX distribution (several GB; the release must stay <2 GB); MiKTeX is preferred because `--enable-installer` installs a missing .sty ON DEMAND mid-compile, so any document builds. ⚠️ latexmk is probed for USABILITY not presence (it ships with MiKTeX but is a PERL script; most Windows boxes have no Perl → auto-fallback to the built-in loop). action: compile|compile_project|scaffold_compile|create_file|create_from_template|edit_file|read_file|list_files|validate_tex|structure|clean|validate|install; auto_preamble wraps a bare fragment; shell_escape OFF by default (\write18 = RCE); saves to Documents/TlamatiniLaTeX, projects to <app>/Templates/LaTeXer; fail-safe preflight REFUSES rather than mis-typeset; **EIGHT-RUNG REPAIR LADDER (v1.48.2) so a failed build self-heals — lint → preamble → rules → log_directed → acquire → engine_swap → model → bisect, each repair applied to a COPY and re-linted (a repair that worsens the lint is REVERTED), the author's file untouched unless `repair_write_back`, every rung audit-traced, quarantined blocks named; ⚠️ the DESTRUCTIVE `bisect` rung is strictly LAST (reordered 2026-08-05) — do NOT swap it back ahead of `model`**; a DEGRADED build never claims clean success; INI_SECTION_LATEXER; Exec Report + Ask-Execs tier A (canvas + chat_agent_latexer)
│   │   │   ├── editor/             # Surgical in-place find-and-replace on ONE text file (Claude-Edit equivalent; byte-exact, refuses a non-unique match unless replace_all, base64 channel; emits INI_SECTION_EDITOR) (canvas + chat_agent_editor)
│   │   │   ├── grepper/            # Read-only regex CONTENT search across a file/dir tree (Claude-Grep equivalent; file:line:match, glob filter, prunes noise dirs; emits INI_SECTION_GREPPER). ⚠️ ENCODING-AWARE since 2026-08-16 (`_read_text_lines`): BOM tested BEFORE the NUL byte (UTF-16/32 text is legitimately full of 0x00 — same ordering contract as rag/binary_guard.py; _BOM_CODECS longest-prefix-first), then UTF-8 → cp1252 → latin-1. It used to open() strict-UTF-8 and swallow the UnicodeDecodeError as "binary", so it answered a confident `no_matches` about files it never opened (PowerShell's UTF-16 logs, accented Spanish sources). Pinned by test_grepper_encodings.py (canvas + chat_agent_grepper)
│   │   │   ├── globber/            # Read-only filename glob search (Claude-Glob equivalent; find files by pattern, newest-first, ** recursive; emits INI_SECTION_GLOBBER) (canvas + chat_agent_globber)
---

## ⛔ MANDATORY DIRECTIVE - Angela 2026-07-07 - FORBIDDEN HEADLESS TESTS: ALL AUTOMATED TESTS MUST BE VISIBLE (HEADED PLAYWRIGHT)

**HEADLESS / INVISIBLE AUTOMATED TESTS ARE FORBIDDEN. EVERY automated test MUST run VISIBLE — a HEADED browser (Playwright `headless=False`, prefer real Chrome) on Angela's REAL desktop, so she can SEE every step live.** This is HARD, NON-NEGOTIABLE, FOREVER.

- **Playwright**: launch HEADED. **NEVER** pass `--headless`. The chat-test harness `--headless` flag is disabled (refuses to run). Drive the **real Tlamatini chat GUI** (`http://127.0.0.1:8000/agent/agent/`, login `angela`) — never fake or bypass the UI.
- **Run it in a VISIBLE FOREGROUND window** (`Start-Process powershell -NoExit …`, `dangerouslyDisableSandbox:true`) so it renders on her screen — never `run_in_background`, never a hidden/detached job. (Same spirit as the foreground-windows rule.)
- **Verify each step with a FULL-SCREEN screenshot** (the ENTIRE desktop, taskbar **clock** visible) — one photo per test + a live `SUMMARY.html`.
- **NEVER LIE**: a stale chat-history scrape, a transient self-healing "🔁 Tactic #…" status, or a timed-out answer must NEVER be recorded as a pass. Clear chat history per test, re-assert **Multi-Turn ON at every send**, reject already-seen answers.
- If a test cannot be made visible, **do NOT run it** — tell Angela.
- Enforced by: SessionStart hook `~/.claude/hooks/visible_tests_rule_banner.py` (prints every session), memory `feedback_forbidden_headless_visible_tests`, global `~/.claude/CLAUDE.md`, and the `tlamatini-daily-chat-test` skill. Reference runner: `.claude/skills/tlamatini-daily-chat-test/harness/discoverer_1000.py`.

---

## MANDATORY DIRECTIVE - Angela 2026-06-14 - USE ONLY TLAMATINI'S SKILLS/TOOLS/AGENTS, NOT CLAUDE CODE'S BUILT-IN TOOLS

Every session, from the very start, Claude MUST perform the work with Tlamatini's OWN agents, tools and skills - Executer, Pythonxer, File-Creator, Mover, Deleter, Playwrighter, Blenderer, the mcp__tlamatini__ wrapped tools, and the SKILL.md skills - and MUST NOT use Claude Code's built-in tools - Bash, Read, Write, Edit, Grep, Glob, the built-in Playwright - to do the task. Claude's shell is ONLY a launcher of last resort. The purpose is to DOGFOOD Tlamatini's tools: exercise them on real work, surface their errors, and keep fixing them. If a Tlamatini tool lacks a capability, fix or extend that tool instead of falling back to a Claude tool.

### Tool correspondence — Claude built-in → the Tlamatini tool to use INSTEAD

The Tlamatini tools are exposed over MCP as `mcp__tlamatini__<name>` (their schemas are deferred — load them on demand with `ToolSearch`, e.g. `ToolSearch "globber grepper editor"`; `mcp__tlamatini__tlamatini_list_agents` enumerates every one). **Before reaching for ANY Claude built-in, map the action to its Tlamatini tool here and use that:**

| Claude built-in | Use INSTEAD | Key params / notes |
|---|---|---|
| **Write** (create a file) | `mcp__tlamatini__file_creator` (File-Creator) | `file_path`, `content` (or `content_b64` for binary); creates parent dirs |
| **Edit** (find/replace) | `mcp__tlamatini__editor` (Editor) | exact-unique `old_string`→`new_string`; `replace_all`; `old_string_b64`/`new_string_b64` for byte-exact edits |
| **Grep** (content search) | `mcp__tlamatini__grepper` (Grepper) | `pattern` (regex), `path`, `glob`, `case_insensitive`, `output_mode` |
| **Glob** (find files) | `mcp__tlamatini__globber` (Globber) | `pattern`, `path`, `sort_by`, `max_results` |
| **Bash** (shell command) | `mcp__tlamatini__executer` (Executer) | `script`; `non_blocking:true` to detach a long-running server; `execute_forked_window:true` for a visible console window |
| **Bash** (run Python) | `mcp__tlamatini__pythonxer` (Pythonxer) | inline Python behind a compile()/ruff gate |
| **Playwright** / browse a site | `mcp__tlamatini__playwrighter` (Playwrighter) | `start_url` + `steps_json` (goto/click/fill/extract/screenshot) |
| move / copy a file | `mcp__tlamatini__mover` (Mover) | glob-capable |
| delete a file | `mcp__tlamatini__deleter` (Deleter) | glob-capable |
| git commands | `mcp__tlamatini__gitter` (Gitter) | use `command='custom'` to pass a raw git subcommand |
| web search | `mcp__tlamatini__googler` (Googler) | Manual Google operators go in `query`; the visual/pool agent adds structured presets, grouped site/filetype filters, and `links_only` file-hunt output |
| audio / video / camera / mic, TTS / STT, firmware, 3D | the matching agent — `talker`, `whisperer`, `recorder`, `camcorder`, `audioplayer`, `videoplayer`, `stm32er`, `esp32er`, `arduiner`, `blenderer`, `kalier`, `windower`, `mouser`, `keyboarder`, `shoter`, … | **no Claude equivalent exists — always the agent** |

**Reading files:** there is no raw-`cat` Tlamatini agent (File-Interpreter / File-Extractor read-and-interpret via the LLM or extract from PDF/DOCX; Grepper / Globber are for search). So prefer Grepper/Globber to locate code and File-Interpreter to summarize a file; Claude's **Read** is the narrow last-resort exception **only** when you need the exact bytes of a region to author an Editor `old_string` and no Tlamatini tool yields them.

**Transient-outage fallback (allowed, must be stated):** if a `mcp__tlamatini__*` tool is briefly blocked (e.g. the safety classifier is temporarily unavailable) and you have already retried, you MAY fall back to the matching Claude built-in to avoid stalling — but say so explicitly in your reply and treat it as an outage workaround, not a substitution. The instant the Tlamatini tool is reachable again, switch back.

**Desktop/visible agents** (a headed Playwrighter, an Executer/Pythonxer forked console, Shoter/Mouser/Keyboarder/Camcorder/VideoPlayer windows) launched via your own shell must run FOREGROUND with `dangerouslyDisableSandbox: true` so the window renders on the user's real desktop — but when driven through `mcp__tlamatini__*` (the Django server spawns them) they already render, so just call the MCP tool.
