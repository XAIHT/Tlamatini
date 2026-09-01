# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Prevent PyInstaller from collecting Torch assets for the frozen web app.

$PyInstaller-Hook-Priority: 2

``--exclude-module=torch`` blocks Torch's Python modules, but PyInstaller may
still execute the upstream ``hook-torch.py`` while analyzing optional importers
such as torchvision/datasets.  That upstream hook calls
``collect_dynamic_libs('torch')`` and copied 2.5 GB of CUDA DLLs into
``_internal/torch/lib`` even though every ``torch.*`` module was excluded.

Tlamatini's frozen Django process does not use Torch.  Talker runs in a separate
pool subprocess under the carried ``<install>/python`` interpreter, where the
build independently provisions and verifies CPU-only Torch.  This higher-
priority no-op hook makes that interpreter boundary true for binaries as well
as Python modules.
"""

datas = []
binaries = []
hiddenimports = []
excludedimports = ["torch"]
