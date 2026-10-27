<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# docs/claude/ — Tlamatini AI-Assistant Docs Index

> Current release: **[v1.91.1](../changes/2026-10-27-v1.91.1.md)**. Dated records below retain their original evidence dates.

## v1.91.1 — Prompt Flow fixes and short tool names

**v1.91.1** is the current version (2026-10-27). Its annotated tag resolves to
`9915938a` and is present on origin; it is published on GitHub as the Latest
release, replacing v1.91.0 (published 2026-10-23). It is a patch release: no agent,
tool, skill or migration was added, so the catalog stays **86 workflow agents, 67
wrapped chat agents, 110 built-in tools, 29 skills and 220 migrations**.

- **Prompt Flow history:** every chain loads the history of the request's own
  `conversation_user_id`; a Prompt Flow run uses only its own in-memory history.
- **YES/NO Decisions:** an `equals` Decision accepts an answer that opens with the
  value (`## YES - ...` equals `YES`; `Yesterday` does not), and the Prompt before it
  asks for that short answer alone on the first line.
- **Usage:** a Prompt Flow run is recorded for the account that owns it.
- **Telegrammer:** "using the bot ..." anywhere in the request (outside quoted values)
  sends as the bot; an explicit `provider` still wins.
- **Short tool names:** a wrapped agent called by its short name (`terminater`) is
  resolved to `chat_agent_terminater` and logged as `[TOOL-ALIAS]`.
- **Prompt Flow tab title:** an Untitled flow shows the name of its file.

See the [v1.91.1 release record](../changes/2026-10-27-v1.91.1.md).

## Carried from v1.91.0 — Live Editor and Terminater configuration

**v1.91.0** was the source version of 2026-10-23. Its existing annotated tag
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
package acceptance. v1.91.0 was published on GitHub on 2026-10-23.
See the [release record](../changes/2026-10-23-v1.91.0.md) and
[settings guide](../interaction-settings.md).

## Carried from v1.90.0 — editable canvas and Interactor


The v1.90.0 source line had **86 workflow agents, 67 wrapped chat agents, 110 built-in tools (21 direct/module + 67 wrapped + 12 ACPX/Skills + 10 supervisors), and 219 migrations** after migration 0219. Interactor added a module/tool, not an Agent. The annotated tag resolves to `ebc5c3b4` and its GitHub release was published on 2026-10-22. Later commits in that line carried the account wizard’s local Notifier checkpoints. This section preserves v1.90.0 history; current configuration and counts are described above. Dated source and frozen runs remain separate.

- **Editor:** `agent_page_editing.js` owns the CodeMirror document, dirty baseline, encoding and save snapshot. `agent_page_canvas.js` owns load/refresh generation and cancellation. Markdown Preview and Source share the buffer; HTML/SVG remain inert source; PDF saving copies the original PDF. Never read a hidden compatibility element instead of the editor.
- **Native files:** `canvas_file_views.py` and `native_dialogs.py` provide local Save As/read/save. Authentication, CSRF, loopback-only host access, account/session-bound capabilities and full revision checks prevent a browser name from becoming an arbitrary host path. Existing Windows replacement preserves metadata; DB backup/restore mechanics are unchanged.
- **Interactor:** `agent/interactor/` connects the synchronous tool loop to the browser through session-authenticated `ws/interactor/`. Server-issued tab identity travels through ContextVar; bounded commands and receipts verify document/revision and full buffer. Browser messages acknowledge/access/stop; they cannot request arbitrary host-path commands.
- **Tutor:** read fresh unsaved text, type a small segment, guide the next field and end mutations for the turn. Continue begins a fresh chat/read. Prepared choices match locally, with no per-key model call. User input and Stop win; hidden tabs pause with bounded recovery rather than repeating edits.
- **Carriage:** migration 0218 seeds the Tool/catalog rows; `tool_gate_table()` supplies binding, Compact selection and cost labels. The offline editor bundle, Interactor browser files, frozen imports and source/static inventories must travel together.
- **Intent:** password input is not ownership of every command; a wizard email field or DONE reply is not notification consent. Preserve genuine user-runs tutorials. The catalog wizard uses createsuperuser and therefore creates an administrative account.

