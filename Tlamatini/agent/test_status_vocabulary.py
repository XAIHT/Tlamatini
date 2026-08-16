"""THE GUARD that ties the status vocabulary to the agents that emit it.

WHY THIS FILE EXISTS
====================

``agent/agent_verdict.py`` decides the colour of every Exec-Report row from the
``status:`` an agent writes into its own ``INI_SECTION`` self-report.  That made
``status:`` load-bearing -- but nothing on earth checked that an agent's status
was a word the engine had ever heard of.

The failure mode was perfectly silent.  An INVENTED token and an APPROVED token
produced the identical outcome: neither matched a rule, both fell through to
R8's anonymous default, and both came out GREEN.  There was no error, no
warning, no log line, no test.  So they accumulated -- a static sweep of the
pool on 2026-08-16 lifted **22** literal status tokens that no rule claimed,
including two that were actively lying to the user:

    talker      status: tokens_only   -- tokens saved, NOTHING audible, GREEN
    kuberneter  status: {exit_code}   -- a NUMBER where a verdict belongs, so a
                                         failed kubectl also rendered GREEN

This module closes that hole permanently.  It walks every pool agent's source,
lifts every status token it can emit WITHOUT RUNNING IT, and requires each one
to be a declared member of ``agent_verdict.KNOWN_STATUSES``.  From now on an
invented status fails LOUDLY, here, before it can ever mis-colour a row.

DESIGN NOTES
------------
* STATIC, not dynamic.  Importing 80-odd pool agents would execute their module
  preambles (PID files, console-handler tweaks, third-party imports).  ``ast``
  reads them as text and cannot have side effects.
* CONSERVATIVE extraction.  Only unambiguous literals count, and a token must
  look like a token (``^[a-z][a-z0-9_]*$``).  A guard that cries wolf gets
  disabled, and a disabled guard is worse than none.
* The extractor is a PUBLIC function, so future tooling (a lint skill, a build
  step, the Spanish tree) can reuse the same definition of "a status an agent
  can emit" rather than growing a second, drifting copy.

Run:  python Tlamatini/manage.py test agent.test_status_vocabulary
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase

from agent import agent_verdict as av

_AGENT_DIR = Path(__file__).resolve().parent
_AGENTS_ROOT = _AGENT_DIR / "agents"

#: Directories that are never part of the shipped template set.
_SKIP_DIRS = {"pools", "__pycache__", ".git", "node_modules"}

#: A status token is a lowercase identifier.  Anything else in a ``status: ...``
#: position is prose (a docstring listing alternatives, an f-string fragment)
#: and is deliberately ignored -- see the CONSERVATIVE note above.
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Expression names that are an EXIT CODE, never a verdict.  An agent that
#: interpolates one of these straight into ``status:`` publishes a number where
#: the engine expects a word, so every rule misses and the row defaults GREEN --
#: which is exactly how a failing ``kubectl`` used to report success.
_EXIT_CODE_NAMES = frozenset({
    "exit_code", "exitcode", "returncode", "return_code", "rc",
    "status_code", "statuscode", "code", "ret", "retcode",
})


# =====================================================================
# The extractor  --  PUBLIC, reusable, side-effect free
# =====================================================================

def _string_literal(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_status_tokens(source: str, filename: str = "<agent>") -> dict:
    """Lift every LITERAL status token ``source`` can emit.

    Returns ``{token: sorted[context]}`` where context names how it was found:
    ``assign`` (``status = "x"``), ``subscript`` (``d["status"] = "x"``),
    ``dict`` (``{"status": "x"}``), ``kwarg`` (``f(status="x")``) or ``emit``
    (a literal ``"status: x"`` line inside an INI_SECTION block).

    Never raises: an unparsable agent yields ``{}`` rather than breaking the
    sweep, because one bad file must not blind the guard to the other 89.
    """
    found: dict = {}

    def add(token, context):
        token = (token or "").strip()
        if not _TOKEN_RE.match(token):
            return
        found.setdefault(token, set()).add(context)

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _string_literal(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("status", "_status"):
                    add(value, "assign")
                elif (isinstance(target, ast.Subscript)
                        and _string_literal(target.slice) == "status"):
                    add(value, "subscript")
        elif isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                if _string_literal(key) == "status":
                    literal = _string_literal(val)
                    if literal is not None:
                        add(literal, "dict")
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "status":
                    literal = _string_literal(keyword.value)
                    if literal is not None:
                        add(literal, "kwarg")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            # A literal "status: <token>" line, as written into an INI_SECTION.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("status: "):
                    add(stripped[len("status: "):], "emit")

    return {token: sorted(contexts) for token, contexts in found.items()}


def extract_interpolated_status_expressions(source: str,
                                            filename: str = "<agent>") -> list:
    """Find ``status:`` lines whose value is INTERPOLATED, with the expression.

    Returns ``[(line_no, expression_source)]``.  Python merges implicitly
    concatenated f-strings into ONE ``JoinedStr`` at parse time, so a whole
    ``INI_SECTION`` emission arrives as a single node and the value that follows
    a ``"...status: "`` constant part is simply the next element of ``values``.
    """
    out: list = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return out

    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        parts = list(node.values)
        for index, part in enumerate(parts[:-1]):
            text = _string_literal(part)
            if text is None or not text.endswith("status: "):
                continue
            nxt = parts[index + 1]
            if isinstance(nxt, ast.FormattedValue):
                try:
                    expression = ast.unparse(nxt.value)
                except Exception:
                    expression = "<unparsable>"
                out.append((getattr(node, "lineno", 0), expression))
    return out


def iter_agent_sources():
    """Yield ``(agent_name, path, source_text)`` for every pool-agent module."""
    if not _AGENTS_ROOT.is_dir():                       # frozen / partial tree
        return
    for path in sorted(_AGENTS_ROOT.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield path.parent.name, path, source


# =====================================================================
# 1. The vocabulary itself must be coherent
# =====================================================================

class StatusVocabularyShapeTests(SimpleTestCase):
    """The five sets are a PARTITION, not five overlapping opinions."""

    SETS = (
        ("DIAGNOSTIC_COMPLETED_STATUSES", av.DIAGNOSTIC_COMPLETED_STATUSES),
        ("WORK_COMPLETED_STATUSES", av.WORK_COMPLETED_STATUSES),
        ("WORK_DEGRADED_STATUSES", av.WORK_DEGRADED_STATUSES),
        ("WORK_NOT_DONE_STATUSES", av.WORK_NOT_DONE_STATUSES),
        ("AGENT_ERROR_STATUSES", av.AGENT_ERROR_STATUSES),
    )

    def test_the_five_sets_are_pairwise_disjoint(self):
        """One token, one verdict.

        Overlap would make ``_classify_status``'s ORDER a silent tie-break, so
        moving a rule for readability could flip a row's colour.  Disjointness
        is what keeps that ordering a purely cosmetic choice.
        """
        for i, (name_a, set_a) in enumerate(self.SETS):
            for name_b, set_b in self.SETS[i + 1:]:
                overlap = sorted(set_a & set_b)
                self.assertEqual(
                    overlap, [],
                    f"{name_a} and {name_b} both claim {overlap}. A token must "
                    f"belong to exactly ONE verdict class.")

    def test_known_statuses_is_exactly_the_union(self):
        union = set()
        for _name, members in self.SETS:
            union |= set(members)
        self.assertEqual(set(av.KNOWN_STATUSES), union,
                         "KNOWN_STATUSES must stay the union of the five sets; "
                         "it is the guard's oracle.")

    def test_every_token_is_a_well_formed_token(self):
        malformed = sorted(t for t in av.KNOWN_STATUSES if not _TOKEN_RE.match(t))
        self.assertEqual(malformed, [],
                         f"status tokens must be lowercase identifiers: {malformed}")

    def test_every_token_classifies_to_a_named_class(self):
        for token in sorted(av.KNOWN_STATUSES):
            self.assertNotEqual(
                av.status_class(token), av.CLASS_UNKNOWN,
                f"{token!r} is in KNOWN_STATUSES but classifies as UNKNOWN -- "
                f"_classify_status is missing a branch.")

    def test_status_class_is_total_and_never_raises(self):
        for value in ("", "   ", None, "not_a_real_status", "ERROR", " Refused "):
            self.assertIsInstance(av.status_class(value), str)
        self.assertEqual(av.status_class("not_a_real_status"), av.CLASS_UNKNOWN)
        # Case and padding must not matter -- agents write free text.
        self.assertEqual(av.status_class(" Refused "), av.CLASS_WORK_NOT_DONE)


# =====================================================================
# 2. THE GUARD -- the agents may not invent statuses
# =====================================================================

class AgentStatusVocabularyGuardTests(SimpleTestCase):
    """Statically tie every agent's ``status:`` back to the rule table."""

    def test_no_agent_emits_a_status_no_rule_knows(self):
        """The whole point of this file.

        If this fails, do NOT widen the regex and do NOT delete the token from
        the agent.  Decide what the token MEANS and put it in the one set whose
        verdict it deserves (``agent_verdict.py``):

            it ran and is reporting a finding  -> DIAGNOSTIC_COMPLETED_STATUSES
            it did the job, deliverable intact -> WORK_COMPLETED_STATUSES
            it delivered something compromised -> WORK_DEGRADED_STATUSES
            the work simply did not happen     -> WORK_NOT_DONE_STATUSES
            the agent itself malfunctioned     -> AGENT_ERROR_STATUSES
        """
        offenders = {}
        for agent_name, path, source in iter_agent_sources():
            for token in extract_status_tokens(source, str(path)):
                if token not in av.KNOWN_STATUSES:
                    offenders.setdefault(token, set()).add(agent_name)

        if offenders:
            lines = [f"  {token:<28} emitted by: {', '.join(sorted(agents))}"
                     for token, agents in sorted(offenders.items())]
            self.fail(
                f"{len(offenders)} status token(s) that NO verdict rule knows.\n"
                f"Each one silently defaults to GREEN in the Exec Report:\n"
                + "\n".join(lines)
                + "\n\nClassify each in agent_verdict.py (see this test's "
                  "docstring for which set).")

    def test_no_agent_publishes_an_exit_code_as_its_status(self):
        """``status:`` is a WORD, never a number.

        Kuberneter used to emit ``status: {exit_code}``.  ``"1"`` matches no
        vocabulary, so every rule missed it and the row defaulted GREEN -- a
        failed ``kubectl`` reported as a success.  The numeric belongs under its
        own key (``returncode:``), with ``status:`` carrying a real verdict.
        """
        offenders = []
        for agent_name, path, source in iter_agent_sources():
            for line_no, expression in extract_interpolated_status_expressions(
                    source, str(path)):
                root = expression.split(".")[0].split("[")[0].strip()
                if root.lower() in _EXIT_CODE_NAMES:
                    offenders.append(f"  {agent_name} ({path.name}:{line_no}): "
                                     f"status: {{{expression}}}")
        self.assertEqual(
            offenders, [],
            "an exit code was published as a status:\n" + "\n".join(offenders)
            + "\n\nEmit the number as `returncode:` and give `status:` a real "
              "token from agent_verdict.KNOWN_STATUSES.")

    def test_the_guard_actually_catches_a_planted_token(self):
        """Prove the guard is not vacuously green.

        A guard nobody has seen FAIL is indistinguishable from a guard that
        cannot fail, so plant every extraction shape and assert each is seen.
        """
        planted = (
            'status = "totally_invented"\n'
            'result["status"] = "second_invention"\n'
            'payload = {"status": "third_invention"}\n'
            'emit(status="fourth_invention")\n'
            'logging.info("INI_SECTION_X<<<\\nstatus: fifth_invention\\n")\n'
        )
        tokens = extract_status_tokens(planted, "<planted>")
        for expected, context in (("totally_invented", "assign"),
                                  ("second_invention", "subscript"),
                                  ("third_invention", "dict"),
                                  ("fourth_invention", "kwarg"),
                                  ("fifth_invention", "emit")):
            self.assertIn(expected, tokens, f"the {context} shape was missed")
            self.assertIn(context, tokens[expected])
            self.assertNotIn(expected, av.KNOWN_STATUSES)

    def test_the_exit_code_lint_actually_catches_a_planted_case(self):
        planted = 'logging.info(f"INI_SECTION_X<<<\\nstatus: {exit_code}\\n")\n'
        found = extract_interpolated_status_expressions(planted, "<planted>")
        self.assertTrue(any(expr == "exit_code" for _line, expr in found),
                        f"the exit-code lint missed a planted case: {found}")

    def test_the_extractor_ignores_prose(self):
        """Docstrings that merely LIST statuses must not enter the vocabulary."""
        prose = (
            'def f():\n'
            '    """Reports status: refused | not_found, or an error.\n'
            '\n'
            '    status: {computed}\n'
            '    """\n'
            '    return 1\n'
        )
        tokens = extract_status_tokens(prose, "<prose>")
        self.assertNotIn("{computed}", tokens)
        for token in tokens:
            self.assertTrue(_TOKEN_RE.match(token), token)

    def test_the_sweep_actually_reaches_the_agents(self):
        """A guard that scanned zero files would pass forever."""
        agents = {name for name, _path, _src in iter_agent_sources()}
        self.assertGreater(len(agents), 50,
                           f"only {len(agents)} agent module(s) scanned -- the "
                           f"sweep is not reaching agent/agents/")
        tokens = set()
        for _name, path, source in iter_agent_sources():
            tokens |= set(extract_status_tokens(source, str(path)))
        self.assertGreater(len(tokens), 20,
                           f"only {len(tokens)} status token(s) extracted -- the "
                           f"extractor has stopped seeing real emissions")


