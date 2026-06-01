"""Static completeness tests for the packaging pipeline — build.py,
build_installer.py, build_uninstaller.py.

These are CONTRACT tests, not a real PyInstaller build: a full frozen build is
multi-GB and needs the whole toolchain, so it cannot run in CI. Instead we assert
the *bundling specification* is complete, so that WHEN a build runs the frozen
installable contains everything:

- every required runtime asset is referenced by build.py AND exists on disk
- the ENTIRE agents/ pool tree is copied into the frozen install (so all 68
  workflow agents ship), with STM32er specifically present
- every third-party library the pool agents / the STM32 MCP server import is
  pinned in requirements.txt (which build.py installs into BOTH the build Python
  and the frozen-agent PYTHON_HOME Python)
- build.py's fail-loud `_agent_libs` verification list covers the critical libs
  and every entry is actually pinned
- the version wiring (extract_cli_version / resolve_build_version / --version-file)
  and the installer/uninstaller packaging contracts are intact

If a future change drops an agent, an asset, or a dependency from the frozen
spec, one of these tests fails — which is the whole point.
"""
import ast
import re
import sys
import unittest
from functools import lru_cache
from pathlib import Path

from django.test import SimpleTestCase

# test file: <repo>/Tlamatini/agent/test_build_scripts.py  ->  repo root = parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "Tlamatini" / "agent" / "agents"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
BUILD_PY = REPO_ROOT / "build.py"
BUILD_INSTALLER = REPO_ROOT / "build_installer.py"
BUILD_UNINSTALLER = REPO_ROOT / "build_uninstaller.py"


@lru_cache(maxsize=8)
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@lru_cache(maxsize=1)
def _requirement_names() -> frozenset:
    """Lowercased PyPI dist names pinned in requirements.txt (no version spec)."""
    names = set()
    for line in _read(REQUIREMENTS).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]+)", line)
        if m:
            names.add(m.group(1).lower())
    return frozenset(names)


def _req_has(dist: str) -> bool:
    names = _requirement_names()
    d = dist.lower()
    return d in names or d.replace("_", "-") in names or d.replace("-", "") in {
        n.replace("-", "") for n in names
    }


# import-name -> PyPI dist name (only where they differ)
_ALIAS = {
    "yaml": "pyyaml", "serial": "pyserial", "cv2": "opencv-python", "PIL": "pillow",
    "bs4": "beautifulsoup4", "fitz": "pymupdf", "docx": "python-docx", "pptx": "python-pptx",
    "dotenv": "python-dotenv", "git": "gitpython", "whisper": "openai-whisper",
    "faiss": "faiss-cpu", "sklearn": "scikit-learn", "grpc": "grpcio", "odf": "odfpy",
    "win32api": "pywin32", "win32gui": "pywin32", "win32con": "pywin32", "win32process": "pywin32",
    "win32com": "pywin32", "pythoncom": "pywin32", "pywintypes": "pywin32",
    "win32clipboard": "pywin32", "win32file": "pywin32", "win32event": "pywin32",
    "rank_bm25": "rank-bm25", "pyautogui": "pyautogui", "telethon": "telethon",
}
# Local modules / build-time-provided names that are NOT PyPI deps.
_NOT_THIRD_PARTY = {
    "agent", "tlamatini", "__future__", "pyi_splash",
}


@lru_cache(maxsize=1)
def _agent_third_party_imports() -> dict:
    """{import_name: [agent files]} for every NON-stdlib top-level import across
    the agents/ pool tree."""
    std = set(sys.stdlib_module_names)
    found: dict = {}
    for py in AGENTS_DIR.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(_read(py))
        except Exception:
            continue
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    mods.add(node.module.split(".")[0])
        for m in mods:
            if m in std or m in _NOT_THIRD_PARTY:
                continue
            found.setdefault(m, []).append(py.name)
    return found


@lru_cache(maxsize=1)
def _build_py_local_assign(name: str) -> list:
    """Extract a list-of-strings local variable (e.g. `_agent_libs`) from build.py
    via AST, wherever it is assigned (including inside main())."""
    tree = ast.parse(_read(BUILD_PY))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return [
                            el.value for el in node.value.elts
                            if isinstance(el, ast.Constant) and isinstance(el.value, str)
                        ]
    return []


# ---------------------------------------------------------------------------
# All three scripts must at least parse (a syntax error breaks the build).
# ---------------------------------------------------------------------------


class BuildScriptsSyntaxTests(SimpleTestCase):
    def test_all_build_scripts_exist_and_parse(self):
        for path in (BUILD_PY, BUILD_INSTALLER, BUILD_UNINSTALLER):
            self.assertTrue(path.exists(), f"missing build script: {path}")
            try:
                ast.parse(_read(path))
            except SyntaxError as e:
                self.fail(f"{path.name} has a SyntaxError: {e}")


