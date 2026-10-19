# Self-modify and self-update carriage review

> Current release: **[v1.85.0](changes/2026-10-16-v1.85.0.md)**. Dated records below retain their original evidence dates.


## Main-chat Views carriage (v1.85.0, 2026-10-16)

`Views → Canvas` and `Views → Reset layout` are ordinary chat capabilities in
both frozen build modes. They do not depend on the Self-modify toolbar switch.
The existing template/static carriers include the implementation; the required
inventories now additionally make omissions fail explicitly:

- `build_runtime_assets.ROOT_SOURCES` requires `agent_page.html` at
  `_internal/agent/templates/agent/agent_page.html`.
- `REQUIRED_STATIC` requires `agent_page_layout.js`, `avatar_size.js`,
  `agent_page_canvas.js` and `agent_page_init.js` in served collected static.
  The template's `_views1` suffix refreshes these scripts in existing browsers.
- `copy_source_assets.REQUIRED_SNAPSHOT_FILES` requires the same sources and
  both `scripts/chat_views_visible.py` and `scripts/chat_views_frozen_visible.py`.
  The existing `Tlamatini.md` requirement carries the new operating instructions;
  self-modify builds still require both installed identity copies and the snapshot.

The updater replaces these application files through the existing swap. No new
dependency, hidden import, migration or preservation-list entry is needed. Canvas
visibility lives in browser-local `tlamatini.chat.views.v1.<user id>` storage;
it survives replacement of application files when the browser origin and account
remain the same. A different browser profile or origin has separate preferences.
Reset restores layout without clearing content, context or history.

The October 16 source check passed 160 packaging, self-update and self-modify
tests, including rendering Views under both frozen availability branches and
rejecting an update receipt that omits any required Views asset. This is distinct
from a compiled-runtime check. The original v1.84.0 package's 79,310 files passed
membership/hash/CRC verification, but its six feature files and the live
installation predate Views. They must not be described as carrying this change.

The focused frozen test uses a disposable extraction of that real `Tlamatini.exe`
with the six current frontend/identity sources overlaid and byte-verified. Its
private test database and normal authenticated browser are separate from the live
installation. This modified test directory intentionally differs from the old
release receipt and is **not a distributable release**. The original package,
installed application and protected database mechanics remain unchanged. The release carrying Views, Reset and the centered portrait is **v1.85.0**.
This dated fixture check establishes frontend compatibility; its overlaid directory
is retained only as test evidence.

Local evidence is under `Temp/views-frozen/` (source sweeps, package comparison,
runtime identity, live console/application logs and the headed-browser gallery).
The earlier source GUI gallery is `Temp/chat-views-visible/run-7/SUMMARY.html`.
The actual frozen executable passed 13 visible checks in `browser-run-3`: served
JavaScript bytes, full-width chat, retained draft/history, reload persistence,
the stored-answer link, retained Source view/Refresh listener, avatar docking,
keyboard toggle, Reset, the real Windows file picker, a narrow viewport and both
visibility choices after full Chrome restarts. Authentication, HTTP and sockets
were real; normal application startup also performed its context-window probe.
No new chat answer was requested. Earlier attempts exposed test-selector and
native-picker harness mistakes, corrected before that complete pass. This remains
focused frozen frontend compatibility evidence, not clean-install/update acceptance.

Initial review on 2026-09-16 read source files, dependency code and packaging
rules. The follow-up ran the two requested file-only inclusion sweeps, generated
sanitized diagnostic snapshots and parsed Python/PowerShell syntax. No automated
application tests, builds, application launches, installs or updates were run.
Those September 16 results are source/snapshot checks. A separate September 20
follow-up rebuilt and installed 1.63.0, then passed source/frozen runtime execution,
model loading, wrapped-chat/MCP File-Creator and visible Models save/reopen checks.
See [dated evidence and limitations](model-configuration-verification.md); this does
not certify every hardware/provider workflow or a remotely published release.

## Build and rebuild

### Central model settings: runtime execution gate (2026-09-20)

