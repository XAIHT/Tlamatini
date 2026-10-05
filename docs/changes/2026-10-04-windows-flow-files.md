<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Windows flow files — 2026-10-04 source implementation

The existing format is .flw (agent flows), not .fmt. Prompting flows use .fpmt.
The full operating and maintenance contract is [Windows flow files](../windows-flow-files.md).

## Changes

- Shared per-user Windows registration, repair, status, removal and Default Apps
  for both types. Preserve UserChoice and other applications' entries; respect
  installation ownership and explicit unregistration. Repair owned legacy ProgIDs.
- Installer/update/uninstaller wiring and legacy entry-point compatibility; carry
  the scripts, backend modules, guide and tests in frozen/self-modify packaging.
- Bounded, authenticated, single-use file handoff; login return; early source/frozen
  command-line routing and reuse of a running instance before database startup.
- Main chat routes both flow extensions to their own editors and keeps its document.
- Validate .flw before clearing a diagram, await loading, enforce edit/run locks,
  preserve saved agent IDs with numbering gaps, and refuse raw credential downloads
  if save-time redaction fails. Remove the old global localStorage handoff.
- Correct relative-path resolution and remove the duplicate hardcoded browser timer
  in Tlamatini.ps1. Keep the main application console and configured port.

## Verification evidence

All development commands ran in HWND-verified visible foreground PowerShell/conhost
windows; the browser used headless=False. The isolated runtime used port 8001 and
normal authentication, with actual file pickers, downloads and server requests.

- 49 format/web/prompt-model tests passed, including authentication, CSRF, login
  redirect safety, format/size/version validation, Unicode/BOM and token ownership,
  expiry, single consumption, startup ordering, and browser-opening failure.
- 25 Windows registry checks passed against an isolated native registry subtree.
- Three packaging omission/copy tests passed, including byte comparison of each
  carried root asset. No real executable build or installer uninstall was run.
- Visible browser evidence is in Temp/flow-files-visible; the final summary records
  each completed checkpoint, source/runtime separation and post-test listening ports.
  Three mixed-style commentaries retain their rendered geometry across save/open.
- Full repository Ruff and frontend lint/parse checks run in the final visible audit.
  Existing frontend warnings are recorded separately from errors.

Main work logs: Temp/fpmt-windows-integration-2026-10-04. Earlier browser harness
attempts stopped on focus gating or assertions about existing filename/dialog
presentation; their logs remain alongside the corrected runs.

The working database backup/restore implementation was not changed. No commit,
staging, push, release executable build or real installation removal was performed.
The PDF and PowerPoint dossiers are refreshed from these source changes, with
render/geometry/tree-parity evidence in build/documentation_refresh.
