<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Release validation and repairs — October 4, 2026

This is an uncommitted local release campaign against source and Windows frozen
artifacts reporting version 1.75.0. It is separate from the published tag. Angela
authorized rebuilding and cleaning the test installation, required visible
execution and at least four hours of validation, restricted Ollama inference to
`nemotron-3-ultra:cloud`, and prohibited commits. The protected development
database backup/restore mechanics were not changed.

**Campaign status: application testing stopped at Angela's request; documentation finalized.** The evidence root is
`Temp/installer-registration-fix-2026-10-04/`. The recorded start is
2026-10-04 20:33:27 UTC; the four-hour threshold is 2026-10-05 00:33:27 UTC.
The stop was recorded at 2026-10-05 00:54:32 UTC, after 4 hours 21 minutes
5 seconds. Document generation, review and task-process cleanup continued afterward;
application testing did not. Elapsed time alone is not an acceptance result.

## Repairs

- Windows PowerShell registration wrappers now resolve an omitted installation
  directory after script initialization. This fixes the actual installer failure
  at `GetFullPath` when invoked through `powershell.exe -File`.
- Uninstall cleanup identifies owned workers and descendants, including orphaned
  agents carrying `TLAMATINI_AGENTS_ROOT`, and preserves unrelated processes.
  Frozen removal relocates its worker; unsafe paths and incomplete removal fail
  visibly, and retry helpers remain available until their preceding steps succeed.
- Ordinary chat instructions following an introductory sentence are accepted by
  prompt-shape validation. Filesystem authorization remains a separate check.
  Single-token literal replies also avoid a nondeterministic classifier echo;
  this narrow route excludes paths and appended instructions.
- System-Metrics and Files-Search honor the effective configuration, including
  nondefault endpoints and UTF-8 BOM files. Files-Search has bounded RPC waits.
  The frozen campaign also exposed BOM rejection in the separate path-security
  loader. Its decoder now accepts both ordinary UTF-8 and BOM UTF-8; focused tests
  prove that allowed descendants still work and sibling/traversal paths remain denied.
  The actual frozen startup exposed a second BOM rejection in the independent
  chat-chain reader. It now uses the same decoder; plain and BOM configurations
  preserve both settings and the prompt. The harness checks the initial server
  log so a later settings Save cannot hide an earlier chat-initialization failure.
  Frozen acceptance 05 then exposed a separate auxiliary SystemRAGChain reading
  its bundled development config and connecting to 8765 instead of 8767. Both
  auxiliary context chains now honor explicit paths, CONFIG_PATH, source/frozen
  defaults and BOM encoding. The file-context chain shares endpoint normalization
  with the MCP client; system-context requests reuse and close their WebSocket.
- The ACP example can load inside its own editor operation without weakening the
  busy/running guard for outside file openings.
- Parametrizer's mapping-only saved metadata no longer suppresses restoration of
  its source and target connections. Explicit saved connection lists are preserved.
- Feed embeddings now requires a real vector store. The live provider returned
  HTTP 401, exposing a tool-enabled prompt-only fallback that previously produced
  false success. The failed candidate is closed and cannot replace prior context
  or advance to the next operation.
- Agents without registered model fields no longer read all global model
  settings. This removes an unrelated configuration dependency from local-only
  agents and restores Kalier's best-effort default handling.
- Flow catalog identifier fields remain stable between public placeholders and
  keyed numeric values. Telegram API IDs and WhatsApp phone-number IDs accept
  strings or integers; booleans, fractional numbers and containers are refused.
- Password-quoting regressions again use their deliberate space-bearing fake
  passwords. A stale fixed-model assertion now follows the `@config` contract,
  and Kalier logging tests establish and restore their own INFO level so a
  focused run does not depend on earlier tests.
- The real-window watchdog fixture explicitly launches a conhost-backed CMD and
  measures the command child. Its former CREATE_NEW_CONSOLE launch did not produce
  an observable foreground window in the third broad run. The windowless negative
  case uses a deterministic fake rather than a hidden workload.