`model_settings.py` has two required carriers: `agent.agents.model_settings` in
the frozen archive for the web process, and `agents/model_settings.py` beside
the executable for standalone agents. Runtime preparation imports compiled code
and copies portable data from `get_agents_root()`. It must never construct a
loose source path from a frozen service module's `__file__`.

`build.py` now executes `check_agent_runtimes` inside the newly built executable
before packaging. The check prepares every agent, refreshes reusable helpers,
validates actual YAML/model loaders and planning catalogs, and executes
File-Creator in private scratch space. The snapshot explicitly requires the
registry, runtime preparation source, command and model regression tests, so
self-modification retains the same release gate. Inclusion sweeps and runtime
execution are complementary checks; passing a file inventory alone is insufficient.

- `--self-modify` carries a fresh, sanitized `TlamatiniSourceCode/` plus
  `Tlamatini.md`. Default builds omit both; `--no-self-modify` wins when both
  options are passed. Public/private release entry points forward this choice.
- `copy_source_assets.py` now keeps the exact PDF.js `build/` directory. The
  previous global exclusion of directories named `build` dropped `pdf.mjs` and
  `pdf.worker.mjs`, breaking PDF rendering after a self-rebuild. Other build
  output directories remain excluded, and credential exclusions retain priority.
- PDF sources, Image-Interpreter, its PyMuPDF hook, viewer assets, decoders and
  fonts now have explicit snapshot requirements. The full vendored tree travels
  with the snapshot, including its upstream licenses.
- A missing required file, generation exception or recorded copy error aborts
  a self-modify build. The build no longer falls back to an older static source
  tree or continues with an incomplete snapshot.
- Generated rebuild instructions require choosing `TLAMATINI_VERSION` for all
  three build scripts. Git history and generated version modules are omitted
  from snapshots, so an implicit version could otherwise become `0.0.0+unknown`.

### Direct chat microphone carriage (source development, 2026-09-27)

The frozen archive now requires `agent.chat_voice_consumer` and
`agent.chat_voice_runtime` and `agent.chat_voice_settings`. The shared runtime
inventory carries the stdlib-only validator as root `chat_voice_settings.py`
for the source/carried worker, and additionally requires
`agents/whisperer/chat_worker.py` plus the collected
`agent/js/chat_dictation.js`, `agent/js/mic_settings.js` and
`agent/css/chat_dictation.css` assets. The final Config → Mic entry, modal,
settings validation and send/draft branch must travel together.
The matching chat template, WebSocket route, composer sizing, avatar handoff and
main-console logger must be present. Worker imports use source/carried Python;
ASR libraries must not migrate into the frozen web process.

The worker is an internal service and starts without a separate console or
foreground activation. The source snapshot must retain its source and relevant
requirements along with the frontend. The main requirements file declares the
direct source/build dependencies; `requirements-esphome.txt` documents the
incompatible separately provisioned ESPHome SDK. Do not merge that SDK into the
main environment to make a package list look complete.

Source regression and hardware checks are recorded in
[the microphone guide](chat-microphone-design.md). Those checks do not certify
the previously built installer or change the older dated evidence above.
Release verification must separately exercise the actual rebuilt worker and
static assets from a visible development session.

### The uninstaller's keep-list (2026-10-09) — what reaches whom

`uninstall.py` now keeps `Templates/` and `doc_generated/` (commit `0520dc97`). The
uninstaller is NOT part of the self-update payload: it is built after `pkg.zip`
(`build.py` → `build_uninstaller.py` → `build_installer.py`), the in-app updater
extracts only `pkg.zip`, and `Uninstaller.exe` is in the `$Preserve` set. So:

- **A fresh install, or a reinstall with the new Installer,** copies the new
  `Uninstaller.exe` (`install.py::_copy_uninstaller` overwrites it) — fixed.
- **An in-app update (About ▸ Check for updates)** keeps the `Uninstaller.exe`
  already on disk — NOT fixed until that install is reinstalled, or the new
  `Uninstaller.exe` from the release zip is copied over it.

