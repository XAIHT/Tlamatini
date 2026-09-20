# Self-modify and self-update carriage review

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
