<!--
Tlamatini — "one who knows"
Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove
-->

# Tlamatini instructions for Codex and every coding agent

> Current release: **[v1.90.0](docs/changes/2026-10-22-v1.90.0.md)**. Dated records below retain their original evidence dates.

## v1.90.0 — editable canvas and Interactor

The current source has **86 workflow agents, 67 wrapped chat agents, 110 built-in tools (21 direct/module + 67 wrapped + 12 ACPX/Skills + 10 supervisors), and 218 migrations**. Interactor adds a module/tool; do not register it as an Agent. The annotated tag resolves to `ebc5c3b4`; the documentation baseline is the follow-up `d274f89c` on main. Dated source and frozen runs remain separate.

- **Editor:** `agent_page_editing.js` owns the CodeMirror document, dirty baseline, encoding and save snapshot. `agent_page_canvas.js` owns load/refresh generation and cancellation. Markdown Preview and Source share the buffer; HTML/SVG remain inert source; PDF saving copies the original PDF. Never read a hidden compatibility element instead of the editor.
- **Native files:** `canvas_file_views.py` and `native_dialogs.py` provide local Save As/read/save. Authentication, CSRF, loopback-only host access, account/session-bound capabilities and full revision checks prevent a browser name from becoming an arbitrary host path. Existing Windows replacement preserves metadata; DB backup/restore mechanics are unchanged.
- **Interactor:** `agent/interactor/` connects the synchronous tool loop to the browser through session-authenticated `ws/interactor/`. Server-issued tab identity travels through ContextVar; bounded commands and receipts verify document/revision and full buffer. Browser messages acknowledge/access/stop; they cannot request arbitrary host-path commands.
- **Tutor:** read fresh unsaved text, type a small segment, guide the next field and end mutations for the turn. Continue begins a fresh chat/read. Prepared choices match locally, with no per-key model call. User input and Stop win; hidden tabs pause with bounded recovery rather than repeating edits.
- **Carriage:** migration 0218 seeds the Tool/catalog rows; `tool_gate_table()` supplies binding, Compact selection and cost labels. The offline editor bundle, Interactor browser files, frozen imports and source/static inventories must travel together.
- **Intent:** password input is not ownership of every command; a wizard email field or DONE reply is not notification consent. Preserve genuine user-runs tutorials. The catalog wizard uses createsuperuser and therefore creates an administrative account.

Contracts and evidence: [v1.90.0](docs/changes/2026-10-22-v1.90.0.md), [Canvas editing](docs/canvas-editing.md), [Interactor](docs/interactor.md), [Account wizard](docs/user-creation-wizard.md). Source/frozen rendering tests do not certify a rebuilt installed executable.



## v1.88.0 — Terminater and the private release's data