⚠️ Delivering a new uninstaller through self-update needs a deliberate design: the
update code that runs is the OLD install's `self_update.py`, which deletes the
extracted bundle (where the new `Uninstaller.exe` sits) before the swap. Any fix
must also keep the guarantee the `$Preserve` entry gives today — an update must
never leave an install without an uninstaller — and needs a real release test.

### Setup windows, the Markdown canvas and the shared theme (2026-10-11/12, `v1.80.0` / `v1.82.0`)

- `install.py` / `uninstall.py` import `setup_wizard`, `setup_recovery`, `setup_windows` and
  `setup_logging`, so PyInstaller carries them into `Installer.exe` / `Uninstaller.exe` through
  the import graph; `build_installer.py` and `build_uninstaller.py` add the Tlamatini icon
  (`--icon`, `--add-data Tlamatini.ico`). The self-modify snapshot carries the modules and the
  `scripts/setup_*` harnesses through its generic walk.
- The Markdown canvas's `agent_page_markdown.js`, `markdown_canvas.css`,
  `marked/lib/marked.umd.js`, `dompurify/dist/purify.min.js` and both LICENSE files are in
  `build_runtime_assets.py` `REQUIRED_STATIC` and `copy_source_assets.py`
  `REQUIRED_SNAPSHOT_FILES`; `dompurify/dist` is a `KEEP_DIR_PATHS` entry and is un-ignored in
  `.gitignore`. The shared theme (`ui_tokens.css`, `ui_shell.css`, `ui_splitters.css`,
  `ui_splitters.js`, `entry_pages.css`, `admin_theme.css`, `templates/admin/base_site.html`)
  is in both inventories.
- The published v1.82.0 zip (checked 2026-10-12) carries all of them, plus
  `agents/video_analyzer/video_fetch.py`. ⚠️ As above, an in-app update keeps the OLD
  `Uninstaller.exe`: the new setup window reaches an existing installation only through a fresh
  install or a reinstall with the new Installer.

### The file-drop router (2026-10-14, `v1.83.0`)

- `file_drop_router.js` is a plain static file in `agent/static/agent/js/`: `collectstatic` serves it from
  `staticfiles/`, and `agent/test_file_drop_router.py` fails if the collected copy differs from the source. It
  is loaded by the `<head>` of `agent_page.html`, `agentic_control_panel.html`, `prompt_flow_panel.html`,
  `welcome.html`, `login.html`, `admin/base_site.html` and `static/agent/pdf/canvas.html`. The snapshot's
  generic walk carries the script, its tests (`test_file_drop_router.py`, `scripts/file_drop_router_cases.mjs`)
  and the visible runner.
- No migration, no new Python module and no new dependency: an in-app update delivers it like any other
  static file, and the Uninstaller is not involved.

### Compact mode and Self-modify switches (source development, 2026-10-02/03)

The Compact mode switch shipped in `v1.75.0` (annotated tag at `f7eb53ff`,
2026-10-03, published on GitHub the same day). The Self-modify switch landed on
`main` right after that tag (commit `70aeeb87`) and ships in `v1.76.0`
(annotated tag at `953ad2d8`, 2026-10-08). `v1.76.0` was published
on GitHub on 2026-10-09; `v1.77.0` (annotated tag at `052bfe0f`, 2026-10-09)
was published the same day. `v1.78.0` (annotated tag at `0e6fc72d`, 2026-10-10;
migration 0213 `UsageDaily` landed one commit later in `7460a147`) was published
on 2026-10-10. `v1.82.0` (annotated tag at `880a335e`, 2026-10-12) was published on
2026-10-12, and `v1.83.0` (annotated tag at `a2914019`, 2026-10-14) on 2026-10-14; the
latest released version is now **v1.85.0**. Neither adds
a migration, and 0213 reaches existing installs through the post-update `migrate` like
every migration.

