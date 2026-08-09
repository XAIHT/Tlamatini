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
test_self_modify_gate.py — "her source and her self-knowledge ship together,
or not at all", and the DEFAULT build carries neither.

Contract under test (2026-08-08, Angela's directive), in three parts:

  1. A build WITHOUT ``--self-modify`` ships NEITHER ``TlamatiniSourceCode/``
     NOR ``Tlamatini.md``.
  2. At runtime the ENTIRE ``<self_knowledge>`` section of prompt.pmt — its long
     identity bullets AND the injected file — is DROPPED in that build, leaving
     one short honest line. The goal is not merely silence: it is a measurably
     SMALLER system prompt on every single request, which is why
     ``test_default_mode_prompt_is_smaller`` asserts the size relation directly.
  3. WITH ``--self-modify`` nothing changes at all: she keeps the full block and
     the full file, exactly as before, so she can still modify herself.

Before this, only HALF the flag worked. The source tree was correctly gated, but
``Tlamatini.md`` shipped unconditionally (an ``--add-data`` bundle entry AND an
install-root copy) and ``rag/config.py`` injected it whenever the placeholder
existed — so a "not-self-able-modify" build still paid for her full
self-description in every prompt.

The placeholder must NEVER survive: a leftover ``{self_knowledge}`` becomes an
unexpected ChatPromptTemplate input variable and breaks every chain.

Run: ``python Tlamatini/manage.py test agent.test_self_modify_gate``
"""

import ast
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from agent.rag.config import (
    NOT_SELF_ABLE_MODIFY_NOTICE,
    NOT_SELF_MODIFY_MARKERS,
    SELF_KNOWLEDGE_MARKERS,
    SELF_KNOWLEDGE_PLACEHOLDER,
    SELF_MODIFY_DIRNAME,
    _load_self_knowledge_block,
    is_self_able_modify,
    load_config_and_prompt,
)

_AGENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_DIR.parent.parent
_BUILD_PY = _REPO_ROOT / "build.py"
_PROMPT_PMT = _AGENT_DIR / "prompt.pmt"

_ALL_MARKERS = SELF_KNOWLEDGE_MARKERS + NOT_SELF_MODIFY_MARKERS

# A sentinel that could only have come from the fake Tlamatini.md on disk.
_SELF_TEXT = "I am Tlamatini and this is my private self-knowledge sentinel."

# A miniature of the real prompt.pmt: two sentinel-wrapped alternatives around
# the same subject, exactly one of which must survive a load.
_FAKE_PROMPT = """Rules that always apply.
<!--SELF_KNOWLEDGE_BEGIN-->
- Your self-knowledge lives in Tlamatini.md, and your own source code may be
  bundled with you in TlamatiniSourceCode/ — a long identity bullet that only
  earns its tokens when those things actually exist.
<self_knowledge>
The block below is your own self-knowledge, injected at prompt-build time.
{self_knowledge}
</self_knowledge>
<!--SELF_KNOWLEDGE_END-->
<!--NOT_SELF_MODIFY_BEGIN-->
- This build carries NEITHER your own source code NOR a self-knowledge file: it
  is a not-self-able-modify build.
<!--NOT_SELF_MODIFY_END-->
Context follows: {context}
"""

# An OLDER prompt revision, with the placeholder but no sentinels at all.
_LEGACY_PROMPT = "Rules. <self_knowledge>{self_knowledge}</self_knowledge> {context}"


def _make_app_dir(with_source_tree, with_self_file=True, prompt=_FAKE_PROMPT,
                  self_text=_SELF_TEXT):
    """Create a throwaway application directory shaped like a real install."""
    app_dir = tempfile.mkdtemp(prefix="selfmodgate_")
    with open(os.path.join(app_dir, "config.json"), "w", encoding="utf-8") as fh:
        fh.write('{"x": 1}')
    with open(os.path.join(app_dir, "prompt.pmt"), "w", encoding="utf-8") as fh:
        fh.write(prompt)
    if with_self_file:
        with open(os.path.join(app_dir, "Tlamatini.md"), "w", encoding="utf-8") as fh:
            fh.write(self_text)
    if with_source_tree:
        os.makedirs(os.path.join(app_dir, SELF_MODIFY_DIRNAME), exist_ok=True)
    return app_dir


def _build_py_source():
    with open(_BUILD_PY, "r", encoding="utf-8") as fh:
        return fh.read()


def _assigns_named(tree, name):
    """Every ast.Assign node in *tree* whose target is the plain name *name*."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                found.append(node)
    return found


class _AppDirTestCase(unittest.TestCase):
    """Shared throwaway-application-directory plumbing."""

    def setUp(self):
        self._dirs = []

    def tearDown(self):
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _app(self, **kwargs):
        d = _make_app_dir(**kwargs)
        self._dirs.append(d)
        return d

    def _prompt(self, **kwargs):
        _, prompt_template, _ = load_config_and_prompt(self._app(**kwargs))
        return prompt_template


# ---------------------------------------------------------------------------
# 1) The whole-block decision — this is where the tokens are saved
# ---------------------------------------------------------------------------


class SelfKnowledgeBlockResolutionTests(_AppDirTestCase):

    def test_default_mode_drops_the_entire_self_knowledge_section(self):
        prompt = self._prompt(with_source_tree=False)
        self.assertNotIn("<self_knowledge>", prompt)
        self.assertNotIn("Your self-knowledge lives in Tlamatini.md", prompt)
        self.assertNotIn(_SELF_TEXT, prompt)
        # ...and the one short honest line takes its place.
        self.assertIn("not-self-able-modify build", prompt)

    def test_self_modify_mode_keeps_her_exactly_as_before(self):
        prompt = self._prompt(with_source_tree=True)
        self.assertIn("<self_knowledge>", prompt)
        self.assertIn("Your self-knowledge lives in Tlamatini.md", prompt)
        self.assertIn(_SELF_TEXT, prompt)
        # The "you carry nothing about yourself" line must NOT appear here.
        self.assertNotIn("not-self-able-modify build", prompt)

    def test_default_mode_prompt_is_smaller(self):
        """The POINT of the default mode: fewer prompt tokens on every request."""
        big = self._prompt(with_source_tree=True)
        small = self._prompt(with_source_tree=False)
        self.assertLess(len(small), len(big))

    def test_real_prompt_saving_measured_and_reported(self):
        """The REAL number, through the REAL loader, on the REAL files."""
        real_md = _AGENT_DIR / "Tlamatini.md"
        if not real_md.is_file():
            self.skipTest("Tlamatini.md not present in this checkout")
        real_prompt = _PROMPT_PMT.read_text(encoding="utf-8")
        real_text = real_md.read_text(encoding="utf-8")
        kwargs = dict(prompt=real_prompt, self_text=real_text)
        big = self._prompt(with_source_tree=True, **kwargs)
        small = self._prompt(with_source_tree=False, **kwargs)
        saved = len(big) - len(small)
        self.assertGreater(saved, 0)
        # ~4 chars/token is the usual rule of thumb; this is a report, not a
        # threshold, so it can never fail for being off by a few percent.
        print(f"\n    [self-modify gate] system prompt: "
              f"{len(big)} chars WITH self-knowledge -> {len(small)} chars without "
              f"(saved {saved} chars, ~{saved // 4} tokens on EVERY request)")

    def test_exactly_one_alternative_survives(self):
        for gated in (True, False):
            prompt = self._prompt(with_source_tree=gated)
            self.assertEqual(
                gated, "<self_knowledge>" in prompt,
                "the self-knowledge section must appear iff the source tree does")
            self.assertEqual(
                not gated, "not-self-able-modify build" in prompt,
                "the short line must appear iff the section does not")

    def test_no_marker_ever_leaks_into_the_prompt(self):
        for gated in (True, False):
            prompt = self._prompt(with_source_tree=gated)
            for marker in _ALL_MARKERS:
                self.assertNotIn(marker, prompt)

    def test_placeholder_is_consumed_in_both_modes(self):
        # A surviving '{self_knowledge}' becomes an unexpected
        # ChatPromptTemplate input variable and breaks every chain.
        for gated in (True, False):
            prompt = self._prompt(with_source_tree=gated)
            self.assertNotIn(SELF_KNOWLEDGE_PLACEHOLDER, prompt)
            self.assertIn("{context}", prompt)

    def test_legacy_prompt_without_sentinels_still_degrades_safely(self):
        # Second layer of defence: an older prompt.pmt with the placeholder but
        # no markers must still lose the self-description, not the whole prompt.
        prompt = self._prompt(with_source_tree=False, prompt=_LEGACY_PROMPT)
        self.assertNotIn(SELF_KNOWLEDGE_PLACEHOLDER, prompt)
        self.assertNotIn(_SELF_TEXT, prompt)
        self.assertIn(NOT_SELF_ABLE_MODIFY_NOTICE, prompt)


# ---------------------------------------------------------------------------
# 2) The injector itself
# ---------------------------------------------------------------------------


class SelfKnowledgeInjectorTests(_AppDirTestCase):

    def test_no_source_tree_means_no_self_knowledge_even_if_the_file_is_there(self):
        # Belt and braces: a stale Tlamatini.md left behind by an older install
        # must STILL not leak into the prompt.
        block = _load_self_knowledge_block(
            self._app(with_source_tree=False, with_self_file=True))
        self.assertEqual(block, NOT_SELF_ABLE_MODIFY_NOTICE)
        self.assertNotIn(_SELF_TEXT, block)

    def test_source_tree_present_injects_the_real_self_knowledge(self):
        block = _load_self_knowledge_block(
            self._app(with_source_tree=True, with_self_file=True))
        self.assertIn(_SELF_TEXT, block)

    def test_self_modify_build_missing_the_file_fails_open(self):
        # Source tree present but Tlamatini.md gone: degrade to a notice, never
        # raise — a broken self-knowledge file must not break the system prompt.
        block = _load_self_knowledge_block(
            self._app(with_source_tree=True, with_self_file=False))
        self.assertNotIn(_SELF_TEXT, block)
        self.assertTrue(block.strip())

    def test_is_self_able_modify_fails_closed(self):
        # Unreadable / nonsense path => "you do NOT carry your own source".
        self.assertFalse(is_self_able_modify(os.path.join(
            tempfile.gettempdir(), "definitely_not_a_tlamatini_install_dir_xyz")))
        self.assertFalse(is_self_able_modify(None))

    def test_the_notice_contains_no_template_braces(self):
        # The notice is injected verbatim (not brace-escaped), so a stray brace
        # would silently become a template variable.
        self.assertNotIn("{", NOT_SELF_ABLE_MODIFY_NOTICE)
        self.assertNotIn("}", NOT_SELF_ABLE_MODIFY_NOTICE)

    def test_real_checkout_is_self_consistent(self):
        # Whatever this checkout looks like, the two must agree.
        _, prompt_template, _ = load_config_and_prompt(str(_AGENT_DIR))
        has_tree = is_self_able_modify(str(_AGENT_DIR))
        self.assertEqual(has_tree, "<self_knowledge>" in prompt_template)
        self.assertNotIn(SELF_KNOWLEDGE_PLACEHOLDER, prompt_template)
        for marker in _ALL_MARKERS:
            self.assertNotIn(marker, prompt_template)


# ---------------------------------------------------------------------------
# 3) The real prompt.pmt carries both alternatives, balanced
# ---------------------------------------------------------------------------


class PromptContractTests(unittest.TestCase):
    def setUp(self):
        with open(_PROMPT_PMT, "r", encoding="utf-8") as fh:
            self.text = fh.read()

    def test_both_marker_pairs_are_present_and_balanced(self):
        for begin, end in (SELF_KNOWLEDGE_MARKERS, NOT_SELF_MODIFY_MARKERS):
            self.assertEqual(
                self.text.count(begin), self.text.count(end),
                f"unbalanced sentinel pair: {begin} / {end}")
            self.assertGreaterEqual(self.text.count(begin), 1)

    def test_the_self_knowledge_section_is_inside_the_gated_block(self):
        begin, end = SELF_KNOWLEDGE_MARKERS
        gated = []
        cursor = 0
        while True:
            start = self.text.find(begin, cursor)
            if start == -1:
                break
            stop = self.text.find(end, start)
            self.assertNotEqual(stop, -1, "SELF_KNOWLEDGE_BEGIN with no END")
            gated.append(self.text[start:stop])
            cursor = stop + len(end)
        joined = "".join(gated)
        self.assertIn(SELF_KNOWLEDGE_PLACEHOLDER, joined)
        self.assertIn("<self_knowledge>", joined)
        self.assertIn("Tlamatini.md", joined)

    def test_the_fallback_line_is_short(self):
        # It exists to be cheap. If it ever grows into a second essay the whole
        # point of the default mode is lost.
        begin, end = NOT_SELF_MODIFY_MARKERS
        start = self.text.find(begin) + len(begin)
        body = self.text[start:self.text.find(end)]
        self.assertLess(len(body), 800, "the not-self-able-modify line must stay short")
        self.assertIn("not-self-able-modify", body)


# ---------------------------------------------------------------------------
# 4) PACKAGING — build.py ships Tlamatini.md ONLY under --self-modify
# ---------------------------------------------------------------------------


class SelfKnowledgePackagingGateTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _build_py_source()
        cls.tree = ast.parse(cls.src)

    def test_add_data_entry_is_gated_on_self_modify(self):
        assigns = _assigns_named(self.tree, "self_knowledge_args")
        self.assertEqual(len(assigns), 1,
                         "build.py must assign self_knowledge_args exactly once")
        value = assigns[0].value
        self.assertIsInstance(value, ast.IfExp,
                              "self_knowledge_args must be a conditional expression")
        self.assertIn("self_modify", ast.dump(value.test))
        self.assertIn("Tlamatini.md", ast.dump(value.body))
        self.assertNotIn("Tlamatini.md", ast.dump(value.orelse))

    def test_pyinstaller_command_has_no_unconditional_self_knowledge(self):
        commands = _assigns_named(self.tree, "command")
        self.assertTrue(commands, "build.py must build a PyInstaller command list")
        for node in commands:
            self.assertNotIn(
                "Tlamatini.md", ast.dump(node),
                "Tlamatini.md must not be hardcoded in the PyInstaller args")
        self.assertTrue(
            any("self_knowledge_args" in ast.dump(n) for n in commands),
            "the PyInstaller args must splat *self_knowledge_args")

    def test_optional_file_copies_dict_has_no_unconditional_self_knowledge(self):
        copies = _assigns_named(self.tree, "optional_file_copies")
        self.assertTrue(copies, "build.py must define optional_file_copies")
        for node in copies:
            self.assertNotIn(
                "Tlamatini.md", ast.dump(node.value),
                "Tlamatini.md must not sit in the unconditional copy dict")

    def test_install_root_copy_lives_inside_an_if_self_modify_block(self):
        self.assertTrue(
            self._gated_ifs_containing("optional_file_copies", "Tlamatini.md"),
            "the install-root Tlamatini.md copy must be inside an `if self_modify:`")

    def test_source_tree_still_gated_on_self_modify(self):
        self.assertTrue(
            self._gated_ifs_containing("TlamatiniSourceCode"),
            "TlamatiniSourceCode must only be produced inside `if self_modify:`")

    def _gated_ifs_containing(self, *needles):
        hits = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.If):
                continue
            if "self_modify" not in ast.dump(node.test):
                continue
            body = "".join(ast.dump(stmt) for stmt in node.body)
            if all(n in body for n in needles):
                hits.append(node)
        return hits


