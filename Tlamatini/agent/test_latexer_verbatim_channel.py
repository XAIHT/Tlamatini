"""Regression tests for the LaTeXer BYTE-EXACT (verbatim + base64) channel.

WHY THIS FILE EXISTS (Angela, 2026-08-11)
=========================================
Angela asked Tlamatini for a fancy LaTeX explanation of
``CompleteOpenMPImplementation.cu`` plus its PDF. Tlamatini produced **no .tex
and no PDF at all** — the target directory was empty. The stored answer (DB
``agent_agentmessage`` id 50) and its Exec Report showed the whole story:

    List of LaTeXer Operations   -> action='validate'          (ONE call, ever)
    List of Pythonxer Operations -> 4 x FAILURE
    List of Executer Operations  -> a PowerShell here-string FAILURE

LaTeXer was never asked to typeset anything, because a real LaTeX document
could not survive the trip to it:

1. ``tools._launch_wrapped_chat_agent`` gave its byte-exact "verbatim" channel
   ONLY to ``file_creator`` (``if spec.template_dir == "file_creator"``). Every
   other agent got the generic coercion, which collapses ``\\\\`` -> ``\\``.
   In LaTeX ``\\\\`` is the ROW/LINE BREAK — so every table, matrix and title
   block was silently destroyed before latexer.py ever saw the document.
2. ``_split_assignment_segments`` keeps a MULTI-LINE quoted value open until
   EOF or an ``and|with KEY=`` conjunction. With the very common comma style
   ``input_text='...multi\\nline...', filename='x.pdf'`` the trailing keys were
   glued INTO the document body and came back EMPTY — so the literal text
   ``', filename='x.pdf'`` was typeset into the PDF and the requested output
   filename was silently dropped.
3. LaTeXer had no parser-immune channel at all (File-Creator has
   ``content_b64``, Editor has ``old_string_b64``/``new_string_b64``).

The fix generalises the immunity: every spec DECLARES its literal fields in
``ChatWrappedAgentSpec.verbatim_fields``, ``tools`` honours ``<field>_b64``
first and otherwise re-extracts the raw bytes (recovering any swallowed
trailing assignments), and latexer.py decodes the ``*_b64`` channels.

These tests fail if any of that is reverted.
"""

import ast
import base64
import logging
import os

import yaml
from django.test import SimpleTestCase

from agent import tools
from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_PY = os.path.join(AGENT_DIR, "tools.py")
LATEXER_PY = os.path.join(AGENT_DIR, "agents", "latexer", "latexer.py")
LATEXER_YAML = os.path.join(AGENT_DIR, "agents", "latexer", "config.yaml")

# A minimal document that still contains the thing that used to be destroyed:
# two LaTeX row breaks (``\\``) inside a tabular.
LATEX_TABLE = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\begin{tabular}{ll}\n"
    "a & b \\\\\n"
    "c & d \\\\\n"
    "\\end{tabular}\n"
    "\\end{document}"
)


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _latexer_config():
    return yaml.safe_load(_read(LATEXER_YAML)) or {}


def _lift_function(path, name, namespace=None):
    """Exec ONE top-level function out of a pool-agent script.

    A pool agent cannot be imported directly (module-level side effects such as
    truncating its .log), so we lift just the function under test — the same
    trick ``test_django_port_config.py`` uses for ``manage.py``.
    """
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            module = ast.Module(body=[node], type_ignores=[])
            scope = dict(namespace or {})
            exec(compile(module, path, "exec"), scope)  # noqa: S102
            return scope[name]
    raise AssertionError("%s does not define %s()" % (path, name))


def _lift_constant(path, name):
    """Read ONE module-level literal constant out of a pool-agent script."""
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError("%s does not define %s" % (path, name))


def _apply_byte_exact(spec, request_text, config):
    """Mirror of the byte-exact block in ``_launch_wrapped_chat_agent``.

    Kept deliberately small and identical in ORDER to the production block:
    b64 wins, else verbatim re-extract, then recover swallowed assignments.
    """
    cfg, error, _notes = tools._apply_requested_assignments_to_config(
        dict(config), request_text
    )
    assert not error, error
    recovered_all = []
    for field_name in spec.verbatim_fields:
        b64_value = cfg.get("%s_b64" % field_name)
        if isinstance(b64_value, str) and b64_value.strip():
            continue
        value = tools._extract_verbatim_assignment(request_text, field_name)
        if value is None:
            continue
        value, recovered = tools._recover_swallowed_assignments(value, cfg)
        cfg[field_name] = value
        recovered_all.extend(recovered)
    return cfg, tuple(recovered_all)