> **Released as v1.88.0** (tagged 2026-10-20). The v1.88.0 tag points to `83e0cbe6`;
> this work landed on `main` in `6e129563` right after it, so a build of `main`
> reports `1.88.0` and carries it. Records: [v1.88.0](docs/changes/2026-10-20-v1.88.0.md),
> [Terminater](docs/changes/2026-10-19-terminater.md) and
> [the private release's data](docs/changes/2026-10-19-private-release-data.md).

**Counts in v1.88.0:** **86 workflow agents, 67 wrapped chat agents, 109 built-in
tools** (20 + 67 + 12 + 10), 51 structured-output producers, **217 migrations**
(0215-0217), 60 JS modules, 27 stylesheets. The static suffix for that release was
`-agent-catalog-1-quality-cleanup-1-usage-status-2-terminater-1`.

**Terminater** (agent #86; full contract in [docs/terminater.md](docs/terminater.md))
raises REAL `cmd.exe` / PowerShell terminals in the **Terminals** area (**Views ▸
Terminals**, Ctrl+`) where the USER watches. Executer returns text from an invisible
shell; Terminater types the command into a terminal the user sees, waits, and reads it
back. Contracts that must not be weakened:

- **Tlamatini types, never pastes.** One key at a time at `typing_wpm` (default 50,
  20-160, never faster than 30 ms per key); there is no instant mode. Output is kept in
  full with an honest `truncated` flag; a command silent for `hang_seconds` (45) is
  `hung` and can be aborted; the user always wins (Esc takes over; `<<USER:hint>>` hands
  the keyboard over; `watch_user` and a deterministic advisor help while they type).
- **One hub, three doors.** A single `TerminalHub` lives in the Django process
  (`terminal_hub.py`; its engine `agents/terminater/terminater_engine.py` is loaded BY
  PATH from the agents tree so the web process, the pool agent and the tests share one
  definition; the three engine files are stdlib-only). Doors: `ws/terminals/`
  (session-authenticated), `POST /agent/terminater/api/` (loopback only +
  `X-Terminater-Token`, token scrubbed from the shells' environment, rendezvous file
  `<app>/Temp/.terminater_hub.json`) and the in-process Prompt Flow Panel runner.
  Closing a page never kills a shell. The reapers ask `terminal_hub.live_pids()` and the
  hub's shells die with Tlamatini.
- **Surfaces.** `chat_agent_terminater` (on the Ask Execs allowlist: visible is not
  harmless), an ordinary active canvas agent, and the 8th executable Prompt Flow Panel
  operation (the kickoff example deliberately has none; the build gate validates one
  separately). Result words: `completed`/`opened`/`typed`/`killed`/`focused`/`warned`
  green; `command_failed`, `hung`, `operator_required`, `aborted` red.
- **Carriage.** Migrations 0215 (Agent row), 0216 (`Chat-Agent-Terminater` Tool row) and
  0217 (catalog prompts 127-129, *Run & Execute*); the display name is pinned in
  `display_name_from_agent_type`; the **`agents_descriptions.md` row feeds the canvas
  tooltip**, so a missing row is a visible defect. `build.py` names the hub, consumer,
  views and `check_terminater` as frozen modules and runs `check_terminater` (real
  PowerShell, real `cmd.exe`, the pool agent under the carried Python, a WebSocket round
  trip) inside the frozen app, refusing to package on failure. xterm.js is vendored
  locally (5.5.0, no CDN).

**The private (keyed) release now carries the data of THIS machine**
(`build_complete_private_release.py`; details in
[the record](docs/changes/2026-10-19-private-release-data.md)): contacts (as before);
**every External MCP server of the running install** merged into the gitignored
`external_mcps.private.json` (the tracked dev catalog still wins for servers both have;
only empty or placeholder values are filled; the install's active selection, at most
5, is kept; the previous snapshot stands in when no install is found); and the whole
**`data.keys`** vault shipped as `<install>/data.keys` through
`TLAMATINI_BUNDLE_DATA_KEYS`. The public builder clears that variable, `build.py` aborts
if the vault is requested with the PUBLIC catalog, and the new file is gitignored and
excluded from the self-modify snapshot. Not solved: an in-app update does not preserve
`data.keys`, and two entries (`OPENROUTER_API_KEY`, `DASHSCOPE_API_KEY`) have no
consumer other than the vault itself.

## v1.87.0 — Leaner catalog, safer removal, smaller release (carried)

**v1.87.0** (tagged 2026-10-18; it also carries
v1.86.0, tagged 2026-10-17) came before v1.88.0. Its catalog was **85 workflow agents, 66 wrapped
chat agents and 108 built-in tools**: Gatewayer, Gateway-Relayer, Node-Manager
and Zavuerer were removed, and migration **0214** deletes their rows and the
Zavuerer prompts without renumbering. Removal moves application entries into a
same-drive recovery folder (schema 2 journal, **Retry cleanup**,
`.tlamatini-removal.json`) instead of copying the payload. `build.py` keeps the
carried-Python-only media and browser packages out of the frozen interpreter
(`test_release_payload_ownership.py`). About ▸ Usage waits for real data and
sends a bodyless `POST /api/me`. `npm run lint:python` runs
`scripts/check_python_quality.py`. From v1.86.0: Mover creates a missing
destination name as a folder (`_names_a_file()`), and `scripts/architecture_atlas/`
rebuilds `Tlamatini-Architecture.pdf` with LaTeXer. The static suffix for that release was
`-agent-catalog-1-quality-cleanup-1-usage-status-2`.

See [the v1.87.0 release record](docs/changes/2026-10-18-v1.87.0.md).

## v1.85.0 — Refresh, Views and centered avatar (carried)

**v1.85.0** (2026-10-16) added Refresh, Views and the centered avatar. `agent_page_canvas.js` owns Refresh
source access, complete-text comparison, cancellation and status. Retain browser
file handles during the drop event; snapshot-only access cannot refresh a path.
PDF replacement stages a ready viewer and keeps its iframe attached at commit.

`agent_page_layout.js` exposes `TlamatiniViews.setCanvasVisible`,
`isCanvasVisible` and `resetLayout`. Hiding toggles `tlm-canvas-hidden`, preserves
the canvas DOM and context, cancels divider gestures and moves focus only when
its current region disappears. The account/browser preference is
`tlamatini.chat.views.v1.<user id>`. `avatar_size.js::setDockedOnly` enforces the
hidden-canvas docking rule in pointer, keyboard and public API paths. Reset shows
both panes, resets their sizes and docks the portrait without clearing content.

The docked frame uses `--tlm-avatar-docked-right` measured from the full Mic/Send
row. Its square size and 120 px minimum stay independent of floating geometry.
v1.85.0's static suffix was `-avatar-center-1`; Views scripts retain `_views1`.
`build_runtime_assets.py` and `copy_source_assets.py` require the Views template,
scripts and snapshot harnesses. No migration or dependency was added.

See [the release implementation and evidence matrix](docs/changes/2026-10-16-v1.85.0.md),
[Refresh](docs/canvas-refresh.md) and [carriage](docs/self-management-carriage.md).



## HEADLESS IS FORBIDDEN. ALL EXECUTION MUST BE VISIBLE.

Angela reaffirmed this mandatory repository rule on 2026-09-23. Read
[TestsVisiblesAndVisibleExecutionFromClaude2Codex.md](TestsVisiblesAndVisibleExecutionFromClaude2Codex.md)
before executing anything. This applies to every automated test, command,
diagnostic, script, build, agent, prompt, CMD/PowerShell session and browser.

- Run in a **visible, forked foreground window on Angela's real desktop**.
  Keep consoles and browsers visible while the work runs, and leave the console
  open afterward so its output can be read. Use PowerShell `-NoExit` or CMD `/k`.
- Browser automation must explicitly use **`headless=False` / `headless: false`**.
  Never rely on a browser library's default. Headless mode is forbidden for CI,
  smoke checks, diagnostics, long runs and all other execution too.
- With Tlamatini's Executer/Pythonxer, use `execute_forked_window: true`;
  with `execute_file`, request `foreground=True`; with Playwrighter, use
  `headless: false` and sufficient `hold_open_seconds` for inspection.
- Never use hidden/minimized windows, `run_in_background`, detached jobs,
  `CREATE_NO_WINDOW`, `DETACHED_PROCESS`, or `-WindowStyle Hidden` to perform
  the requested work. A saved log or screenshot is not a substitute for visibility.
- Verify that the actual window is visible on the interactive desktop before
  running the workload. A PID, successful launch call, or activation request
  alone does not establish that. **If visibility cannot be confirmed, do not
  execute the workload; explain the limitation to Angela.**
- Monitor long runs live. Read the live transcript every 5–15 seconds, report
  meaningful progress or failures, and inspect the first error and application
  log. Record the exit code and final result; never report unseen work as watched.
- Every new skill, runbook, harness and execution example must preserve this rule.
  Legacy headless flags must be refused loudly and must never enable a hidden
  browser. Review launch sites and fallbacks, not only default settings.

The linked policy contains the concrete launch instructions. It governs development and verification, including tests of background product
implementation. It does not require additional end-user service windows.

## Product UX boundary — clarified by Angela on 2026-09-27

The visibility rule governs our development work and verification. It must not
be imposed on end users as extra application windows. Internal chat dictation
runs without a separate console or foreground activation; its status belongs in
the chat and its diagnostics in Tlamatini's main console/log. Verify this product
behavior from a visible development console. Do not reintroduce a persistent
Whisperer PowerShell/conhost window or require its visibility to enable recording.

## About → Usage — 2026-10-10, shipped in `v1.78.0`

The new **ABOUT USAGE** dialog stays available during an answer. It reads actual
Ollama credits, allowance, usage and refill weeks/date; presents rolling cloud
token/request charts; and separates per-user recorded chat/model statistics.
It uses the shared dialog theme, normal fonts, at most two decimal places and
less than 60% of the browser client area. Missing fields are explained, never
invented. Monthly, legacy-limit and purchased-only layouts follow the response.
The cloud API does not expose the website’s full per-model breakdown.

It ships in the published `v1.78.0` release, with its outage recovery: a brief
Ollama failure is retried after 15 s and Refresh rechecks a refused connection. See the
[Usage guide and evidence](docs/usage-dashboard.md).

## Existing repository contracts

Read [CLAUDE.md](CLAUDE.md) and relevant documents indexed by
[docs/claude/INDEX.md](docs/claude/INDEX.md). Preserve unrelated local edits.
Never rewrite Git history. Do not modify the protected database backup/restore
mechanics unless Angela explicitly requests it in the current turn.

## Compact mode is a real switch (2026-10-02)

Since 2026-10-02 (shipped in `v1.75.0`, tag at `f7eb53ff`) the chat
toolbar's **Compact mode** box (`#compact-mode-enabled`; `agent/compact_mode.py`,
model `CompactState`, migration 0211) rewrites the REAL Configure rows:

- Ticking it unticks every MCP, tool, agent and skill row (Config ▸ Configure
  MCPs, Configure Agents, ACPX-Skills) except **System-Metrics, Files-Search and
  Current-Time**, and pauses the External MCPs (the active list is saved, then
  restored). The user ticks back only what she needs; a Compact request binds
  exactly the ticked tools. Unticking it ticks EVERY row again.
- **STRICT = locked ON:** a model that cannot hold everything activated switches
  the box ON by itself and locks it (greyed, 🔒); the server refuses a forged
  untick. A big model unlocks it and keeps Compact ON until the user unticks it.
- Saved Configure dialogs apply at once (`compact_mode.after_toggles_saved`);
  there is no "restart the agent" any more. The old Compact badge and ACPX lock
  are gone: ACPX tools ride along only when their rows are ticked AND the
  toolbar's ACPX box is on.
- The gauge legend reads **CONTEXT-WINDOW** and may pass 100 % (`OVER`); a cut
  request shows `CUT · read X of ≈Y tokens`, and its answer carries a
  CONTEXT-WINDOW warning line. The Configure dialogs price every row
  (`compact_costs.js`, `GET /agent/compact_mode/costs/`).
- Register every new built-in tool in **`tools.tool_gate_table()`**, the one
  gate list that binding, Compact mode and the cost labels read.
- A model's VERDICT (`compact_mode.VERDICT_KINDS`: `capacity`,
  `self_modify_fit`) updates every tab's box and stops there; it must never
  re-send rows or re-measure, or two pages on two models ping-pong forever
  (2026-10-08, `v1.76.0`).

Contract: [CLAUDE.md](CLAUDE.md) → *Compact mode*,
`docs/claude/architecture.md` → *Compact mode*,
`docs/claude/recent-fixes.md` (2026-10-02).

## Self-modify is a switch, only where it exists (2026-10-03)

The chat toolbar's **Self-modify** box (`#self-modify-toggle`, after Compact
mode; `self_modify_switch.js`; `CompactState.self_modify`, migration 0212, ON by
default) decides per request whether her self-knowledge (`Tlamatini.md`,
size measured from the current document per request) is sent. It shipped in `v1.76.0`
(commit `70aeeb87`, on `main` right after the `v1.75.0` tag).

