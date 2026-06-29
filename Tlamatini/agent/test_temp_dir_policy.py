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
test_temp_dir_policy.py — the "temp stays inside Tlamatini" contract.

Policy under test: EVERY temporary file Tlamatini writes — by the core process,
by any pool agent, by any bundled library — lives under ONE directory, ``Temp``
at the application root, and NEVER anywhere else (no ``C:\\Temp``, no ``%TEMP%``,
no system temp). These tests drive the REAL shipped code:

  * agent/path_guard.py        — the canonical resolver + enforcer
  * agent/rag/config.py        — the {temp_directory} prompt injection
  * the 6 temp-creating agents — their actual ``_enforce_tlamatini_temp`` block
                                 is extracted from disk and executed
  * manage.py / settings.py    — process-wide enforcement (static contract)
  * build.py / prompt.pmt      — packaging + LLM-instruction contract (static)

Run: ``python Tlamatini/manage.py test agent.test_temp_dir_policy``
"""

import os
import re
import sys
import tempfile
import unittest

from agent import path_guard


# Resolve repo layout from THIS file's location (agent/test_temp_dir_policy.py):
#   agent dir   = <repo>/Tlamatini/agent
#   project dir = <repo>/Tlamatini          (manage.py lives here)
#   repo root   = <repo>                     (build.py, .git, CLAUDE.md live here)
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_AGENT_DIR)
_REPO_ROOT = os.path.dirname(_PROJECT_DIR)
_AGENTS_DIR = os.path.join(_AGENT_DIR, "agents")

# The 5 agents that create temporary files and therefore ship an explicit
# _enforce_tlamatini_temp() block (kept in lock-step with the source edits).
_TEMP_CREATING_AGENTS = (
    "executer", "de_compresser", "esp32er", "stm32er", "arduiner",
)


def _read(*parts):
    with open(os.path.join(*parts), "r", encoding="utf-8") as fh:
        return fh.read()


class _TempStateGuard(unittest.TestCase):
    """Base class that snapshots & restores the global temp state.

    enforce_app_temp_dir() and the agent blocks mutate ``os.environ`` and the
    process-global ``tempfile.tempdir``; without restoration they would leak
    into sibling tests. setUp snapshots, tearDown restores byte-for-byte.
    """

    _TEMP_VARS = ("TMP", "TEMP", "TMPDIR", "TLAMATINI_TEMP")

    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in self._TEMP_VARS}
        self._saved_tempdir = tempfile.tempdir

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        tempfile.tempdir = self._saved_tempdir


class ResolutionTests(_TempStateGuard):
    """path_guard's resolver points at <app-root>/Temp and stays inside it."""

    def test_temp_root_is_app_root_slash_temp(self):
        root = path_guard.get_app_temp_root()
        self.assertEqual(
            os.path.normcase(root),
            os.path.normcase(os.path.join(path_guard._get_application_root(),
                                          path_guard.TEMP_DIR_NAME)),
        )

    def test_source_mode_temp_root_is_repo_root_temp(self):
        # In source mode (these tests are NOT frozen) the app root is the repo
        # root — matching the user-spec example ``…\\Tlamatini\\Temp``.
        self.assertFalse(getattr(sys, "frozen", False))
        self.assertEqual(
            os.path.normcase(path_guard.get_app_temp_root()),
            os.path.normcase(os.path.join(_REPO_ROOT, "Temp")),
        )

    def test_temp_root_is_created_on_demand(self):
        root = path_guard.get_app_temp_root()
        self.assertTrue(os.path.isdir(root), f"Temp root not created: {root}")

    def test_temp_root_is_within_application_root(self):
        # The whole point: Temp can NEVER be outside Tlamatini.
        self.assertTrue(
            path_guard.is_within_application_root(path_guard.get_app_temp_root())
        )

    def test_is_within_app_temp(self):
        root = path_guard.get_app_temp_root()
        self.assertTrue(path_guard.is_within_app_temp(root))
        self.assertTrue(path_guard.is_within_app_temp(os.path.join(root, "a", "b.txt")))
        # A sibling of Temp (the app root itself) is NOT inside Temp.
        self.assertFalse(path_guard.is_within_app_temp(path_guard._get_application_root()))
        self.assertFalse(path_guard.is_within_app_temp(r"C:\Temp\evil.txt"))

    def test_resolve_temp_path_joins_and_blocks_traversal(self):
        ok = path_guard.resolve_temp_path("sub", "file.bin")
        self.assertIsNotNone(ok)
        self.assertTrue(path_guard.is_within_app_temp(ok))
        # Traversal that escapes Temp must be rejected.
        self.assertIsNone(path_guard.resolve_temp_path("..", "..", "escape.txt"))


