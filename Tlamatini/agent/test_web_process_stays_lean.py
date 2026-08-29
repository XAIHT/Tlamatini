"""The frozen Django process must NOT drag in the transformers/torch ML stack.

Angela reported a "bug" starting in FROZEN mode (2026-08-29, v1.50.3): the
console opened with TWELVE identical
``UserWarning: Unable to retrieve source for @torch.jit._overload function:
<function upsample at 0x...>`` lines, plus a LangChain deprecation. The first
instinct -- muting them -- was WRONG. Angela was right: fix the root.

The root, found by booting the real app with an import tracer:

    agent/mcp_agent.py
      -> langchain_ollama
        -> langchain_core.language_models.base:44
             `from transformers import GPT2TokenizerFast`
          -> transformers/modeling_gguf_pytorch_utils.py:34
               `import torch`

Tlamatini uses Ollama / Anthropic models that count their own tokens; nothing
in ``agent/**`` imports transformers, sentence_transformers or HuggingFace
embeddings. That import chain was loading **248 transformers + 663 torch**
submodules into the web process for a GPT-2 token-counter FALLBACK it never
calls -- and torch's ``.py`` sources live inside the PyInstaller PYZ, so
``inspect.getsource()`` fails and torch warns once per overload. Excluding
transformers measured **0 + 0 submodules and 3.62 s instead of 9.47 s**.

The second warning was our own code: three ``agent/**`` modules still imported
from the deprecated ``langchain.tools`` shim instead of ``langchain_core.tools``.

⚠️ INTERPRETER BOUNDARY (Angela, 2026-08-29): a user may have NO Python of
their own. Tlamatini ships two interpreters and they are NOT interchangeable:

  * the FROZEN process (``_internal``) -- runs Django/RAG; this is what
    ``--exclude-module=transformers`` applies to;
  * the CARRIED Python (``<install>/python``) -- runs the pool agents. Talker
    imports torch + snac THERE, so torch must stay in the carried tree. It
    already has ``transformers`` pruned (``_PRUNE_PKG_STEMS``) and Talker
    works, which is live proof the dependency is unused.

These tests pin the root fixes so nobody re-introduces the ML stack -- or
"solves" it again by muting.
"""

import ast
import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PROJECT_ROOT.parent
_AGENT_DIR = _PROJECT_ROOT / 'agent'
_BUILD_PY = _REPO_ROOT / 'build.py'
_MANAGE_PY = _PROJECT_ROOT / 'manage.py'
_SETTINGS_PY = _PROJECT_ROOT / 'tlamatini' / 'settings.py'

# Pool agents run under the CARRIED Python, never inside the frozen web
# process, so their imports are outside this contract.
_POOL_AGENTS_DIR = _AGENT_DIR / 'agents'


def _read(path):
    return path.read_text(encoding='utf-8', errors='replace')


def _web_process_sources():
    """Every agent/** module that can be imported by the FROZEN web process.

    Excluded on purpose:
      * ``agent/agents/**`` -- pool agents, which run under the CARRIED Python
        (Talker legitimately imports torch + snac there);
      * ``test_*.py`` -- test modules are never imported by the running server,
        and they must stay free to import torch in order to CHECK the carried
        Python's dependencies (e.g. test_talker_agent.py probes torch + snac).
    """
    for path in _AGENT_DIR.rglob('*.py'):
        if _POOL_AGENTS_DIR in path.parents:
            continue
        if '__pycache__' in path.parts:
            continue
        if path.name.startswith('test_') or path.name == 'tests.py':
            continue
        yield path


class DeprecatedLangChainImportTests(unittest.TestCase):
    """Root fix #2 -- the LangChainDeprecationWarning was OUR import."""

    def test_no_module_imports_the_deprecated_langchain_tools_shim(self):
        offenders = []
        for path in _AGENT_DIR.rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            for number, line in enumerate(_read(path).splitlines(), start=1):
                if re.search(r'^\s*from\s+langchain\.tools\s+import\b', line):
                    offenders.append("%s:%d" % (path.relative_to(_REPO_ROOT), number))
        self.assertEqual(
            [], offenders,
            "these import the DEPRECATED langchain.tools shim (which prints a "
            "LangChainDeprecationWarning on every boot) -- import from "
            "langchain_core.tools instead: " + ", ".join(offenders),
        )

    def test_the_canonical_module_is_actually_importable(self):
        """Guard the replacement, not just the removal."""
        from langchain_core.tools import StructuredTool, Tool, tool
        for symbol in (Tool, tool, StructuredTool):
            self.assertIsNotNone(symbol)