class LatexerVerbatimChannelTests(SimpleTestCase):
    """The LaTeX document must reach LaTeXer byte-for-byte."""

    def setUp(self):
        self.spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_latexer"]
        self.config = _latexer_config()

    def test_spec_declares_its_literal_fields(self):
        for field_name in ("input_text", "content", "find_text", "replace_text"):
            self.assertIn(
                field_name, self.spec.verbatim_fields,
                "LaTeXer must declare %r verbatim or the parser mangles it"
                % field_name,
            )

    def test_row_breaks_survive_plain_input_text(self):
        """THE regression: ``\\\\`` must NOT collapse to ``\\``."""
        request = (
            "Run LaTeXer with action='compile', input_text='" + LATEX_TABLE + "'"
        )
        cfg, _ = _apply_byte_exact(self.spec, request, self.config)
        self.assertEqual(
            cfg["input_text"], LATEX_TABLE,
            "LaTeX source was altered in transit — the document is corrupt",
        )
        self.assertEqual(
            cfg["input_text"].count("\\\\"), LATEX_TABLE.count("\\\\"),
            "LaTeX row breaks were lost; every table/matrix would break",
        )

    def test_trailing_keys_are_not_swallowed_into_the_body(self):
        """``', filename='x.pdf'`` must stay an assignment, not become text."""
        request = (
            "Run LaTeXer with action='compile', input_text='" + LATEX_TABLE
            + "', filename='demo.pdf', output_dir='C:\\Temp\\x'"
        )
        cfg, recovered = _apply_byte_exact(self.spec, request, self.config)
        self.assertEqual(cfg["input_text"], LATEX_TABLE)
        self.assertNotIn("filename=", cfg["input_text"])
        self.assertEqual(cfg["filename"], "demo.pdf")
        self.assertEqual(cfg["output_dir"], "C:\\Temp\\x")
        self.assertEqual(set(recovered), {"filename", "output_dir"})

    def test_b64_channel_wins_and_plain_field_is_left_alone(self):
        """When ``input_text_b64`` is supplied the plain field is not touched."""
        encoded = base64.b64encode(LATEX_TABLE.encode("utf-8")).decode("ascii")
        request = (
            "Run LaTeXer with action='compile', input_text_b64='" + encoded + "'"
        )
        cfg, _ = _apply_byte_exact(self.spec, request, self.config)
        self.assertEqual(cfg["input_text_b64"], encoded)
        self.assertEqual(cfg["input_text"], "")

    def test_recovery_never_cuts_genuine_latex(self):
        """A body containing ``', word='`` for an UNKNOWN key stays intact."""
        tricky = (
            "\\documentclass{article}\n\\begin{document}\n"
            "He said 'go', banana='yes' -- still prose.\n"
            "\\end{document}"
        )
        value, recovered = tools._recover_swallowed_assignments(
            tricky, self.config
        )
        self.assertEqual(value, tricky, "real document text must never be cut")
        self.assertEqual(recovered, ())


class LatexerBase64ConfigTests(SimpleTestCase):
    """latexer.py must decode the parser-immune channels, fail-open."""

    def setUp(self):
        self.b64_fields = _lift_constant(LATEXER_PY, "_B64_FIELDS")
        self.decode = _lift_function(
            LATEXER_PY, "_decode_b64_fields",
            {"logging": logging, "base64": base64,
             "_B64_FIELDS": self.b64_fields},
        )

    def test_agent_decodes_every_declared_literal_field(self):
        for field_name in ("input_text", "content", "find_text", "replace_text"):
            self.assertIn(field_name, self.b64_fields)

    def test_config_yaml_exposes_every_b64_key(self):
        config = _latexer_config()
        for key in ("input_text_b64", "content_b64",
                    "find_text_b64", "replace_text_b64"):
            self.assertIn(key, config,
                          "%s must exist in config.yaml or assignments drop it"
                          % key)

    def test_b64_overrides_the_plain_field(self):
        config = {
            "input_text": "WRONG",
            "input_text_b64": base64.b64encode(
                LATEX_TABLE.encode("utf-8")).decode("ascii"),
        }
        self.decode(config)
        self.assertEqual(config["input_text"], LATEX_TABLE)

    def test_malformed_b64_is_fail_open(self):
        config = {"input_text": "KEEP ME", "input_text_b64": "!!!not base64!!!"}
        self.decode(config)
        self.assertEqual(config["input_text"], "KEEP ME")

    def test_absent_b64_changes_nothing(self):
        config = {"input_text": "KEEP ME", "input_text_b64": ""}
        self.decode(config)
        self.assertEqual(config["input_text"], "KEEP ME")


