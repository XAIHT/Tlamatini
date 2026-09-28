<!--
Tlamatini - Created by Angela Lopez Mendoza - @angelahack1
Tlamatini Author Banner - do not remove
-->
# Python dependency coverage audit - 2026-09-27

The refreshed source audit covers **744 Python files and all 89 runnable agents**.
The added `chat_voice_settings.py` shares stdlib-only Mic preference validation
between Django and the carried Whisperer worker; the new dialog adds no package.
There are **87 declarations in the main requirements file**, covering all
**69 pip distributions referenced by the scanned source and build inventories**.
The additional declarations are retained: packages can also be needed through
framework integrations, runtime tooling, or transitive compatibility constraints.

## Missing declarations added

| Distribution | Version | Source that needs it |
| --- | --- | --- |
| `autobahn` | `26.7.1` | Explicit collection and package lookup in `build.py`; Daphne WebSockets |
| `lxml` | `6.1.3` | Direct XML import in `Tlamatini/agent/doc_generation/dossier_pptx.py` |
| `six` | `1.17.0` | Conditional hidden import in `pyinstaller_hooks/hook-numpy.py` |
| `pip` | `26.2.1` | `audit_dependencies.py` packaging fallback and Python package installer invocations |
| `platformio` | `6.2.0` | Python module commands used by ESP32er and STM32er |

Use `python -m pip` when installing the main requirements, including when pip
itself needs updating. Existing requirement versions and ranges are preserved.

## ESPHome and other runtime boundaries

`requirements-esphome.txt` declares `esphome==2026.9.0` separately, and the
main requirements file explicitly points to it. ESPHomer already provisions
ESPHome in its private per-user library directory, adding that directory to
its subprocess environment. This audit records a resolved version of that
separate SDK; it does not change the agent's existing provisioning behavior.

Do **not** include that manifest with `-r` in the main environment. ESPHome
2026.9.0 requires `py7zr==1.1.3` and `platformio==6.1.19`, conflicting
with Tlamatini's `py7zr==0.22.0` and `platformio==6.2.0`. Its dependency
graph was resolved independently for Python 3.12 on Windows.

Blender's `bpy` and Unreal's `unreal` are provided by their application
Python runtimes. `tkinter` is CPython's optional Tcl/Tk component. These are
not missing pip declarations. JavaScript/npm dependencies, vendored browser
libraries, external executables, device toolchains, user-configured external
MCP servers and downloaded model weights have their own installation contracts;
a Python requirements file cannot install those resources.

## Repeatable coverage guard

`scripts/check_requirements_coverage.py` inspects tracked and non-ignored new
`.py`/`.pyw` files, including hidden skill harnesses. It parses source without
importing or starting the application. It checks:

- Ordinary and optional imports throughout the repository, not just agent folders.
- Literal dynamic imports and module names in statically resolvable loops.
- Generated multiline Python import statements outside test fixtures.
- Explicit PyInstaller inventories, package collection and Python `-m` commands.
- Module/distribution aliases, local modules, host-provided modules and the
  separate ESPHome manifest.

Every detected third-party import must have a declaration. Syntax errors and
unreviewed computed import expressions fail the check. Computed local imports
and generic package-location helpers have explicit, documented review entries.
Fixture-only command strings are excluded; actual test imports are included.
This is a static source check, not a promise to infer arbitrary generated code
or libraries in future user-provided scripts.

The existing `RequirementsCoverageTests` now invokes this whole-repository
guard. Ten focused tests cover aliases, optional imports, generated code,
dynamic imports, namespace handling, SDK manifests and malformed source.

**All execution must run in a verified visible, forked foreground console,
kept open afterward.** Follow
[the mandatory visible execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md)
before running these commands; do not run them headlessly:

```powershell
python scripts/check_requirements_coverage.py --report Temp/dependency-audit/coverage.json
python -m unittest discover -s Tests -p test_requirements_coverage.py -v
```

## Validation and limits

- Static coverage: 743 files, 89 agents, zero missing declarations, zero parse
  errors and zero unreviewed computed imports.
- Ten new coverage regression tests and four existing/extended build dependency
  tests passed. The latter used minimal Django settings with an empty database
  configuration; no application database was used.
- The complete main requirements file passed pip's dry-run resolver against
  the current Python 3.12 installation.
- The separate ESPHome manifest passed a dry run with `--ignore-installed`,
  resolving its independent dependency graph.
- New Autobahn, lxml and PlatformIO versions were installed only into a temporary
  virtual environment. Imports of Autobahn/Twisted, Daphne and PlatformIO passed,
  as did lxml XML parsing and real PPTX/DOCX save/reload checks.
- The temporary environment shares existing site-packages for unchanged
  dependencies. This is not a full clean installation or a frozen installer
  build. The user's main Python installation was not modified.
- New/changed Python audit code passed syntax and correctness lint checks.

Local evidence is under `Temp/dependency-audit/`: `coverage.json`,
`resolve-main.json`, `resolve-esphome.json`, `runtime-smoke.json`,
and package metadata snapshots. Visible console transcripts remain under
`Temp/voice-development/`. These generated artifacts are not source dependencies.

## Package selection evidence

The Snyk dependency-health tool was unavailable, so the skill's manual fallback
used official PyPI release metadata, Windows/Python compatibility information
and listed vulnerability records. The selected added versions had no
PyPI-listed advisories at audit time; this is not a complete security audit.

Autobahn 26.7.1 replaces the installed 25.12.2 version in the declaration because
the older version is affected by
[GHSA-hxp9-w8x3-p566](https://osv.dev/vulnerability/GHSA-hxp9-w8x3-p566).

Primary release metadata:
[Autobahn](https://pypi.org/project/autobahn/26.7.1/),
[lxml](https://pypi.org/project/lxml/6.1.3/),
[six](https://pypi.org/project/six/1.17.0/),
[pip](https://pypi.org/project/pip/26.2.1/),
[PlatformIO](https://pypi.org/project/platformio/6.2.0/),
[ESPHome](https://pypi.org/project/esphome/2026.9.0/).
