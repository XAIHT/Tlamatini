# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Custom PyInstaller hook for torch -- OVERRIDES pyinstaller-hooks-contrib's
hook-torch.py to prevent a multi-hour freeze hang.

Root cause (observed 2026-06-27): the contrib hook's ``collect_submodules('torch')``
imports every torch submodule while walking the package, including
``torch._inductor.codecache``, which probes for a C++ compiler / OpenMP at import
time and spins. Symptom: the PyInstaller *isolated* child process pegged one core
for ~3 hours with the build log frozen at "Looking for dynamic libraries".

Fix: collect torch with a ``filter`` that skips the heavy subpackages a pure
*inference* build never uses -- torch.compile / Dynamo / Inductor JIT, distributed
training, ONNX export, and the test / benchmark / tensorboard tooling. PyInstaller's
``collect_submodules(filter=...)`` does not recurse into (and therefore does not
import) the filtered subpackages, so the hanging ``_inductor.codecache`` import
never happens. The frozen Django app plus the Talker SNAC vocoder and faster-whisper
only need core tensor / nn / serialization ops, all of which are kept.

These subpackages are lazy in torch 2.x (``import torch`` does not pull them in), so
excluding them from the frozen graph is safe for code that never calls
``torch.compile()`` or ``torch.distributed``.
"""
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Heavy / import-hanging torch subpackages NOT needed for inference.
_SKIP_PREFIXES = (
    "torch._inductor",          # the hang: codecache.py probes a C++ compiler at import
    "torch._dynamo",            # torch.compile graph capture (pulls in _inductor)
    "torch.distributed",        # multi-GPU / RPC training (source of the deprec-warning spam)
    "torch.testing",            # test utilities
    "torch.onnx",               # ONNX export
    "torch.utils.tensorboard",  # TensorBoard logging
    "torch.utils.benchmark",    # micro-benchmark tooling
    "torch.utils.bottleneck",   # profiler entrypoint
    "torch._export",            # export/serialization graph tooling
)


def _keep(name):
    return not any(name == p or name.startswith(p + ".") for p in _SKIP_PREFIXES)


hiddenimports = collect_submodules("torch", filter=_keep)
datas = collect_data_files("torch")
binaries = collect_dynamic_libs("torch")
excludedimports = list(_SKIP_PREFIXES)