class NeverLoseTheAuthorsWorkTests(SimpleTestCase):
    """The DESTRUCTIVE bisect rung must not fire on an infrastructure blip.

    Angela's OpenMP guide: rung 7 (model) timed out, so rung 8 (bisect)
    quarantined block 10 and a 27-page CLEAN pdf became a 26-page DEGRADED one.
    Losing the author's work is the worst outcome the ladder can produce.
    """

    def setUp(self):
        markers = _lift_constant(LATEXER_PY, "_MODEL_UNREACHABLE_MARKERS")
        self.never_answered = _lift_function(
            LATEXER_PY, "_model_rung_never_answered",
            {"_MODEL_UNREACHABLE_MARKERS": markers},
        )

    def test_timeout_counts_as_never_answered(self):
        trace = [{"rung": "model", "detail": "Ollama call failed: timed out"}]
        self.assertTrue(self.never_answered(trace))

    def test_a_real_model_verdict_does_not_block_bisect(self):
        trace = [{"rung": "model",
                  "detail": "the model's rewrite still does not compile -- discarded"}]
        self.assertFalse(self.never_answered(trace))

    def test_no_model_rung_keeps_the_old_behaviour(self):
        self.assertFalse(self.never_answered([{"rung": "lint", "detail": "x"}]))

    def test_fail_safe_protects_the_document_on_bad_input(self):
        self.assertTrue(self.never_answered(object()))

    def test_ladder_actually_guards_the_bisect_rung(self):
        source = _read(LATEXER_PY)
        self.assertIn(
            'if "bisect" in rungs and _model_rung_never_answered(trace):', source,
            "the destructive bisect rung lost its infrastructure guard - a "
            "network blip can delete the author's content again",
        )


class CleanBuildIsTheEndOfTheJobTests(SimpleTestCase):
    """A clean PDF must tell the model to STOP, not invite more polishing."""

    def test_clean_compile_emits_an_explicit_stop(self):
        source = _read(LATEXER_PY)
        self.assertIn("THE DOCUMENT IS FINISHED", source)
        self.assertIn('outcome["status"] = "compiled"', source)
        stop_at = source.index("THE DOCUMENT IS FINISHED")
        compiled_at = source.index('outcome["status"] = "compiled"')
        self.assertLess(
            compiled_at, stop_at,
            "the STOP banner must be attached to the CLEAN-compile branch",
        )

    def test_model_repair_timeout_is_generous_enough_for_a_real_document(self):
        raw = _read(LATEXER_YAML)
        value = yaml.safe_load(raw).get("repair_model_timeout")
        self.assertGreaterEqual(
            int(value), 600,
            "a 60 KB .tex times out at 180 s, which hands the job to the "
            "destructive bisect rung",
        )


class ByteExactWiringContractTests(SimpleTestCase):
    """The immunity must stay GENERIC — never re-hardcoded to one agent."""

    def test_tools_no_longer_hardcodes_file_creator(self):
        source = _read(TOOLS_PY)
        self.assertNotIn(
            'if spec.template_dir == "file_creator":', source,
            "The byte-exact channel was re-hardcoded to File-Creator; LaTeXer "
            "(and every future literal-text agent) would be corrupted again",
        )
        self.assertIn('getattr(spec, "verbatim_fields", ())', source)

    def test_file_creator_keeps_its_byte_exact_content(self):
        """No regression: the original Java-regex corruption stays fixed."""
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_file_creator"]
        self.assertIn("content", spec.verbatim_fields)
        java = 'Pattern.compile("\\\\.")'
        request = (
            "Run File-Creator with file_path='C:\\Temp\\A.java', "
            "content='" + java + "'"
        )
        value = tools._extract_verbatim_assignment(request, "content")
        self.assertEqual(value, java)
