# Self-modify and self-update carriage review

Reviewed on 2026-09-16 by reading source files, dependency code and packaging
rules only. No tests, sweep scripts, builds, application launches or update
operations were run. Changes below are source-reviewed, not runtime-verified.

## Build and rebuild

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
  security logs keep the existing stash/restore path.

## Delivery limit

These changes require a fresh build and reinstall/release. An artifact assembled
while this review was in progress does not prove inclusion of the final edits.
Physical payload inspection and execution of the updated mechanisms remain
unperformed under the requested no-process/no-tests constraint.