- **Compact mode switch (2026-10-02).** `agent/compact_mode.py` is imported at
  module level by `mcp_agent.py`, so the frozen archive carries it through the
  import graph. Model `CompactState` arrives with migration
  `0211_compact_state.py`. The snapshot requires `compact_mode.py`,
  `0211_compact_state.py`, `context_fitter.py`, `compact_costs.js`,
  `model_capacity.js` / `.css` and `chat_table_contrast.js`; the runtime
  inventory's `REQUIRED_STATIC` requires the same page assets.
- **Self-modify switch (2026-10-03).** `rag/config.self_modify_available()`
  decides whether a deployment can self-modify at all: a source (dev) run of
  this checkout always can, folder or no folder; a frozen build only when
  `build.py --self-modify` bundled `TlamatiniSourceCode/` beside the
  executable. The chat template renders the toolbar's **Self-modify** box and
  `self_modify_switch.js` only where that is true, so a default build carries
  the script but never shows it. The choice persists in
  `CompactState.self_modify` (migration `0212_compact_state_self_modify.py`,
  ON by default) and decides, per request, whether `Tlamatini.md` (a size that changes with its contents) is sent; a model that cannot hold it shows
  the box locked OFF.
- **Carriage.** `copy_source_assets.REQUIRED_SNAPSHOT_FILES` names
  `0212_compact_state_self_modify.py` and `self_modify_switch.js`, and
  `build_runtime_assets.REQUIRED_STATIC` names `agent/js/self_modify_switch.js`
  (read from source on 2026-10-03). Both migrations reach existing users
  through the normal post-update path: the updater stages the database through
  `DB/ToLoad` and the first launch after the swap runs `migrate`.
- **Evidence and limits.** Source unit tests (473 across the self-modify, gate,
  Compact, capacity, gauge and frontend suites) and the visible
  `compact_switch_visible.py` (57 checks) and `self_modify_visible.py` (28
  checks) runs passed on 2026-10-03. The frozen branch is covered only by
  `FrozenPageTests`, which render the real chat page under a patched
  `sys.frozen`; no frozen build was produced for this, because `build.py`
  erases `Tlamatini/db.sqlite3` and wipes `dist/` before it builds. A release
  still needs both inclusion sweeps and a visible rebuild check.

### The Model Brain (2026-10-08, `v1.76.0`)

- **Frozen carriage.** `build.py` names `agent.model_brain`,
  `agent.model_brain_chat` and `agent.model_brain_views` in
  `_FROZEN_REQUIRED_AGENT_MODULES` and passes each as `--hidden-import` (the
  first two are imported fail-open, so a missing module could not report
  itself). The sourced knowledge base ships with
  `--add-data=Tlamatini/agent/model_profiles.json;agent` and is read beside the
  module when frozen. `model_brain_tuning.js` / `.css` ride `collectstatic`
  like every page asset.
- **No migration, no required key.** `model_brain` falls back to `auto` in code;
  `model_brain: off` restores the legacy fixed sampler.
- **User state outside the install.** Learned profiles are written to
  `%LOCALAPPDATA%\Tlamatini\model_brain\model_profiles.learned.json`, so a
  self-update neither ships nor erases them.
- **Self-modify snapshot.** The generic walk of `copy_source_assets.py` carries
  the three modules, `model_profiles.json` and the dialog's assets; both
  inclusion sweeps passed CLEAN on 2026-10-08.

## Self-update

- `apply_update.ps1`, `preserved_user_state.json` and the standalone
  `sqlite_copy.py` helper are required install-root assets. Missing/copy failures
  abort packaging. The frozen module archive also requires `agent.self_update`
  and `agent.sqlite_copy`.
- The updater selects the incoming release's swap script, falling back to its
  installed script for older payloads. It copies the script outside the install
  directory before launching it.
- Before replacing application files, the swapper uses carried Python in
  isolated mode to run the shipped SQLite helper. A verified online backup
  includes committed WAL pages and atomically installs one self-contained file
  in `DB/ToLoad`. A plain copy of only `db.sqlite3` omitted recent commits.
