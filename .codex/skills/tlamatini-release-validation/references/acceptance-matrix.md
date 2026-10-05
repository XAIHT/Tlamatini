<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Acceptance matrix

Apply this to the current build, using actual UI labels and endpoints found in
source. Test all visible controls in each named area. The rows below establish
minimum coverage, not permission to omit new controls. Keep each observation and
its result separately; do not replace evidence with a checked list.

## Installation and Windows lifecycle

| ID | Required observation |
| --- | --- |
| I01 | Explicitly authorized directory/registry reset, then absence of installation, shortcuts, owned registrations and processes. |
| I02 | Real package manifest membership, hashes, executable version and source-snapshot carriage where present. |
| I03 | Actual compiled installer: browse/type destination, validation, all stages, 100 percent and success dialog; no mock pipeline. |
| I04 | Extracted executable/helpers/uninstaller, desktop/local shortcuts, Installed Apps and companion discovery point to the selected directory. |
| I05 | Launch via installed shortcut; startup, welcome/login and chat load without startup traceback. |
| I06 | Explorer/ShellExecute .flw and .fpmt open the correct editors; paths with spaces/Unicode; cold and warm instance reuse; no automatic execution. |
| I07 | Independent and combined register/remove/repair/status; user defaults and other Open With candidates preserved; update respects opt-out and ownership. |
| I08 | Installer-style fresh powershell.exe -File entry points without explicit InstallDir, from a different working directory. |
| I09 | Reinstall/upgrade preserves the existing user state through the existing product mechanisms; do not rewrite DB backup/restore code. |
| I10 | Actual compiled uninstaller: running-process gate, cancellation, completion, removal of application binaries/shortcuts/owned registrations, and preservation of agents plus nonempty content directories. Verify the installed uninstaller itself is removed and Explorer remains running. Full directory/registry reset is a separate explicitly authorized action. |
| I11 | Reinstall after uninstall succeeds; finalize the user's intended installation and clean task-owned workers. |
| I12 | Corrected outer distribution ZIP contains the verified package, installer runtime and uninstaller; integrity and size gates pass. |

## Authentication, main chat and administration

| ID | Required observation |
| --- | --- |
| A01 | Normal login/logout; safe return to the requested panel; wrong credentials stay rejected. |
| A02 | Admin Panel opens for staff; nonstaff cannot enter it or invoke its protected actions. |
| A03 | Every registered admin model's list page loads; exercise available search, filters, sorting and pagination with test fixtures. |
| A04 | Create/edit/delete a uniquely named test user and group through admin forms; permissions and validation behave correctly; remove fixtures. |
| A05 | Admin links, add/change/history/delete permissions and validation on safe test records; classify actions requiring external effects before running them. |
| A06 | Configure tools/MCPs/agents/skills: inspect rows, change a test selection, save/reopen and restore it; Compact and Self-modify contracts remain consistent. |
| A07 | Config Models, Mic and other visible dialogs: inspect every tab/control; Save/Cancel/Escape semantics; preserve real credentials and settings. |
| A08 | Main-chat File/Open/drop/Reopen routes .flw/.fpmt correctly and keeps the chat document; regular document operations still work. |
| A09 | Navbar Panels navigation, dialog dismissal, context/status/error displays and no uncaught browser or application errors. |
| A10 | Actual System-Metrics and Files-Search requests on configured nondefault ports; source CONFIG_PATH and frozen installation config, Unicode/BOM configuration and service shutdown. A listening default port does not prove the saved setting is honored. |
| A11 | Real chat answer and follow-up using only the model authorized by the user; distinguish request rejection, model failure and test-selector failure. |

## Prompt Flow Panel

| ID | Required observation |
| --- | --- |
| P01 | Palette, toolbar, menus, status, run output, pan/zoom/Fit and independent Operations splitter render and respond. |
| P02 | Create/configure/duplicate/delete each of the seven executable operation types; ports, edges, Start and invalid-graph messages. |
| P03 | Three independent static commentaries; double-click/Enter editing with the floating toolbar and no configuration dialog. |
| P04 | Multiple fonts, sizes, text colors and bold/italic/underline within one note; selection and caret formatting; note color/alignment. |
| P05 | Drag every border/corner at multiple zoom levels, including while editing; wrapped text stays contained without internal scrollbars; Fit text. |
| P06 | Done/Cancel, Ctrl+Enter/Escape, local text undo and completed flow Undo/Redo; duplicate preserves styles. |
| P07 | Actual File Save/Open for several mixed-style notes: compare literal text, runs, geometry and rendered appearance, not just JSON parse success. |
| P08 | Draft recovery; v1 executable-commentary migration to User Input; malformed/oversized/wrong-format files preserve the current graph. |
| P09 | User Input reply and cancellation; pause/resume/stop, runtime errors and per-run isolation; static commentary never executes. |
| P10 | Execute prompt/scheduled/decision/embedding operations against configured real services when available; verify actual output events, pause/resume during a delay and Stop before inference. An embedding error must stop before the next node and remain a blocked capability, not a successful embedding test. Record blockers without mocking success. |
| P11 | Run output splitter at 5/20/50/95 percent, keyboard/collapse/reopen/window resize; canvas scale and internal content sizes remain unchanged and scroll independently. |

## Agentic Control Panel

| ID | Required observation |
| --- | --- |
| C01 | Complete palette and search; create each available agent type and verify label/ports/configuration schema from its current contract. |
| C02 | Drag, select, multi-select, pan, zoom, Fit and Operations splitter at different window sizes. |
| C03 | Configure, duplicate, delete, Undo/Redo, connection creation/removal, Starters and Flow settings, including cancellation. |
| C04 | Validate a harmless Starter/Sleeper/Ender flow, invalid edges/required settings and helpful errors; use real backend validation. |
| C05 | Save/Open .flw with nonconsecutive IDs and configuration references; IDs, coordinates, edges and redacted settings survive. |
| C06 | Malformed files, failed session preparation, expired login and save-redaction failure leave the diagram intact and report failure. |
| C07 | Actual harmless runtime: Start, running edit lock, Pause/Resume where supported, Stop, LEDs/log output and process cleanup. |
| C08 | Separate agent-specific external-service/hardware tests from core panel coverage; never claim all agents ran because their configuration dialogs opened. |
| C09 | Cleaner has a real companion agent to select; Parametrizer has supported source and target connections. Save an actual mapping and verify it survives .flw Save/Open. |
| C10 | Execute safe local file agents in scratch space using the product's source and frozen runtime cloning/Python resolver; verify resulting bytes and semantic status, including intentional refusals, rather than relying on exit code alone. |
| C11 | Public and keyed templates export identical field contracts. Numeric messaging identifiers accept their supported string/integer forms; booleans and fractional numbers are rejected. Local-only agents do not read unrelated model settings. |

## Final audit

For each case attach the source/frozen distinction, observed evidence and status.
Check app logs and browser console, remove test-created records/files/settings,
stop owned workers, verify intended registrations and installation, and report
unexecuted cases explicitly. Run repository checks appropriate to the changed
code and validate this skill's frontmatter and links. A new skill remains
untracked until the user authorizes staging; never stage merely to satisfy the
repository's tracked-skill inventory check.
