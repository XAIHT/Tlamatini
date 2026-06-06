---
name: numpy 2.x duplicate .pyd crashes frozen bundle
description: Root cause and fix for "cannot load module more than once per process" at Tlamatini startup
type: project
originSessionId: 2d3ec596-7d25-4d52-af08-6bef97baaa27
---
Fact: numpy >= 2.0 ships the compiled extensions (`_multiarray_umath.pyd`, `_simd.pyd`, `_multiarray_tests.pyd`, `_rational_tests.pyd`, `_operand_flag_tests.pyd`, `_struct_ufunc_tests.pyd`, `_umath_tests.pyd`) as **byte-for-byte duplicates** under both `numpy/_core/` (canonical) and `numpy/core/` (legacy shim). Stock PyInstaller `hook-numpy.py` bundles both. At runtime the same C extension initializes twice — numpy 2.x raises `ImportError: cannot load module more than once per process`. numpy 1.x had only `numpy/core/` and no one-init guard, so older builds did not hit this.

Secondary fact: site-packages can carry multiple `numpy-X.Y.Z.dist-info` directories side-by-side after upgrades. `importlib.metadata.version("numpy")` returns whichever sorts first alphabetically (often the stale older one), and `collect_dynamic_libs("numpy")` walks the wrong file list — returning zero binaries and letting the module-graph walker bundle numpy unsupervised. Always use `numpy.__version__` as the version-truth source in any numpy-related hook/build logic.

**Why:** First surfaced on 2026-04-17 as a crash in the installed build at `C:\Tlamatini\tlamatini.log` after numpy was silently upgraded from 1.26.4 to 2.4.4 on the build machine. The crash first appeared via the daphne→autobahn→flatbuffers import chain, then migrated to langchain→faiss after a failed first-attempt fix — confirming the numpy-duplicate root cause rather than any autobahn-specific issue.

**How to apply:** The repo fix lives in three places — `pyinstaller_hooks/hook-numpy.py` (priority-2 override that filters `numpy/core/` binaries and uses `numpy.__version__`), `build.py::_purge_numpy_environment` (wipes numpy residuals before each `pip install` so dist-info cruft can't return), and the `--additional-hooks-dir=pyinstaller_hooks` flag wired into the PyInstaller command. Any new build-pipeline or numpy-upgrade work must preserve all three. Don't add band-aid fixes that patch individual import chains (autobahn, faiss, etc.) — address the duplicate .pyd root cause instead.
