<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Required runtime files: packaging repair and verification

> Current release: **[v1.91.0](changes/2026-10-23-v1.91.0.md)**. Dated records below retain their original evidence dates.

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
See the [release record](changes/2026-10-23-v1.91.0.md) and
[settings guide](interaction-settings.md).

## Carried from v1.90.0 — editable canvas and Interactor

The v1.90.0 source line had **86 workflow agents, 67 wrapped chat agents, 110 built-in tools (21 direct/module + 67 wrapped + 12 ACPX/Skills + 10 supervisors), and 219 migrations** after migration 0219. Interactor added a module/tool, not an Agent. The annotated tag resolves to `ebc5c3b4` and its GitHub release was published on 2026-10-22. Later commits in that line carried the account wizard’s local Notifier checkpoints. This section preserves v1.90.0 history; current configuration and counts are described above. Dated source and frozen runs remain separate.

- **Editor:** `agent_page_editing.js` owns the CodeMirror document, dirty baseline, encoding and save snapshot. `agent_page_canvas.js` owns load/refresh generation and cancellation. Markdown Preview and Source share the buffer; HTML/SVG remain inert source; PDF saving copies the original PDF. Never read a hidden compatibility element instead of the editor.
- **Native files:** `canvas_file_views.py` and `native_dialogs.py` provide local Save As/read/save. Authentication, CSRF, loopback-only host access, account/session-bound capabilities and full revision checks prevent a browser name from becoming an arbitrary host path. Existing Windows replacement preserves metadata; DB backup/restore mechanics are unchanged.
- **Interactor:** `agent/interactor/` connects the synchronous tool loop to the browser through session-authenticated `ws/interactor/`. Server-issued tab identity travels through ContextVar; bounded commands and receipts verify document/revision and full buffer. Browser messages acknowledge/access/stop; they cannot request arbitrary host-path commands.
- **Tutor:** read fresh unsaved text, type a small segment, guide the next field and end mutations for the turn. Continue begins a fresh chat/read. Prepared choices match locally, with no per-key model call. User input and Stop win; hidden tabs pause with bounded recovery rather than repeating edits.
- **Carriage:** migration 0218 seeds the Tool/catalog rows; `tool_gate_table()` supplies binding, Compact selection and cost labels. The offline editor bundle, Interactor browser files, frozen imports and source/static inventories must travel together.
- **Intent:** password input is not ownership of every command; a wizard email field or DONE reply is not notification consent. Preserve genuine user-runs tutorials. The catalog wizard uses createsuperuser and therefore creates an administrative account.

Contracts and evidence: [v1.90.0](changes/2026-10-22-v1.90.0.md), [Canvas editing](canvas-editing.md), [Interactor](interactor.md), [Account wizard](user-creation-wizard.md). Source/frozen rendering tests do not certify a rebuilt installed executable.



Verified on 2026-09-27 in visible foreground PowerShell consoles, retained with
`-NoExit`. Every workload first confirmed its console was visible, foreground
and not minimized. No Git command, commit, live update or database operation
was executed.

## Failure and repair

The build stopped while creating the verified runtime receipt:

```text
Frozen release lost or changed a required source asset: chat_voice_settings.py
```

`build_runtime_assets.ROOT_SOURCES` required the worker's loose settings helper,
but `build.py` maintained a separate required-file copy dictionary that omitted
it. A compiled `agent.chat_voice_settings` module alone cannot satisfy the
standalone Whisperer worker running under carried Python.

`build.py` now calls `copy_root_sources(repo_root, dist_manage)`. The copier uses
the verifier's inventory directly, checks all inputs before copying, creates
destination directories and copies source bytes. The pre-freeze hash baseline
still rejects files changed during a build. Required receipt entries now include
every `ROOT_SOURCES` destination, so both ZIP and extracted update verification
reject a missing helper even if someone also removes it from the receipt.

The self-update sweep understands this carrier and offers explicit `--no-git`
working-file checks. Normal sweeps retain their tracked-file/history checks.
The self-modify sweep includes the same inventory in its build-input census;
snapshot validation already checks every runtime source input. Both `.claude`
and `.gemini` skill/script mirrors document the shared contract.

## Verification results

| Check | Result |
| --- | --- |
| Focused build, root-asset, panel-carriage, self-update, self-modify, preservation, security-carriage and pip-policy suite | 146 tests run: 145 passed, 1 skipped; exit 0 |
| Actual build carrier invoked against source files | Every mapped destination matched its source bytes |
| Newly declared root asset | Copied without editing another build list |
| Missing/empty input and source changes during freezing | Refused |
| ZIP creation, verification, extraction and staging verification | Passed using real carried source files and synthetic runtime binaries |
| Packaged Whisperer worker import | Resolved `chat_voice_settings.py` from the staged installation root |
| Missing helper, edited helper, extra unmanifested file | Rejected by package and staging verifiers |
| Every root destination removed from a receipt | Rejected, including otherwise self-consistent receipts |
| Self-modify receipt | Required snapshot markers/build helpers and both identity copies |
| Self-update inclusion sweep with `--no-git` | No findings; source/vendor, preservation and pre-shutdown integrity wiring passed; exit 0 |
| Generated self-modify snapshot | 1,579 files, 33.08 MB, 11 redacted files, zero copy errors; exit 0 |
| Snapshot runtime carriage | All 778 runtime source inputs carried or explicitly restore-mapped |
| Snapshot redaction and rebuild instructions | Passed; optional gallery omission and regenerated collected static explicitly reported |

The dependency test now recognizes `chat_voice_settings` as a carried local
module, rather than a missing pip dependency. The skipped test uses a Git-based
repository dependency census; fresh-clone/public-release tests that require
Git were excluded. An audit hook blocked all real subprocess creation inside
the file-only Python verification harness, including a Git-dependent check
encountered in the initial test attempt. The initial harness also required
isolation of the pure `rag.config` module from application model initialization;
the successful run tested its real functions without starting app services.

## Evidence and limits

Local transcripts and workload logs are under
`Temp/build-voice-asset-fix/`: `verification3-*`, `update-audit-*` and
`snapshot-audit-*`. The inspected source snapshot is retained at
`Temp/_self_modify_sweep_a2lgn7tg/`. These are local development evidence,
not release artifacts.

This verifies copying, receipt enforcement, update wiring and generated rebuild
inputs. It does **not** certify a newly frozen executable or a complete installer:
no full PyInstaller release/rebuild, live update swap or Git-history census ran.
The normal build path uses Git and was not invoked under the user's prohibition.
No failed/partial package was promoted. Existing installations need a normal
rebuild/update to receive the fix; source changes alone do not update an exe.

For future development checks, use a verified visible forked foreground console,
keep it open afterward, and monitor its live output. Use the update sweep's
`--no-git` only when that limitation is required and report the omitted coverage.

## Usage dashboard additions — 2026-10-10

The runtime receipt now requires `agent/js/usage_dashboard.js`,
`agent/css/usage_dashboard.css` and `templates/agent/usage_dialog.html`. The root source map also ships the
user guide as `docs/usage-dashboard.md`. The frozen
backend requires `usage_tracking`, `usage_provider` and `usage_views`; the source
snapshot additionally requires migration 0213 and Usage tests/harnesses. Both
inclusion sweeps and source/collected-static byte parity passed during the Usage
campaign. This extends the source inventory; it does not recertify an older
installer. See [Usage delivery and validation](usage-dashboard.md).
