---
name: tlamatini-release-validation
description: Validate a real Tlamatini Windows release through clean installation, administration, chat, Prompt Flow Panel, Agentic Control Panel, and lifecycle tests. Use for release acceptance or installation and panel regressions.
---

<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Tlamatini release validation

Test the deliverable the user will run. A source test, registry helper test,
mock installer, or package inspection cannot substitute for the compiled
Installer.exe completing against its actual pkg.zip.

## Scope and authority

Read the checkout's AGENTS.md, CLAUDE.md and
TestsVisiblesAndVisibleExecutionFromClaude2Codex.md. Preserve unrelated edits and
the user's commit prohibition. Do not run build.py merely to test: it deletes
the development database and dist directory. Do not edit protected database
backup/restore mechanics. Use the existing release when available.

Read [the acceptance matrix](references/acceptance-matrix.md) for a full run.
For a focused regression, identify the relevant cases and label the result as
focused. Never call a partial run a complete release pass.

## Establish a real clean baseline

1. Identify the exact release folder, Installer.exe, pkg.zip, Uninstaller.exe,
   installation directory and user-owned state. Record versions and hashes.
2. A clean-install request authorizes removing the specified installation and
   its Tlamatini-owned registrations. A generic test request alone does not
   authorize deleting an existing personal installation; use a disposable
   Windows account/machine or obtain the missing authorization.
3. For an authorized reset, inspect the preview from
   scripts/tlamatini_clean_install.ps1 before using -Execute. Its installation
   path must be explicit, distinct from the checkout, and free of reparse points.
   It exports application-owned registry keys before removal. Leave other
   applications and Windows-managed UserChoice values untouched.
4. Verify the directory is absent, the Tlamatini desktop shortcut is absent,
   application ProgIDs/capabilities/Installed Apps/discovery are absent, and no
   installed process or service port remains. Record any Windows-managed residue.
   Reinstalling over the failed installation is not a clean-install test.

## Execution and observation

Run every command, test and build in a forked visible foreground console on the
real desktop, using PowerShell -NoExit or CMD /k. Verify the actual HWND is visible,
not minimized and foreground before the workload starts. Refuse execution when
visibility cannot be established. Keep consoles open afterward.

Use the available native Computer Use workflow for the actual installer and
headed Playwright with explicit headless=False for the browser. Authenticate
normally; do not inject cookies, replace responses, mock services or write canvas
state to make UI tests pass. A separate development console does not imply that
internal product services should open extra windows.

Check the initial application log before configuration dialogs can rewrite a
test configuration. Exercise plain and BOM UTF-8 with nondefault service ports
through the actual compiled clients and chat startup. Also invoke both auxiliary
chat context chains: direct MCP clients
passing does not prove SystemRAGChain/FileSearchRAGChain read the same config.
Assert the allowed model, effective endpoints, actual Unicode search/system
context and closed system socket; reject context-fetch errors in the chat log.
When an incoming flow
meets a recovered draft, test both Cancel (draft preserved) and Continue (file
loaded); do not remove or bypass that product confirmation to simplify a test.
After a Shoter checkpoint, re-establish and verify the browser foreground before
sending another input.

Poll live transcripts and app logs every 5–15 seconds during long operations.
Read the first error. Report changed progress at least every minute. After an
interruption, inventory process ownership and partial outputs before resuming.
Capture whole-desktop evidence with Tlamatini's Shoter at meaningful checkpoints.
Observe the app's result after input; delivered clicks are not success evidence.
After each backend run, copy its durable application log into the evidence
directory before starting another application process. The console-shield queue
can finish draining after the runner exits; preserve and print the final test
summary from the application log as well as the exit code and live transcript.

## Run the actual release

Verify package membership and every SHA-256 using build_runtime_assets.verify_package.
Launch the exact compiled Installer.exe beside that package. Complete every
wizard stage and observe the success dialog and 100 percent completion. Inspect
the extracted helpers, shortcuts, registrations, uninstaller and discovery data.
Then launch the installed executable/shortcut and exercise the matrix through
normal browser interactions. Tests must name whether they used source or frozen
code; source results never certify the frozen installation.

Windows PowerShell entry-point regressions must include a fresh powershell.exe
-NoProfile -ExecutionPolicy Bypass -File process WITHOUT -InstallDir, launched
from an unrelated directory. Cover register_flw.ps1, register_fpmt.ps1,
unregister_flw.ps1, unregister_fpmt.ps1 and the shared helper. Passing the directory
explicitly misses the Windows PowerShell default-parameter failure found on
2026-10-04. Keep scripts/flow_file_associations_test.ps1's native isolated-registry
checks in addition to the real installer run.

## Evidence and verdict

Keep one dated evidence directory under Temp. For every matrix case record:
case ID, artifact/hash, source or frozen mode, action, expected result, observed
result, status (PASS/FAIL/BLOCKED/NOT_RUN), screenshot/log path and cleanup result.
Inventory all visible navigation and controls in the tested build; map them to
cases so newly added controls cannot disappear from coverage.

Do not transform unavailable credentials, external services, untested panels,
timeouts or interrupted runs into passes. A full acceptance verdict requires all
mandatory cases to pass; document conditional cases and their concrete blockers.
Do not print secrets from config files, registries, browser storage or logs.

Stop task-owned browsers, test servers and workers when finished. Preserve user
processes and leave readable idle consoles. Restore only test-created settings
or records and the user's intended final installation. Record final listener,
process and Git checks; do not stage, commit, push or publish unless authorized.

If the release was repaired, validate both the corrected pkg.zip and outer ZIP;
retain the original separately, deliver the exact corrected artifact path, and
state whether executables were rebuilt or only packaged assets changed.
