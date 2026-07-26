---
name: project_ghost_distinfo_dependency_audit
description: "site-packages carries ~30 GHOST dist-info dirs; pip's conflicts were mostly phantom. audit_dependencies.py + the numpy floor fix (2026-07-26)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 69614274-24d6-4daa-92af-01a874c256f6
  modified: 2026-07-26T22:58:15.405Z
---

**Most of pip's dependency conflicts on this machine were PHANTOM — stale `dist-info`
metadata, not real incompatibility.** Found 2026-07-26 from
`pyhackrf 0.2.0 requires numpy<2.0.0, but you have numpy 2.2.6`.

**The GHOST class.** `site-packages` held DUPLICATE `*.dist-info` dirs for ~30 packages
(an install overwrote the code but pip never removed the old metadata dir — common with
`+cpu` local versions, `--user` vs system site, interrupted installs):
- **torch**: dist-infos `2.10.0` + `2.12.1+cpu`; real code = **2.10.0+cpu**. The GHOST
  declared `setuptools<82` → that whole conflict was fake. Real torch has no upper bound
  and imports fine without `pkg_resources` (removed in setuptools 82).
- **starlette**: `0.41.3` + `1.3.1`; real = **1.3.1**. `pip check` read the ghost.
- **packaging**: SPLIT BRAIN — metadata said 25.0 while the imported module was 26.2
  (pip wrote the dist-info to a different site than the code winning on `sys.path`).
  **ALWAYS verify a version by IMPORTING it, never by metadata alone.**

**pyhackrf is benign and must NOT be uninstalled (Angela).** Its module ships as
`hackrf/` and uses only `np.array/complex128/float64/int8` — all unchanged in numpy 2 —
and it can't even load on Windows (`CDLL('libhackrf.so.0')`, a Linux .so). 0.2.0 is the
newest release, so there is nothing to upgrade to.

**Real fixes applied to requirements.txt:** `numpy<2.3.0` → **`numpy>=2.0,<2.3.0`**
(the missing FLOOR was a latent bug — opencv-python 4.13 needs `>=2`, so a resolver
could have installed 1.x and silently broken Camcorder/VideoPlayer/Video-Analyzer/
Recorder/Whisperer); `fastapi==0.115.6` → `==0.140.0`; `packaging<26.0.0` pinned;
9 drifted pins raised to the installed+working versions. Env: packaging→25.0,
hf-xet→1.5.1, ghosts renamed aside. **`pip check` went 4 conflicts + 9 drifts → 1 line.**

**⚠️ MY MISTAKE, do not repeat:** the ghost sweep compares dist-info version to the
package's `__init__.__version__`; for packages exposing NO `__version__` it matched
nothing and renamed EVERY dist-info, leaving **certifi / svglib / eval-type-backport
with zero metadata**. Repaired by restoring the highest version. Any such sweep MUST
assert ≥1 dist-info survives per package BEFORE moving anything. Backups live in place
as `<name>-<ver>.dist-info.GHOST-BACKUP-2026-07-26` (rename back to restore).

**Tool:** `audit_dependencies.py` at the repo root — read-only, runs on any interpreter,
and crucially **evaluates PEP 508 markers** (without that it reports 3 numpy conflicts on
3.12 when only 1 is real). `python audit_dependencies.py requirements.txt`.

Also noted: `C:\Tlamatini` was uninstalled during this session (only `agents`, `Temp`,
`Uninstaller.exe` remain), so the carried Python could not be audited.

Related: [[project_carried_python_for_agents]], [[project_numpy_pyinstaller]],
[[project_build_carried_python_guard]], [[project_live_app_is_frozen_install]].
