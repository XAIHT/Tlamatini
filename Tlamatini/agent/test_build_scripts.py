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

    def test_arduiner_agent_ships_complete(self):
        ard = AGENTS_DIR / "arduiner"
        self.assertTrue((ard / "arduiner.py").exists(), "arduiner.py missing")
        self.assertTrue((ard / "config.yaml").exists(), "arduiner config.yaml missing")
        # The bundled ArduinoTemplateProject must ship with the agent so the uniform
        # template-project scheme works offline in both source and frozen builds.
        tpl = ard / "ArduinoTemplateProject"
        self.assertTrue((tpl / "ArduinoTemplateProject.ino").exists(), "template .ino missing")
        self.assertTrue((tpl / "sketch.yaml").exists(), "template sketch.yaml missing")
        self.assertTrue((tpl / "src" / "Heartbeat.h").exists(), "template src/Heartbeat.h missing")

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


class CarriedPythonContractTests(SimpleTestCase):
    """The frozen build MUST ship a self-contained Python 3.12.10 (with deps)
    into <install_dir>/python so the pool agents can run on a machine that has
    no system Python — and every agent/app resolver must ALWAYS prefer it.
    """

    def setUp(self):
        self.build_src = _read(BUILD_PY)

    def test_build_pins_carried_python_to_31210_exactly(self):
        self.assertIn("CARRIED_PYTHON_VERSION = (3, 12, 10)", self.build_src)

    def test_build_defines_and_calls_bundler(self):
        self.assertIn("def bundle_carried_python(", self.build_src)
        self.assertIn("bundle_carried_python(dist_manage", self.build_src)

    def test_build_bundler_targets_the_python_subdir(self):
        # The interpreter must land at <dist>/python (the path every resolver uses).
        self.assertRegex(self.build_src, r'Path\(dist_manage\)\s*/\s*"python"')

    def test_build_aborts_on_venv_or_wrong_version(self):
        # Fail-loud preflight: a venv or a non-3.12.10 source must raise.
        self.assertIn("is a VIRTUALENV", self.build_src)
        self.assertIn("MUST be exactly", self.build_src)

    def test_agents_resolver_prefers_carried_python(self):
        # Every agent that resolves an interpreter must look in <install_dir>/python.
        # get_user_python_home (62 agents) returns that dir first in frozen mode.
        checked = 0
        missing = []
        for py in AGENTS_DIR.rglob("*.py"):
            src = _read(py)
            if "def get_user_python_home(" not in src:
                continue
            checked += 1
            if "os.path.dirname(sys.executable), 'python')" not in src:
                missing.append(py.name)
        self.assertGreaterEqual(checked, 50, "expected the helper in many agents")
        self.assertEqual(missing, [], f"agents not preferring carried python: {missing}")

    def test_cleaner_special_case_prefers_carried_python(self):
        # cleaner.py has get_python_command but no helper — patched directly.
        cleaner = _read(AGENTS_DIR / "cleaner" / "cleaner.py")
        self.assertIn("exe_dir, 'python', 'python.exe'", cleaner)

    def test_app_side_resolvers_prefer_carried_python(self):
        for rel in ("views.py", "tools.py", "chat_agent_runtime.py"):
            src = _read(REPO_ROOT / "Tlamatini" / "agent" / rel)
            self.assertIn(
                "'python'", src.replace('"python"', "'python'"),
                f"{rel} should reference the carried python subdir",
            )
        # The two app-side resolvers must NOT fall back to a user PYTHON_HOME first.
        tools_src = _read(REPO_ROOT / "Tlamatini" / "agent" / "tools.py")
        self.assertIn("carried = os.path.join(os.path.dirname(sys.executable), 'python', 'python.exe')",
                      tools_src)

    def test_build_carries_playwright_browsers(self):
        # Playwright browsers live outside site-packages, so the carried Python
        # alone is not enough — Playwrighter/Googler need them bundled too.
        self.assertIn("def bundle_playwright_browsers(", self.build_src)
        self.assertIn("bundle_playwright_browsers(dist_manage)", self.build_src)
        self.assertIn("ms-playwright", self.build_src)

    def test_frozen_app_pins_playwright_browsers_path(self):
        # manage.py must export PLAYWRIGHT_BROWSERS_PATH at the carried location
        # so the in-process Googler and every spawned agent (os.environ.copy)
        # find the bundled browsers on a clean machine.
        manage_src = _read(REPO_ROOT / "Tlamatini" / "manage.py")
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH", manage_src)
        self.assertIn("'ms-playwright'", manage_src)
        self.assertIn("_pin_playwright_browsers()", manage_src)

    def test_build_carries_java_and_git(self):
        # J-Decompiler needs Java; Gitter + the STM32er MCP clone need Git.
        for fn in ("def bundle_java_runtime(", "def bundle_git(",
                   "bundle_java_runtime(dist_manage)", "bundle_git(dist_manage)"):
            self.assertIn(fn, self.build_src)

    def test_frozen_app_pins_java_and_git(self):
        manage_src = _read(REPO_ROOT / "Tlamatini" / "manage.py")
        self.assertIn("_pin_bundled_tools()", manage_src)
        self.assertIn("JAVA_HOME", manage_src)
        self.assertIn("'jre'", manage_src)
        self.assertIn("'git'", manage_src)

    def test_jdcli_bat_has_no_hardcoded_dev_path(self):
        # The J-Decompiler launcher must NEVER hardcode a developer JAVA_HOME;
        # it resolves an ambient JAVA_HOME or the carried <install>/jre.
        bat = _read(REPO_ROOT / "Tlamatini" / "jd-cli" / "jd-cli.bat")
        self.assertNotIn("D:\\devenv", bat)
        self.assertNotIn("GlassFish", bat)
        self.assertIn("%~dp0..\\jre", bat)
        self.assertIn("if not defined JAVA_HOME", bat)