- **Who sees it:** `rag/config.self_modify_available()`. A source (dev) run of
  this checkout is ALWAYS self-able; a frozen build only when
  `build.py --self-modify` bundled `TlamatiniSourceCode/`. Otherwise the box and
  its script are not rendered at all (`{% if self_modify_available %}`).
- **ON** sends the identity bullets and the whole `<self_knowledge>` section as
  before; **OFF** replaces the bullets with `SELF_MODIFY_OFF_NOTICE` (she must
  not read, edit or rebuild her own code) and drops the section. No marker is
  ever left in a prompt.
- **Only when it fits:** a model that cannot hold it shows the box unticked,
  greyed and 🔒, and the server refuses a forged tick. Her choice is never
  rewritten; a big model unlocks it by itself. Compact mode's STRICT check is
  measured WITHOUT the self-knowledge.
- ⚠️ **`build.py` ERASES `Tlamatini/db.sqlite3` and wipes `dist/`** before it
  builds. Never run it just to "test the frozen mode"; `FrozenPageTests` render
  the real chat page as a frozen build. Ask Angela before any real build.

Contract: [CLAUDE.md](CLAUDE.md) → *Self-modify*,
`docs/claude/architecture.md` → *The Self-modify switch*,
`docs/claude/recent-fixes.md` (2026-10-03).