class EnforcementTests(_TempStateGuard):
    """enforce_app_temp_dir() actually redirects tempfile + the env vars."""

    def test_enforce_sets_every_handle(self):
        root = path_guard.enforce_app_temp_dir()
        self.assertEqual(os.path.normcase(root),
                         os.path.normcase(path_guard.get_app_temp_root()))
        for var in ("TMP", "TEMP", "TMPDIR", "TLAMATINI_TEMP"):
            self.assertEqual(os.path.normcase(os.environ[var]),
                             os.path.normcase(root),
                             f"{var} not pinned to the app Temp root")
        self.assertEqual(os.path.normcase(tempfile.tempdir),
                         os.path.normcase(root))

    def test_real_tempfile_lands_under_app_temp_after_enforce(self):
        # The acid test: after enforcement, a genuine NamedTemporaryFile and a
        # genuine mkdtemp are physically created INSIDE <app>/Temp.
        path_guard.enforce_app_temp_dir()
        with tempfile.NamedTemporaryFile(prefix="policytest_", delete=True) as tf:
            self.assertTrue(
                path_guard.is_within_app_temp(tf.name),
                f"NamedTemporaryFile escaped the app Temp: {tf.name}",
            )
        d = tempfile.mkdtemp(prefix="policytest_")
        try:
            self.assertTrue(path_guard.is_within_app_temp(d),
                            f"mkdtemp escaped the app Temp: {d}")
        finally:
            os.rmdir(d)

    def test_gettempdir_returns_app_temp_after_enforce(self):
        root = path_guard.enforce_app_temp_dir()
        self.assertEqual(os.path.normcase(tempfile.gettempdir()),
                         os.path.normcase(root))


class AgentEnforcementBlockTests(_TempStateGuard):
    """Extract the ACTUAL _enforce_tlamatini_temp() block from each of the 5
    temp-creating agents on disk and execute it — proving the shipped code (not
    a stand-in) redirects tempfile to TLAMATINI_TEMP."""

    # The enforcement is a guarded if-block (mirrors the conhost-guard shape so
    # it is valid before the remaining module imports — a top-level def would
    # trip E402). Extract from the `if` to the `except: pass` tail.
    _BLOCK_RE = re.compile(
        r"if \(os\.environ\.get\('TLAMATINI_TEMP'\).*?\n        pass",
        re.DOTALL,
    )

    def _extract_block(self, agent):
        src = _read(_AGENTS_DIR, agent, agent + ".py")
        m = self._BLOCK_RE.search(src)
        self.assertIsNotNone(m, f"{agent}: TLAMATINI_TEMP enforcement block not found")
        return m.group(0)

    def test_all_temp_creating_agents_have_the_block(self):
        for agent in _TEMP_CREATING_AGENTS:
            with self.subTest(agent=agent):
                self._extract_block(agent)  # raises via assert if missing

    def test_extracted_block_redirects_tempfile_to_tlamatini_temp(self):
        import shutil
        # Build our own scratch dirs WITHOUT tempfile (each exec pins
        # tempfile.tempdir process-wide — proving the policy works — so relying
        # on tempfile.mkdtemp here would target a previous iteration's dir).
        base = os.path.join(self._saved_tempdir or os.getcwd(),
                            f"agentblocks_{os.getpid()}")
        os.makedirs(base, exist_ok=True)
        try:
            for agent in _TEMP_CREATING_AGENTS:
                with self.subTest(agent=agent):
                    block = self._extract_block(agent)
                    target = os.path.join(base, agent)
                    os.makedirs(target, exist_ok=True)
                    os.environ["TLAMATINI_TEMP"] = target
                    tempfile.tempdir = None  # so we detect the block setting it
                    # Run the agent's real module-load enforcement code.
                    ns = {"os": os}
                    exec(compile(block, f"<{agent}>", "exec"), ns)  # noqa: S102
                    self.assertEqual(
                        os.path.normcase(tempfile.tempdir),
                        os.path.normcase(target),
                        f"{agent}: block did not pin tempfile.tempdir",
                    )
                    self.assertEqual(os.path.normcase(os.environ["TEMP"]),
                                     os.path.normcase(target))
                    self.assertEqual(os.path.normcase(os.environ["TMP"]),
                                     os.path.normcase(target))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_block_is_fail_open_when_handle_absent(self):
        # No TLAMATINI_TEMP set → block must NOT raise and must NOT clobber
        # tempfile.tempdir (leaves Python's default in place).
        block = self._extract_block("executer")
        os.environ.pop("TLAMATINI_TEMP", None)
        tempfile.tempdir = None
        ns = {"os": os}
        exec(compile(block, "<executer>", "exec"), ns)  # noqa: S102
        self.assertIsNone(tempfile.tempdir)

    def test_executer_nonblocking_uses_tlamatini_temp_not_bare_gettempdir(self):
        src = _read(_AGENTS_DIR, "executer", "executer.py")
        # The non-blocking script path must derive its dir from TLAMATINI_TEMP,
        # not a naked tempfile.gettempdir() that could be C:\\Temp / %TEMP%.
        self.assertIn("os.environ.get('TLAMATINI_TEMP')", src)
        self.assertNotIn("temp_dir = tempfile.gettempdir()", src)


