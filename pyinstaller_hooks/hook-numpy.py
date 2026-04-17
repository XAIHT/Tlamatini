"""
Tlamatini custom PyInstaller hook for numpy.

$PyInstaller-Hook-Priority: 2

Why this hook exists
--------------------
numpy 2.0 renamed ``numpy.core`` to ``numpy._core`` and kept ``numpy.core``
as a pure-Python deprecation shim. ``numpy/core/__init__.py`` uses
``__getattr__`` to forward every attribute access to ``numpy._core``.
However, the Windows wheels for numpy >= 2.x ALSO ship the compiled
extensions (``_multiarray_umath.pyd``, ``_multiarray_tests.pyd``,
``_simd.pyd``, etc.) under BOTH ``numpy/_core/`` and ``numpy/core/`` as
byte-for-byte duplicates, preserved for binary-level backward compat.

PyInstaller's stock numpy hook (priority 1) calls
``collect_dynamic_libs("numpy")``, which walks the numpy tree and bundles
every ``.pyd``/``.dll`` it finds — so both copies end up in the frozen app.
At runtime the same compiled extension is registered under two different
fully-qualified module names (``numpy._core._multiarray_umath`` and
``numpy.core._multiarray_umath``). numpy 2.x's one-init-per-process guard
in ``_multiarray_umath`` then raises:

    ImportError: cannot load module more than once per process

numpy 1.x had no duplicate layout (only ``numpy/core/`` existed) and its C
extension had no one-init guard, which is why older Tlamatini builds did
not hit this.

The fix
-------
Drop every binary whose source path lives under ``numpy/core/``. The
duplicates there are never actually needed: numpy.core's Python shim
forwards attribute access to ``numpy._core`` via ``__getattr__``, so
``numpy.core.X`` at runtime returns ``numpy._core.X``. We also add the
legacy numpy.core extension names to ``excludedimports`` so the module
graph walker does not pull the duplicate ``.pyd`` files back in if some
dependency happens to reference them directly.

This hook mirrors the stock PyInstaller numpy hook exactly, except for
the binaries filter and the added ``excludedimports`` entries — so future
upstream behavior changes keep working.
"""

import os

from PyInstaller import compat
from PyInstaller.utils.hooks import (
    get_installer,
    collect_dynamic_libs,
)

from packaging.version import Version


def _drop_legacy_numpy_core(entries):
    """Strip (src, dest) tuples whose source file lives under ``numpy/core/``.

    The filter matches both forward- and back-slash separators so it works
    identically on Windows and POSIX builds.
    """
    filtered = []
    for entry in entries:
        src = entry[0]
        norm = src.replace(os.sep, '/').lower()
        if '/numpy/core/' in norm:
            print(f"[tlamatini hook-numpy] Dropping legacy duplicate: {src}")
            continue
        filtered.append(entry)
    return filtered


# Use numpy.__version__ as the source of truth. site-packages routinely
# carries stale ``numpy-X.Y.Z.dist-info`` directories from earlier installs
# — when more than one exists, ``importlib.metadata.version("numpy")``
# returns whichever comes first alphabetically, which is NOT necessarily
# the version actually imported. The stock PyInstaller hook hits this case
# in polluted environments and silently takes wrong version branches. We
# defer to numpy itself, which is the only authoritative version source.
import numpy as _numpy_for_version  # noqa: E402
numpy_version = Version(_numpy_for_version.__version__).release
numpy_installer = get_installer('numpy')

hiddenimports = []
datas = []
binaries = []

binaries += _drop_legacy_numpy_core(collect_dynamic_libs("numpy"))

if numpy_installer == 'conda':
    from PyInstaller.utils.hooks import conda_support
    datas += _drop_legacy_numpy_core(
        conda_support.collect_dynamic_libs("numpy", dependencies=True)
    )

if compat.is_win and numpy_version >= (1, 26) and numpy_installer == 'pip':
    from PyInstaller.utils.hooks import collect_delvewheel_libs_directory
    datas, binaries = collect_delvewheel_libs_directory(
        "numpy", datas=datas, binaries=binaries
    )
    binaries = _drop_legacy_numpy_core(binaries)
    datas = _drop_legacy_numpy_core(datas)

if numpy_version >= (2, 0):
    hiddenimports += ['numpy._core._dtype_ctypes', 'numpy._core._multiarray_tests']
else:
    hiddenimports += ['numpy.core._dtype_ctypes']
    if numpy_version >= (1, 25):
        hiddenimports += ['numpy.core._multiarray_tests']

if numpy_version >= (2, 3, 0):
    hiddenimports += ['numpy._core._exceptions']

if compat.is_conda and numpy_version < (1, 19):
    hiddenimports += ["six"]

excludedimports = [
    "scipy",
    "pytest",
    "nose",
    "f2py",
    "setuptools",
]

if numpy_version < (1, 22, 0) or numpy_version > (1, 22, 1):
    excludedimports += [
        "distutils",
        "numpy.distutils",
    ]

if numpy_version < (2, 0):
    excludedimports += [
        "numpy.f2py",
    ]

# Belt-and-suspenders: block module-graph discovery of the legacy numpy.core
# C extensions. _drop_legacy_numpy_core() already filters their .pyd files
# out of `binaries`; this prevents PyInstaller from dragging them back in if
# a dependency happens to reference them by fully-qualified module name.
if numpy_version >= (2, 0):
    excludedimports += [
        "numpy.core._multiarray_umath",
        "numpy.core._multiarray_tests",
        "numpy.core._operand_flag_tests",
        "numpy.core._rational_tests",
        "numpy.core._simd",
        "numpy.core._struct_ufunc_tests",
        "numpy.core._umath_tests",
    ]
