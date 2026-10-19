<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Installation and removal windows

> Current release: **[v1.85.0](changes/2026-10-16-v1.85.0.md)**. Dated records below retain their original evidence dates.


**Status: shipped in the published `v1.82.0` release (tag at `880a335e`, 2026-10-12).**
The validation campaign below describes that released implementation and is dated
2026-10-11/12. The following removal redesign is newer and not yet released.

## Removal redesign in the working tree — 2026-10-18

Removal now journals same-drive moves of application entries instead of copying
and hashing the entire installed payload. Preserved directories remain in place.
Only setup-owned shortcut/catalog metadata receives a small recovery copy.
Application entries and Windows state are restored if a reversible removal step
fails. After commit, cleanup deletes the quarantined payload and then `Temp`.
A cache lock cannot trigger restoration of the application.

The completion window distinguishes complete removal from **Application removed;
cleanup incomplete**, lists remaining paths, and offers **Retry cleanup**. That
action handles only this removal's residue; it refuses a new application or a
changed journal. It does not repeat Windows unregistration or alter preserved
content. A small `.tlamatini-removal.json` receipt bound to the installation
directory's filesystem identity survives an incomplete cleanup. Reopening the
uninstaller can finish that cleanup even after the application and recovery
quarantine are gone. Completed rollback is distinguished from completed removal;
a restored installation is never treated as cleanup residue. The receipt is
removed after temporary cleanup succeeds.
Recovery has its own heading, original failure reason and advancing
progress. File cleanup displays activity and actual deletion counts instead of
an invented percentage. Elapsed time includes recovery within the same attempt.

The acceptance target is three minutes, with five minutes the requested maximum.
The source uses bounded helper waits and a cleanup deadline; a deadline failure
is incomplete work, not successful removal. Full compiled-client timing remains
required. See the [research and failure analysis](setup-lifecycle-research.md).

Focused source regressions are in `Tests/test_setup_release_paths.py`, including
native file/directory locks, interrupted moves, collision handling, legacy
journals, unchanged preserved-file hashes and cleanup retries. They do not
replace compiled lifecycle acceptance. The older campaign below is retained as
historical evidence and does not certify this redesign.

The latest source gates passed 33 focused recovery tests and 110 existing
lifecycle tests, including a new wizard resuming locked-Temp cleanup after the
quarantine journal has already been removed. The separate full-payload filesystem
benchmark removed 64,264 package files (3,880,548,374 bytes before preservation)
in 22.297 seconds, with all 254 preserved-content hashes unchanged. This measures
the filesystem phase, not a completed compiled uninstall. Evidence is local under
`Temp/uninstall-redesign-20261018/`.

## Released setup behavior and original campaign

The standalone Installer and Uninstaller share `setup_wizard.py`: Tlamatini's
dark palette, native keyboard controls, a destination/review page, real progress,
and persistent completion or recovery details. The action row occupies its own
window row. During work the entire row is removed, preventing the clipped button
strips previously visible during removal. Resizing, long paths and large fonts
scroll the body without losing the footer. Closing an active operation through
Escape or the title bar leaves the operation running and explains its status.
Long result details have a reserved scrollbar column, so the text cannot squeeze
the scrollbar out of view. Both the final detail line and the Close button remain
reachable at large font scales.

Errors remain in the window with Retry and Change folder actions. A missing
package can be restored beside Installer.exe and checked again without restarting
the client. Windows registration warnings appear in the completion details.
Each executable writes a private local transcript under
`%LOCALAPPDATA%/Tlamatini/SetupLogs`; the result page shows its exact path.
Long destination inventories report their file count. Parent-directory existence
checks are deduplicated within the inventory, while every file retains its own
redirection check. Progress diagnostics are throttled to one line per ten seconds.
Removal preparation occupies the first 20 percent and shows copied bytes and file
counts. Actual removal advances to 95 percent; recovery cleanup finishes before
the client reports 100 percent.

## Files and Windows state

`setup_recovery.py` prepares and verifies a recovery copy before installation or
removal changes files. Its durable journal lives at `Temp/.setup-recovery` inside
the selected installation. A subsequent setup run restores an interrupted active
transaction before continuing. Failed restoration keeps the journal and copies
and reports the location; it must not claim that rollback succeeded. Successful
commit removes recovery material. A final cleanup failure is reported separately
from the successful operation.
Readability is checked before bulk copying. Permission/sharing failures retry for
at most five seconds, then identify the file and, when Windows can determine it,
the programs holding it. The owner lookup never closes another program.

