<!--
Tlamatini — "one who knows"
Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove
-->

# Tlamatini instructions for Codex and every coding agent

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

Contract: [CLAUDE.md](CLAUDE.md) → *Compact mode*,
`docs/claude/architecture.md` → *Compact mode*,
`docs/claude/recent-fixes.md` (2026-10-02).

## Self-modify is a switch, only where it exists (2026-10-03)

The chat toolbar's **Self-modify** box (`#self-modify-toggle`, after Compact
mode; `self_modify_switch.js`; `CompactState.self_modify`, migration 0212, ON by
default) decides per request whether her self-knowledge (`Tlamatini.md`,
115,711 chars ≈ 28.9K tokens per request) is sent. It is on `main` right after the
`v1.75.0` tag (commit `70aeeb87`), not yet in a tag; a source run reports
`1.75.0`.

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

## Prompt Flow comments are static; User Input runs (2026-10-03)

**Commentary/Input contract (2026-10-04, source changes):** Seven executable operations remain separate from static **User Commentary**. **User Input** (`user_input`) keeps the question/reply/cancellation mechanism and notched figure. **User Commentary** (`user_commentary`) is edited entirely on the canvas: double-click/Enter writes in the bubble; a floating mini toolbar formats selected text with different fonts, sizes, text colors, bold, italic and underline within the same note. With a caret, formatting applies to newly typed text; outside editing it applies to the whole note. Bubble color and alignment affect the note. There is no commentary configuration dialog or numeric dimension form. Drag any border or corner to resize, including while editing; Fit text removes spare height. Done/Ctrl+Enter saves; Cancel/Escape restores the whole edit. Ctrl+Z/Y works inside the editor; completed edits, moves, resizes and duplicates use flow Undo/Redo. Bubbles contain their full wrapped text without internal scrollbars. Version 2 files persist allowlisted `runs` plus matching literal `text`; older plain notes normalize to one run, and version 1 executable commentary still migrates to User Input with IDs/edges/settings intact. Comments have no ports/Start/runtime/context/history/step effects. The draft key remains `.draft.v1.<user id>`. Cache suffix: `-flow-file-opening-2`. See `docs/prompting-flow-designer.md` and the 2026-10-04 verification record; the October 4 local release-validation campaign tracks subsequent isolated frozen builds and runtime acceptance.

Preserve this distinction when editing the designer, importing legacy diagrams,
writing documentation or verifying the shipped example. The user explicitly
rejected internal commentary scrollbars. Automatic containment must include
font/width changes, inline typing, file/draft recovery and canvas Fit.

## Prompt Flow Run output resizing (2026-10-04)

**Run output layout (2026-10-04, source changes):** Drag the horizontal divider to give Run output 5–95% of the combined canvas/output pane height, excluding fixed headers, status and divider (initial share: 20%). Each pane scrolls independently; resizing preserves zoom, node geometry and text size. Up/Down changes one percentage point, Shift+Up/Down five, Home/End selects 5%/95%. Escape, blur or pointer cancellation ends a drag. Collapse/reopen and window resizing retain the ratio. The per-user `tlamatini.prompting-flow.layout.v1.<user id>` preference is separate from flow files, drafts, dirty state and Undo/Redo. Keep the native details log viewport explicitly sized so its scrollbar remains usable. See `docs/changes/2026-10-04-run-output-resize.md`.


## Windows flow-file lifecycle — 2026-10-04 source changes

Both `.flw` agent flows and `.fpmt` prompting flows now have Windows registration, repair, removal, status and Default Apps handling. Explorer/source command-line opening validates a bounded snapshot, reuses a matching running server before database startup, and returns through login to the correct editor without execution. Main-chat Open/drop/Reopen routes both formats into separate editor tabs while preserving the chat document. The historical `.flw` installer wrappers cover both types for old installer/uninstaller binaries; independent management uses `flow_file_associations.ps1 -Extensions`. Never erase UserChoice or another application’s Open With entries. Update Repair respects explicit unregistration and installation ownership. See [Windows flow files](docs/windows-flow-files.md). Cache suffix: `-flow-file-opening-2`. Committed to `main` on 2026-10-04. The October 4 local release-validation campaign also rebuilds isolated frozen artifacts; its dated evidence distinguishes build completion from runtime acceptance.

## Complete release verification (2026-10-04)

For release acceptance and installer/panel regressions, use
[the release-validation skill](.codex/skills/tlamatini-release-validation/SKILL.md).
A clean-install test requires the authorized installation directory and owned
registrations to be removed first. Run the actual compiled Installer.exe with
its pkg.zip, then test the installed Admin, Prompt Flow and Agentic Control
Panels. Explicit-argument registry tests do not certify the installer’s
PowerShell -File invocation. Keep source/frozen and partial/full results distinct.
