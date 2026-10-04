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

**Commentary/Input split (2026-10-03, source changes):** The Operations bar contains seven executable operations and a separate static **User Commentary** asset. **User Input** (`user_input`) keeps the old question/reply/cancellation mechanism and uses the supplied notched-top, downward-point figure. **User Commentary** (`user_commentary`) is a speech-bubble review note: double-click/Enter writes in place, Done/Ctrl+Enter saves, Escape cancels; Configure selects palette color, font, size, emphasis, alignment and dimensions. Bubbles and their editors grow to contain the full wrapped text at the chosen width/font, **without internal scrollbars**; saved height is a minimum. They move, resize, duplicate and Undo/Redo, save/open/recover with the diagram, have no ports or Start status, and never affect model context, history or playback steps. New `.fpmt` saves use version **2**; version 1 files/drafts migrate their executable commentary to User Input while preserving IDs, connections and configuration. The local-storage key still ends in `.draft.v1.<user id>` for compatibility; it does not identify the document version. Current cache suffix: `-prompt-commentary-input-1`. Verified: 61 backend/packaging tests and nine real foreground Chrome checks in `scripts/prompt_flow_commentary_visible.py`. No release executable was rebuilt. See `docs/prompting-flow-designer.md` and the 2026-10-03 entry in `docs/claude/recent-fixes.md`.

Preserve this distinction when editing the designer, importing legacy diagrams,
writing documentation or verifying the shipped example. The user explicitly
rejected internal commentary scrollbars. Automatic containment must include
font/width changes, inline typing, file/draft recovery and canvas Fit.