## v1.83.0 — a smart file-drop router, a docked avatar that follows both dividers (2026-10-14)

`v1.83.0` (annotated tag at `a2914019`, pushed 2026-10-14) — *"Release v1.83.0 A smart file-drop router
for every page: each dropped file is recognised by its bytes and sent to its own mechanism, so an MCP
.json imports everywhere and never errors, opens as text or navigates away."* It was published on GitHub
on 2026-10-14 ("Tlamatini Release v1.83.0 Win11x64", marked Latest), so self-update delivered `v1.83.0` then;
that historical runtime version was `1.83.0`. The current release is `v1.90.0`. `v1.83.0` carried everything in `v1.82.0` plus the three
changes below. `v1.83.0` added no migration after 0213 (0214 arrived in v1.87.0); the frontend has 60 JS modules and 26
stylesheets, and the live `STATIC_VERSION` cache suffix is now `-agent-catalog-1-quality-cleanup-1-usage-status-2`.

- **File-drop router (`a2914019`).** `static/agent/js/file_drop_router.js` is the ONE listener for files
  dropped on any page, in the `<head>` of the chat, the Agentic Control Panel, the Prompt Flow Panel,
  welcome, login (`data-auth="none"`), the Django admin and the PDF viewer iframe (which relays to its
  parent). It claims only `Files` drags, in the capture phase, classifies each file by its bytes
  (extension, MIME, magic numbers, a BOM-aware text/binary test, and a real JSON parse that recognises an
  MCP config in any shape, UTF-16 from PowerShell included) and sends each kind to its own mechanism: MCP
  `.json` → confirm, then the External MCP catalog; `.flw` → the ACP canvas or a new ACP tab; `.fpmt` →
  the Prompt Flow Panel or a new tab; image → attached to the message (saved in `Temp`); PDF / Markdown /
  code / plain JSON → the chat canvas; folder / archive / binary → a plain-words explanation. Pages
  register with `TlamatiniFileDrop.register(kinds, fn, {label})`; the label also drives the drag-time
  overlay. It replaced four per-page handlers (the chat zone listeners with `#chat-drop-overlay`, the
  canvas blind-open drop target, the External MCPs dialog's private drop import — that dialog now
  refreshes on the `tlm:external-mcps-imported` event — and the Prompt Flow Panel viewport drop).
  Contracts: capture phase and `Files` only; an MCP import is never silent; the flow tab is reserved
  synchronously in the drop task; a bare name→server map counts only if EVERY value is a server; login
  never imports or navigates. Proof: `scripts/file_drop_router_cases.mjs` (138 checks),
  `agent/test_file_drop_router.py` (22 tests), 319 Django tests in the touched suites, ESLint with 0
  errors, and a headed-Chrome run of 58/58 checks with 24 Shoter photos
  (`.claude/skills/tlamatini-daily-chat-test/harness/file_drop_visible.py`). Contract
  `docs/claude/frontend.md`; story `docs/claude/recent-fixes.md` (2026-10-14).
