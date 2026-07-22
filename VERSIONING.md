<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini — Versioning

This document is the **authoritative reference** for how Tlamatini is versioned. Read it once end-to-end before cutting your first release; after that, the [Cheat Sheet](#cheat-sheet) at the bottom is the only thing you need on screen.

---

## TL;DR

1. **Standard**: [Semantic Versioning 2.0.0](https://semver.org/) — `MAJOR.MINOR.PATCH[-prerelease][+build]`.
2. **Single source of truth**: a **git tag** of the form `v1.44.0`.
3. **No code edits**: you never hand-edit a version string in source files. You tag, then build.
4. **Three injection points**, all computed automatically at build time:
   - `Tlamatini/agent/_version.py` (read at runtime by the About dialog, the startup banner, and `/agent/version/`)
   - PyInstaller `--version-file=…` → embedded into the Win32 `VERSIONINFO` resource of `Tlamatini.exe`, `Installer.exe`, and `Uninstaller.exe` (visible in Explorer → Properties → Details)
   - The release folder name (`dist/Tlamatini_Release_v1.44.0/`)
5. **Fallback**: if you don't tag at HEAD, the version is the **bare base tag** that's reachable from HEAD (e.g. `1.1.1`). No `.devN`, no `+gSHA`, no `.dirty` suffix is ever emitted — the displayed version is always a clean SemVer. If no `v*` tag exists at all, the fallback is `0.0.0`.

---

## 1. The standard: Semantic Versioning 2.0.0

A Tlamatini version always has this shape:

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]

Examples:
  1.0.0
  1.44.0
  2.0.0-rc.1
  1.44.0+build.482
```

**Bump rules** (when do you increment what?):

| Component | Bump when… | Example trigger in Tlamatini |
|---|---|---|
| **MAJOR** | You make a **backward-incompatible** change | The `.flw` file schema changes, an Agent Contract is removed, a public endpoint URL changes, the LLM tool surface name changes such that old configs break |
| **MINOR** | You add **backward-compatible** functionality | A new agent type (e.g. ACPXer in 1.x → 1.(x+1)), a new toolbar checkbox, a new SKILL, a new endpoint, a new field on an existing API |
| **PATCH** | You make a **backward-compatible** bug fix | Conjunction parser fix, exec-report ordering fix, ACPX oneshot-prompt fix, any commit that fits "fixes regression / closes bug" |
| **-PRERELEASE** | You want a labelled candidate before the real release | `2.0.0-alpha.1`, `2.0.0-rc.2` — sort BEFORE `2.0.0` and are NOT considered stable |
| **+BUILD** | Build metadata (commit, CI number, timestamp) | Generated automatically — you never type this part |

**Pick the right level by asking**: "Will a user running the previous version need to change anything to use this one?"
- **No, and there are new features** → MINOR
- **No, and it's just fixes** → PATCH
- **Yes, they'll have to change something** → MAJOR

---

## 2. Where Tlamatini stores the version

There is **exactly one place** the version lives: **git tags**. Everything else is computed from it.

```
git tags (the source of truth)
   │
   ▼
build.py / build_installer.py / build_uninstaller.py
   │
   ▼  emits two files at build time
   ├─►  Tlamatini/agent/_version.py        (read at runtime)
   └─►  Tlamatini.version.txt              (consumed by PyInstaller --version-file)
   │
   ▼  the build outputs ship with the version baked in
   ├─►  Tlamatini.exe / Installer.exe / Uninstaller.exe
   │       └── right-click → Properties → Details → ProductVersion
   ├─►  dist/Tlamatini_Release_v1.44.0/       (release folder name)
   └─►  Runtime surfaces:
            ├── About dialog:   "Tlamatini v1.44.0"
            ├── Console banner: "--- [VERSION] Tlamatini 1.44.0"
            ├── tlamatini.log:  (same banner — tee'd)
            └── GET /agent/version/  →  { version, build, commit, date, source }
```

**Files you never edit by hand to bump a version:**
- `Tlamatini/agent/_version.py` — generated, gitignored.
- `Tlamatini.version.txt` (and the `Installer.` / `Uninstaller.` siblings) — generated, gitignored, cleaned up at end of build.
- The `Tlamatini v…` string in `agent_page.html` — it now reads `{{ version }}` from a context processor.

---

## 3. How the version is resolved (precedence)

There are **two** resolution moments: **build time** (what gets baked into the artefacts) and **runtime** (what the running app reports).

### 3.1 Build-time resolution

When you run `python build.py`, `build_installer.py`, or `build_uninstaller.py`, the script picks a version using this precedence (highest wins):

| # | Source | How to use it | Example value |
|---|---|---|---|
| 1 | **`--version X.Y.Z` CLI flag** | `python build.py --version 1.44.0` | `1.44.0` |
| 2 | **`$env:TLAMATINI_VERSION`** | `$env:TLAMATINI_VERSION = "1.44.0"; python build.py` | `1.44.0` |
| 3 | **`git describe --tags --abbrev=0 --match 'v[0-9]*'`** | `git tag -a v1.44.0 -m "..."; python build.py` | always the bare base tag → `1.44.0` (distance / dirty state never appear in the version string) |
| 4 | **Sentinel** | _(no git, no tags, no flag)_ | `0.0.0+unknown` |

> `build.py` exports `$env:TLAMATINI_VERSION` so that if you run all three scripts in the same shell, `build_installer.py` and `build_uninstaller.py` see the same version `build.py` decided on — even if you never tagged at all (i.e. the git-derived dev version stays consistent across the three artefacts).

### 3.2 Runtime resolution

When `Tlamatini.exe` starts (or `python manage.py runserver` in source mode), `agent.version.get_version()` resolves the displayed version like this:

| # | Source | When this fires |
|---|---|---|
| 1 | `agent._version.__version__` | Frozen builds always hit this; source-mode hits it only after you've run `build.py` at least once (since the build emits `_version.py`) |
| 2 | `git describe --tags --abbrev=0 --match 'v[0-9]*'` against the working tree (always returns the bare base tag — no dev/dirty suffix) | Source-mode developer who hasn't run `build.py` |
| 3 | `"0.0.0+unknown"` sentinel | Last resort — never raises |

> The runtime resolution and build resolution intentionally **share the same `git describe` helper** so the version you see in the About dialog during development matches what would be baked in if you ran `build.py` right now.

---

## 4. Step-by-step: how to cut a release

This is the canonical happy path. Follow it exactly the first few times until it becomes muscle memory.

### Step 1 — Make sure the working tree is clean and on `main`

```powershell
git status                  # should report "nothing to commit, working tree clean"
git checkout main           # solo-dev rule: tags always cut from main
git pull --ff-only          # make sure you're at the tip
```

If `git status` shows changes: commit or stash them first. Building with a dirty tree is allowed but it will produce a `…dirty` version, which is the loud signal that "this is not a clean release".

### Step 2 — Decide the new version number

Use the bump-rules table in §1. Look at the commits since the previous tag if you're unsure:

```powershell
git log --oneline (git describe --tags --abbrev=0)..HEAD
# (if no tags yet, just: git log --oneline)
```

- All commits are bug fixes? → PATCH (`1.2.0` → `1.2.1`).
- At least one new feature? → MINOR (`1.2.0` → `1.3.0`).
- Anything that breaks a `.flw` / API / agent contract that already shipped? → MAJOR (`1.2.0` → `2.0.0`).

### Step 3 — Create the annotated tag

```powershell
git tag -a v1.44.0 -m "Release 1.44.0: <one-line summary>"
```

The `-a` flag makes it an **annotated** tag (carries a message + author + date). `--match 'v[0-9]*'` in the resolver is why the leading `v` is required.

### Step 4 — Push the tag

```powershell
git push origin v1.44.0
# or push everything: git push --follow-tags
```

### Step 5 — Build

```powershell
python build.py
python build_uninstaller.py
python build_installer.py
```

All three scripts will pick up `v1.44.0` automatically (precedence #3 — git describe finds an exact tag at HEAD).

You'll see this in each script's output:
```
Tlamatini version : 1.44.0
VERSIONINFO file  : C:\Development\Tlamatini\Tlamatini.version.txt
…
  Build completed successfully in 240s
  Version : 1.44.0
```

The final artefact is **`dist/Tlamatini_Release_v1.44.0/`** — zip and distribute.

### Step 6 — Verify

After install, the user (or you) should see:

- **About dialog**: `Tlamatini v1.44.0`
- **Right-click `Tlamatini.exe` → Properties → Details**: ProductVersion = `1.44.0`
- **Console banner on startup**: `--- [VERSION] Tlamatini 1.44.0`
- **`curl http://localhost:8000/agent/version/`** (after login or with anonymous access since it's open):
  ```json
  {"version":"1.44.0","build":"1.44.0","commit":"abc1234","date":"2026-05-18T12:00:00Z","source":"generated"}
  ```

If any of those four says something different, you missed Step 3 (the tag), or you've got a stale `_version.py` from a previous build — clean it up and re-run `build.py`.

---

## 5. Step-by-step: what happens if you DON'T specify a version

This is the most common path during development. The system never blocks you for "no version" and it never decorates the version with distance / commit / dirty suffixes — the displayed version is **always** a clean SemVer.

### 5.1 You ran `build.py` with no tag, no CLI flag, no env var

The build script falls through to **precedence #3** (`git describe --tags --abbrev=0 --match 'v[0-9]*'`) — the most recent reachable `v*` tag, stripped to its bare body:

| Situation | Tlamatini version |
|---|---|
| Tags exist; HEAD is exactly on `v1.2.0` | `1.2.0` |
| Tags exist; HEAD is 17 commits past `v1.2.0` (clean tree) | `1.2.0` |
| Same as above + uncommitted edits | `1.2.0` |
| **No tags at all yet** | `0.0.0` |
| No tags AND dirty tree | `0.0.0` |
| Not a git repo (e.g. running on a download zip) | `0.0.0+unknown` |

There is **no `.devN`, no `+gSHA`, no `.dirty`** in any of these outputs. The version you see in the About dialog, the banner, the `.exe` properties, and `/agent/version/` is always a clean `MAJOR.MINOR.PATCH`. If you cut a release on a tree that has uncommitted edits the audit trail lives in git (commit log, `git status`), not in the version string.

### 5.2 You ran `build.py` with no tag, BUT in a shell where `$env:TLAMATINI_VERSION` is set

The build script uses that environment value (precedence #2). This is the **only** legitimate path that lets you produce a release-shaped artefact without first creating a git tag. It's intended for CI: a CI job derives the version from a release-trigger event, exports it, then runs all three build scripts.

For a manual local build, do **not** rely on the env var — tag first (it's two seconds and creates the audit trail you'll want when triaging a regression later).

### 5.3 You ran `build.py --version 2.0.0-rc.1` on a tree that doesn't have that tag

The CLI flag wins (precedence #1). Useful for cutting a release candidate locally **before** you actually commit to the tag — build, smoke-test the `.exe`, then if happy, tag and rebuild.

---

## 6. Pre-releases (alpha / beta / rc)

SemVer allows any dot-separated identifiers in the pre-release part. Tlamatini's convention:

```
2.0.0-alpha.1     # early, expect breakage
2.0.0-alpha.2
2.0.0-beta.1      # feature-complete, debugging
2.0.0-rc.1        # release candidate — bug-fix-only from here
2.0.0-rc.2
2.0.0             # the actual release
```

Tag them exactly the same way:

```powershell
git tag -a v2.0.0-rc.1 -m "Release candidate 1 for 2.0.0"
git push origin v2.0.0-rc.1
python build.py
# → produces dist/Tlamatini_Release_v2.0.0-rc.1/
```

**Pre-releases sort BEFORE the final release** per SemVer (`2.0.0-rc.2` < `2.0.0`). Windows' "Programs & Features" registry honors this ordering too.

---

## 7. What if I tag the wrong version?

A git tag is just a ref — it can be deleted and re-created. **But never re-use a tag that has already been pushed to a remote where someone else might have fetched it.** For Tlamatini (solo, push to one remote), the recovery is:

```powershell
git tag -d v1.20.0                    # delete local tag
git push origin :refs/tags/v1.20.0    # delete remote tag
git tag -a v1.20.0 -m "Release 1.20.0" # re-create at correct commit
git push origin v1.20.0
```

A safer flow: **never delete tags**. If you tagged `v1.20.0` at the wrong commit, bump to `v1.44.0` at the right commit and move on. SemVer was designed assuming you'd do exactly this.

---

## 8. File-by-file reference

What each new/changed file does. Read this only when you need to debug or extend the system.

| File | Role |
|---|---|
| **`Tlamatini/agent/version.py`** | Runtime version resolution. `get_version()`, `get_version_info()`, `derive_version_from_git()`, plus the SemVer parser and the Win32 VERSIONINFO renderer. Has **zero Django dependency** — safe to import from `manage.py` before Django is initialised. |
| **`Tlamatini/agent/_version.py`** | **Generated at build time** by `build.py`. Holds `__version__`, `__build__`, `__commit__`, `__date__`. **Gitignored.** Do not edit by hand. |
| **`versioning.py`** (repo root) | Top-level shim the three build scripts import. Adds the CLI-arg parser, the precedence resolver (`resolve_build_version`), and the artefact emitter (`emit_build_artifacts`). |
| **`Tlamatini/tlamatini/context_processors.py`** | Adds `app_version(_request)` that exposes `{{ version }}` to every Django template. Registered in `settings.py`. |
| **`Tlamatini/tlamatini/settings.py`** | One-line addition registering the `app_version` context processor. |
| **`Tlamatini/agent/views.py`** | New `version_view`. Open endpoint (no `@login_required`) so it can be used as a health-check. |
| **`Tlamatini/agent/urls.py`** | Adds `path('version/', views.version_view, name='version')`. |
| **`Tlamatini/agent/templates/agent/agent_page.html`** | The hardcoded `Tlamatini v1.0.0` becomes `Tlamatini v{{ version }}`. |
| **`Tlamatini/manage.py`** | Adds `_print_version_banner()` — one `print()` after the tee stream is installed, so both the console AND `tlamatini.log` get a `--- [VERSION] Tlamatini X.Y.Z` line on every startup. |
| **`build.py`** | Resolves the version, writes `agent/_version.py` and `Tlamatini.version.txt`, passes `--version-file=…` to PyInstaller, exports `$env:TLAMATINI_VERSION`, cleans up the .txt at the end. |
| **`build_uninstaller.py`** | Reads `$env:TLAMATINI_VERSION` (or falls back to git), writes `Uninstaller.version.txt`, passes `--version-file=…` to PyInstaller. |
| **`build_installer.py`** | Same pattern as the uninstaller. Also renames the release folder to `Tlamatini_Release_v<version>` so distribution is unambiguous. |
| **`.gitignore`** | Adds the generated `_version.py` and the three transient `*.version.txt` files. |

---

## 9. Cheat sheet

The one-screen version of this entire document.

```
PICK A NUMBER         MAJOR.MINOR.PATCH per SemVer 2.0.0
                      ─ MAJOR: breaking change
                      ─ MINOR: backward-compat feature
                      ─ PATCH: backward-compat fix

TAG IT                git tag -a v1.44.0 -m "Release 1.44.0"
                      git push origin v1.44.0

BUILD IT              python build.py
                      python build_uninstaller.py
                      python build_installer.py

WHERE IT LANDS        dist/Tlamatini_Release_v1.44.0/
                      About dialog : "Tlamatini v1.44.0"
                      Exe → Properties → Details : ProductVersion = 1.44.0
                      curl /agent/version/ : {"version":"1.44.0", …}
                      Console banner : --- [VERSION] Tlamatini 1.44.0

NO TAG AT HEAD?       Build still works.  Version becomes the most recent
                      reachable v* tag, bare (no dev/sha/dirty suffix), or
                      0.0.0 if no tags at all (0.0.0+unknown if no git).

OVERRIDE              python build.py --version 2.0.0-rc.1
                      $env:TLAMATINI_VERSION = "2.0.0-rc.1"; python build.py

UNDO A TAG            git tag -d v1.44.0
                      git push origin :refs/tags/v1.44.0
                      (… but prefer: just bump to v1.44.0 instead)
```

---

## 10. FAQ

**Q: I just want to ship a build. Do I really have to learn all this?**
A: No. Run `python build.py` with no flags — you'll get a clean version (the most recent reachable `v*` tag, e.g. `1.1.1`, or `0.0.0` if there are no tags yet) that runs, installs, and shows the right number everywhere. The discipline (Steps 1–6 above) only matters when you want the version string itself to reflect that you cut a fresh release at exactly this commit.

**Q: Where does `_version.py` come from on a fresh clone?**
A: It doesn't. The file is gitignored. On a fresh clone, `agent.version.get_version()` falls through to the git-derive path until the first time you run `build.py`. The About dialog, banner, and `/agent/version/` will all show the same git-derived value — so the runtime is **never** stuck on a stale `1.0.0`.

**Q: Why is there no `.devN` / `+gSHA` / `.dirty` suffix on the version string?**
A: Deliberate. The version surface (About dialog, banner, `.exe` properties, `/agent/version/`) is meant to read as a clean SemVer like `1.1.1`. Distance-from-tag and dirty state are git concerns and stay in git (`git status`, `git describe --long --dirty`). If you want the "this isn't a clean release" signal in the build output itself, pass `--version <something>-rc.1` explicitly.

**Q: What if `python build.py` is run from a directory that isn't the repo root?**
A: The `versioning.py` shim resolves paths from its own file location, not from `os.getcwd()`. Run it from anywhere.

**Q: The frozen `.exe` shows `0.0.0+unknown` but I tagged before building.**
A: Two common causes:
1. The build was run inside a shell where `$env:TLAMATINI_VERSION` was already set to a stale value — that takes precedence over `git describe`. Clear it: `Remove-Item env:TLAMATINI_VERSION`.
2. `git describe` couldn't see the tag because it's only local. Run `git fetch --tags` (or push the tag) so the build machine sees it.

**Q: Can I commit `_version.py` to lock a release?**
A: No need. Git tags already lock the release — the tag points at a specific commit and that commit is what gets built. Committing `_version.py` would just create a never-ending stream of "bump version" commits, which is exactly what this system was designed to eliminate.