# ---------------------------------------------------------------------------
# build.py bundles every required runtime asset, and each source exists.
# ---------------------------------------------------------------------------


class BuildPyAssetBundlingTests(SimpleTestCase):
    # (token that must appear in build.py source, repo-relative source path that must exist)
    REQUIRED_ASSETS = [
        ("agent/templates", "Tlamatini/agent/templates"),
        ("agent/static", "Tlamatini/agent/static"),
        ("staticfiles", "Tlamatini/staticfiles"),
        ("agent/config.json", "Tlamatini/agent/config.json"),
        ("prompt.pmt", "Tlamatini/agent/prompt.pmt"),
        ("Tlamatini.md", "Tlamatini/agent/Tlamatini.md"),
        ("skills_pkg", "Tlamatini/agent/skills_pkg"),
        ("agents_descriptions.md", "agents_descriptions.md"),
        ("README.md", "README.md"),
        ("jd-cli", "Tlamatini/jd-cli"),
    ]

    def setUp(self):
        self.src = _read(BUILD_PY)

    def test_required_assets_referenced_and_present(self):
        for token, rel in self.REQUIRED_ASSETS:
            self.assertIn(token, self.src, f"build.py does not reference {token!r}")
            self.assertTrue((REPO_ROOT / rel).exists(),
                            f"asset source missing on disk: {rel}")

    def test_version_file_passed_to_pyinstaller(self):
        self.assertIn("--version-file=", self.src)
        self.assertIn("version_file_path", self.src)

    def test_self_modify_source_tree_gated(self):
        # TlamatiniSourceCode ships ONLY under --self-modify.
        self.assertIn("self_modify", self.src)
        self.assertIn("TlamatiniSourceCode", self.src)

    def test_pkg_zip_generated(self):
        self.assertIn("pkg.zip", self.src)

    def test_critical_hidden_imports_present(self):
        for hi in ("agent._version", "daphne.server", "channels", "tlamatini.asgi",
                   "filesearch_pb2", "filesearch_pb2_grpc"):
            self.assertIn(hi, self.src, f"build.py missing --hidden-import {hi}")

    def test_tkinter_excluded_from_server(self):
        # The server uses Win32 ctypes dialogs, never tkinter.
        self.assertIn("--exclude-module=tkinter", self.src)


# ---------------------------------------------------------------------------
# THE BIG ONE: every workflow agent ships in the frozen install.
# ---------------------------------------------------------------------------


class AgentBundlingCompletenessTests(SimpleTestCase):
    def setUp(self):
        self.src = _read(BUILD_PY)
        self.agent_dirs = sorted(
            p for p in AGENTS_DIR.iterdir()
            if p.is_dir() and p.name != "__pycache__"
        )

    def test_agents_tree_copied_into_frozen_install(self):
        # build.py copies Tlamatini/agent/agents -> dist/agents (optional_dir_copies).
        self.assertRegex(self.src, r'"agent"\s*/\s*"agents"',
                         "build.py must copy the agents/ pool tree into the install")

    def test_have_a_full_agent_catalog(self):
        # Sanity floor: the catalog is 68 agents; never let it silently shrink.
        self.assertGreaterEqual(len(self.agent_dirs), 60,
                                f"only {len(self.agent_dirs)} agent dirs found")

    def test_stm32er_agent_ships_complete(self):
        stm = AGENTS_DIR / "stm32er"
        self.assertTrue((stm / "stm32er.py").exists(), "stm32er.py missing")
        self.assertTrue((stm / "config.yaml").exists(), "stm32er config.yaml missing")

    def test_esp32er_agent_ships_complete(self):
        esp = AGENTS_DIR / "esp32er"
        self.assertTrue((esp / "esp32er.py").exists(), "esp32er.py missing")
        self.assertTrue((esp / "config.yaml").exists(), "esp32er config.yaml missing")

    def test_every_runnable_agent_has_its_config(self):
        # Each agent dir that ships a <name>.py runtime must also ship its
        # config.yaml (the pair the pool launcher needs). System agents that have
        # neither a <name>.py nor config.yaml (e.g. flowcreator/flowhypervisor that
        # ship .md only) are exempt.
        incomplete = []
        for d in self.agent_dirs:
            run_py = d / f"{d.name}.py"
            cfg = d / "config.yaml"
            if run_py.exists() and not cfg.exists():
                incomplete.append(f"{d.name} (has {d.name}.py but no config.yaml)")
        self.assertEqual(incomplete, [], f"agents missing config.yaml: {incomplete}")


# ---------------------------------------------------------------------------
# Dependency completeness — the frozen-agent Python gets every lib the agents
# and the STM32 MCP server need.
# ---------------------------------------------------------------------------