# ---------------------------------------------------------------------------
# 5) The wrapper builders default to a NOT-self-able-modify release
#    (Angela, 2026-08-08: "make the default building with build_complete_* be
#    like if --no-self-modify were set").
# ---------------------------------------------------------------------------


class BuildWrapperDefaultTests(unittest.TestCase):
    PRIVATE = _REPO_ROOT / "build_complete_private_release.py"
    PUBLIC = _REPO_ROOT / "build_complete_public_release.py"

    @staticmethod
    def _read(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_build_py_honours_an_explicit_no_self_modify(self):
        # --no-self-modify is a REAL flag now, and it WINS over --self-modify so
        # a wrapper can force the release off.
        src = _build_py_source()
        self.assertIn('"--no-self-modify" not in sys.argv', src)
        assigns = _assigns_named(ast.parse(src), "self_modify")
        self.assertTrue(assigns, "build.py must assign self_modify")
        dumped = "".join(ast.dump(a.value) for a in assigns)
        self.assertIn("--self-modify", dumped)
        self.assertIn("--no-self-modify", dumped)

    def test_private_release_defaults_to_no_self_modify(self):
        src = self._read(self.PRIVATE)
        # The opt-IN flag must exist...
        self.assertIn('"--self-modify", action="store_true"', src)
        # ...and the old opt-OUT default ("bundled unless told otherwise") is gone.
        self.assertNotIn("self_modify = not args.no_self_modify", src)
        self.assertIn("self_modify = args.self_modify and not args.no_self_modify", src)

    def test_public_release_defaults_to_no_self_modify(self):
        src = self._read(self.PUBLIC)
        self.assertIn('"--self-modify", action="store_true"', src)
        self.assertNotIn("self_modify = not args.no_self_modify", src)

    def test_wrappers_pass_the_decision_explicitly_either_way(self):
        # Both flags are always passed down, so the intent is recorded in the
        # build log and a stray ambient "--self-modify" cannot flip the build.
        for path in (self.PRIVATE, self.PUBLIC):
            tree = ast.parse(self._read(path))
            ternaries = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.IfExp)
                and "self_modify" in ast.dump(node.test)
                and "--self-modify" in ast.dump(node.body)
                and "--no-self-modify" in ast.dump(node.orelse)
            ]
            self.assertTrue(
                ternaries,
                f"{path.name} must pass --self-modify / --no-self-modify explicitly")

    def test_wrappers_verify_what_they_actually_built(self):
        # "No lying": each wrapper opens pkg.zip and proves the payload matches
        # the flag, in BOTH directions, instead of trusting build.py.
        for path in (self.PRIVATE, self.PUBLIC):
            src = self._read(path)
            self.assertIn("def assert_self_modify_payload", src)
            self.assertIn("assert_self_modify_payload(", src)
            self.assertIn("TlamatiniSourceCode/", src)
            self.assertIn("Tlamatini.md", src)
            self.assertIn("zipfile", src)

    def test_public_lets_no_self_modify_win(self):
        src = self._read(self.PUBLIC)
        self.assertIn("if args.no_self_modify:", src)
        self.assertIn("args.self_modify = False", src)


if __name__ == "__main__":
    unittest.main()