# =====================================================================
# 3. The decisions this review made, pinned as behaviour
# =====================================================================

class ReviewedStatusDecisionsTests(SimpleTestCase):
    """The 2026-08-16 review's four additions and the degraded ruling."""

    def test_the_four_reviewed_tokens_are_work_not_done(self):
        for token in ("unreachable", "forward_failed", "rejected", "ignored"):
            self.assertIn(token, av.WORK_NOT_DONE_STATUSES)
            self.assertEqual(av.status_class(token), av.CLASS_WORK_NOT_DONE, token)

    def test_degraded_statuses_are_not_clean_successes(self):
        for token in ("tokens_only", "operator_required", "degraded",
                      "compiled_with_errors", "assert_failed"):
            self.assertIn(token, av.WORK_DEGRADED_STATUSES)
            self.assertEqual(av.status_class(token), av.CLASS_DEGRADED, token)

    def test_fault_tolerant_paths_that_still_deliver_stay_green(self):
        """The boundary is the DELIVERABLE, not the path taken to it."""
        for token in ("partial_interpreter_1_only", "partial_interpreter_2_only",
                      "merge_fallback_concat"):
            self.assertEqual(av.status_class(token), av.CLASS_COMPLETED, token)


class DegradedVerdictEndToEndTests(SimpleTestCase):
    """The live false-green, reproduced byte-faithfully and then killed."""

    TALKER_SECTION = (
        "INI_SECTION_TALKER<<<\n"
        "output_path: C:\\Users\\angel\\Music\\TlamatiniTalker\\talker_1.wav\n"
        "output_dir: C:\\Users\\angel\\Music\\TlamatiniTalker\n"
        "filename: talker_1.wav\n"
        "model: Orpheus-3b-FT\n"
        "language: en\n"
        "voice: tara\n"
        "gender: female\n"
        "emotion: \n"
        "sample_rate: 24000\n"
        "audio_seconds: 0\n"
        "char_count: 42\n"
        "played: false\n"
        "status: tokens_only\n"
        "\n"
        "Saved 512 audio tokens; snac/torch missing so nothing was rendered.\n"
        ">>>END_SECTION_TALKER"
    )

    def test_talker_tokens_only_is_now_red(self):
        """Talker's section carries NO ``success:`` key at all.

        That is why ``tokens_only`` used to reach R8 and render GREEN: there was
        no boolean for R5 to read and no rule that knew the word.  Angela was
        told Tlamatini had spoken while nothing was ever audible.
        """
        section = av.parse_section(self.TALKER_SECTION)
        self.assertIsNotNone(section)
        self.assertIsNone(section.get("success"),
                          "fixture drift: the point of this test is that Talker "
                          "publishes no success flag")

        verdict = av.evaluate(section, exit_code=0)
        self.assertFalse(verdict.ok, "tokens_only must NOT be a clean success")
        self.assertEqual(verdict.rule, "R3b.work_degraded")
        self.assertEqual(verdict.source, "agent")
        self.assertIn("tokens_only", verdict.evidence)

    def test_the_wrapped_payload_reports_the_degraded_verdict(self):
        """End to end, through the real integration point tools.py calls."""
        payload = {"status": "completed", "exit_code": 0,
                   "log_excerpt": self.TALKER_SECTION}
        av.reconcile_payload_verdict(payload)
        self.assertEqual(payload["verdict"], "failed")
        self.assertEqual(payload["verdict_rule"], "R3b.work_degraded")
        self.assertEqual(payload["process_status"], "completed",
                         "the process view must survive alongside the agent's")

    def test_a_latexer_degraded_build_is_red(self):
        section = av.parse_section(
            "INI_SECTION_LATEXER<<<\n"
            "action: compile\n"
            "output_path: C:\\Users\\angel\\Documents\\TlamatiniLaTeX\\a.pdf\n"
            "page_count: 26\n"
            "errors: 0\n"
            "success: True\n"
            "status: degraded\n"
            "\n"
            "Quarantined block 10 (lines 812-887).\n"
            ">>>END_SECTION_LATEXER"
        )
        verdict = av.evaluate(section, exit_code=0)
        self.assertFalse(verdict.ok,
                         "a build that only succeeded by DELETING the author's "
                         "content must never be reported as a clean success")
        self.assertEqual(verdict.rule, "R3b.work_degraded")

    def test_an_image_interpreter_partial_stays_green(self):
        section = av.parse_section(
            "INI_SECTION_IMAGE_INTERPRETER<<<\n"
            "file_path: C:\\Development\\Tlamatini\\image.png\n"
            "status: partial_interpreter_1_only\n"
            "\n"
            "Full report from the surviving vision model.\n"
            ">>>END_SECTION_IMAGE_INTERPRETER"
        )
        verdict = av.evaluate(section, exit_code=0)
        self.assertTrue(verdict.ok,
                        "the documented fail-safe still handed back a complete "
                        "interpretation -- that is a success, not a defect")
        self.assertEqual(verdict.rule, "R7b.work_completed")


