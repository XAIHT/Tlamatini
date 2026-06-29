---
name: tlamatini-self-update-inclusion
description: Sweep the whole codebase and keep the SELF-UPDATE pipeline complete — so every new asset/feature added to Tlamatini is actually carried into a release by build.py AND survives (or is correctly replaced by) the self-update swap. Invoke whenever you add/rename a new agent, top-level file or directory, dependency, bundled runtime, migration, static/template asset, or any "ship it next to the exe" artifact — and ALWAYS after a feature like Blenderer or the self-update capability lands. Audits the three files that own the pipeline (build.py, agent/self_update.py, apply_update.ps1) against four hard invariants, with a runnable sweep script that never forgets the minimal thing. Pairs with copy_source_assets.py (the self-modify snapshot) and VERSIONING.md.
---

# Tlamatini — Self-Update Inclusion Sweep

> **Audience:** Claude Code working ON the Tlamatini codebase for **Angela**.
> **Goal:** guarantee that *every* asset a new feature introduces is (1) **carried into
> the release** by `build.py`, and (2) **handled correctly by the self-update swap** —
> either preserved (user data) or replaced (app code). Nothing minimal forgotten, ever.

This skill is the **safety net for shipping**. A feature can be 100% correct in source and
still be invisible to every existing user after they click *About ▸ Check for updates* —
because the asset was never bundled, or because the swap deleted/kept the wrong thing. This
sweep makes that class of bug impossible to ship silently.

---

## The three files this skill owns

| File | Role in the pipeline |
|---|---|
| **`build.py`** (repo root) | Assembles the release tree (`dist/manage` → `pkg.zip`). If an asset isn't carried by one of its 6 mechanisms (below), it is **not in the download**, so a self-update can never deliver it. |
| **`Tlamatini/agent/self_update.py`** | In-app updater: checks GitHub, downloads + unzips + stages the new build, hands off to the PowerShell swapper. Its **docstring preserve list** documents what survives. |
| **`apply_update.ps1`** (repo root) | The external file-swapper. Its **`$Preserve` array** is the *authoritative, executed* contract for what is kept vs replaced. Renames `agents → agents_backup`, then full-replaces everything not preserved. |

> `apply_update.ps1` must itself be shipped by `build.py` (`support_files`) so a self-updated
> install carries the *next* updater. The pipeline is self-hosting — this is invariant #1's
> most easily-forgotten case.

---

## How the release is assembled — the 6 carrier mechanisms in `build.py`

Every asset reaches users through **exactly one** of these. When you add an asset, ask
"which carrier moves it?" If the answer is "none", it will NOT ship.

| # | Mechanism (`build.py`) | Carries | Auto-includes new files? |
|---|---|---|---|
| 1 | **PyInstaller import graph → PYZ** | every `.py` reachable from the import graph (incl. lazy `from . import x`) — views, tools, registries, `self_update.py`, **migrations** | ✅ yes, if imported/in a collected package |
| 2 | **`--add-data` list** | whole trees: `agent/templates`, `agent/static`, `staticfiles`, `agent/skills_pkg`; single files: `config.json`, `prompt.pmt`, `Tlamatini.md`; dependency data files | ✅ for files *inside* an already-listed tree; ❌ for a **new** top-level tree |
| 3 | **`optional_dir_copies` → install root** | `agent/images`, **`agent/agents`** (the whole agent-template tree → new agents auto-ship), `agent/skills_pkg` | ✅ new agents/skills inside these dirs |
| 4 | **`optional_file_copies` / `required_file_copies` → install root** | `config.json`, `prompt.pmt`, `Tlamatini.md`; `README.md`, `agents_descriptions.md` | ❌ a **new** root-level required file must be added by hand |
| 5 | **`support_files` → install root** | the `.ps1` helpers (`Tlamatini.ps1`, `register_flw`/`unregister_flw`, `CreateShortcut`/`RemoveShortcut`, **`apply_update.ps1`**), `Tlamatini.ico`, `CreateShortcut.json`, `cat_art.py` | ❌ a **new** root-level support file must be added by hand |
| 6 | **bundled runtimes + deps** | carried Python, `jre`, `git`, `ms-playwright`; PyInstaller **hidden imports**, **`--collect-all`** (e.g. `ffpyplayer`); **`requirements.txt`** | ❌ a **new** runtime / hidden import / collect-all / pip dep must be added by hand |
| — | **DB delivery** | `build.py` step 8a runs `migrate`, so the shipped `db.sqlite3` carries every migration's seeded rows (new agent row, `chat_agent_*` tool row, demo prompts) | ✅ rows ship; ⚠️ see the DB special case |

**The forgettable carriers are 2 (new top-level tree), 4, 5, and 6** — anything that lives at
the repo root or needs an explicit PyInstaller flag. Mechanisms 1 and 3 are automatic, which
is exactly why a new *agent* needs no build edit but a new *root-level script* does.

---

## How an update swaps — preserve vs replace

`apply_update.ps1` does: validate staged build → kill running app → `agents → agents_backup`
→ **delete** old install except `$Preserve` → **move in** new build except `$Preserve` → relaunch.