- Barrier's standalone test now verifies its visible console, inherits live
  output, waits for the target to exit, treats a stale second-cycle PID as failure,
  and verifies its bounded temporary-directory cleanup. A failed second cycle can
  no longer pass through an unchanged success flag.

## Recorded evidence

| Area | Observation | Evidence |
| --- | --- | --- |
| Installation | Actual compiled Installer completed all eight stages, 100% and the success dialog after an authorized clean baseline. | `installed-result.json`, `clean-install-complete.png` |
| Registry | 34 real isolated-registry checks, including fresh PowerShell entry points without InstallDir. | Registration transcript in the evidence root |
| Targeted backend | 143 tests passed after the lifecycle, chat and MCP fixes. | `backend-and-main-rebuild.log` |
| Frozen build | Isolated build passed the no-Torch check and all 32 required runtime-module checks. | `backend-and-main-rebuild.log` |
| Source commentary | Mixed styles, eight resize borders/corners, no internal scrollbars, cancellation, undo, draft recovery and repeated three-note file/render comparisons passed. | `source-campaign/editors-07/` |
| Source ACP editing | All 17 graphical editing cases passed after the example fix. | `source-campaign/editors-08/` |
| Source output/runtime | All 31 core, divider and real ACP runtime checkpoints passed; no remaining service listeners. | `source-campaign/editors-09/summary.json` |
| Source authentication | User create/edit/search/history, wrong password, return URL, nonstaff Admin denial, logout and fixture removal passed. | `source-campaign/acceptance-11/checks.json` |
| Source agent catalog | 88 agent cases passed; the stronger Parametrizer case found a reload defect. The repaired mapping passed a focused rerun. | `source-campaign/acceptance-11/`, `source-campaign/acceptance-12/` |
| Source local agents | 11 actual local file-agent executions checked exact bytes, intentional refusals and PID-file cleanup. | `local-agents-source-02/summary.json` |
| Source live Prompt Flow | Real prompt, decision branch, scheduled pause/resume, cancellation, flush, clean and loop-limit cases passed. A rejected embedding request stopped before the following node; no browser errors or remaining application listeners. | `source-campaign/acceptance-17/summary.json` |
| Broad backend discovery | The first 5,966-test run exposed 13 failures and one error; 18 conditional tests were skipped. The corrected areas passed 159 focused tests before the full rerun. | `full-backend-suite.result.json`, `full-suite-repairs-02.application.log` |
| Broad backend retest | 5,967 tests completed in 477.230 seconds with no failures or errors; 18 skips were explicitly inventoried. All 54 JavaScript files parsed; repository lint and diff whitespace checks passed. | `full-backend-suite-02.application.log`, `full-backend-suite-02.result.json` |
| Complementary path policy | The four denial tests skipped under the broad task-root policy passed under a deliberately narrow fixture policy. Eleven checks completed, with two allowed-path cases skipped that had already passed in the full suite. | `path-policy-retests.application.log` |
| BOM path-security repair | Five configured-MCP tests passed, including ordinary/BOM JSON and allowed/sibling/traversal boundaries. | `bom-repair.application.log` |
| BOM chat-chain repair | Six configured-MCP tests passed after adding plain/BOM chat configuration coverage. | `bom-chat-repair.application.log` |
| Actual frozen MCP clients | Compiled clients successfully searched a Unicode fixture, enforced traversal boundaries, and obtained real system metrics/time on nondefault ports with BOM configuration. No model was invoked. | `frozen-campaign/acceptance-04/live-mcp-clients.json` |
| Frozen agent carriage/local execution | All 89 runtime folders, 21 model loaders and three planner catalogs checked; 11 actual local file-agent executions passed. | `frozen-agent-carriage.application.log`, `local-agents-frozen-01/summary.json` |
| Third broad discovery | 5,969 tests in 562.710 seconds; one real-window fixture failure, zero errors, 18 conditional skips. The fixture was corrected without weakening the product watchdog. | `full-backend-suite-03.application.log` |
| Visibility retest | 28 focused real-window checks passed; then 43 combined watchdog/WhatsApp guard tests and both concurrent/staggered Barrier cycles passed, with no stale PID/flags. | `foreground-fixture-retest.log`, `visibility-audit-retest.log` |
| Document generation/review | 111 PDF pages, 142 slides, exact 1,602-path tree parity, 2,331 native PowerPoint text boxes checked; all 19 contact sheets and changed full-size pages/slides inspected. The third generation includes the final auxiliary-context repair. | `document-review/review.json`, `refresh-final-documents-03.transcript.txt` |
| Frozen combined UI run | 94 checkpoints passed, including all 89 agent editors, full commentary/ACP editing and output resizing. The run stopped at its unhandled dirty-ACP close confirmation; this was a harness precondition, not a lost diagram. It also exposed the auxiliary context endpoint defect. Browser errors and remaining service ports were empty. | `frozen-campaign/acceptance-05/summary.json` |
| Source/frozen note parity | All three notes match exactly in text, fonts, colors, emphasis, coordinates, bubble path and every rendered line box; only session-generated IDs are excluded. | `source-frozen-rich-rendering-parity.json` |
| Fourth broad run | 5,971 tests in 519.736 seconds; two inherited-override fixture failures and one incomplete sidecar-mock error, with 18 conditional skips. | `full-backend-suite-04.application.log`, `full-backend-suite-04.result.json` |
| Context fixture retest | All 18 endpoint, default-path and no-placeholder/lifecycle tests passed after fixture isolation; actual live search/system context and BOM/explicit override coverage remain included. | `context-defaults-retest.application.log` |
| Final broad backend retest | 5,971 tests completed in 505.743 seconds, zero failures/errors and 18 conditional skips. Repository lint, all 54 JavaScript parses and diff whitespace passed. The complete durable application log and final visible transcript were retained. | `full-backend-suite-05.result.json`, `full-backend-suite-05.application.log`, `full-backend-suite-05.transcript.txt` |
| Final isolated executable build | The context-chain repair compiled successfully; all 32 required modules are present in the 14,491-module PYZ and frozen Torch remains absent. Staging changed only the executable and base-library ZIP, with configuration/database hashes unchanged. Executable SHA-256: `bfc489edd01d4ad26d4cec77576a424e383d854894f6bb939e6c82650353f266`. | `final-context-build.transcript.txt`, `staged-frozen-context-runtime.json` |
| Final frozen context/UI run | 94 checkpoints passed on the new executable, including both actual context chains, all 89 editor round trips, commentary and both splitters. The run stopped because the runtime test looked for a tlmpop wrapper while ACP uses the accessible Unsaved changes dialog. The product retained the graph. The selector now targets that dialog's role/name; the complementary runtime retest is recorded separately. | `frozen-campaign/acceptance-06/summary.json`, `frozen-campaign/acceptance-06/live-mcp-clients.json`, `frozen-campaign/acceptance-06/failure.png` |
| Final frozen runtime integration | All 40 checkpoints passed: core opening/Admin, actual context clients/chains, all ACP editing cases, dirty-diagram Cancel/Continue, real worker start/pause/resume/stop and real Prompt Flow execution. No browser errors, static-resource failures or remaining service ports. The three source/frozen rich notes match in every recorded field except generated IDs. | `frozen-campaign/acceptance-07/summary.json`, `source-frozen-rich-rendering-parity.json` |
| Complementary frozen coverage | Runs 06 and 07 cover 104 distinct passed UI checkpoints on the same final executable. Run 06 remains an incomplete run; run 07 passed the corrected editor/runtime sequence. No product code changed between them. | `final-frozen-coverage.json` |
| Final source context integration | All 13 core/context checkpoints passed with fresh source modules, BOM configuration, isolated ports 8001/8766/50052, exact Unicode file matching and both context chains. The system socket closed; browser errors and remaining service ports were empty. The isolated source settings were restored afterward. | `source-campaign/acceptance-18/summary.json`, `source-campaign/acceptance-18/live-mcp-clients.json` |
| Uninstaller targeted regression | The initial 59-test run had one stale source-inspection assertion for the centralized running-process detector; all 59 passed in the corrected 11.269-second run. Later ownership cases also run in the passing full suite. | `uninstall-tests.log`, `uninstall-retest-build.log` |
| Task-process cleanup | No owned installed/source workers or acceptance-port listeners remained. Original installed config.json was restored byte for byte, contacts remained unchanged, and readable idle consoles were retained. No staged changes or new commit. | `final-cleanup.json`, `final-cleanup-03.transcript.txt` |