`setup_windows.py` snapshots the application's registry trees, its selected
values in shared registration keys, and its Desktop shortcut. Recovery restores
that scope only. Windows UserChoice and other applications' Open With candidates
are excluded. Uninstallation retains existing ownership checks. Installed Apps
does not advertise a silent uninstall mode that the executable does not support.
Installed Apps removal verifies that the key is absent; an ownerless or invalid
entry is reported as needing repair instead of being mistaken for an absent key.

Existing reinstall preservation, database/WAL handling and migration flags remain
unchanged. Removal always keeps `agents/`, and keeps `application`, `applications`,
`content_generated`, `context_files`, `doc_generated` and `Templates` when they hold
content. `Temp` is removed after successful recovery-copy cleanup.

The main application must close normally before removal. Confirmed leftover
workers use the existing PID/creation-time and installation-ownership checks.
PowerShell helpers are noninteractive, bounded to 120 seconds and contained in a
Windows job before their script starts. A timeout closes the job, including its
descendants. A session mutex refuses concurrent setup operations. Missing removal
helpers fail visibly instead of silently reporting that their work succeeded.

These are custom EXE recovery mechanics, not MSI transactions or a guarantee
against every storage or operating-system failure. The design research and its
primary Microsoft sources are in [setup-lifecycle-research.md](setup-lifecycle-research.md).

## Visible validation

All development commands and checks must run in a verified foreground console
on Angela's real desktop, left open afterward. Browser checks require explicit
`headless=False`; screenshots use Shoter with `all_screens=True`. The repository
visibility policy applies to every harness below.

- `scripts/setup_wizard_visible.py`: source UI gallery and 52 layout checkpoints;
  these do not count as installations.
- `scripts/setup_lifecycle_checks.py`: real filesystem recovery, journal, Windows
  registry, shortcut, mutex, lock and helper-process checks in disposable fixtures.
- `scripts/build_setup_full_payload.py`: fresh complete build from the current
  source in an isolated local snapshot; an explicit resume completes interrupted
  copying before invoking the normal build pipeline.
- `scripts/build_setup_validation.py`: freezes both current setup clients, then
  verifies and attaches the full newly built package and records artifact hashes.
- `scripts/setup_release_cycles.py`: five compiled-client scenarios with native
  UI input performed separately, real window observation, full payload hashes,
  registry/shortcut assertions and a live evidence gallery. Its count requires
  both a real completion screen and independent state verification.
- `scripts/setup_crash_agents_visible.py`: the installed frozen server, normal
  login in headed Chrome, actual Starter/Sleeper/Pythonxer/Executer deployment,
  abrupt server termination and independent orphan-process checks. A suspended
  agent and blocked child workloads exercise real process cleanup; a different
  Python process and stale PID file check that unrelated processes survive.

Current local evidence is under `Temp/setup-wizard-visible` and
`Temp/setup-release-validation/evidence`. The latter's `SUMMARY.html` reports only
completed checks, with pending cases labelled explicitly. This is focused setup
verification, not acceptance of every application panel or external service.

### Current local campaign (2026-10-11–12)

- Current source presentation: 52/52 visible checkpoints passed, including the
  action-row regression and 96/144/192 DPI font scales. The desktop case 3 result
  exposed a squeezed-out details scrollbar; the repair and twelve additional
  overflow/last-line checks passed in `Temp/setup-wizard-visible/result-scrollbar`.
  The earlier 40-check gallery is retained separately. The first four desktop
  installations used clients built before this scrollbar repair; per-case
  artifact records preserve that distinction.
- Recovery and helper checks: 28/28 passed; uninstaller lifecycle checks:
  21/21 passed; mechanics and process ownership: 61/61 passed through Django.
- A new complete runtime package built successfully: version 1.80.0 (the
  nearest tag then; the package later published as v1.82.0 was built separately),
  77,541 manifest files, approximately 1.921 GB compressed. Integrity verification
  passed. The original checkout's database and release directory were not used
  as build scratch space.
- Two real compiled installation GUIs completed (clean case 1 and crash case 5).
  Independent verification checked
  77,540 unmodified payload files plus the configured shortcut file, bundled
  Uninstaller, Desktop shortcut, Installed Apps entry and both flow registrations.
  These checks used the development launch context; the registry comparison
  below means they cannot certify normal desktop registration. This first cycle
  used the initial setup binaries; its hashes are retained in
  `evidence/case-1-original-build.json`. Subsequent client builds add the preflight
  optimization and progress diagnostics.
- The first real removal reached its completion window, but its independent
  audit found the Installed Apps entry remaining. It is not counted as a passed
  uninstallation because the two processes inspected different registry views,
  as established by the comparison below.