class PromptInjectionTests(unittest.TestCase):
    """rag/config.py resolves and injects the absolute Temp path."""

    def test_resolver_returns_app_temp_root(self):
        from agent.rag.config import _resolve_temp_directory_for_prompt
        resolved = _resolve_temp_directory_for_prompt()
        # Brace-escaped form of the real app temp root.
        expected = path_guard.get_app_temp_root().replace("{", "{{").replace("}", "}}")
        self.assertEqual(resolved, expected)

    def test_load_config_and_prompt_replaces_placeholder(self):
        from agent.rag.config import load_config_and_prompt, TEMP_DIRECTORY_PLACEHOLDER
        app_dir = tempfile.mkdtemp(prefix="promptinj_")
        try:
            with open(os.path.join(app_dir, "config.json"), "w", encoding="utf-8") as fh:
                fh.write('{"x": 1}')
            with open(os.path.join(app_dir, "prompt.pmt"), "w", encoding="utf-8") as fh:
                fh.write("Temp dir is {temp_directory}. Self: {self_knowledge}. {context}")
            _, prompt_template, _ = load_config_and_prompt(app_dir)
            # Placeholder consumed; real Temp path present; {context} untouched.
            self.assertNotIn(TEMP_DIRECTORY_PLACEHOLDER, prompt_template)
            self.assertIn(path_guard.get_app_temp_root(), prompt_template)
            self.assertIn("{context}", prompt_template)
        finally:
            import shutil
            shutil.rmtree(app_dir, ignore_errors=True)


class RealPromptEndToEndTests(unittest.TestCase):
    """Load the REAL prompt.pmt through the real loader and confirm both new
    placeholders are resolved (a leaked '{temp_directory}' / '{templates_directory}'
    would become an undefined ChatPromptTemplate variable → runtime KeyError)."""

    def test_real_prompt_resolves_both_placeholders(self):
        from agent.rag.config import load_config_and_prompt
        # In source mode the application_path for prompt.pmt is the agent dir.
        _, prompt_template, _ = load_config_and_prompt(_AGENT_DIR)
        self.assertNotIn("{temp_directory}", prompt_template)
        self.assertNotIn("{templates_directory}", prompt_template)
        self.assertNotIn("{self_knowledge}", prompt_template)
        # The genuine template variables must survive for the chains to fill.
        self.assertIn("{context}", prompt_template)
        # The resolved absolute dirs are present (proves real injection ran).
        self.assertIn(path_guard.get_app_temp_root(), prompt_template)
        self.assertIn(path_guard.get_app_templates_root(), prompt_template)