- Backup prerequisites are checked before closing the app. Backup must succeed
  before renaming agents or removing application files; there is no fallback to
  an unverified raw database copy. The migration marker is written only after
  backup succeeds. Existing startup code restores the DB and runs migrations.
- The preservation sets match the shared JSON: configurations, contacts, DB,
  context packages, generated content, Temp, Templates and Uninstaller.exe stay.
  Application code, PDF viewer assets, bundled runtimes, helpers and the source
  snapshot are replaced. Agents keep their existing one-generation backup;
  security logs use a unique stash/restore path (see the follow-up below).

## Delivery limit

Code changes require a fresh build and reinstall/release. The September 20 local
rebuild/install is recorded in the evidence linked above; it was not published
remotely. A package assembled before later edits does not prove their inclusion.
The earlier v1.62.0 `dist/Tlamatini_Release_v1.62.0/pkg.zip` was subsequently
inspected read-only: all 354 application static files were byte-identical in
both `_internal/agent/static` and `_internal/staticfiles`, and all four
application templates matched. MuPDF's two native extensions and DLL were
present. This does not validate the new build gates or newly localized templates.
No automated tests, builds or application launches were performed.

## Local frontend and release completeness gate

The September 16 follow-up adds `build_runtime_assets.py` and removes all CDN
script/style/font loads from the four application templates. The new
`static/agent/vendor/frontend/` tree carries 50 upstream files plus its manifest:
Bootstrap 5.3.3, jQuery 3.7.1, jQuery UI 1.13.3, highlight.js 11.9.0 and Nunito
400/700 with all supplied language subsets. Licenses travel with the files.
`scripts/vendor_frontend.py` reproduces them from SHA-512-pinned npm archives;
normal builds never invoke that network operation. Fonts and CSS references stay
local. The previous duplicate Bootstrap 5.3.0 load is removed.

The narrowly scoped `.gitignore` exception makes PDF.js `build/pdf.mjs` and
`build/pdf.worker.mjs` visible to Git. Until these new files are committed with
the rest of the change, existing remote clones still lack them. Snapshot KEEP
rules alone do not change Git publication. The snapshot now also requires the
new build helper and frontend vendoring recipe/manifest and keeps vendor fonts.
Both Git and source-snapshot exclusions also exempt the exact upstream
Bootstrap/jQuery `dist/` directories. Vendored bytes are marked `-text` in
`.gitattributes`, preventing Windows checkout newline conversion from breaking
the integrity receipts.

Build gates (source-input checks exercised by the follow-up sweep; build-time
and fresh-package checks still require a build):

- Check mandatory source inputs and the frontend vendor receipt before expensive
  build steps. Reject missing tracked runtime assets when Git metadata exists.
- Fresh source `collectstatic --clear`; match every application static file by
  bytes/hash, resolve literal static tags and local CSS URLs, and reject template
  CDN resource tags. Freeze the complete source-to-payload inventory.
- Require agent/skill trees, helpers, security toolkit, Java, Git and the active
  Playwright revisions. Pool sessions/logs/caches are not template resources.
  Preserve the public/private secret-handling and user-state policies.
- Fail on unreadable required frozen-module archives, frozen migrations/default
  user creation/collectstatic, required support copies, or executable rename.
- Compare all inventoried source resources with the assembled release; require
  native MuPDF extensions/DLL and browser executables. Write a SHA-256 receipt
  for every payload file, including bundled runtimes, before creating the ZIP.
- Verify exact ZIP membership, duplicate/unsafe paths and every streamed hash/CRC
  before promoting `pkg.zip.part` to `pkg.zip`. Installer assembly independently
  requires the receipt and the matching product version.
- Keep both inner and final outer ZIPs at or below **1,990,000,000 bytes**.
  Complete public/private wrappers write `.pending.zip`, measure the actual
  final archive, and only publish it under its final name if within budget.
  This is not achieved by dropping required files. Oversized pending output is
  retained for inspection; no successful release is reported.