So every top-level entry is in one of three buckets:

- **PRESERVED** (`$Preserve`) — user data / runtime state. Kept across updates. Must equal the
  set of runtime-writable dirs.
- **SWAP-BACKED** — `agents` only (renamed to `agents_backup`, then replaced). One backup kept.
- **REPLACED** — everything else (the exe, `python`/`jre`/`git`, `.ps1`/`.ico`, `prompt.pmt`,
  `Tlamatini.md`, `README.md`, `agents_descriptions.md`, `images`, `skills_pkg`, **`db.sqlite3`**).

---

## The FOUR invariants (this is the whole job)

### Invariant 1 — CARRY: every new asset reaches the release
For each asset a feature adds, a carrier (table above) moves it into `dist/manage`/`pkg.zip`.
The high-risk cases: a **new repo-root file** (→ `support_files` or `*_file_copies`), a **new
top-level tree** (→ `--add-data` or `optional_dir_copies`), a **new dependency** (→
`requirements.txt` + maybe hidden-import / `--collect-all`), a **new bundled runtime**.

### Invariant 2 — PRESERVE PARITY: the two preserve lists are identical
`apply_update.ps1` `$Preserve` (executed) **==** `self_update.py` docstring "Preserved across
the swap" list (documented). A drift here means the docs lie about what survives.

### Invariant 3 — PRESERVE CORRECTNESS: state preserved, code replaced
`$Preserve` **==** `build.py` `empty_dirs` (reduced to top-level names; `DB/ToLoad`+`DB/Older`
→ `DB`) **+ `config.json`**. Rationale: `empty_dirs` *is* the canonical list of runtime-writable
dirs the app creates. A **new runtime-state dir** added to `empty_dirs` that is NOT added to
both preserve lists will be **wiped on every update** (silent user-data loss). Conversely an
**app-code** top-level entry (anything under `optional_dir_copies` like `images`/`skills_pkg`,
or `python`/`jre`/`git`) must **NOT** be preserved, or users get stuck on stale code forever.

### Invariant 4 — DB DELIVERY: new migration rows actually reach users
Today `db.sqlite3` is **REPLACED** (not in `$Preserve`), so the freshly-migrated build DB —
with the new agent/tool/prompt rows — lands. ✅ new rows arrive, ⚠️ **but the user's chat
history + custom Tool/Mcp/Agent toggles are reset every update.** If `db.sqlite3` is ever moved
into `$Preserve` to fix that, you MUST add a **first-run `migrate`** (apps.ready / manage.py /
the `DB/ToLoad` swap) or new migrations will silently never apply. Pick one and keep it coherent
— never "preserve the DB" without a migrate path. (See the DB note in the Blenderer/self-update
review.)

---

## THE SWEEP — run this every time

### Step 0 — run the deterministic checker (does 90% of the work)

```bash
python .claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py
```

