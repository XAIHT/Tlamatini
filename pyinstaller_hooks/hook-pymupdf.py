# Tlamatini Author Banner — Angela López Mendoza
"""Bundle native MuPDF libraries used by PDF context in the frozen web process.

$PyInstaller-Hook-Priority: 2

The carried Python is a separate interpreter. Its PyMuPDF installation cannot
satisfy imports inside Tlamatini.exe. Collect the wheel's native libraries next
to the extension modules, including mupdfcpp64.dll on Windows.
"""

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs("pymupdf")
hiddenimports = ["pymupdf._extra", "pymupdf._mupdf"]