Cleanup has two explicit limits. `external_mcps.json` differs from its earlier
hash and was preserved rather than overwritten from an unverified backup. The
final registry ownership assertion failed; that audit is incomplete, and no
registry correction or new acceptance run was attempted after the stop request.
The first two cleanup transcripts preserve those observations. The third receipt's
PASS applies to task-process shutdown and main-configuration restoration only;
it does not turn the settings difference or registry assertion into a pass.

The frozen browser harness initially lost foreground focus after a Shoter
checkpoint. It now reactivates and verifies the test browser before subsequent
input; recorded pointer and Bootstrap events confirm the repaired File menu
interaction. A later Windows-open check encountered the expected recovered-draft
confirmation. The test now exercises Cancel and Continue through their real
buttons instead of assuming an incoming file silently replaces unsaved work.
These harness failures remain in their original evidence folders.

The source live-prompt fixtures needed corrections to required fields, both
decision branches and control selectors. Those failed harness runs are retained;
they do not count as successful model execution. In `acceptance-15`, real prompt,
scheduled/pause/resume, branch, flush, clean, cancellation and loop-limit cases
passed. Its embedding-success checkpoint is **invalidated** by the provider's
HTTP 401 in the application log; that observation led to the runtime fix above.
The corrected embedding failure path passed in `acceptance-17`; the same run
passed 15 targeted backend regressions before the visible checks. The final source
and complementary frozen results are recorded in the table above. The final runtime
was built and staged, but refreshing its distributable package, reinstalling that
final package and exercising the final shortcuts are **NOT RUN**: Angela stopped
testing. Earlier installer success does not certify this later runtime's full
distribution lifecycle. Prepared scripts are not evidence of execution.