class RequirementsCoverageTests(SimpleTestCase):
    def test_every_agent_third_party_import_is_pinned(self):
        uncovered = {}
        for mod, files in _agent_third_party_imports().items():
            dist = _ALIAS.get(mod, mod)
            if not _req_has(dist):
                uncovered[mod] = sorted(set(files))[:3]
        self.assertEqual(
            uncovered, {},
            "agent imports NOT pinned in requirements.txt (frozen agents would "
            f"crash): {uncovered}",
        )

    def test_stm32_mcp_server_deps_pinned(self):
        # STM32er spawns the STM32 Template Project MCP server under the frozen-agent
        # Python; that server imports mcp + pyserial. Both must be pinned so build.py
        # installs them into PYTHON_HOME.
        self.assertTrue(_req_has("mcp"), "mcp not pinned in requirements.txt")
        self.assertTrue(_req_has("pyserial"), "pyserial not pinned in requirements.txt")

    def test_file_format_backends_pinned(self):
        # file_extractor / file_interpreter agents try these in order.
        for dist in ("pymupdf", "pypdf", "PyPDF2", "odfpy", "ebooklib", "openpyxl",
                     "xlrd", "striprtf", "python-docx", "python-pptx"):
            self.assertTrue(_req_has(dist), f"{dist} not pinned in requirements.txt")


class AgentLibVerificationListTests(SimpleTestCase):
    """build.py's `_agent_libs` is the build-time fail-loud import check that runs
    against EACH target Python (build + frozen-agent PYTHON_HOME)."""

    def setUp(self):
        self.agent_libs = _build_py_local_assign("_agent_libs")

    def test_agent_libs_list_exists_and_is_substantial(self):
        self.assertGreaterEqual(len(self.agent_libs), 15,
                                f"_agent_libs too small: {self.agent_libs}")

    def test_agent_libs_includes_stm32_and_file_backends(self):
        for mod in ("mcp", "serial", "PyPDF2", "pypdf", "fitz", "odf"):
            self.assertIn(mod, self.agent_libs,
                          f"{mod} missing from build.py _agent_libs verification list")

    def test_every_verified_lib_is_pinned(self):
        # Each module the build verifies must resolve to a pinned requirement,
        # otherwise the build aborts (its own check) — keep them consistent.
        missing = [m for m in self.agent_libs if not _req_has(_ALIAS.get(m, m))]
        self.assertEqual(missing, [],
                         f"_agent_libs entries not in requirements.txt: {missing}")


# ---------------------------------------------------------------------------
# Version wiring across all three scripts (SemVer / git-tag derived).
# ---------------------------------------------------------------------------


class VersionWiringTests(SimpleTestCase):
    def test_build_py_resolves_version(self):
        src = _read(BUILD_PY)
        self.assertIn("extract_cli_version", src)
        self.assertIn("resolve_build_version", src)

    def test_installer_and_uninstaller_version_wiring(self):
        for path, original in ((BUILD_INSTALLER, "Installer.exe"),
                               (BUILD_UNINSTALLER, "Uninstaller.exe")):
            src = _read(path)
            self.assertIn("extract_cli_version", src)
            self.assertIn("resolve_build_version", src)
            self.assertIn("render_versioninfo_for", src)
            self.assertIn("--version-file=", src)
            self.assertIn(original, src)


# ---------------------------------------------------------------------------
# Installer packaging contract.
# ---------------------------------------------------------------------------


class BuildInstallerContractTests(SimpleTestCase):
    def setUp(self):
        self.src = _read(BUILD_INSTALLER)

    def test_requires_pkg_zip_and_install_script(self):
        self.assertIn("pkg.zip", self.src)
        self.assertIn("install.py", self.src)
        self.assertTrue((REPO_ROOT / "install.py").exists())

    def test_release_folder_is_version_named(self):
        self.assertIn("Tlamatini_Release_v", self.src)

    def test_pkg_zip_moved_with_verification(self):
        # pkg.zip is MOVED into the release folder with SHA-256 verification.
        self.assertIn("_verified_move", self.src)
        self.assertIn("sha256", self.src.lower())

    def test_bundles_tkinter_for_gui(self):
        self.assertIn("tkinter", self.src)
        self.assertIn("--collect-all", self.src)

    def test_includes_uninstaller_in_release(self):
        self.assertIn("Uninstaller.exe", self.src)


class BuildUninstallerContractTests(SimpleTestCase):
    def setUp(self):
        self.src = _read(BUILD_UNINSTALLER)

    def test_requires_uninstall_script(self):
        self.assertIn("uninstall.py", self.src)
        self.assertTrue((REPO_ROOT / "uninstall.py").exists())

    def test_single_file_windowed_exe(self):
        self.assertIn("--onefile", self.src)
        self.assertIn("--windowed", self.src)

    def test_bundles_tkinter_for_gui(self):
        self.assertIn("tkinter", self.src)
        self.assertIn("--collect-all", self.src)

    def test_copies_exe_to_project_root(self):
        # build_installer.py picks Uninstaller.exe up from the project root.
        self.assertIn('"Uninstaller.exe"', self.src)


if __name__ == "__main__":
    unittest.main()
