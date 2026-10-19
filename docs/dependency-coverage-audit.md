<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Python dependency coverage and reproducible installation — 2026-10-18

The main [requirements.txt](../requirements.txt) describes the complete Windows
CPython 3.12 environment used by Tlamatini, its retained agents, build tools,
self-modification and verification commands. It pins **263 distributions**:
direct dependencies are grouped by purpose, followed by their transitive closure.
This is the application's dependency graph, not a freeze of the developer's
unrelated user-site packages.

The source audit covers **855 Python files and 85 runnable agents** and finds
**72 directly referenced pip distributions**. Framework registrations, build
hooks, command-line tools and compatibility dependencies account for additional
direct requirements. Optional feature imports remain included so their features
work in a fresh installation.

## Installation and compatibility

Run every command below in a verified visible, forked foreground console, kept
open afterward, following the [visible execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Use the full x64 CPython 3.12 distribution, including Tcl/Tk for setup windows.
Install into a fresh environment with no inherited site-packages:

~~~powershell
python -m pip install -r requirements.txt
python -m pip check
python scripts/check_requirements_coverage.py --report Temp/dependency-audit/coverage.json
python scripts/check_python_quality.py
~~~

The CPU Torch pin matches the carried runtime; its wheel comes from the official
PyTorch CPU index declared in the manifest. NumPy 2.2.6 satisfies OpenCV's NumPy 2
floor while retaining the existing upper boundary. Packaging 25.0 satisfies
LangChain Core's below-26 requirement. PyInstaller and its contributed hooks are
both pinned. Ruff is also a runtime dependency because Pythonxer invokes it before
executing Python scripts. Install using the interpreter's -m pip, not another
environment's executable.

A package belongs to the interpreter that executes it. Keep the complete
environment in carried python/; collect into frozen Django only what that
process uses. Pool-only media/browser packages do not need a duplicate frozen
copy. See [self-management carriage](self-management-carriage.md).

## Separate runtimes

- ESPHomer provisions requirements-esphome.txt in its private runtime.
  Do not merge it into this environment: its py7zr and PlatformIO pins conflict
  with the main archive/firmware stack.
- Blender supplies bpy; Unreal Editor supplies unreal. Tcl/Tk is a CPython
  installation component, not a pip package.
- Browser binaries, Git, Java, device toolchains, external MCP servers and model
  weights follow their own build/provisioning contracts. Python requirements
  do not replace those assets.

## Coverage guard

scripts/check_requirements_coverage.py reads tracked and non-ignored new Python
sources, including hidden skill harnesses. It checks ordinary and optional
imports, literal dynamic imports, resolvable import loops, generated Python,
PyInstaller inventories and Python module commands. It handles distribution
aliases, local modules, application-provided SDKs and the separate ESPHome
manifest. Missing declarations, syntax errors and unreviewed computed imports
fail the gate. Test fixture command strings are excluded; real test imports count.

Ten regression tests exercise those boundaries:

~~~powershell
python -m unittest discover -s Tests -p test_requirements_coverage.py -v
~~~

The guard cannot infer arbitrary libraries in future user-supplied scripts.
Those remain the responsibility of their own environments.

## Executed evidence

The October 18 comparison inspected the source-carried interpreter, the prior
release preview, the installed Tlamatini interpreter, the system interpreter and
its separate user-site environment. The three application environments each
contained 263 distributions; the installed and source-carried versions matched.
The system user site contained 479 distribution records and was not used to
populate the application manifest.

A new full CPython runtime was prepared without site-packages, Scripts or
inherited user packages. Installing the rewritten requirements completed
successfully. Its 263 installed versions exactly matched the source-carried
environment, with no extra, missing or changed distribution. pip check passed
for the clean runtime, the installed application and the prior release preview.

The clean runtime imported Django/ASGI, MCP, PlatformIO, NumPy/FAISS, OpenCV,
PyAV, ffpyplayer, audio libraries, Torch/SNAC, both local transcription stacks,
ONNX Runtime, Playwright, Tcl/Tk and document libraries successfully. This verifies
installation/import readiness; it does not claim live hardware, credentials or
every external provider was exercised.

Local evidence is under Temp/release-size-analysis-20261018/: the environment
inventories, clean-pip-install-report.json, clean-environment-results.json,
clean-pip-check.log, clean-runtime-imports.log and dependency-coverage-repair.json.
Release and browser results are recorded separately against the exact rebuilt artifact.