The Markdown contracts, release-validation skill, PDF and PowerPoint document
the implemented behavior and its limits. The separate
`TlamatiniProfiled1004206ByCodex.md` inventories the full local delta with
file-by-file summary tables, old/current line spans, implementation explanations
and complete text diffs; private configuration values are withheld. Its scope
includes pre-existing edits without claiming authorship for them.

## Explicit limit

The desktop-control tool blocked launching the actual compiled
`C:\Tlamatini\Uninstaller.exe`. Angela confirmed she had been waiting for that
launch; she had not manually launched it. Consequently, no executable crash is
inferred from the absent window, and the compiled uninstaller GUI is **BLOCKED**.
The separate backend, scratch-directory and owned-worker tests do not certify
its confirmation/cancellation/completion screens. The blocked launch is not
bypassed through another shell, path or UI mechanism.

Hardware and external-service agent execution must be reported separately from
opening configuration dialogs. A model that cannot initialize embeddings does
not justify selecting a different model or marking Feed embeddings successful.

## Reuse

The repository and installed `tlamatini-release-validation` skill contain the
acceptance matrix. `scripts/installed_panels_visible.py` selects source or frozen
mode and composes the visible checks. See [Windows flow lifecycle](../windows-flow-files.md)
for flags and [Prompt Flow Designer](../prompting-flow-designer.md) for the file,
commentary and layout contracts. All commands and browsers run visibly, evidence
uses Shoter, and task-owned workers are audited after each run.