The existing final v1.62.0 ZIP is 1,905,278,037 bytes, leaving 84,721,963 bytes
against the new ceiling. New vendored frontend files total about 2.18 MB before
ZIP compression. These are baseline/input sizes, not a new release measurement.
External model/API/network-agent traffic is deliberately outside the no-CDN UI
contract. The modified release-size regression expectation was updated but not run.

## Self-management follow-up: inclusion skills and executed file audits

The `.claude` and `.gemini` copies of both inclusion skills and their scripts
are synchronized. Their instructions now distinguish source evidence from a
real build, accept both support and required-file carriers, and use the shared
13-name preservation contract rather than the obsolete `empty_dirs + config`
formula. No application tests are needed to run these file-only sweeps:

```powershell
python -B .claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py
python -B .claude/skills/tlamatini-self-modify-inclusion/scripts/sweep_self_modify.py --keep
```

The snapshot checker needs the project's declared PyYAML dependency. It writes
only a fresh diagnostic directory beneath repository `Temp/`; `--keep` prints
its location. It does not start Django or invoke a build.

### Gaps corrected

- **Snapshot completeness:** every file in the shared runtime source trees and
  root-file inventory must survive byte-for-byte (except sanitized config) or
  have an explicit restore mapping matching a real runtime carrier. The first
  sweep exposed 15 tracked PDFer `_art` PNGs (80,854 bytes) previously dropped
  by the broad image exclusion. A narrow KEEP rule includes them. Optional
  gallery artwork remains omitted; the user's deleted images remain deleted.
- **Rebuild pipeline:** explicit snapshot requirements now cover the complete
  public/private wrappers, installer/uninstaller, integrity checker, MCP runtime
  provisioner/defaults, and inclusion skills. Wrappers abort on missing `pkg.zip`
  and require its verified `self_modify` receipt to match the requested flag.
- **Redaction:** JSON/YAML parse or decoding failures abort generation; YAML is
  parsed structurally, including multiline and flow values. Serialization drops
  comments/shadowed duplicate keys. The local external MCP catalog is reset to
  empty `mcpServers`/`active` state, never carried with credentials in arbitrary
  headers, environment keys, arguments or URLs. Audit messages withhold values.
  Unknown secret-bearing formats still require review; pattern scans alone
  cannot prove absence of every possible secret.
- **Snapshot state/paths:** local `artifacts/` previews, generated agent discovery
  metadata and `.tlamatini` state are excluded. Custom destinations must be
  repository descendants and nonempty replacements must carry a snapshot
  manifest. Linked source paths are rejected; emitted manifests omit developer
  absolute paths. These rules do not remove the original local artifacts.
- **Runtime integrity:** `build_runtime_assets.py` ships as a required root
  script and a required frozen module. The installer verifies the entire ZIP
  before extraction. The in-app updater validates outer ZIP paths, then verifies
  inner package membership/version/hash/CRC and extracted staging bytes.
  The external swapper repeats staging verification before shutdown, using
  isolated carried Python (`-I -B -S`, no bytecode writes or site startup hooks).
  Legacy packages without receipts must be rebuilt.
  A receipt detects omissions/corruption; it is not a publisher signature.
- **Swap boundaries/data:** scratch cleanup is limited to owned install-local
  update paths, rejects link redirection and aborts failed cleanup. The swapper
  requires the exact `Temp/_update/staging` location and rejects reparse
  ancestors. It no longer falls back to a process-tree kill that kills itself.
  Preserved state is skipped only when it exists; absent entries get defaults.
  Security evidence receives a unique stash: failed stashing stops deletion,
  failed restoration retains both copies. WAL-aware DB backup remains mandatory.
- **Reinstall:** retain `_internal/db.sqlite3` and its existing WAL companions,
  and flag first-launch migration instead of overwriting with a seeded DB.
  Capture pre-existing preserved directories before extraction, so newly created
  seed directories do not cause sibling files to be skipped. Uninstall retains
  its separate intentional removal policy; it does not consume this contract.

### Evidence and limits

- Self-update source sweep: **0 findings**, shared **13-entry** state contract,
  all seven root PowerShell helpers and four mandatory update helpers carried.