- **Docked avatar (`63a62cc1`, 2026-10-13).** The vertical composer divider now shrinks the DOCKED
  portrait as well as the message box. The dock side is `max(120, floor(min(25 % of the form width,
  available portrait height)))`; the initial quarter-width portrait is kept until the user first moves
  the bar, and the composer minimum reserves only 120 px plus its controls — never the avatar's current
  width, which is exactly what used to lock vertical shrinking. `agent_page_layout.js` sets
  `--tlm-avatar-docked-size`, `avatar.css` applies it only while docked, `avatar_size.js` keeps floating
  geometry and persistence. At 1440 CSS px the portrait went from 282 px to 120 px. Verified in headed
  Chrome (19 docked-avatar and 18 composer checkpoints) plus 7 focused source tests; credited to
  Tlamatini's-AutoBot. Record `docs/changes/2026-10-13-docked-avatar-divider.md`.
- **A wrongly worded request is not fatal (`91ff8453`, 2026-10-12).** When the wrapped-agent launcher
  refuses a call BEFORE the agent starts (a setting the agent does not have, or a mandatory one missing)
  it returns `error_kind: "request"`, and `tools._is_visual_start_failure` keeps that refusal from
  raising the red Fatal analysis errors dialog for Image-Interpreter / Video-Analyzer; a real start
  failure still raises it. Video-Analyzer has NO `transcription.engine` setting (`engine=` belongs to
  Whisperer). Pinned by `agent/test_visual_fatal_errors.py::RequestRefusalIsNotFatalTests` (5 tests);
  credited to Tlamatini's-AutoBot.

