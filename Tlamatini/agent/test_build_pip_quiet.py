"""Guard: the build pipeline must NEVER print pip's self-upgrade nag.

Angela, 2026-08-09: every run of ``build_complete_public_release.py`` /
``build_complete_private_release.py`` ended with

    [notice] A new release of pip is available: 25.0.1 -> 26.2
    [notice] To update, run: python.exe -m pip install --upgrade pip

and it kept coming back even after she manually upgraded pip.

ROOT CAUSE (why "just upgrade pip" is NOT the fix):

* The BUILD Python is normally the SYSTEM interpreter (e.g.
  ``C:/Program Files/Python312``), whose pip lives in a READ-ONLY prefix, so
  ``python -m pip install --upgrade pip`` cannot write there without admin.
* Upgrading a DIFFERENT interpreter's pip -- e.g. the writable carried
  ``<repo>/python`` -- changes nothing for the build Python. That is exactly
  what happened: carried pip was 26.2.1 while the build pip stayed 25.0.1.
* Even a SUCCESSFUL upgrade only buys silence until pip's next release, so
  "keep pip current" is a treadmill, not a fix.

THE FIX (two layers, both pinned by this file):

1. Every build script sets ``PIP_DISABLE_PIP_VERSION_CHECK=1`` in the
   environment, so EVERY child pip inherits the suppression -- including
   nested ones the build does not spawn directly.
2. Every DIRECT pip command also passes ``--disable-pip-version-check``
   explicitly (belt-and-braces), so the silence survives a refactor that
   rebuilds the environment from scratch.

FAIL-OPEN: the build scripts live at the repo root and are NOT shipped inside
a frozen install, so every test here SKIPS when they are absent rather than
failing a packaged test run.
"""

import ast
import unittest
from pathlib import Path

# <repo>/Tlamatini/agent/this_file.py  ->  parents[2] == <repo>
REPO_ROOT = Path(__file__).resolve().parents[2]

ENV_KEY = "PIP_DISABLE_PIP_VERSION_CHECK"
CLI_FLAG = "--disable-pip-version-check"

# Every script a build_complete_* run touches. The two wrappers spawn the other
# three, so the pin must exist in all five for the suppression to be total no
# matter which entry point Angela launches.
BUILD_SCRIPTS = (
    "build.py",
    "build_installer.py",
    "build_uninstaller.py",
    "build_complete_private_release.py",
    "build_complete_public_release.py",
)

# Scripts that actually shell out to pip (the wrappers only spawn the others).
PIP_INVOKING_SCRIPTS = (
    "build.py",
    "build_installer.py",
    "build_uninstaller.py",
)


def _read(name):
    """Source text of a repo-root build script, or None when absent."""
    path = REPO_ROOT / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _const_or_none(node):
    """The str value of a constant AST node, else None (a variable, call, ...)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _pip_argv_lists(source):
    """Every list literal in ``source`` that is a ``python -m pip ...`` argv.

    Returned as the list of its elements mapped to their string value (or None
    for a non-constant element such as ``target_python``), so callers can both
    assert membership and report a readable command.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.List):
            continue
        values = [_const_or_none(elt) for elt in node.elts]
        for i in range(len(values) - 1):
            if values[i] == "-m" and values[i + 1] == "pip":
                found.append(values)
                break
    return found


def _assigns_env_key(source):
    """True when the source assigns ``<mapping>[ENV_KEY] = "1"`` anywhere.

    Accepts BOTH shapes in use: the module-level ``os.environ[...] = "1"`` pin
    (build.py / build_installer.py / build_uninstaller.py) and the
    ``env[...] = "1"`` line inside the wrappers' ``_utf8_env()`` helper, which
    is what actually reaches their child processes.
    """
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if _const_or_none(node.value) != "1":
            continue
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            if _const_or_none(target.slice) == ENV_KEY:
                return True
    return False


class BuildPipVersionNagTests(unittest.TestCase):
    """Both suppression layers, pinned in both directions."""

    def test_every_build_script_exists(self):
        """Sanity: a renamed/moved build script must not silently skip the suite."""
        missing = [n for n in BUILD_SCRIPTS if not (REPO_ROOT / n).is_file()]
        if len(missing) == len(BUILD_SCRIPTS):
            self.skipTest("no repo-root build scripts here (frozen/packaged tree)")
        self.assertEqual(
            missing, [],
            "Build script(s) missing from the repo root. If one was renamed, "
            "update BUILD_SCRIPTS in this test so the pip-nag guard keeps "
            "covering it: " + ", ".join(missing),
        )

    def test_every_build_script_pins_the_env_var(self):
        """Layer 1 - the environment pin every child pip inherits."""
        checked = 0
        for name in BUILD_SCRIPTS:
            source = _read(name)
            if source is None:
                continue
            checked += 1
            self.assertTrue(
                _assigns_env_key(source),
                f"{name} must set {ENV_KEY} = '1' (os.environ[...] at module "
                f"level, or env[...] inside _utf8_env for the wrappers). "
                f"Without it, a pip spawned indirectly re-prints the "
                f"'A new release of pip is available' notice on every build.",
            )
        if not checked:
            self.skipTest("no repo-root build scripts here (frozen/packaged tree)")

    def test_every_pip_command_passes_the_cli_flag(self):
        """Layer 2 - the explicit flag on every direct pip invocation."""
        checked = 0
        for name in PIP_INVOKING_SCRIPTS:
            source = _read(name)
            if source is None:
                continue
            argvs = _pip_argv_lists(source)
            self.assertTrue(
                argvs,
                f"{name} is listed as a pip-invoking build script but no "
                f"'-m', 'pip' command literal was found. Either the call was "
                f"removed (drop it from PIP_INVOKING_SCRIPTS) or it is now "
                f"built in a shape this guard cannot see - make it a plain "
                f"list literal so the flag stays checkable.",
            )
            for argv in argvs:
                checked += 1
                rendered = " ".join("<expr>" if v is None else v for v in argv)
                self.assertIn(
                    CLI_FLAG, argv,
                    f"{name}: pip command is missing {CLI_FLAG} -> {rendered}. "
                    f"Every pip call in the build must carry it; upgrading pip "
                    f"does NOT fix the notice (the build Python's prefix is "
                    f"usually read-only Program Files).",
                )
        if not checked:
            self.skipTest("no repo-root build scripts here (frozen/packaged tree)")

    def test_no_pip_upgrade_treadmill_in_the_build(self):
        """The build must not try to 'fix' the notice by upgrading pip itself.

        That path needs admin on a Program Files prefix, adds a network call to
        an already long build, and buys silence only until pip's next release.
        """
        for name in BUILD_SCRIPTS:
            source = _read(name)
            if source is None:
                continue
            for argv in _pip_argv_lists(source):
                if "install" not in argv:
                    continue
                upgrades_pip = "pip" in argv[argv.index("install"):]
                self.assertFalse(
                    upgrades_pip and ("--upgrade" in argv or "-U" in argv),
                    f"{name} must not run 'pip install --upgrade pip' during a "
                    f"build. Suppress the version CHECK instead (see this "
                    f"test's docstring).",
                )


if __name__ == "__main__":
    unittest.main()
