---
name: project-versioning-2026-05-15
description: "SemVer 2.0.0 versioning system with git-tag-derived versions, injected into build artefacts at build time. Replaces the hardcoded \"Tlamatini v1.0.0\" in agent_page.html and gives all three build scripts a real version. Authoritative docs in VERSIONING.md."
metadata: 
  node_type: memory
  type: project
  originSessionId: 881d31f8-12cd-42f3-a3a9-62976ad43ad4
---

2026-05-15: Tlamatini gained a full versioning system. SemVer 2.0.0, git tags are the single source of truth, `0.0.0+unknown` is the last-resort sentinel.

**Why:** The About page hardcoded `v1.0.0` forever, and `build.py` / `build_installer.py` / `build_uninstaller.py` had no way to specify the version, so Windows Properties → Details showed nothing useful and "what version is this?" had no answer.

**How to apply:** When the user wants to cut a release, follow VERSIONING.md §4: `git tag -a vX.Y.Z -m "..."` on `main`, push, then run the three build scripts in order. The release folder is automatically named `dist/Tlamatini_Release_v<version>/`. The About dialog, the console banner, `tlamatini.log`, the right-click → Properties → Details ProductVersion, and `GET /agent/version/` will all show the same value.

**Files introduced/modified:**
- `Tlamatini/agent/version.py` — runtime version-resolution module (no Django dep). `get_version()`, `get_version_info()`, `derive_version_from_git()`, plus SemVer parser and Win32 VERSIONINFO renderer.
- `Tlamatini/agent/_version.py` — **generated** by `build.py`. Gitignored. Holds `__version__`, `__build__`, `__commit__`, `__date__`. Never hand-edit.
- `versioning.py` (repo root) — build-time shim. `extract_cli_version(sys.argv)`, `resolve_build_version(cli_arg)`, `emit_build_artifacts(version)`, `render_versioninfo_for(version, path, ...)`.
- `Tlamatini/tlamatini/context_processors.py::app_version(_request)` — exposes `{{ version }}` to every Django template; registered in `settings.py`.
- `Tlamatini/agent/views.py::version_view` — open (no login_required) JSON endpoint at `/agent/version/` returning `{version, build, commit, date, source}`.
- `Tlamatini/agent/urls.py` — `path('version/', views.version_view, name='version')`.
- `Tlamatini/agent/templates/agent/agent_page.html:414` — `Tlamatini v1.0.0` → `Tlamatini v{{ version }}`.
- `Tlamatini/manage.py::_print_version_banner()` — prints `--- [VERSION] Tlamatini X.Y.Z` on every startup. Tee is already installed so it lands in `tlamatini.log` too.
- `build.py` — version-resolution at top of `main()`, writes both `agent/_version.py` AND `Tlamatini.version.txt`, passes `--version-file=...` to PyInstaller, exports `$env:TLAMATINI_VERSION` for downstream scripts, adds `--hidden-import=agent._version`. Cleans up the .txt at end.
- `build_uninstaller.py` — same pattern, picks up `$env:TLAMATINI_VERSION` set by `build.py`. Writes `Uninstaller.version.txt`, passes `--version-file=...`.
- `build_installer.py` — same. Also renames release folder to `Tlamatini_Release_v<version>` (sanitised — `+` becomes `_`).
- `.gitignore` — adds `Tlamatini/agent/_version.py` plus the three transient `*.version.txt` files.

**Resolution precedence (highest wins):**
1. `--version X.Y.Z` CLI flag (build-time only)
2. `$env:TLAMATINI_VERSION` (build-time only — set by build.py so all 3 scripts agree)
3. `git describe --tags --long --dirty --match 'v[0-9]*'`
4. `0.0.0+unknown` sentinel

At runtime: `_version.py` → `git describe` → sentinel. Same `derive_version_from_git()` helper feeds both build-time and runtime.

**No-tag fallback semantics:** uses PEP 440-shaped dev versions (`1.2.0.dev17+gabc1234.dirty`) so they sort BEFORE the next stable. Pre-release tags use pure SemVer (`v2.0.0-rc.1`). `.dirty` suffix means uncommitted edits at build time — never ship dirty.

**Smoke test (verified 2026-05-15):** `python -c "from versioning import ...; print(derive_version_from_git())"` → `0.0.0.dev0+g0da6424.dirty` (no tags exist yet). `get_version_info()` → `{'version': '0.0.0.dev0', 'build': '0.0.0.dev0+g0da6424.dirty', 'commit': '0da6424', 'date': '', 'source': 'git'}`.

**Do NOT:**
- Hand-edit `_version.py` — it's regenerated on every build.
- Re-add a hardcoded `Tlamatini v1.0.0` anywhere. The About dialog now uses `{{ version }}`.
- Commit `_version.py` — it's gitignored intentionally. On a fresh clone, `get_version()` falls through to `git describe` until the first build.
- Drop the `--match 'v[0-9]*'` from the git-describe call — without it, non-version tags (if any are ever added) would confuse the resolver.
- Drop `--hidden-import=agent._version` from `build.py` — PyInstaller's static analysis catches the import inside try/except, but the explicit hint guards against future analysis regressions.

**Related docs:** `VERSIONING.md` at the repo root is the authoritative user-facing reference (§9 is the one-screen cheat sheet, §10 is the FAQ). [[user-profile]] [[feedback-main-branch-only]]
