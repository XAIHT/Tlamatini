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
Brace sets, pattern lists and folder globs for **Grepper** and **Globber**
(2026-10-18).

Before this change both agents handed the pattern straight to fnmatch / glob,
which only know ``*``, ``?`` and ``[..]``:

* ``glob='*.{js,py,html}'`` searched **0 files** (``{`` was read literally);
* ``glob='*.py,*.js'`` and ``'*.py|*.js'`` searched 0 files too;
* Grepper's ``glob='**/*.py'`` or ``'src/*.py'`` searched 0 files, because the
  pattern was compared with the bare FILE NAME, which never contains a slash.

Each failure looked like an honest ``no_matches`` — a confident wrong answer.

Three layers of proof here:

1. the shared helper block is byte-identical in both agents, and its pure
   functions do what a shell does (nested sets, several sets, literals kept);
2. the REAL agent scripts, run as subprocesses over a throwaway tree, find
   the right files - and every pattern that worked before still works;
3. TLAMATINI COMPATIBILITY: the chat's own request parser keeps such a value
   whole, and the real wrapped-agent launcher the chat uses runs it end to end.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml
from django.test import SimpleTestCase, TestCase

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GREPPER_PY = os.path.join(_THIS_DIR, "agents", "grepper", "grepper.py")
GLOBBER_PY = os.path.join(_THIS_DIR, "agents", "globber", "globber.py")
_BEGIN = "# >>> SHARED GLOB HELPERS"
_END = "# <<< SHARED GLOB HELPERS <<<"


def _source(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8").replace("\r\n", "\n")


def _shared_block(path):
    text = _source(path)
    start = text.index(_BEGIN)
    end = text.index(_END) + len(_END)
    return text[start:end]


def _load_helpers():
    """exec the helpers without importing the agent module.

    Importing a pool agent runs its module top (log truncation, handlers), so
    the shared block and Grepper's two matcher functions are compiled on
    their own instead.
    """
    ns = {"os": os}
    exec(compile(_shared_block(GREPPER_PY), "shared_glob_block", "exec"), ns)
    src = _source(GREPPER_PY)
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == "_glob_matcher":
            exec(compile(ast.get_source_segment(src, node), node.name, "exec"), ns)
    return ns


def _load_globber_walk():
    """Globber's shared block + _glob_walk + NOISE_DIRS, without importing it."""
    ns = {"os": os}
    exec(compile(_shared_block(GLOBBER_PY), "shared_glob_block", "exec"), ns)
    src = _source(GLOBBER_PY)
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in ("_glob_walk", "_drop_noise"):
            exec(compile(ast.get_source_segment(src, node), node.name, "exec"), ns)
        elif isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "NOISE_DIRS" for t in node.targets):
            exec(compile(ast.get_source_segment(src, node), "NOISE_DIRS", "exec"), ns)
    return ns


H = _load_helpers()
G = _load_globber_walk()


def _build_tree():
    """a.py, d.js, c.txt, 'a,b.txt', sub/b.py, sub/deep/e.py - each says MARK."""
    tree = tempfile.mkdtemp(prefix="glob_tree_")
    files = ("a.py", "d.js", "c.txt", "a,b.txt",
             os.path.join("sub", "b.py"), os.path.join("sub", "deep", "e.py"))
    for rel in files:
        full = os.path.join(tree, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("value = 1  # MARK\n")
        time.sleep(0.01)
    return tree


def _run_agent(script, config):
    name = os.path.splitext(os.path.basename(script))[0]
    tmp = tempfile.mkdtemp(prefix=f"{name}_glob_test_")
    adir = os.path.join(tmp, name)
    os.makedirs(adir, exist_ok=True)
    try:
        shutil.copy(script, os.path.join(adir, f"{name}.py"))
        cfg = dict(config, source_agents=[], target_agents=[])
        with open(os.path.join(adir, "config.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, allow_unicode=True)
        subprocess.run([sys.executable, f"{name}.py"], cwd=adir, timeout=60, capture_output=True)
        with open(os.path.join(adir, f"{name}.log"), encoding="utf-8") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _section(log, tag):
    m = re.search(rf"INI_SECTION_{tag}<<<(.*?)>>>END_SECTION_{tag}", log, re.S)
    assert m, f"no INI_SECTION_{tag} in log:\n{log}"
    head, _, body = m.group(1).partition("\n\n")
    return head, body.strip()


def _names(body):
    """Base names of the files a Grepper(files)/Globber body lists."""
    return sorted(os.path.basename(line.strip()) for line in body.splitlines()
                  if line.strip() and not line.startswith("..."))


# ---------------------------------------------------------------------------
# 1. The shared block and its pure functions
# ---------------------------------------------------------------------------
class SharedBlockTests(SimpleTestCase):
    def test_both_agents_carry_the_same_block(self):
        self.assertEqual(_shared_block(GREPPER_PY), _shared_block(GLOBBER_PY),
                         "Grepper and Globber must expand patterns identically")

    def test_both_agents_use_it(self):
        self.assertIn("_glob_matcher(glob_pat)", _source(GREPPER_PY))
        self.assertIn("variants = _glob_variants(pattern)", _source(GLOBBER_PY))
        self.assertIn("found = _glob_walk(path, pattern, variants)", _source(GLOBBER_PY))


class BraceExpansionTests(SimpleTestCase):
    def expand(self, pattern):
        return H["_glob_brace_expand"](pattern)

    def test_simple_set(self):
        self.assertEqual(self.expand("*.{js,py,html}"), ["*.js", "*.py", "*.html"])

    def test_several_sets(self):
        self.assertEqual(self.expand("{a,b}{1,2}"), ["a1", "a2", "b1", "b2"])

    def test_nested_set(self):
        self.assertEqual(self.expand("a{b,{c,d}}e"), ["abe", "ace", "ade"])

    def test_empty_option(self):
        self.assertEqual(self.expand("x{,.bak}"), ["x", "x.bak"])

    def test_set_without_comma_is_literal(self):
        self.assertEqual(self.expand("{x}.txt"), ["{x}.txt"])

    def test_unbalanced_is_literal(self):
        self.assertEqual(self.expand("*.{js,py"), ["*.{js,py"])

    def test_braces_inside_a_character_class_are_literal(self):
        self.assertEqual(self.expand("[{,]x"), ["[{,]x"])

    def test_explosion_is_capped(self):
        self.assertLessEqual(len(self.expand("{a,b}" * 12)), H["_GLOB_MAX_PATTERNS"])


class VariantTests(SimpleTestCase):
    def variants(self, pattern):
        return H["_glob_variants"](pattern)

    def test_plain_pattern_is_untouched(self):
        self.assertEqual(self.variants("*.py"), ["*.py"])
        self.assertEqual(self.variants("**/*.py"), ["**/*.py"])

    def test_original_always_comes_first(self):
        self.assertEqual(self.variants("*.{js,py}"), ["*.{js,py}", "*.js", "*.py"])

    def test_empty(self):
        self.assertEqual(self.variants(""), [])
        self.assertEqual(self.variants(None), [])

    def test_comma_and_semicolon_lists(self):
        for pat in ("*.py,*.js", "*.py; *.js", " *.py , *.js "):
            self.assertEqual(self.variants(pat)[1:], ["*.py", "*.js"], pat)

    def test_pipe_list_is_only_its_pieces(self):
        # '|' is forbidden in Windows file names: the list as written never matches.
        self.assertEqual(self.variants("*.py|*.js"), ["*.py", "*.js"])
        self.assertEqual(self.variants("*.py | src/*.{js,ts}"), ["*.py", "src/*.js", "src/*.ts"])

    def test_list_with_one_plain_name(self):
        self.assertEqual(self.variants("test*.py,tests.py")[1:], ["test*.py", "tests.py"])

    def test_literal_comma_name_stays_one_name(self):
        self.assertEqual(self.variants("a,b.txt"), ["a,b.txt"])

    def test_list_of_brace_sets(self):
        self.assertEqual(self.variants("{a,b}.txt,*.md")[1:], ["a.txt", "b.txt", "*.md"])


class PathMatcherTests(SimpleTestCase):
    def setUp(self):
        self.tree = _build_tree()

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def hits(self, pattern):
        match = H["_glob_matcher"](pattern)
        found = []
        for root, _dirs, files in os.walk(self.tree):
            for name in files:
                full = os.path.join(root, name)
                if match(full, self.tree):
                    found.append(os.path.relpath(full, self.tree).replace("\\", "/"))
        return sorted(found)

    def test_no_glob_means_no_filter(self):
        self.assertIsNone(H["_glob_matcher"](""))

    def test_double_star_includes_the_root_folder(self):
        self.assertEqual(self.hits("**/*.py"), ["a.py", "sub/b.py", "sub/deep/e.py"])

    def test_single_star_stays_in_one_folder(self):
        self.assertEqual(self.hits("sub/*.py"), ["sub/b.py"])

    def test_folder_then_double_star(self):
        self.assertEqual(self.hits("sub/**/*.py"), ["sub/b.py", "sub/deep/e.py"])
        self.assertEqual(self.hits("sub/**"), ["sub/b.py", "sub/deep/e.py"])

    def test_backslash_and_dot_slash_are_accepted(self):
        self.assertEqual(self.hits(r"sub\*.py"), ["sub/b.py"])
        self.assertEqual(self.hits("./sub/*.py"), ["sub/b.py"])

    def test_absolute_glob(self):
        absolute = self.tree.replace("\\", "/") + "/sub/deep/*.py"
        self.assertEqual(self.hits(absolute), ["sub/deep/e.py"])

    def test_name_pattern_behaves_as_before(self):
        self.assertEqual(self.hits("*.py"), ["a.py", "sub/b.py", "sub/deep/e.py"])

    def test_brace_set_in_a_folder_glob(self):
        self.assertEqual(self.hits("**/*.{js,txt}"), ["a,b.txt", "c.txt", "d.js"])


class WalkPruningTests(SimpleTestCase):
    """A folder glob lets Grepper skip folders that can never match.

    Measured on this repository (2026-10-18): 'Tlamatini/agent/test_*.py|...'
    walked every release copy under Temp in 34 s; pruned, the SAME 57 matches
    in the same 170 files came back in 0.13 s.
    """

    def prefixes(self, pattern):
        found = H["_glob_dir_prefixes"](pattern)
        return None if found is None else sorted(p.lower() for p in found)

    def test_fixed_leading_folders(self):
        self.assertEqual(self.prefixes("Tlamatini/agent/test_*.py"), ["tlamatini/agent"])
        self.assertEqual(self.prefixes("src/**/*.py"), ["src"])
        self.assertIn("src", self.prefixes("{src,lib}/*.py"))
        self.assertIn("lib", self.prefixes("{src,lib}/*.py"))

    def test_anything_that_can_match_anywhere_disables_pruning(self):
        for pattern in ("*.py", "**/*.py", "*/x.py", "C:/proj/*.py", "/abs/*.py", "*.py|src/*.js"):
            self.assertIsNone(self.prefixes(pattern), pattern)

    def test_globber_reads_a_bare_name_as_the_top_folder_only(self):
        found = H["_glob_dir_prefixes"]
        self.assertEqual(found("*.py", names_anywhere=False), [])
        self.assertEqual([p.lower() for p in found("*.py|src/*.js", names_anywhere=False)], ["src"])
        self.assertIsNone(found("**/*.py", names_anywhere=False))

    def test_dir_may_match(self):
        may = H["_dir_may_match"]
        self.assertTrue(may("src", ["src/app"]))           # on the way down
        self.assertTrue(may("src/app", ["src/app"]))       # the folder itself
        self.assertTrue(may("src/app/deep", ["src/app"]))  # below it
        self.assertFalse(may("docs", ["src/app"]))
        self.assertFalse(may("srcx", ["src"]))             # not a mere text prefix


# ---------------------------------------------------------------------------
# 2. The REAL agent scripts
# ---------------------------------------------------------------------------
class GrepperRealRunTests(SimpleTestCase):
    def setUp(self):
        self.tree = _build_tree()

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def files(self, glob_pat):
        log = _run_agent(GREPPER_PY, {"pattern": "MARK", "path": self.tree, "glob": glob_pat,
                                      "case_insensitive": False, "output_mode": "files",
                                      "max_results": 200})
        head, body = _section(log, "GREPPER")
        return log, head, _names(body)

    def test_brace_set(self):
        log, head, names = self.files("*.{py,txt}")
        self.assertEqual(names, ["a,b.txt", "a.py", "b.py", "c.txt", "e.py"])
        self.assertIn("status: matches", head)
        self.assertIn("glob understood as 3 pattern(s)", log)

    def test_folder_globs(self):
        self.assertEqual(self.files("**/*.py")[2], ["a.py", "b.py", "e.py"])
        self.assertEqual(self.files("sub/*.py")[2], ["b.py"])
        self.assertEqual(self.files("sub/**/*.py")[2], ["b.py", "e.py"])
        self.assertEqual(self.files("sub/deep/*.py")[2], ["e.py"])   # pruned walk
        if os.name == "nt":  # Windows names ignore case, as fnmatch always did
            self.assertEqual(self.files("SUB/*.PY")[2], ["b.py"])

    def test_lists(self):
        self.assertEqual(self.files("*.py,*.js")[2], ["a.py", "b.py", "d.js", "e.py"])
        self.assertEqual(self.files("*.js|c.txt")[2], ["c.txt", "d.js"])

    def test_old_patterns_unchanged(self):
        self.assertEqual(self.files("*.py")[2], ["a.py", "b.py", "e.py"])
        self.assertEqual(self.files("a,b.txt")[2], ["a,b.txt"])
        log, _head, _names_found = self.files("*.py")
        self.assertNotIn("glob understood as", log)


class GlobberRealRunTests(SimpleTestCase):
    def setUp(self):
        self.tree = _build_tree()

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def found(self, pattern):
        log = _run_agent(GLOBBER_PY, {"pattern": pattern, "path": self.tree,
                                      "sort_by": "name", "max_results": 500})
        head, body = _section(log, "GLOBBER")
        return log, head, _names(body)

    def test_recursive_brace_set(self):
        log, head, names = self.found("**/*.{py,js}")
        self.assertEqual(names, ["a.py", "b.py", "d.js", "e.py"])
        self.assertIn("matches: 4", head)
        self.assertIn("pattern understood as 3 glob(s)", log)

    def test_top_level_brace_set(self):
        self.assertEqual(self.found("*.{py,js}")[2], ["a.py", "d.js"])

    def test_semicolon_list(self):
        self.assertEqual(self.found("*.py;*.txt")[2], ["a,b.txt", "a.py", "c.txt"])

    def test_overlapping_patterns_count_each_file_once(self):
        _log, head, names = self.found("**/*.py|sub/*.py")
        self.assertEqual(names, ["a.py", "b.py", "e.py"])
        self.assertIn("matches: 3", head)

    def test_old_patterns_unchanged(self):
        self.assertEqual(self.found("**/*.py")[2], ["a.py", "b.py", "e.py"])
        self.assertEqual(self.found("a,b.txt")[2], ["a,b.txt"])
        self.assertEqual(self.found("*.zzz")[1].count("status: no_matches"), 1)


class GlobberSingleWalkParityTests(SimpleTestCase):
    """_glob_walk (one walk) == the union of glob.glob per pattern (one walk EACH)."""

    def setUp(self):
        self.tree = _build_tree()
        for rel in (os.path.join(".hidden", "h.py"), os.path.join("node_modules", "n.js"),
                    os.path.join("sub", "x.PY")):
            full = os.path.join(self.tree, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write("x\n")

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def by_glob(self, pattern):
        import glob as globmod
        seen = set()
        out = []
        for variant in G["_glob_variants"](pattern):
            hits = globmod.glob(os.path.join(self.tree, variant), recursive="**" in variant,
                                include_hidden=True)
            for hit in hits:
                key = os.path.normcase(os.path.abspath(hit))
                if key not in seen and os.path.isfile(hit):
                    seen.add(key)
                    out.append(hit)
        return sorted(os.path.normcase(p) for p in G["_drop_noise"](out, self.tree, pattern))

    def by_walk(self, pattern):
        found = G["_glob_walk"](self.tree, pattern, G["_glob_variants"](pattern))
        found = [p for p in G["_drop_noise"](found, self.tree, pattern) if os.path.isfile(p)]
        return sorted(os.path.normcase(p) for p in found)

    def test_same_files_as_glob(self):
        for pattern in ("**/*.{py,js}", "*.{py,js}", "sub/{*.py,deep/*.py}", "*.py;*.txt",
                        "**/*.py|sub/*.py", "{sub,.hidden}/*.py", "**/node_modules/*.{js,py}",
                        "sub/**", "**/*.{PY,js}"):
            self.assertEqual(self.by_walk(pattern), self.by_glob(pattern), pattern)

    def test_noise_folders_are_skipped_unless_named(self):
        self.assertFalse(any("node_modules" in p for p in self.by_walk("**/*.{js,py}")))
        self.assertTrue(any("node_modules" in p for p in self.by_walk("**/node_modules/*.{js,py}")))


# ---------------------------------------------------------------------------
# 3. Tlamatini compatibility: the chat's parser and the real wrapped launcher
# ---------------------------------------------------------------------------
class ChatRequestParserTests(SimpleTestCase):
    def value_of(self, request, key):
        from agent.tools import _parse_requested_assignments
        parsed, error = _parse_requested_assignments(request)
        self.assertIsNone(error, error)
        values = {a["requested_key"]: a["value"] for a in parsed["assignments"]}
        return values.get(key)

    def test_quoted_brace_set_survives(self):
        req = "Run Grepper with pattern='MARK', path='C:/proj', glob='*.{py,js,html}'"
        self.assertEqual(self.value_of(req, "glob"), "*.{py,js,html}")

    def test_unquoted_brace_set_survives(self):
        req = "Run Grepper with pattern=MARK, glob=*.{py,js}, path=C:/proj"
        self.assertEqual(self.value_of(req, "glob"), "*.{py,js}")

    def test_quoted_list_survives(self):
        req = "Run Grepper with pattern='MARK', glob='*.py,*.js', path='C:/proj'"
        self.assertEqual(self.value_of(req, "glob"), "*.py,*.js")

    def test_globber_conjunction_style(self):
        req = "Run Globber with pattern='**/*.{js,css}' and path='C:/proj'"
        self.assertEqual(self.value_of(req, "pattern"), "**/*.{js,css}")


class WrappedLauncherEndToEndTests(TestCase):
    """The very tool the chat binds (chat_agent_grepper / chat_agent_globber)."""

    def setUp(self):
        self.tree = _build_tree()
        self.runtime_dirs = []

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)
        # Remove only the run folders THIS test created under _chat_runs_.
        for folder in self.runtime_dirs:
            if os.path.basename(os.path.dirname(folder)) == "_chat_runs_":
                for _ in range(10):
                    shutil.rmtree(folder, ignore_errors=True)
                    if not os.path.exists(folder):
                        break
                    time.sleep(0.3)

    def launch(self, tool_name, request, tag):
        from agent import tools
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME[tool_name]
        payload = json.loads(tools._build_wrapped_chat_agent_tool(spec).func(request))
        if payload.get("runtime_dir"):
            self.runtime_dirs.append(os.path.normpath(payload["runtime_dir"]))
        text = ""
        deadline = time.time() + 60
        log_path = payload.get("log_path") or ""
        while time.time() < deadline:
            if log_path and os.path.isfile(log_path):
                with open(log_path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            text = text or str(payload.get("log_excerpt") or "")
            if f">>>END_SECTION_{tag}" in text:
                break
            time.sleep(0.5)
        self.assertIn(f">>>END_SECTION_{tag}", text, f"wrapped run never finished: {payload}")
        return _section(text, tag)

    def test_chat_agent_grepper_with_brace_set(self):
        tree = self.tree.replace("\\", "/")
        head, body = self.launch(
            "chat_agent_grepper",
            f"Run Grepper with pattern='MARK', path='{tree}', glob='*.{{py,js}}', output_mode='files'",
            "GREPPER")
        self.assertIn("status: matches", head)
        self.assertEqual(_names(body), ["a.py", "b.py", "d.js", "e.py"])

    def test_chat_agent_globber_with_brace_set(self):
        tree = self.tree.replace("\\", "/")
        head, body = self.launch(
            "chat_agent_globber",
            f"Run Globber with pattern='**/*.{{txt,js}}', path='{tree}', sort_by='name'",
            "GLOBBER")
        self.assertIn("matches: 3", head)
        self.assertEqual(_names(body), ["a,b.txt", "c.txt", "d.js"])