- Self-modify sweep: **0 findings**, **1,470 copied source files**, approximately
  **31.6 MiB**, **740 runtime source inputs** accounted for, **5 configs** with
  value redactions; generated manifest/runbook are additional files. Two heavy
  inputs remain explicitly restored from the install: `jd-cli.jar` and the demo
  video. Optional gallery omission is an intentional advisory, not a failure.
- Python AST parsing, PowerShell parser inspection and `git diff --check` are
  syntax/patch checks, not executed application tests. They do not prove a
  destructive swap, installer, PyInstaller build or first-start migration works.
- The existing v1.62.0 package predates these gates. A fresh public/private build
  and controlled install/update exercise are still needed before release. The
  final ZIP remains capped at 1,990,000,000 bytes; no fresh size is claimed here.
- This update mechanism is not a full transactional rollback system. A failure
  after old application deletion can still require reinstalling; the DB,
  preserved state, agents backup and uniquely stashed evidence are separate
  recovery safeguards, not a rollback guarantee.


## Accumulated visual errors (2026-09-27)

Release assets require `agents/visual_errors.py` and `docs/visual-analysis-errors.md`.
Self-modify snapshots also require `visual_error_reporting.py`, the error regression
suite, visible browser harness and forward prompt-contract migration. Portable
image/video runtime refresh copies the shared notification helper. These support
accumulated themed errors without changing retries or configured recovery routes.
See [the behavior and verification record](visual-analysis-errors.md).

## About Usage carriage (source development, 2026-10-10)

`build.py` requires the frozen `agent.usage_tracking`, `agent.usage_provider` and
`agent.usage_views` modules. `build_runtime_assets.py` requires the Usage template
and collected JS/CSS, plus the user guide `docs/usage-dashboard.md`. `copy_source_assets.py` requires those sources,
`0213_usage_ledger.py`, `test_usage.py` and the three visible-browser harness
modules. The migration adds only `UsageDaily`; there is no manual credit-setting
model or endpoint. Keep these files, the chat template and the `-usage-2` static
cache suffix together. Existing DB preservation/migration mechanics are unchanged.

The 2026-10-10 self-modify sweep produced 1,698 files with zero copy errors and
verified 798 carried/restored runtime inputs byte-for-byte; the self-update
source sweep also passed. These are dated pre-documentation-refresh inclusion
results, not runtime proof of a fresh executable or installed update.
See [the Usage guide](usage-dashboard.md) and its rebuild acceptance boundary.

## Release payload ownership (2026-10-18)

Browser and media agents execute under the carried `python/` interpreter.
`build.py` excludes `cv2`, `ffpyplayer`, `av`, `playwright`, `faster_whisper`,
`ctranslate2` and `onnxruntime` from the frozen Django interpreter, and verifies
that they did not enter its PYZ or package directories. Their carried wheels,
native libraries and agent implementations remain present. PDF context still
requires frozen PyMuPDF; RAG still requires its frozen numeric/search libraries.
Never delete a native library merely because another runtime carries a copy.

Bundled Chromium and FFmpeg revisions come from the **carried** Playwright
manifest. Browser installation uses that interpreter; stale FFmpeg revisions are
filtered along with stale Chromium revisions. Both Chromium and its headless
shell remain available to product configurations. Development verification must
still use visible foreground consoles and explicitly headed browsers.

After all frozen setup checks, only bytecode caches with matching `.py` source
are removed before the runtime receipt is written. Source-less bytecode, PYZ and
standard-library ZIPs remain intact. Carried import verification uses `-B`.
Git's copied root `unins<digits>.exe/.dat/.msg` files are excluded; Git commands,
Bash, hooks, helpers and documentation remain available. The inner package uses
standard DEFLATE level 9, preserving existing installer/updater compatibility.

The Public wrapper's privacy handling is independent of self-modification.
Use its explicit `--self-modify` flag when retaining that capability. Real build
and before/after measurements must use the same mode and source baseline, in a
verified visible development console; static analysis alone is not release
acceptance.
