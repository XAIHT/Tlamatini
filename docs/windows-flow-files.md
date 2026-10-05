<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Windows flow files

Source implementation: 2026-10-04. The established agent-flow extension is **.flw**;
**.fpmt** is the prompting-flow extension. There is no .fmt format or conversion.
A frozen release must include these source changes before its executable can open
.fpmt through Explorer. Registration alone does not update an older executable.

| File | Windows description / ProgID | Editor |
| --- | --- | --- |
| .flw | Tlamatini Agent Flow / Tlamatini.FlowFile | Agentic Control Panel |
| .fpmt | Tlamatini Prompting Flow / Tlamatini.PromptFlowFile | Prompt Flow Panel |

## Open, save and recover

- Explorer double-click or **Open with → Tlamatini** passes one quoted file path
  to the application. Paths with spaces and Unicode and uppercase extensions work.
- Opening from the main chat's **Open** control opens the correct editor in a new
  tab, preserving the document already in the chat canvas. Drag/drop and Reopen
  use the same routing. Allow pop-ups for Tlamatini if the browser blocks the tab.
- Each editor also has its own File → Open and Save controls. Opening never presses
  Play, starts agents, sends prompts, or resumes a run. Static commentary stays static.
- The application validates the format, UTF-8 JSON and the 5 MiB limit before
  loading. UTF-8 BOMs are accepted. A different format or unsupported version is
  rejected rather than silently interpreted as an empty diagram.
- Login returns to the requested editor and file. Already-running instances are
  reused on the configured web port. A different service on that port produces
  an error; the file is never sent to that service. Concurrent cold launches wait
  for the first instance to start instead of launching competing servers.
- Unsaved diagrams/recovered prompt drafts require replacement confirmation. The
  .fpmt format preserves version-2 rich text runs and layout and migrates version-1
  executable commentary to User Input. See [the designer guide](prompting-flow-designer.md).
- .flw validation finishes before clearing the current canvas. Opening is blocked
  during running/paused/busy states; failed session preparation keeps the canvas.
  Saved agent IDs (including numbering gaps after deletion) and configuration references remain stable across opening and saving. Save reports failed credential redaction and does not download a raw secret-bearing
  snapshot. Save again after restoring the connection/session.
- Parametrizer mappings remain editable after Save/Open. Mapping-only metadata
  does not suppress rebuilding its source and target connections; explicitly
  saved connection lists retain their values.

## Installation and management

The installer registers both types per Windows user; no elevation is required.
The wrapper scripts resolve their omitted installation directory inside the
script body. Windows PowerShell can evaluate parameter defaults before
`$PSScriptRoot` is populated; using it as the parameter default caused the real
installer to fail at registration with an invalid `GetFullPath` argument. Fresh
`powershell.exe -File` entry-point tests cover this exact launch path.
The shared **flow_file_associations.ps1** handles Register, Repair, Unregister,
Status and DefaultApps. It advertises both types in Windows Default Apps using
RegisteredApplications and capabilities and supplies their icon and Open With
ProgIDs. Windows' existing user choice remains authoritative.

Run these commands in a **visible foreground PowerShell window** opened with
-NoExit, from the installed application directory. Keep that console open to
inspect results. Verify its actual window is visible before starting the commands.

~~~powershell
.\flow_file_associations.ps1 -Action Status
.\flow_file_associations.ps1 -Action Register
.\flow_file_associations.ps1 -Action DefaultApps
.\flow_file_associations.ps1 -Action Unregister -Extensions '.fpmt'
.\flow_file_associations.ps1 -Action Register -Extensions '.fpmt'
.\flow_file_associations.ps1 -Action Repair
~~~

DefaultApps opens Windows Settings, where the user chooses defaults. Registration
never clears UserChoice, its hash, another application's default, or its Open With
entries. Removing Tlamatini while it is the user-chosen default can leave Windows
asking the user to select another application; the uninstaller does not forge a choice.