## v1.82.0 — setup windows that recover, Markdown as a page (2026-10-12); v1.80.0 and v1.79.0 (2026-10-11)

`v1.82.0` (annotated tag at `880a335e`, pushed 2026-10-12) names the new setup windows. It was
published on GitHub on 2026-10-12 and was marked Latest until `v1.83.0` replaced it on
2026-10-14; `v1.83.0` carries everything below. There is no `v1.81.0` tag. `v1.80.0` (`82099963`)
and `v1.79.0` (`5f549868`), both tagged and pushed on 2026-10-11, have no published release of
their own; they reach users through `v1.82.0` and `v1.83.0`.

- **Setup windows (v1.82.0).** `install.py` / `uninstall.py` drive one `setup_wizard.py` window.
  `setup_recovery.py` prepares and verifies a recovery copy before any file changes (journal
  `Temp/.setup-recovery`; an interrupted run is restored first; a failed restore is reported, never
  hidden); a locked file gets a five-second retry and is then named with its holder (read-only
  Restart Manager; it never closes that program). `setup_windows.py` snapshots only Tlamatini's own
  registry values and Desktop shortcut. PowerShell helpers are non-interactive and bounded to 120 s
  in a Windows job; a mutex refuses concurrent setup. Preservation is unchanged. Custom EXE recovery,
  NOT an MSI transaction. Guide `docs/setup-wizards.md`; visible harnesses `scripts/setup_*`.
- **Markdown canvas (v1.82.0).** `.md` / `.markdown` open in a sanitized Preview (vendored Marked
  18.1.0 + DOMPurify 3.4.16) with a Source view; Copy / Use as context / Save take the source bytes.
  `docs/markdown-canvas.md`. Cache suffix at that change: `-markdown-canvas-1`.
- **One look (v1.80.0).** `ui_tokens.css` / `ui_shell.css` / `ui_splitters.css` / `ui_splitters.js`,
  `entry_pages.css`, `admin_theme.css` + `templates/admin/base_site.html`; keep `dialog_theme.css`
  last. `docs/changes/2026-10-11-ui-sweep.md`.
- **Video-Analyzer web links (v1.79.0).** `video_fetch.py` downloads one item itself; never let the
  model install a downloader. `91ff8453` (shipped in `v1.83.0`, see above) stops a wrongly worded
  request from raising the fatal image/video dialog (`error_kind: "request"`) and says
  Video-Analyzer has no `transcription.engine`.

## v1.78.0 — About ▸ Usage, a message box that shrinks, Image-Interpreter lists (2026-10-10)

`v1.78.0` (annotated tag at `0e6fc72d`, pushed 2026-10-10) names the Usage dialog. The
Usage commit `7460a147` and `113eddc4` (message-box resize + Usage outage recovery) landed
right after the tag, so a build of `main` reported `1.78.0` (until the `v1.79.0` tag) and carried everything below.
It was published on GitHub on 2026-10-10 (marked Latest; its release title still reads
"v1.77.0"), so self-update delivered `v1.78.0` until `v1.82.0` was published on 2026-10-12; the published zip matches `113eddc4`.