Contracts and evidence: [v1.90.0](../changes/2026-10-22-v1.90.0.md), [Canvas editing](../canvas-editing.md), [Interactor](../interactor.md), [Account wizard](../user-creation-wizard.md). Source/frozen rendering tests do not certify a rebuilt installed executable.


> **Carried from v1.88.0 (tagged 2026-10-20):** [Terminater](../terminater.md) (workflow agent #86 and the Terminals area) and a private release that carries the builder's own data. Counts: 86 workflow agents, 67 wrapped chat agents, 109 built-in tools, 217 migrations. See the [v1.88.0 release record](../changes/2026-10-20-v1.88.0.md) and the change records [Terminater](../changes/2026-10-19-terminater.md) and [private-release data](../changes/2026-10-19-private-release-data.md).


- **[v1.88.0 release record](../changes/2026-10-20-v1.88.0.md)** — Terminater, the Terminals area, the data-bearing private release, release facts (tag `83e0cbe6`, work in `6e129563`), counts and evidence.
- **[v1.87.0 release record](../changes/2026-10-18-v1.87.0.md)** — the 85-agent catalog, the recoverable Uninstaller, the smaller payload.
- **[v1.85.0 release record](../changes/2026-10-16-v1.85.0.md)** — Refresh, Views/Reset, centered avatar, implementation matrix, current counts and dated evidence.
- **[Interactor live editor tutor](../interactor.md)** — module-based unsaved-buffer reads, visible typing, learner handoff, local field completions and native saving; shipped in v1.90.0.
- **[Canvas Refresh](../canvas-refresh.md)** — original-source rereading, state feedback, Markdown/PDF preservation, cancellation and visible verification.
- **[Terminater](../terminater.md)** — visible, user-supervised terminals (workflow agent #86, `chat_agent_terminater`, the Terminals area on three pages, the 8th Prompt Flow Panel operation): typing rules, actions, hub/WebSocket/loopback API, verdict words, carriage, the `check_terminater` build gate. *New in v1.88.0.*
- **[2026-10-19 Terminater record](../changes/2026-10-19-terminater.md)** and **[private-release data record](../changes/2026-10-19-private-release-data.md)** — what changed, defects found while validating, dated evidence and its limits; the private (keyed) release now carries every External MCP server of the install and the whole `data.keys`.


> **HEADLESS IS FORBIDDEN. ALL EXECUTION MUST BE VISIBLE.** Every automated test, command, diagnostic, script, build, agent, prompt and browser must run in a visible, forked foreground window on Angela's real desktop. Use visible CMD/PowerShell consoles and headed browsers (`headless=False`); keep output on screen and monitor live. No hidden/background execution, including CI or quick checks. If visibility cannot be confirmed, do not run. Mandatory policy: [visible execution](../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

> **Developer/product boundary (Angela, 2026-09-27):** these visibility requirements govern development and verification. They must not create extra windows, steal focus or expose internal diagnostics in the shipped UX. Direct chat dictation keeps status in chat and uses only Tlamatini's main console/log.

This directory holds the specialized onboarding documents that back the root `CLAUDE.md`. The root file imports each of these via `@docs/claude/<name>.md` so that every assistant session loads the full set automatically.

- **[Usage dashboard](../usage-dashboard.md)** — About → Usage, actual credits/refill, plan-sensitive layouts, rolling cloud versus local recorded activity, unavailable fields, refresh/privacy, packaging and 2026-10-10 source verification.

One-line descriptions:

- **[Whole-site appearance and resize sweep](../changes/2026-10-11-ui-sweep.md)** — complete HTML/resize inventory, shared theme ownership, visible 25–400% zoom and pane/dialog/commentary checks, source validation and local evidence.

- **[Setup windows](../setup-wizards.md)** — the shared Installer/Uninstaller window (`setup_wizard.py`), its recovery transaction (`setup_recovery.py`), Windows-state scope (`setup_windows.py`), logs, preservation contract and the dated visible campaign (2026-10-11/12, shipped in `v1.82.0`); research and primary sources in [setup-lifecycle-research.md](../setup-lifecycle-research.md).

- **[Markdown canvas](../markdown-canvas.md)** — `.md` / `.markdown` Preview/Source in the chat canvas, vendored Marked + DOMPurify, source-preserving Copy / Use as context / Save, packaging and 30/30 visible verification (2026-10-11, shipped in `v1.82.0`).

- **[../build-root-assets-verification.md](../build-root-assets-verification.md)** — shared required-file build carrier, missing voice-helper repair, update/rebuild inclusion checks and dated verification limits.

- **[../dependency-coverage-audit.md](../dependency-coverage-audit.md)** - whole-repository Python dependency coverage, required manifests, private ESPHome runtime boundary and visible regression checks.

- **[../chat-microphone-design.md](../chat-microphone-design.md)** — direct Whisperer chat dictation: user steps, Config → Mic automatic Send/editable draft choices, capture preferences, host microphone, windowless worker/main logging, gate/ASR/configuration, authenticated protocol, packaging, troubleshooting and dated verification.

- **[../visual-analysis-errors.md](../visual-analysis-errors.md)** — strict configured image/video models, accumulated themed errors, preserved retries/recovery routes, PDF context behavior and visible verification.

- **[../model_configuration.md](../model_configuration.md)** — all 38 model/engine/voice settings, 21 agent mappings, defaults, inheritance, API, compatibility, frozen/source paths and release checks.
- **[../model-configuration-verification.md](../model-configuration-verification.md)** — dated source/frozen/installed execution evidence and its limits.

- **architecture.md** — Configuration, system prompt & identity, **Compact mode** (`context_fitter.py`: every request fitted to the model's REAL window, 2026-10-01, `v1.74.0`; since 2026-10-02 (`v1.75.0`) a real toolbar **switch** — `compact_mode.py` + `CompactState` — that rewrites the real Configure rows, locks ON for a model that cannot hold everything activated, prices every row, and reads ONE gate list, `tools.tool_gate_table()`; since 2026-10-08 a model's verdict (`compact_mode.VERDICT_KINDS`) only updates the box and never re-measures), **Self-Knowledge & Self-Modification** (`Tlamatini.md` → `{self_knowledge}` injection, optional `TlamatiniSourceCode/` self-modify tree — generated fresh by `copy_source_assets.py` on `build.py --self-modify`, loaded-context priority) and **The Self-modify switch** (2026-10-03: a toolbar box rendered only where self-modify exists — always in a source run, a frozen build only with `--self-modify` — ON by default, locked OFF when the model cannot hold the self-knowledge document), the Five Layers of the system, application log (`tlamatini.log`), doc generation pipeline, **`agent/services/` layer** (response post-processing + agent contracts + flow compiler), database models. Also the **Prompt Flow Panel runtime** (separate WebSocket, per-run isolation, version 2 static notes and legacy input migration). Also the **binary-content guard for context loading** (`agent/rag/binary_guard.py`) — byte-level binary detection that drops binary files from the embedding chain and logs every omission as `--- [BINARY-GUARD]` in `tlamatini.log`. And **the REAL context gauge** (2026-09-28, `v1.72.1`): Ollama's own `prompt_eval_count` on the ring, the at-rest probe of the next request, and exact byte accounting in one-shot and Multi-Turn. And **chat history and the Drop button** (2026-09-30): the history the model reads is the `AgentMessage` table, re-read on every request, so dropping a card's row makes her forget it with no reconnect. And **the Model Brain** (2026-10-08, `v1.76.0`): every model's sampling, thinking level and `num_ctx` from formal sources (`model_brain.py` + `model_profiles.json`), the learned-profile cache, `BrainChatOllama`, and the sampler triple kept as the legacy set used only with `model_brain: off`. And **console colours and the console TYPE** (2026-10-08): the window is painted by level while `tlamatini.log` stays plain text, and startup logs which program draws the window.
- **multi-turn.md** — Multi-Turn mode, **full-surface tool binding** (every enabled tool/agent/skill is bound — the fix for the starved-operator loop — plus the system-prompt + `keep_alive` cost trims), **Step-by-Step mode** (`step_by_step_enabled`, one-action-at-a-time runtime modifier), short follow-up message scoring, "Create Flow" pipeline (now backend-normalized via `/agent/flow_from_tool_calls/`), what a dropped message means for Multi-Turn (2026-09-30), **Multi-Turn on a small model** (with the Compact mode box ON it binds exactly the rows the user ticked; the self-knowledge document rides only while the Self-modify switch is ON and the model can hold it), the **Model Brain in the tool loop** (2026-10-08: `BrainChatOllama` hands a thinking model its own reasoning back between the tool calls of one answer; the self-healing watchdog stays), unified section format used by Parametrizer.
- **exec-report.md** — The Exec Report feature end-to-end: scope map, capture/render pipeline, strict ordering contract, styling, how to add a new agent to the report (capture is automatic for EVERY Multi-Turn agent since 2026-06-07), and the **deterministic verdict engine** `agent_verdict.py` whose ordered rules classify a CLOSED five-set status vocabulary from the agent's own `INI_SECTION` self-report, which OUTRANKS the process exit code. Diagnostic/work-completed rows are green; degraded/not-done/error rows are red; `test_status_vocabulary.py` prevents invented tokens and numeric-status regressions.
- **agents.md** — Backend Agent Contract registry (`agent/services/agent_contracts.py`), 8-step guide for creating a new workflow agent, naming convention transforms, agent lifecycle, connection fields, catalog of all 86 agent types (including PPTXer, PDFer, LaTeXer, NetSpeed-Calculator, and Googler's structured dork/file-discovery surface), FlowCreator AI skill, FlowHypervisor monitoring.
- **acpx.md** — ACPX (Agent Communication Protocol eXtension): authoritative definition, the 14-agent registry with transport profiles, all 12 LLM-facing tools, canonical flows (spawn-and-go, multi-CLI relay, harvest-transcript, skill-routing), runtime drain mechanics, permission model, the **ACPX toolbar toggle** (per-request enable/disable via `agent.acpx.filter_acpx_tools()`, defaults to OFF), and the "when the user says ACPX" decision matrix. (Note: the **External MCP** supervisor tools are a separate surface — NOT ACPX tools, NOT gated by the ACPX checkbox — documented in `mcp-tools.md`.)
- **mcp-tools.md** — How to add a new MCP-backed context provider, a unified-agent tool (registered in `tools.tool_gate_table()`, the ONE gate list binding, Compact mode and the Configure-dialog prices read; while Compact mode is ON a gate with no Tool row reads OFF), a wrapped chat-agent tool, **OR** a Skill (`agent/skills_pkg/<name>/SKILL.md` driven by `SkillHarness`); the **External MCPs** config-driven universal MCP client (`external_mcp_manager.py` + sanitized/preserved `external_mcps.json`, 4 transports, 10 supervisor tools, private runtime provisioner, inactive Memory/Sequential-Thinking defaults, the "External ▸ MCPs" dialog + 4 endpoints, the bulletproof contract, MCP Doctor, the `adding-external-mcp` lifecycle skill, and the contrast vs `Mcp`-model checkboxes / ACPX / inline per-agent clients); plus the hardcoded-assumption warnings around `factory.py` and the MCP UI; plus the **ACPX-Skills navbar dropdown** (Browse / Configure / Diagnostics / Reload — admin surface for the 29 SKILL.md packages).
- **frontend.md** — the shared site theme and the five pane dividers (`ui_tokens.css` / `ui_shell.css` / `ui_splitters.css` / `ui_splitters.js`, 2026-10-11, shipped in `v1.80.0`); the Markdown canvas (`agent_page_markdown.js`, shipped in `v1.82.0`); the page-wide file-drop router (`file_drop_router.js`, 2026-10-14) and the docked avatar that follows both composer dividers (2026-10-13), both shipped in `v1.83.0`; **About ▸ Usage** (`usage_dashboard.js`) and the message box that shrinks when the avatar is undocked (both 2026-10-10, shipped in `v1.78.0`); direct microphone UI and avatar handoff; the Copy + **Drop** buttons on every chat card (2026-09-30); the toolbar's **Compact mode** box (`model_capacity.js`), the per-row prices in the Configure dialogs (`compact_costs.js`) and the **Self-modify** box (`self_modify_switch.js`, rendered only where self-modify exists); the Model Brain's **Auto-tuning** dialog after Config ▸ Models ▸ Save (`model_brain_tuning.js`, 2026-10-08) and the PDF progress dialog's **Failed** step; all 59 JavaScript modules (25 chat + 15 ACP + 1 ACP entry + 15 shared + 1 welcome + 2 Prompt Flow Panel); the **chat navbar layout** (since 2026-09-25: **Panels** = Agentic Control Panel / Prompt Flow Panel / Admin Panel, and **Configure MCPs / Configure Agents** live in **Config**; the old MCPs / Agents / Admin menus are gone) and the one menu re-arm path `restoreMenuControlsAfterOperation()`; the **ACP flow-editor toolbar** (`acp-editor-tools.js`: Undo/Redo, Configure, Duplicate, Delete, Starters, Flow settings, zoom/Fit, agent search) and the edit lock `ACP.canEdit()`; the **Prompt Flow Panel** page (`.fpmt`, User Input/static User Commentary split, mixed-style floating editor and 5–95% Run output divider); the centralized dialog theme + dismissal policy (**since 2026-08-16 Escape dismisses EVERY dialog and means exactly what the titlebar ✕ means, while an outside click still never dismisses**; the dispatcher activates each dialog's own dismiss control, so Deny / resolve-false / scroll-unlock / sealed-updater-refusal all survive; `closeOnEscape: false` is a forbidden pattern, and the themed `tlmAlert` / `tlmConfirm` popups replace the last native `alert()` / `confirm()` calls); long-operation navigation locks; safe update-note rendering; chat and ACP modules; the **ACP Canvas DOM Contract** (now zoom-aware: every pointer delta is divided by `ACP.zoom`); and the shared Flow Compiler pipeline.
- **[../prompting-flow-designer.md](../prompting-flow-designer.md)** — *(NOT in this directory; consult-on-demand; ships to users beside the executable)* The **Prompt Flow Panel** user and maintainer guide: eight executable operations (seven prompting plus Terminater, on `main`), static User Commentary (inline rich text, a floating selection toolbar, all-border resizing, no configuration dialog and automatic containment without internal scrollbars), version 2 `.fpmt` files and version 1 User Input migration (and why `.pmt` stays with the system prompts), the 5–95% Run output divider with independent scrolling, shortcuts, playback/pause/stop semantics, per-run isolation, tests and release/self-modify carriage. Its filename keeps the first draft's name because `build.py`, `build_runtime_assets.py` and `copy_source_assets.py` reference that exact path.
- **gotchas.md** — Claude API client, build/packaging/linting commands, versioning quick-map, known hardcoded assumptions (items 22-38: a small model gets a COMPACT request; Compact mode rewrites the REAL Configure rows and a new built-in tool goes into `tools.tool_gate_table()`; the self-knowledge is a switch and dev mode always has it; `build.py` erases `db.sqlite3` and wipes `dist/`; the sampler keys are the legacy set and the stall clocks are gone; two accounts in one browser share one session cookie; a model's verdict never re-measures; the `v1.76.0` tag sits one commit before the Model Brain commit; Claude Code sets `NO_COLOR` and Windows Terminal is the default console; fixed chat lines are recognised by their words; an in-app update keeps the old `Uninstaller.exe`; the `v1.78.0` tag sits one commit before the Usage commit and its GitHub title still says v1.77.0; `v1.83.0` carries `91ff8453`, `63a62cc1` and `a2914019`, and no `v1.81.0` tag exists; one listener claims every dropped file; a registry read from a development console can differ from what an Explorer-launched process sees), roadmap of recommended new agents, work-style preferences for AI assistants. (The dated fix log that used to live here was split out into `recent-fixes.md` — see below.)
- **recent-fixes.md** — *(NOT auto-imported; consult-on-demand)* The chronological "Recent Fixes / Gotchas" log: dated "do NOT revert this / keep these surfaces aligned" contracts for ACPX, the Flow Compiler, the planner, the Exec Report pipeline, the ACP canvas, wrapped chat-agent parsing, the desktop-UI agents, `prompt.pmt`, `regen_secrets.py`, the logging filters, and more — newest first: **2026-10-16** (v1.85.0, Views/Reset and centered avatar), **2026-10-15** (canvas Refresh), **2026-10-14** (v1.83.0 released; one smart listener recognises every file dropped on any page), **2026-10-13** (the composer divider shrinks the docked avatar), **2026-10-12** (v1.82.0 published; the setup windows recover; a wrongly worded image/video request no longer raises the fatal dialog), **2026-10-11** (Markdown files open as a page; Video-Analyzer transcribes web links; the whole-site theme and resize sweep), **2026-10-10** (About ▸ Usage reports real balances; v1.78.0 published, the message box shrinks when the avatar is undocked, Image-Interpreter takes a comma-separated list), **2026-10-09** (first-person chat lines, the uninstaller keeps `Templates/`, the full v1.77.0 sweep), **2026-10-08** (the Model Brain replaces the stall timers; the console is coloured by level and knows its host; two chat pages on two models no longer ping-pong and a refused PDF says why; LaTeXer's `.DEGRADED.pdf` naming and region repair), **2026-10-07** (Mover preserves destinations; LaTeXer verifies the delivered PDF and reports layout overflow; the Windows access scripts include the real agent interpreters), **2026-10-05** (the uninstaller no longer fails on its own `Uninstaller.exe`; a time limit on the context sidecars' own Ollama calls), **2026-10-04** (graphical rich-text commentary, Run output resizing and the full documentation/PDF/PPTX refresh) and **2026-10-03** (the static User Commentary/User Input split, automatic containment without internal scrollbars, the four-stop-sequence limit and the Self-modify switch) and **2026-10-02** (the Compact mode switch, shipped in `v1.75.0`). It was split off `gotchas.md` (and removed from the `@`-import set) so every session's auto-loaded context stays lean. **Read it before modifying or reverting code in any of those subsystems**, and prepend new fix entries there.
- **`docs/external_mcp_bulletproof_architecture.md`** — *(NOT in this directory; NOT auto-imported; consult-on-demand)* The original design contract for the **External MCPs** universal client: 4 transports, lazy background connect, negative cache, and "never crash / never hang the chat build" invariants. Read it with `mcp-tools.md` and the 2026-08-15 section of `recent-fixes.md`, which extend the design to 10 supervisors, private runtimes, default seeding/tombstones, and public/private catalog separation.

- **[PPTXer styles and visibility](../../Tlamatini/agent/agents/pptxer/STYLES.md)** — Canonical guide for 36 named treatments, the 12 explicit styles, 17 font pairings, complete-text pagination, native audit interpretation, dated verification scope, reproduction commands, and disposable output cleanup.

- **[PDFer signature collection](../../Tlamatini/agent/agents/pdfer/STYLES.md)** — Canonical guide to 24 explicit styles in five families, the separate 20-theme semantic classifier, catalog mode, configuration precedence, vector artwork, output/audit fields, long-text handling and reproducible validation. Preview assets are optional ignored outputs. Integration details: `agents.md`, `architecture.md`, `multi-turn.md`, `exec-report.md`; dated evidence: `recent-fixes.md`.

- **[LaTeXer signature collection](../../Tlamatini/agent/agents/latexer/STYLES.md)** — Canonical guide for all 30 styles, six families, eight independent structures, engine-free discovery, screen/print and cover controls, LaTeX body helpers, output contract and real-engine verification. Integration details are in `agents.md`, `architecture.md`, `multi-turn.md`, `frontend.md` and `exec-report.md`; the 2026-09-15 entry in `recent-fixes.md` records the validation snapshot.

Read order when joining the project cold: root `CLAUDE.md` → `architecture.md` → `multi-turn.md` → `exec-report.md` → `agents.md` → `acpx.md` → `mcp-tools.md` → `frontend.md` → `gotchas.md`. Then consult `recent-fixes.md` on demand whenever you touch one of the subsystems it covers.

## Desktop control and flow contracts — 2026-09-15

Mouser now resolves explicit physical, window and screenshot coordinates; Keyboarder binds Unicode/key delivery to a verified window; Shoter publishes capture geometry. `input_sent` is delivery evidence, not application success, and a failed or interrupted input segment must be observed before replay.

Parametrizer derives its parser registry from current contracts and validates complete typed mappings. FlowCreator selects from all 86 installed agents and validates the generated graph before publishing; FlowHypervisor separates execution, kill and observation relationships and uses current desktop receipts/timing. GUI-Manager remains design only.

See [configuration, examples and limitations](../desktop-input-and-flow-contracts.md), the [complete generated coverage inventory](../agent-coverage.md), and the [GUI-Manager design](../GUI-Manager-design.md).

- **[Windows flow files](../windows-flow-files.md)** — `.flw` / `.fpmt` registration, repair, ownership-aware removal, Default Apps, source/frozen startup, authenticated file handoff, chat routing and visible validation (2026-10-04, shipped in `v1.76.0`).

- **[October 4 release validation](../changes/2026-10-04-release-validation.md)** — installation repair, owned-worker cleanup, source/frozen panel and agent checks, real model execution, package evidence and explicitly blocked cases.