class NoGpuCudaFreeContractTests(SimpleTestCase):
    """The build MUST produce a CPU-only, CUDA-free package and the audio agents
    (Talker = torch/snac, Whisperer = faster-whisper/ctranslate2) MUST run on a
    machine with no GPU. Guards the contract documented in CLAUDE.md / agents.md:
    no NVIDIA CUDA wheels ship, torch is the CPU build, and every local-inference
    path falls back to CPU instead of hard-requiring a GPU.
    """

    def setUp(self):
        self.build_src = _read(BUILD_PY)

    # -- build (compilation) is CPU-only --------------------------------------
    def test_torch_installed_cpu_only(self):
        # torch must come from the PyTorch CPU wheel index, never the CUDA build.
        self.assertIn("https://download.pytorch.org/whl/cpu", self.build_src,
                      "build.py must install the CPU-only torch wheel")

    def test_nvidia_cuda_wheels_pruned(self):
        # The NVIDIA CUDA runtime wheels (nvidia-*) must be pruned from the build.
        self.assertIn('_PRUNE_PKG_PREFIXES = ("nvidia",)', self.build_src,
                      "build.py must prune the nvidia* CUDA runtime wheels")
        for mod in ("torchvision", "torchaudio"):
            self.assertIn(mod, self.build_src,
                          f"build.py should drop {mod} (GPU-heavy, unused)")

    def test_requirements_torch_is_not_a_cuda_variant(self):
        # The torch pin must not request a +cuXXX (CUDA) local-version build.
        torch_lines = [ln.strip() for ln in _read(REQUIREMENTS).splitlines()
                       if re.match(r"^torch\b", ln.strip())]
        self.assertTrue(torch_lines, "torch must be pinned in requirements.txt")
        for ln in torch_lines:
            self.assertNotIn("+cu", ln,
                             f"torch must not pin a CUDA build, got: {ln!r}")

    def test_ctranslate2_engine_is_kept_not_pruned(self):
        # faster-whisper (Whisperer's local engine) rides on ctranslate2; both
        # must be collected so CPU inference works in the frozen build.
        for mod in ("faster_whisper", "ctranslate2"):
            self.assertIn(mod, self.build_src,
                          f"build.py must keep {mod} for CPU speech-to-text")

    # -- runtime falls back to CPU (no forced GPU) ----------------------------
    def test_whisperer_autodetects_and_falls_back_to_cpu(self):
        src = _read(AGENTS_DIR / "whisperer" / "whisperer.py")
        # auto -> cpu when no CUDA device; and an explicit GPU->CPU retry.
        self.assertIn("get_cuda_device_count", src)
        self.assertIn("else 'cpu'", src)
        self.assertIn("falling back to CPU", src)
        # missing engine must degrade, not crash.
        self.assertIn("engine_unavailable", src)

    def test_talker_decodes_on_cpu_no_forced_cuda(self):
        src = _read(AGENTS_DIR / "talker" / "talker.py")
        # snac/torch decode must not force the GPU.
        self.assertNotIn(".cuda(", src)
        self.assertNotIn("to('cuda')", src)
        self.assertNotIn('to("cuda")', src)
        # absent vocoder degrades to tokens_only instead of crashing.
        self.assertIn("tokens_only", src)


if __name__ == "__main__":
    unittest.main()