- **About ▸ Usage** (migration 0213 `UsageDaily`): see *About → Usage* above and
  `docs/usage-dashboard.md`.
- **Message box.** With the avatar undocked the input form shrinks to its own action
  buttons (the 30% floor is gone); docking restores the portrait's room. Keyboard: arrows,
  Shift+arrows, Home/double-click (smallest), End (tallest); Escape ends a drag.
  `agent_page_layout.js`, `avatar_size.js`, `dialog_policy.js::fitDialog`; record
  `docs/changes/2026-10-10-composer-resize.md`.
- **Image-Interpreter** accepts a comma-separated list of images (each resolved, merged,
  de-duplicated; a single file with a comma in its name is never split). Commit `0e6fc72d`,
  credited to Tlamatini's-AutoBot; no dedicated test yet.

## v1.77.0 — first-person chat lines, the uninstaller keeps Templates (2026-10-09)

`v1.77.0` (annotated tag at `052bfe0f`, pushed 2026-10-09) carries the two
changes below; a build of `main` reported `1.77.0` until the `v1.78.0` tag. It was published on
GitHub on 2026-10-09; self-update delivered `v1.77.0` until `v1.78.0` was published on 2026-10-10.

- **First person, by name.** Every fixed chat line Tlamatini sends (`agent/constants.py`) speaks in the
  first person and names the user (`display_name()` + `say()`; with no name the placeholder and its comma
  vanish). Several lines are recognised BY THEIR WORDS: change one and update `agent_page_ui.js`,
  `agent_page_chat.js`, `avatar.js`, `agents/teletlamatini/teletlamatini.py` and the harness markers in
  the same pass; the old phrases stay matched on purpose.
- **Uninstaller.** `application`, `applications`, `content_generated`, `context_files`, `doc_generated`
  and `Templates` are kept whenever they hold a file; `Temp/` is erased; `agents/` is always kept
  (`uninstall.py::PRESERVED_WHEN_NOT_EMPTY`, commit `0520dc97`). An in-app update keeps the old
  `Uninstaller.exe`; only a new Installer replaces it.

## v1.76.0 — the Model Brain, a coloured console, honest PDF refusals (2026-10-08)

`v1.76.0` (annotated tag, pushed) names the Model Brain. The tag points to
`953ad2d8`; the Model Brain commit `72799950` landed right after it, so a build
of `main` reported `1.76.0` (until the `v1.77.0` tag) and carried everything below. It was published on
GitHub on 2026-10-09; self-update delivered `v1.76.0` until `v1.77.0` was
published the same day.

- **Model Brain** (`agent/model_brain.py`, `model_profiles.json`): every model
  is tuned from formal sources — an explicit `model_brain_overrides` entry, the
  sourced knowledge base, a profile learned once from Hugging Face for an
  unknown model, then Ollama's `/api/show`. `num_ctx` is clamped to the real
  context length, and thinking models get their own reasoning back inside the
  current tool loop. Config ▸ Models ▸ Save opens the Auto-tuning dialog;
  `model_brain: off` restores the legacy fixed sampling. Never hard-wire a
  model name, and never re-add the stall timers the Model Brain replaced.
- **Console colours** (`manage.py::_ConsoleColorizer`, `console_colors`): the
  WINDOW is painted by level while `tlamatini.log` stays plain text; startup
  logs the console host (`--- [CONSOLE] host: …`). Windows Terminal is the
  default console on Windows 11, and Claude Code sets `NO_COLOR` for the
  programs it launches.
- **PDF refusals say why:** when a second account signs in from the same
  browser, the upload goes out as that account; the chat now names the cause
  and says to reload (F5), the header comes back, the running step shows
  **Failed**, and the server logs `[PDF-CONTEXT] refused for user N`.
- **Compact verdicts never re-measure** (`compact_mode.VERDICT_KINDS`): two
  chat pages on two models used to re-measure each other forever.
- **File-Creator `append`** adds to the end of a file instead of overwriting it.