class RuleOrderNeutralityTests(SimpleTestCase):
    """The two new SUCCESS-side rules must not have moved any existing verdict."""

    def _section(self, *lines):
        return av.parse_section("INI_SECTION_X<<<\n" + "\n".join(lines)
                                + "\n\nbody\n>>>END_SECTION_X")

    def test_r7b_never_overrules_an_explicit_failure_flag(self):
        verdict = av.evaluate(self._section("status: sent", "success: False"), 0)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.rule, "R5.agent_flag_false")

    def test_r7b_never_overrules_a_nonzero_error_count(self):
        verdict = av.evaluate(self._section("status: created", "errors: 3"), 0)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.rule, "R6.error_count")

    def test_r7b_never_overrules_a_nonzero_exit_code(self):
        verdict = av.evaluate(self._section("status: compiled"), 1)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.rule, "R7.exit_nonzero")

    def test_r3b_outranks_the_diagnostic_and_flag_rules(self):
        """A degraded build reporting ``errors: 0`` is still degraded."""
        verdict = av.evaluate(
            self._section("status: compiled_with_errors", "errors: 0",
                          "success: True"), 0)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.rule, "R3b.work_degraded")

    def test_an_unknown_status_still_fails_open_but_is_named(self):
        """Fail-open is the contract; SILENCE was the bug.

        The verdict deliberately does not change -- an unrecognised word is not
        evidence of failure -- and ``source`` stays ``default`` so every
        downstream consumer keeps its exact previous fall-through.  What is new
        is that the token is NAMED, so it is greppable in tlamatini.log.
        """
        verdict = av.evaluate(self._section("status: freshly_invented"), 0)
        self.assertTrue(verdict.ok, "fail-open must survive")
        self.assertEqual(verdict.rule, "R8b.unknown_status")
        self.assertEqual(verdict.source, "default",
                         "an unrecognised token is NOT a verdict the engine can "
                         "claim to have understood")
        self.assertIn("freshly_invented", verdict.reason)

    def test_a_report_with_no_status_still_reaches_r8(self):
        verdict = av.evaluate(self._section("action: compile", "pages: 3"), 0)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.rule, "R8.default")


class SingleVocabularyContractTests(SimpleTestCase):
    """One definition, imported -- never re-inlined."""

    def test_mcp_agent_aliases_rather_than_copies(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor as Executor
        self.assertIs(Executor._DIAGNOSTIC_COMPLETED_STATUSES,
                      av.DIAGNOSTIC_COMPLETED_STATUSES,
                      "mcp_agent must ALIAS the shared vocabulary; a second copy "
                      "drifts and silently mis-colours rows")

    def test_agent_verdict_imports_nothing_from_agent(self):
        """It is imported by BOTH tools.py and mcp_agent.py -- a cycle would be
        fatal, and stdlib-only is what keeps frozen and source identical."""
        source = (_AGENT_DIR / "agent_verdict.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("agent"):
                self.fail(f"agent_verdict imports from agent.*: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.startswith("agent."),
                                     f"agent_verdict imports {alias.name}")