For a source checkout, from that checkout's root in the same visible console:

~~~powershell
.\flow_file_associations.ps1 -Action Register -Source -PythonExe 'C:\Program Files\Python312\python.exe'
python .\Tlamatini\manage.py 'C:\Flows\My review.fpmt'
python .\Tlamatini\manage.py 'C:\Flows\My agents.flw'
~~~

Choose the Python environment that already runs this checkout. Source registration
uses that interpreter and the absolute manage.py path. Frozen registration uses
Tlamatini.exe. Both commands use conhost.exe to keep the application's main console.
Tlamatini.ps1 resolves relative filenames before changing directories and delegates
browser opening to manage.py, avoiding the old duplicate, hardcoded-port browser timer.

The register_fpmt.ps1/unregister_fpmt.ps1 wrappers affect .fpmt. The historical
register_flw.ps1/unregister_flw.ps1 entry points handle **both** types so older
installer/uninstaller executables continue to work after an update. Pass -OnlyFlw
for independent .flw management, or use the shared helper's -Extensions parameter.
Explicit Register claims this installation; Repair never takes a different
installation's owned registration or re-enables an explicitly unregistered type.
Unregister checks installation ownership so an old installation cannot remove a
newer installation's associations. Reinstalling explicitly registers both again.

The updater invokes Repair after replacing application files. The uninstaller
removes this installation's registrations before removing application files.
User-created .flw/.fpmt documents are not part of association removal.

### Uninstallation and worker cleanup

The uninstaller asks for confirmation and blocks removal while the main
Tlamatini application is running. After confirmation it stops workers belonging
to the selected installation, including agents launched by the carried Python,
system Python and descendant programs. Ownership uses executable/script paths,
agent working directories, process creation times and the product's inherited
`TLAMATINI_AGENTS_ROOT`. That inherited identity also identifies surviving agent
children after their original parent exits. Process names and stale `agent.pid`
files alone never authorize termination; unrelated processes and Explorer are
preserved. A worker that cannot be stopped makes removal report an error.

The installed frozen uninstaller starts a temporary copy with an independent
PyInstaller environment so Windows can remove the installed `Uninstaller.exe`.
The normal confirmation still applies. The installation must be a recognized
application folder; drive roots, shared system folders, source checkouts and
redirected directories are rejected.

`agents/` remains available to companion applications. Nonempty `application/`,
`applications/`, `content_generated/`, `context_files/` and `Temp/` are preserved,
and the result names the directories actually kept. Locked application files and
denied Installed Apps registry removal report incomplete uninstallation. Removal
retains the uninstaller and required helper/installation-marker files until the
preceding steps succeed, so a failed removal can be retried. Desktop
shortcut and Installed Apps removal check installation ownership. Shell refresh
uses an association-change notification without restarting Explorer or deleting
its global icon cache. Full removal of preserved content/discovery is a separate,
explicitly authorized clean-reset operation.

## Implementation and packaging

- flow_file_open.py provides pure validation and early command-line dispatch.
  services/__init__.py lazily loads its DB-backed helpers, allowing the pure prompt
  validator to run before Django. A warm launch exits before database startup work.
- A file snapshot is stored below the current Windows user's LocalAppData,
  Tlamatini/FlowFileOpen/configuration-hash. URLs contain a random 256-bit, single-use
  token, never an arbitrary filesystem path. Requests expire after 15 minutes;
  the queue allows 32 pending requests and removes expired entries on new opens.
- Authenticated, CSRF-protected browser uploads bind the token to the signed-in
  user. External opening supplies an unguessable local capability and still requires
  login. A token for the wrong user/editor remains unconsumed. Successful claims
  remove the snapshot. The old global pendingFlwData localStorage slot is retired.
- A loopback-only GET /agent/flow_files/status/ identifies a matching configuration;
  POST /agent/flow_files/open/ uploads and POST /agent/flow_files/validate/ validates.
  URLs are removed from the editor's address after consuming the opening request.