- The real crash preparation in case 5 passed: the installed server exited
  abruptly, without Ctrl+C, and five tracked agent/workload identities survived
  four subsequent checks. Native Python stack inspection confirmed Executer
  waiting for its child and two payloads blocked in `threading.Event.wait`;
  the Sleeper worker was suspended. Evidence is in `evidence/crash-agents`.
  The manually operated compiled Uninstaller stopped all five owned identities
  while the unrelated control survived until the result window. Process cleanup
  passed. Complete removal did not: recovery preparation encountered a locked
  temporary file and correctly stopped before application-file deletion. The
  temporary file later disappeared; its owner could not be identified afterward.
  This failure led to the bounded access retry and early-readability regression
  checks. The rebuilt retry completed file removal, but its independent audit
  again found the Installed Apps entry and owned flow registrations remaining.
  The actual uninstaller reports those entries as absent; a separate reader
  finds them in all registry views under the same account. This discrepancy is
  explained by a launch-context difference: the same read-only Python script
  sees the three product keys from the development console and sees them absent
  when Angela launches it from Explorer. Both processes have the same user SID,
  no package identity and no AppContainer token. The exact Windows mechanism has
  not been identified; native hive names alone did not distinguish the views.
  Earlier registry checks therefore cannot certify normal desktop integration.
  Neither removal is counted as a complete pass.
- `scripts/setup_desktop_cycles.py` is a fixed, manually desktop-launched
  campaign using fresh destinations and a separate evidence folder. It accepts
  no external command queue, changes no security settings and never launches or
  operates the blocked Uninstaller. Installer interaction remains through the
  native UI; Uninstaller launch and confirmation remain manual. Its independent
  checks execute in that same desktop launch context. Case 5 repeats the real
  application crash and surviving-agent test. Final Windows checks now also
  require the entire Installed Apps key, flow capabilities and owned Open With
  values to be absent. The explicitly retained file-type opt-out preference is
  not mistaken for an active registration.
- The desktop campaign has independently passed installations and removals 1 and 2 (clean
  destination and a path containing spaces, an accented character and an
  apostrophe), checking 77,540 unchanged payload files per installation. Both
  removals passed their GUI and filesystem/Windows audits in that same desktop context.
  The fresh campaign's evidence is in `evidence/desktop-campaign`; its live
  gallery remains authoritative as subsequent cases finish.
  The observer's 20-minute operation limit begins when progress starts, so time
  spent waiting for manual launch or confirmation does not trigger a false
  timeout. Manually restarted consoles have unique titles for visibility checks.
- Desktop installation 3 also passed: 77,539 unchanged package files, the
  configured shortcut, bundled Uninstaller and Windows integrations verified;
  the pre-existing configuration and all six protected-content markers survived.
  Its removal passed the independent filesystem and Windows audit, preserving
  all six content markers and 292 retained payload files in the allowed folders.
- Desktop installation 4 passed: 77,540 unchanged payload files, the configured
  shortcut, bundled Uninstaller and Windows integrations verified. Its read-only
  file removal also passed the completion-window, filesystem, preserved-content,
  shortcut and registry audits.
- Both setup clients were rebuilt after the result-scrollbar repair; package
  verification passed again. Desktop case 5 uses these rebuilt clients. The
  earlier hashes are saved in `desktop-campaign/pre-result-scrollbar-build.json`.
- Desktop installation 5 passed its full payload, executable and Windows-state
  audits. The installed frozen application ran, the headed browser completed
  normal login, and the product deployed Starter, Sleeper, Pythonxer and Executer.
  An abrupt main-process exit left five real worker/payload identities alive
  through four subsequent checks; Sleeper was suspended and an unrelated Python
  control remained alive. Its removal is recorded in the next item.
- Desktop removal 5 did not pass. The compiled Uninstaller stopped during
  recovery preparation, before deleting anything: a Chrome renderer started by
  the headed crash test had inherited the installation's `Temp` as its `TEMP`
  and still held a file there (`case-5-chrome-lock-owner.json`). The application
  executable, Uninstaller and runtime manifest stayed intact and no recovery
  journal was left (`case-5-after-lock-release.json`); the campaign state reads
  `needs-attention`. The tally is five real installations and four real removals.
- Optimized preflight processed the real 77,541-file manifest in 41.88 seconds
  in a disposable destination; this measurement is not another installation.
- The requested five installations and five uninstallations are **not yet
  complete**. The native automation service blocks `Uninstaller.exe`, requiring
  manual UI operation; the real-window observer and independent checks remain
  available. Read the live report for subsequent results.

The desktop observer must not synthesize Alt to refocus an already active Tk
window: Windows can enter its menu loop and pause normal event callbacks. It now
uses foreground attachment without that keystroke, verifies the resulting state,
and accepts only windows owned by the compiled setup process, excluding previews.
Uninstaller observation is strictly passive on this machine: no launch, input,
activation or repositioning is used to bypass the desktop service's app block.