It parses the three files and reports `[PASS]` / `[FINDING]` for invariants 2, 3, the
root-`.ps1` census (invariant 1's worst case), app-dir-must-not-be-preserved (invariant 3),
and a migrations-since-last-tag count (invariant 4). Exit code is non-zero if any finding —
so it's usable as a pre-release gate. Fix every `[FINDING]` before shipping.

### Step 1 — diff since the last release and classify every new path

```bash
# what changed since the last shipped tag
git diff --name-status "$(git describe --tags --abbrev=0 --match 'v[0-9]*')"..HEAD
# any brand-new TOP-LEVEL repo entries (the highest-risk for "forgot to ship")
git diff --name-status "$(git describe --tags --abbrev=0 --match 'v[0-9]*')"..HEAD \
  | awk '$1=="A"{print $2}' | awk -F/ '{print $1}' | sort -u
```

For each **new top-level file or dir**, run it through the **asset taxonomy** below and confirm
its carrier is wired. New nested files inside `agent/static`, `agent/templates`,
`agent/agents/<x>`, `agent/skills_pkg`, or any `.py` in a package are auto-carried — note them
but they need no edit.

### Step 2 — the carrier checks the script can't fully judge (do by eye)

Run these greps and reconcile each hit against `build.py`:

```bash
# (a) New third-party imports in pool agents / app → requirements.txt + maybe hidden-imports/collect-all
grep -rnE "^\s*(import|from)\s+([a-z0-9_]+)" Tlamatini/agent/agents --include=*.py \
  | grep -ivE "import (os|sys|json|re|time|subprocess|socket|threading|pathlib|typing|shutil|logging|urllib|zipfile|tarfile|wave|base64|struct|math|datetime|tempfile|argparse|queue|signal|ctypes|glob|io|collections|functools|itertools)\b"
grep -nE "hiddenimports|--hidden-import|--collect-all|--collect-submodules" build.py
# (b) Any external EXE/runtime a new agent shells out to (like jre/git) → must be bundled
grep -rnE "subprocess|Popen|shutil.which|\.exe\b" Tlamatini/agent/agents --include=*.py | grep -iE "\.exe|which\(" | head
# (c) New requirements vs what build pins
grep -nE "_agent_libs|AGENT_DEP|pip install|requirements" build.py | head
```

If a new agent imports a new library, it must be in `requirements.txt` **and** importable by the
**carried Python** (see `bundle_carried_python` / the `_agent_libs` verify list) — otherwise the
frozen pool agent crashes at runtime even though the source is correct.

### Step 3 — confirm the asset actually lands in `pkg.zip` (ground truth)

The only 100%-sure check is to look at a real bundle. If a recent `dist/manage` or `pkg.zip`
exists, list it; otherwise note that a build is required to verify physically:

```bash
[ -f pkg.zip ] && python - <<'PY'
import zipfile
names = zipfile.ZipFile("pkg.zip").namelist()
for probe in ("apply_update.ps1","db.sqlite3","agents/blenderer/blenderer.py","Tlamatini.exe"):
    print(("OK  " if any(probe in n for n in names) else "MISS"), probe)
PY
```

If no bundle exists, do NOT claim it ships — say "verified in source/wiring; physical bundle
check needs a `python build.py` run."

### Step 4 — fix every finding, then re-run Step 0 until clean.

---

## Asset taxonomy — type → carrier → preserve?

| New asset | Carry via (build.py) | Preserve on update? |
|---|---|---|
| New **agent** (`agent/agents/<x>/`) | mech 3 (`optional_dir_copies` agents) + mech 1 (PYZ) — **automatic** | No (arrives via `agents` swap) |
| New **migration** (seeds rows) | mech 1 (PYZ) + step-8a `migrate` → shipped `db.sqlite3` | No (DB replaced — invariant 4 caveat) |
| New **repo-root `.ps1`/script** (e.g. `apply_update.ps1`) | mech 5 `support_files` — **manual** | No (app code, replaced) |
| New **repo-root required data file** | mech 4 `*_file_copies` — **manual** | No |
| New **top-level source tree** (new package dir to ship as data) | mech 2 `--add-data` / mech 3 `optional_dir_copies` — **manual** | No |
| New **static/template/skill** file (inside existing tree) | mech 2 / 3 — **automatic** | No |
| New **pip dependency** | mech 6 `requirements.txt` (+ hidden-import / `--collect-all` if dynamic) — **manual** | n/a |
| New **bundled runtime** (CLI the agent shells out to) | mech 6 bundler (mirror `bundle_git`/`bundle_java_runtime`) — **manual** | No (replaced) |
| New **runtime-writable dir** (app writes user data here) | mech `empty_dirs` (ship empty) — **manual** | **YES — add to BOTH preserve lists** |
| New **config key with a secret** | already in `config.json` (preserved) | Yes (config.json preserved) |

The single most dangerous omission is the last-but-one row: a **new runtime-state dir** added to
`empty_dirs` but not to `$Preserve` + the `self_update.py` docstring → **wiped on every update.**
The sweep script flags exactly this.

---

## Where to make each fix

- **Carry a root file** → add to `support_files` (scripts/icons) or `required_file_copies`
  (data) in `build.py`, with a one-line comment on *why it must be next to the exe*.
- **Carry a new tree** → add an `--add-data` line (if read from the bundle) or an
  `optional_dir_copies` entry (if read from the install root).
- **Carry a dep** → `requirements.txt`; if PyInstaller can't see it, add a hidden-import or
  `--collect-all`; if a pool agent imports it, confirm the **carried Python** has it
  (`_agent_libs`).
- **Preserve a new state dir** → add the top-level name to `apply_update.ps1` `$Preserve`
  **and** the `self_update.py` docstring list (keep them identical), and ship it empty via
  `build.py` `empty_dirs`.
- **Stop preserving stale app code** → remove it from `$Preserve` (+ docstring).
- **DB** → if preserving `db.sqlite3`, wire a first-run `migrate`; if replacing it (current),
  leave it out of `$Preserve` and keep the docstring honest ("the live db.sqlite3 is replaced;
  the `DB/` swap folder is preserved").

---

## Done criteria (all must hold)

1. `sweep_self_update.py` exits clean (no `[FINDING]`).
2. Every new top-level repo path from the since-last-tag diff has a wired carrier.
3. The two preserve lists are byte-identical and equal `empty_dirs`(top-level) + `config.json`.
4. No app-code dir is preserved; no runtime-state dir is left unpreserved.
5. New deps are in `requirements.txt` and importable by the carried Python.
6. The DB story is coherent (replaced + honest docs, OR preserved + first-run migrate).
7. If a physical bundle was available, the probe in Step 3 shows the new assets `OK`; otherwise
   you stated a build is needed to physically confirm.
8. `python -m ruff check` clean on any edited `.py`; `apply_update.ps1` still parses.

---

## Companion references
- `copy_source_assets.py` (repo root) — the **self-modify** snapshot generator; its
  `REQUIRED_SNAPSHOT_FILES` completeness check is a sibling guarantee (that the *source* tree
  ships), distinct from this skill (that the *runnable release* ships + survives an update).
- `VERSIONING.md` — the git-tag version contract (a self-update compares tags via
  `self_update.is_newer`).
- `docs/claude/architecture.md` → *Self-Knowledge & Self-Modification* for the build flags.