Contract: [CLAUDE.md](CLAUDE.md) → *The Model Brain*, *The console is
coloured by level*, *A refused PDF says why*; `docs/claude/recent-fixes.md`
(2026-10-08).

## Prompt Flow comments are static; User Input runs (2026-10-03)

**Commentary/Input contract (2026-10-04, shipped in `v1.76.0`):** Executable operations (seven at that date, eight with Terminater on main) remain separate from static **User Commentary**. **User Input** (`user_input`) keeps the question/reply/cancellation mechanism and notched figure. **User Commentary** (`user_commentary`) is edited entirely on the canvas: double-click/Enter writes in the bubble; a floating mini toolbar formats selected text with different fonts, sizes, text colors, bold, italic and underline within the same note. With a caret, formatting applies to newly typed text; outside editing it applies to the whole note. Bubble color and alignment affect the note. There is no commentary configuration dialog or numeric dimension form. Drag any border or corner to resize, including while editing; Fit text removes spare height. Done/Ctrl+Enter saves; Cancel/Escape restores the whole edit. Ctrl+Z/Y works inside the editor; completed edits, moves, resizes and duplicates use flow Undo/Redo. Bubbles contain their full wrapped text without internal scrollbars. Version 2 files persist allowlisted `runs` plus matching literal `text`; older plain notes normalize to one run, and version 1 executable commentary still migrates to User Input with IDs/edges/settings intact. Comments have no ports/Start/runtime/context/history/step effects. The draft key remains `.draft.v1.<user id>`. Cache suffix at that change: `-flow-file-opening-2`. See `docs/prompting-flow-designer.md` and the 2026-10-04 verification record; the October 4 local release-validation campaign tracks subsequent isolated frozen builds and runtime acceptance.

Preserve this distinction when editing the designer, importing legacy diagrams,
writing documentation or verifying the shipped example. The user explicitly
rejected internal commentary scrollbars. Automatic containment must include
font/width changes, inline typing, file/draft recovery and canvas Fit.

## Prompt Flow Run output resizing (2026-10-04)

**Run output layout (2026-10-04, shipped in `v1.76.0`):** Drag the horizontal divider to give Run output 5–95% of the combined canvas/output pane height, excluding fixed headers, status and divider (initial share: 20%). Each pane scrolls independently; resizing preserves zoom, node geometry and text size. Up/Down changes one percentage point, Shift+Up/Down five, Home/End selects 5%/95%. Escape, blur or pointer cancellation ends a drag. Collapse/reopen and window resizing retain the ratio. The per-user `tlamatini.prompting-flow.layout.v1.<user id>` preference is separate from flow files, drafts, dirty state and Undo/Redo. Keep the native details log viewport explicitly sized so its scrollbar remains usable. See `docs/changes/2026-10-04-run-output-resize.md`.


## Windows flow-file lifecycle — 2026-10-04, shipped in `v1.76.0`

Both `.flw` agent flows and `.fpmt` prompting flows now have Windows registration, repair, removal, status and Default Apps handling. Explorer/source command-line opening validates a bounded snapshot, reuses a matching running server before database startup, and returns through login to the correct editor without execution. Main-chat Open/drop routes both formats into separate editor tabs while preserving the chat document. The historical `.flw` installer wrappers cover both types for old installer/uninstaller binaries; independent management uses `flow_file_associations.ps1 -Extensions`. Never erase UserChoice or another application’s Open With entries. Update Repair respects explicit unregistration and installation ownership. See [Windows flow files](docs/windows-flow-files.md). Cache suffix at that change: `-flow-file-opening-2`. Committed to `main` on 2026-10-04. The October 4 local release-validation campaign also rebuilds isolated frozen artifacts; its dated evidence distinguishes build completion from runtime acceptance.

## Complete release verification (2026-10-04)

For release acceptance and installer/panel regressions, use
[the release-validation skill](.codex/skills/tlamatini-release-validation/SKILL.md).
A clean-install test requires the authorized installation directory and owned
registrations to be removed first. Run the actual compiled Installer.exe with
its pkg.zip, then test the installed Admin, Prompt Flow and Agentic Control
Panels. Explicit-argument registry tests do not certify the installer’s
PowerShell -File invocation. Keep source/frozen and partial/full results distinct.