class StaticContractTests(unittest.TestCase):
    """Pin the wiring in files that cannot safely be imported (manage.py runs
    side-effects at import; build.py is a script) so a careless edit fails CI."""

    def test_manage_py_enforces_temp_before_django(self):
        src = _read(_PROJECT_DIR, "manage.py")
        self.assertIn("def _enforce_app_temp_dir", src)
        self.assertIn("_enforce_app_temp_dir()", src)
        self.assertIn("TLAMATINI_TEMP", src)
        # Enforcement must run BEFORE main()/Django (i.e. at module level, above
        # the execute_from_command_line call site).
        self.assertLess(src.index("_enforce_app_temp_dir()"),
                        src.index("def main()"))

    def test_settings_py_pins_temp(self):
        src = _read(_PROJECT_DIR, "tlamatini", "settings.py")
        self.assertIn("_pin_temp_directory", src)
        self.assertIn("_pin_temp_directory()", src)
        self.assertIn("TLAMATINI_TEMP", src)

    def test_build_py_ships_empty_temp(self):
        src = _read(_REPO_ROOT, "build.py")
        # "Temp" must be in the empty_dirs tuple shipped into pkg.zip.
        m = re.search(r"empty_dirs\s*=\s*\((.*?)\)", src, re.DOTALL)
        self.assertIsNotNone(m, "empty_dirs tuple not found in build.py")
        self.assertIn('"Temp"', m.group(1))

    def test_prompt_pmt_has_temp_rule_and_no_c_temp_example(self):
        src = _read(_AGENT_DIR, "prompt.pmt")
        self.assertIn("15) Temporary files location rule", src)
        # Templates rule inserted at 16; the Talker female-voice rule was then
        # inserted at 17, pushing Conflict resolution to 18.
        self.assertIn("16) Template / project directory location rule", src)
        self.assertIn("17) Talker voice rule", src)
        self.assertIn("18) Conflict resolution rule", src)
        self.assertIn("{temp_directory}", src)
        self.assertIn("{templates_directory}", src)
        # The old harmful example that taught the LLM to use C:\\Temp is gone.
        self.assertNotIn(r"C:\\Temp\\hello.py", src)

    def test_tlamatini_md_documents_policy(self):
        src = _read(_AGENT_DIR, "Tlamatini.md")
        self.assertIn("Temp directory (HARD POLICY)", src)
        self.assertIn("TLAMATINI_TEMP", src)
        self.assertIn("Templates directory (DEFAULT project home)", src)
        self.assertIn("TLAMATINI_TEMPLATES", src)


# ════════════════════════════════════════════════════════════════════════════
# Templates policy — the DEFAULT scaffold home for STM32er/ESP32er/Arduiner/
# Unrealer projects (distinct from Temp; never sets TEMP/TMP/tempfile).
# ════════════════════════════════════════════════════════════════════════════
class TemplatesResolutionTests(unittest.TestCase):
    def test_templates_root_is_app_root_slash_templates(self):
        root = path_guard.get_app_templates_root()
        self.assertEqual(
            os.path.normcase(root),
            os.path.normcase(os.path.join(path_guard._get_application_root(),
                                          path_guard.TEMPLATES_DIR_NAME)),
        )

    def test_source_mode_templates_root_is_repo_root_templates(self):
        self.assertFalse(getattr(sys, "frozen", False))
        self.assertEqual(
            os.path.normcase(path_guard.get_app_templates_root()),
            os.path.normcase(os.path.join(_REPO_ROOT, "Templates")),
        )

    def test_created_and_within_app_root_and_distinct_from_temp(self):
        root = path_guard.get_app_templates_root()
        self.assertTrue(os.path.isdir(root))
        self.assertTrue(path_guard.is_within_application_root(root))
        # Templates is NOT the Temp dir.
        self.assertNotEqual(os.path.normcase(root),
                            os.path.normcase(path_guard.get_app_temp_root()))

    def test_is_within_and_resolve(self):
        root = path_guard.get_app_templates_root()
        self.assertTrue(path_guard.is_within_app_templates(os.path.join(root, "proj", "x")))
        self.assertFalse(path_guard.is_within_app_templates(r"C:\elsewhere\proj"))
        self.assertIsNotNone(path_guard.resolve_templates_path("leg_ctrl"))
        self.assertIsNone(path_guard.resolve_templates_path("..", "escape"))


class TemplatesEnforcementTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("TLAMATINI_TEMPLATES")
        self._saved_tempdir = tempfile.tempdir
        self._saved_tmp = {k: os.environ.get(k) for k in ("TMP", "TEMP", "TMPDIR")}

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("TLAMATINI_TEMPLATES", None)
        else:
            os.environ["TLAMATINI_TEMPLATES"] = self._saved
        tempfile.tempdir = self._saved_tempdir
        for k, v in self._saved_tmp.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_enforce_exports_handle_and_creates_dir(self):
        root = path_guard.enforce_app_templates_dir()
        self.assertEqual(os.path.normcase(os.environ["TLAMATINI_TEMPLATES"]),
                         os.path.normcase(root))
        self.assertTrue(os.path.isdir(root))

    def test_enforce_does_not_touch_tempfile_or_tmp(self):
        # Templates are deliverables — enforcement must NOT hijack OS temp.
        tempfile.tempdir = None
        before = {k: os.environ.get(k) for k in ("TMP", "TEMP", "TMPDIR")}
        path_guard.enforce_app_templates_dir()
        self.assertIsNone(tempfile.tempdir)
        self.assertEqual({k: os.environ.get(k) for k in ("TMP", "TEMP", "TMPDIR")},
                         before)


class TemplatesPromptInjectionTests(unittest.TestCase):
    def test_resolver_returns_app_templates_root(self):
        from agent.rag.config import _resolve_templates_directory_for_prompt
        resolved = _resolve_templates_directory_for_prompt()
        expected = path_guard.get_app_templates_root().replace("{", "{{").replace("}", "}}")
        self.assertEqual(resolved, expected)

    def test_load_config_and_prompt_replaces_templates_placeholder(self):
        from agent.rag.config import (load_config_and_prompt,
                                      TEMPLATES_DIRECTORY_PLACEHOLDER)
        app_dir = tempfile.mkdtemp(prefix="tmplinj_")
        try:
            with open(os.path.join(app_dir, "config.json"), "w", encoding="utf-8") as fh:
                fh.write('{"x": 1}')
            with open(os.path.join(app_dir, "prompt.pmt"), "w", encoding="utf-8") as fh:
                fh.write("Templates: {templates_directory}. Temp: {temp_directory}. {context}")
            _, prompt_template, _ = load_config_and_prompt(app_dir)
            self.assertNotIn(TEMPLATES_DIRECTORY_PLACEHOLDER, prompt_template)
            self.assertIn(path_guard.get_app_templates_root(), prompt_template)
        finally:
            import shutil
            shutil.rmtree(app_dir, ignore_errors=True)


class TemplatesWiringTests(unittest.TestCase):
    """Static contract for the surfaces that can't be safely imported."""

    def test_manage_and_settings_export_templates(self):
        self.assertIn("TLAMATINI_TEMPLATES", _read(_PROJECT_DIR, "manage.py"))
        self.assertIn("TLAMATINI_TEMPLATES",
                      _read(_PROJECT_DIR, "tlamatini", "settings.py"))

    def test_build_py_ships_empty_templates(self):
        src = _read(_REPO_ROOT, "build.py")
        m = re.search(r"empty_dirs\s*=\s*\((.*?)\)", src, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn('"Templates"', m.group(1))

    def test_stm32er_create_project_defaults_to_templates(self):
        src = _read(_AGENTS_DIR, "stm32er", "stm32er.py")
        # The create_project payload defaults a blank dest_parent to the env var.
        self.assertIn('os.environ.get("TLAMATINI_TEMPLATES")', src)

    def test_registry_purposes_mention_templates_for_four_agents(self):
        src = _read(_AGENT_DIR, "chat_agent_registry.py")
        # The 'Template / project directory location rule' is referenced in the
        # purpose of each of the four scaffolding agents (count >= 4).
        self.assertGreaterEqual(
            src.count("Template / project directory location rule"), 4)


if __name__ == "__main__":
    unittest.main()