class NoMlStackInTheWebProcessTests(unittest.TestCase):
    """Root fix #1 -- transformers dragged all of torch into Django."""

    def test_no_web_process_module_imports_transformers(self):
        offenders = []
        for path in _web_process_sources():
            for number, line in enumerate(_read(path).splitlines(), start=1):
                if re.search(r'^\s*(import\s+transformers|from\s+transformers\b)', line):
                    offenders.append("%s:%d" % (path.relative_to(_REPO_ROOT), number))
                if re.search(r'^\s*(import|from)\s+sentence_transformers\b', line):
                    offenders.append("%s:%d" % (path.relative_to(_REPO_ROOT), number))
        self.assertEqual(
            [], offenders,
            "the frozen web process must stay free of the transformers/torch "
            "stack (build.py excludes it): " + ", ".join(offenders),
        )

    def test_no_web_process_module_imports_torch(self):
        offenders = []
        for path in _web_process_sources():
            for number, line in enumerate(_read(path).splitlines(), start=1):
                if re.search(r'^\s*(import\s+torch\b|from\s+torch\b)', line):
                    offenders.append("%s:%d" % (path.relative_to(_REPO_ROOT), number))
        self.assertEqual(
            [], offenders,
            "torch belongs to the CARRIED Python (Talker/snac), never the "
            "frozen web process: " + ", ".join(offenders),
        )

    def test_build_excludes_transformers_from_the_frozen_process(self):
        self.assertIn(
            "'--exclude-module=transformers'", _read(_BUILD_PY),
            "build.py must pass --exclude-module=transformers, or the frozen "
            "Django process re-imports 248 transformers + 663 torch modules "
            "and the twelve torch JIT warnings come back",
        )

    def test_build_still_keeps_torch_for_the_carried_python(self):
        """Talker needs torch under the CARRIED interpreter -- do not prune it."""
        build_source = _read(_BUILD_PY)
        prune_block = build_source.split('_PRUNE_PKG_STEMS', 1)[1][:400]
        self.assertIn('"transformers"', prune_block)
        self.assertNotIn('"torch",', prune_block)
        self.assertNotIn("'torch',", prune_block)

    def test_torch_is_never_excluded_from_the_build(self):
        self.assertNotIn(
            "'--exclude-module=torch'", _read(_BUILD_PY),
            "excluding torch outright would break the Talker pool agent",
        )


class UpstreamContractTests(unittest.TestCase):
    """Our exclusion is only safe because langchain_core GUARDS that import.

    If a langchain_core upgrade ever makes ``from transformers import
    GPT2TokenizerFast`` a hard import, ``--exclude-module=transformers`` would
    crash the frozen app on a user machine that has no Python to fall back on.
    Fail loudly HERE instead of in the field.
    """

    def test_langchain_core_still_guards_its_transformers_import(self):
        from langchain_core.language_models import base

        source_path = Path(base.__file__)
        tree = ast.parse(_read(source_path))
        guarded = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            imports_transformers = any(
                isinstance(child, ast.ImportFrom) and (child.module or '').split('.')[0] == 'transformers'
                for child in ast.walk(node)
            )
            handles_import_error = any(
                isinstance(handler.type, ast.Name) and handler.type.id == 'ImportError'
                for handler in node.handlers
            )
            if imports_transformers and handles_import_error:
                guarded = True
                break
        self.assertTrue(
            guarded,
            "langchain_core.language_models.base no longer wraps its "
            "transformers import in try/except ImportError -- "
            "--exclude-module=transformers in build.py is NO LONGER SAFE. "
            "Re-verify before shipping (file: %s)" % source_path,
        )

    def test_transformers_is_not_a_declared_requirement(self):
        requirements = _read(_REPO_ROOT / 'requirements.txt')
        for line in requirements.splitlines():
            stem = line.strip().split('=')[0].split('>')[0].split('<')[0].strip()
            self.assertNotEqual(
                'transformers', stem.lower(),
                "transformers is not used by Tlamatini; adding it to "
                "requirements.txt re-imports torch into the web process",
            )


class NoWarningMutingTests(unittest.TestCase):
    """Angela, 2026-08-29: root-fix it, do not mute it.

    The first attempt at this bug installed ``warnings.filterwarnings`` filters
    in manage.py / settings.py. That hid the symptom and left 911 useless
    modules loading on every boot. Muting is not a fix.
    """

    def test_startup_does_not_install_warning_filters(self):
        for path in (_MANAGE_PY, _SETTINGS_PY):
            source = _read(path)
            self.assertNotIn(
                'filterwarnings', source,
                "%s must not mute startup warnings -- fix the cause instead "
                "(see the transformers exclusion in build.py)" % path.name,
            )
            self.assertNotIn('simplefilter', source, "%s must not mute warnings" % path.name)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