- build.py includes the opening modules and registration scripts;
  build_runtime_assets.py carries the scripts and this guide; copy_source_assets.py
  requires the backend, tests, scripts and documentation in self-modify snapshots.
  No real build is needed for the isolated lifecycle checks; do not run build.py
  merely to test packaging because its database/dist cleanup requires explicit approval.

## Verification

Run scripts/flow_file_associations_test.ps1 in a verified visible foreground
PowerShell -NoExit console. It exercises real Windows registry operations under
an isolated FileAssociationTests key and removes only that key afterward. It tests
idempotence, legacy installer entry points and ProgIDs, ownership, defaults/Open With preservation, repair opt-out, independent
removal, quoted commands, capabilities and source registration.
Include the omitted `InstallDir` tests from an unrelated working directory; passing
the directory explicitly does not reproduce the installer regression.

The repository skill `.codex/skills/tlamatini-release-validation/SKILL.md` defines
actual compiled installation/uninstallation acceptance, source/frozen panel
coverage and cleanup evidence. `scripts/installed_panels_visible.py` uses the
installed executable by default; `--source` explicitly selects an isolated source
runtime. `--extended` adds real chat and configuration checks, and
`--agent-catalog` inspects and round-trips every ACP agent. `--commentary` exercises
mixed text styles, all eight resize borders/corners, containment, undo/redo,
legacy migration, cancellation, drafts and repeated `.fpmt` round trips.
`--acp-editor` covers graphical editing, connections, zoom and diagram undo.
`--output-resize` checks the 5–95% divider, independent scrolling and window
resizing. `--acp-runtime` starts, pauses, resumes and stops real local agents.
`--authentication` adds wrong-password rejection, nonstaff Admin denial,
normal logout and disposable-user CRUD. `--prompt-runtime` exercises actual
model replies, scheduling, branching, cancellation, loop limits and embedding
capability/error handling. Select the authorized model before these live cases;
an unavailable embedding capability is not a successful embedding test.
`--shell-files` uses the installed Windows associations through ShellExecute and
checks warm-instance reuse for both Unicode file paths; it requires frozen mode.
`--mcp-fixture <directory>` executes actual source/frozen clients against the
running application's configured MCP endpoints. Preconfigure that bounded
directory in `allowed_paths` and create `MCP Unicode ñ.txt` inside it; the probe
checks the exact match, case-insensitive key, traversal refusal and system time.
It uses no model. Restore the temporary policy after the test.
Opening 89 configuration
dialogs does not establish that all 89 agents executed successfully. External
hardware/service cases and blocked native UI actions must remain explicitly
unverified until exercised.

The [October 4 release record](changes/2026-10-04-release-validation.md) records
both passing and failed attempts, the actual compiled installer result and the
blocked compiled-uninstaller GUI. Preserve the durable application test log
before starting another command so its final result is not overwritten.

Run scripts/flow_files_visible.py from a verified visible foreground console.
It uses real Chrome with headless=False, normal login, an isolated source runtime
on port 8001, actual file pickers/downloads, and Shoter whole-desktop evidence.
The test covers cold/warm opening, login return, three rich notes and unchanged
save/reopen rendering, malformed .flw rejection, both formats from chat, and keeping
its existing document. It never substitutes hidden execution for a visible check.

The format and web tests are agent.test_flow_file_open and agent.test_flow_file_views.
They cover wrong formats, versions, sizes, Unicode/BOM, duplicate IDs, invalid
edges, authentication, CSRF, safe login redirects, token isolation/expiry and startup
ordering. Run them through the visible isolated harness, not against the working DB.

Windows references: [application registration](https://learn.microsoft.com/en-us/windows/win32/shell/app-registration),
[Open With ProgIDs](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-include-an-application-on-the-open-with-dialog-box),
[Default Programs capabilities](https://learn.microsoft.com/en-us/windows/win32/shell/default-programs),
[opening Default Apps settings](https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-default-apps-settings).
