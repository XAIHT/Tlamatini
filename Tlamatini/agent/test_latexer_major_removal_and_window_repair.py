"""2026-10-08 -- two fixes born from Angela's Podman cheat-sheet run (46.6 minutes).

1. Rung 7 (model) used to ask for the WHOLE document back: a 22,589-character
   .tex cost 3.5 minutes and changed ONE character. A large document whose
   compiler error names a line is now repaired by REGION, with a capped reply.
2. Rung 8 (bisect) "quarantined 1 of 7 blocks" -- but block 7 was the entire
   two-column body, and the one-page result was delivered under the requested
   file name. A degraded build that lost a large share of its body now takes
   "<stem>.DEGRADED.pdf" instead and leaves the requested name untouched.

Pure functions over strings plus temp files: no TeX, no network, no model.

Created by Angela L\u00f3pez Mendoza \u00b7 @angelahack1 \u2014 Tlamatini.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from agent.test_latexer_repair_ladder import LX

FILLER = "Line %d of the author's real content, long enough to matter here."


def _document_lines(total=400, broken_at=None):
    r"""A large document with predictable 1-based line numbers.

    line 1 = \documentclass, line 2 = \begin{document}, lines 3.. = filler
    (``Line N ...``), last line = \end{document}. ``broken_at`` leaves ONE
    filler line with an unclosed brace.
    """
    lines = [r"\documentclass{article}", r"\begin{document}"]
    for number in range(3, total + 3):
        if broken_at == number:
            lines.append(r"Line %d \textbf{broken here" % number)
        else:
            lines.append(FILLER % number)
    lines.append(r"\end{document}")
    return lines


def _join(lines):
    return "\n".join(lines) + "\n"


def _ask(source, diag, answer, config=None, done_reason=None):
    """Run _ollama_repair against a canned model reply.

    Returns (result, trace, request_payload).
    """
    fields = {"response": answer}
    if done_reason:
        fields["done_reason"] = done_reason
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        fields).encode("utf-8")
    trace = []
    with mock.patch.object(LX.urllib.request, "urlopen", return_value=response) as opened:
        result = LX._ollama_repair(
            source, diag, config or {"repair_model": "test-model"}, trace)
    request = opened.call_args[0][0]
    return result, trace, json.loads(request.data.decode("utf-8"))


class ErrorLineTests(unittest.TestCase):
    def test_file_line_error_form(self):
        diag = {"errors": ["Doc.latexer-fixed.tex:196: Missing $ inserted."]}
        self.assertEqual(LX._error_line_from_diag(diag), 196)

    def test_classic_form(self):
        diag = {"errors": [r"Undefined control sequence. l.42 \foo"]}
        self.assertEqual(LX._error_line_from_diag(diag), 42)

    def test_a_package_file_line_says_nothing_about_the_authors_document(self):
        diag = {"errors": ["xcolor.sty:12: Package xcolor Error: nope."]}
        self.assertEqual(LX._error_line_from_diag(diag), 0)

    def test_the_first_error_that_names_a_line_wins(self):
        diag = {"errors": ["Emergency stop.", "a.tex:7: first", "a.tex:9: second"]}
        self.assertEqual(LX._error_line_from_diag(diag), 7)

    def test_nothing_usable_is_zero_and_never_raises(self):
        for diag in ({}, {"errors": []}, None, {"errors": None}, {"errors": [object()]}):
            with self.subTest(diag=repr(diag)):
                self.assertEqual(LX._error_line_from_diag(diag), 0)


class WindowSelectionTests(unittest.TestCase):
    def setUp(self):
        self.big = _join(_document_lines())            # 403 lines, ~25 KB
        self.assertGreater(len(self.big), LX._MODEL_WINDOW_MIN_DOC_CHARS)

    def test_window_surrounds_the_reported_line(self):
        window = LX._model_repair_window(self.big, {"errors": ["a.tex:100: x"]})
        self.assertEqual(window, (70, 130, 100))

    def test_window_is_clamped_at_both_ends(self):
        self.assertEqual(
            LX._model_repair_window(self.big, {"errors": ["a.tex:5: x"]}), (1, 35, 5))
        self.assertEqual(
            LX._model_repair_window(self.big, {"errors": ["a.tex:400: x"]}), (370, 403, 400))

    def test_a_small_document_keeps_the_whole_document_request(self):
        small = _join(_document_lines(total=5))
        self.assertLess(len(small), LX._MODEL_WINDOW_MIN_DOC_CHARS)
        self.assertIsNone(LX._model_repair_window(small, {"errors": ["a.tex:3: x"]}))

    def test_no_line_or_a_line_past_the_end_keeps_the_whole_document_request(self):
        self.assertIsNone(LX._model_repair_window(self.big, {"errors": []}))
        self.assertIsNone(LX._model_repair_window(self.big, {"errors": ["a.tex:9999: x"]}))


class WindowedModelRepairTests(unittest.TestCase):
    def setUp(self):
        self.broken = _join(_document_lines(broken_at=200))
        self.fixed = _join(_document_lines())
        self.diag = {"errors": [
            "doc.latexer-fixed.tex:200: Paragraph ended before \\textbf was complete."]}
        self.region = "".join(self.broken.splitlines(True)[169:230])        # lines 170-230

    def test_large_document_is_repaired_by_region(self):
        answer = "\n".join(_document_lines()[169:230])
        result, trace, payload = _ask(self.broken, self.diag, answer)
        self.assertEqual(result, self.fixed, "the repaired region was not spliced in place")
        self.assertTrue(trace[-1]["applied"])
        self.assertIn("repaired lines 170-230", trace[-1]["detail"])

    def test_only_the_region_travels_and_the_reply_is_capped(self):
        _result, _trace, payload = _ask(
            self.broken, self.diag, "\n".join(_document_lines()[169:230]))
        prompt = payload["prompt"]
        self.assertIn(r"Line 200 \textbf{broken here", prompt)
        self.assertNotIn("Line 10 of the author's real content", prompt,
                         "a far-away line travelled: this was the whole document again")
        self.assertNotIn("COMPLETE LaTeX document", prompt)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"]["num_predict"], LX._MODEL_WINDOW_NUM_PREDICT)
        self.assertIs(payload["think"], False,
                      "a 60-line repair must not be allowed to spend the cap thinking")
        # Told "line 31 of the region", glm-5.3 counted lines aloud until it hit the
        # cap (live, 2026-10-08). The reported line is quoted instead.
        self.assertIn("The compiler stopped at this line", prompt)
        self.assertNotIn("of the region below", prompt)

    def test_a_reply_cut_by_the_output_cap_is_no_answer_and_protects_the_document(self):
        narration = "Let me analyse this region. Line 1: podman run -it --rm alpine. " * 80
        result, trace, _payload = _ask(
            self.broken, self.diag, narration, done_reason="length")
        self.assertEqual(result, self.broken)
        self.assertFalse(trace[-1]["applied"])
        self.assertIn("output cap", trace[-1]["detail"])
        self.assertTrue(LX._model_rung_never_answered(trace),
                        "a truncated monologue must never let bisect cut the document")

    def test_a_server_that_rejects_the_think_field_is_asked_again_without_it(self):
        class _Http400(OSError):
            code = 400

        good = mock.MagicMock()
        good.__enter__.return_value.read.return_value = json.dumps(
            {"response": "\n".join(_document_lines()[169:230])}).encode("utf-8")
        trace = []
        with mock.patch.object(LX.urllib.request, "urlopen",
                               side_effect=[_Http400("does not support thinking"), good]
                               ) as opened:
            result = LX._ollama_repair(self.broken, self.diag, {"repair_model": "m"}, trace)
        self.assertEqual(result, self.fixed)
        sent = [json.loads(call[0][0].data.decode("utf-8"))
                for call in opened.call_args_list]
        self.assertEqual(len(sent), 2)
        self.assertIs(sent[0]["think"], False)
        self.assertNotIn("think", sent[1])

    def test_any_other_failure_is_not_retried(self):
        trace = []
        with mock.patch.object(LX.urllib.request, "urlopen",
                               side_effect=OSError("timed out")) as opened:
            LX._ollama_repair(self.broken, self.diag, {"repair_model": "m"}, trace)
        self.assertEqual(opened.call_count, 1)

    def test_small_document_still_sends_the_whole_document(self):
        small = "\\documentclass{article}\n\\begin{document}\nTiny \\textbf{broken\n" \
                "\\end{document}\n"
        _result, _trace, payload = _ask(
            small, {"errors": ["doc.tex:3: Paragraph ended."]}, small)
        self.assertIn("COMPLETE LaTeX document", payload["prompt"])
        self.assertNotIn("num_predict", payload["options"])

    def test_large_document_without_an_error_line_still_sends_the_whole_document(self):
        _result, _trace, payload = _ask(self.broken, {"errors": []}, self.broken)
        self.assertIn("DOCUMENT:", payload["prompt"])
        self.assertNotIn("num_predict", payload["options"])

    def test_a_region_that_legitimately_holds_the_preamble_is_accepted(self):
        broken = _join(_document_lines(broken_at=3))
        answer = "\n".join(_document_lines()[0:33])           # includes \documentclass
        result, trace, _payload = _ask(
            broken, {"errors": ["doc.tex:3: Paragraph ended."]}, answer)
        self.assertEqual(result, self.fixed)
        self.assertTrue(trace[-1]["applied"])

    def test_bad_replies_are_discarded_and_never_edit_the_document(self):
        cases = {
            "empty": ("", "no response"),
            "truncated": ("x", "truncated"),
            "unchanged": (self.region, "unchanged"),
            "far larger than the region": ("y" * (len(self.region) * 4 + 1000), "far larger"),
        }
        for label, (answer, expected) in cases.items():
            with self.subTest(label):
                result, trace, _payload = _ask(self.broken, self.diag, answer)
                self.assertEqual(result, self.broken)
                self.assertFalse(any(record["applied"] for record in trace))
                # An unusable region reply (the model DID answer) is followed by the
                # whole-document request, so the reason sits somewhere in the trace.
                self.assertTrue(any(expected in record["detail"] for record in trace),
                                "no trace record mentions %r: %r" % (expected, trace))

    def test_a_whole_document_reply_is_not_a_region(self):
        """Tested on the region function itself: the whole-document fallback that
        follows in _ollama_repair would (legitimately) accept an echoed document."""
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"response": self.broken}).encode("utf-8")
        trace = []
        with mock.patch.object(LX.urllib.request, "urlopen", return_value=response):
            result = LX._ollama_repair_window(
                self.broken, (170, 230, 200), self.diag, "http://x", "m", {}, trace)
        self.assertEqual(result, self.broken)
        self.assertFalse(trace[-1]["applied"])
        self.assertIn("whole document", trace[-1]["detail"])

    def test_a_reply_that_makes_the_lint_worse_is_rejected(self):
        # Keeps the original broken line AND adds a stray \end: strictly MORE lint
        # errors than the source had. (A reply with the SAME error count is not
        # "worse" -- the gate is "not worse", exactly as for every other rung.)
        worse = self.region.rstrip("\n") + "\n\\end{itemize}"
        result, trace, _payload = _ask(self.broken, self.diag, worse)
        self.assertEqual(result, self.broken)
        self.assertFalse(any(record["applied"] for record in trace))
        self.assertTrue(any("lint got worse" in record["detail"] for record in trace))

    def test_a_chatty_reply_is_read_from_its_last_fenced_block(self):
        # glm-5.3 reasons out loud even with think off, then fences the region.
        region_fixed = "\n".join(_document_lines()[169:230])
        answer = ("Let me analyse the problem. The compiler stopped at:\n"
                  "```\nLine 200 of the quoted line\n```\n"
                  "Wait, but could the cause be earlier? No.\n"
                  "So the corrected region is:\n```latex\n" + region_fixed + "\n```\n")
        result, trace, _payload = _ask(self.broken, self.diag, answer)
        self.assertEqual(result, self.fixed)
        self.assertTrue(trace[-1]["applied"])

    def test_an_unusable_region_reply_falls_back_to_the_whole_document_request(self):
        """The model answered, but not with a region: the proven request still runs,
        so the region path can never do worse than the behaviour before it."""
        def reply(text):
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {"response": text}).encode("utf-8")
            return response

        trace = []
        with mock.patch.object(LX.urllib.request, "urlopen",
                               side_effect=[reply("x"), reply(self.fixed)]) as opened:
            result = LX._ollama_repair(self.broken, self.diag, {"repair_model": "m"}, trace)
        # The whole-document path has always .strip()-ed the model's reply.
        self.assertEqual(result.strip(), self.fixed.strip())
        sent = [json.loads(call[0][0].data.decode("utf-8"))
                for call in opened.call_args_list]
        self.assertEqual(len(sent), 2, "the whole-document request never ran")
        self.assertNotIn("COMPLETE LaTeX document", sent[0]["prompt"])
        self.assertIn("COMPLETE LaTeX document", sent[1]["prompt"])
        self.assertTrue(trace[-1]["applied"])

    def test_no_answer_at_all_does_not_trigger_a_second_long_request(self):
        for label, kwargs in (("empty", {"answer": ""}),
                              ("capped", {"answer": "monologue " * 50,
                                          "done_reason": "length"})):
            with self.subTest(label):
                response = mock.MagicMock()
                fields = {"response": kwargs["answer"]}
                if "done_reason" in kwargs:
                    fields["done_reason"] = kwargs["done_reason"]
                response.__enter__.return_value.read.return_value = json.dumps(
                    fields).encode("utf-8")
                with mock.patch.object(LX.urllib.request, "urlopen",
                                       return_value=response) as opened:
                    LX._ollama_repair(self.broken, self.diag, {"repair_model": "m"}, [])
                self.assertEqual(opened.call_count, 1)




    def test_an_empty_reply_counts_as_never_answered_so_bisect_cannot_cut_content(self):
        _result, trace, _payload = _ask(self.broken, self.diag, "")
        self.assertTrue(LX._model_rung_never_answered(trace),
                        "an empty reply must protect the document from the destructive rung")

    def test_a_failed_request_counts_as_never_answered_too(self):
        trace = []
        with mock.patch.object(LX.urllib.request, "urlopen",
                               side_effect=OSError("timed out")):
            result = LX._ollama_repair(self.broken, self.diag, {"repair_model": "m"}, trace)
        self.assertEqual(result, self.broken)
        self.assertIn("Ollama call failed", trace[-1]["detail"])
        self.assertTrue(LX._model_rung_never_answered(trace))


class FencedBlockTests(unittest.TestCase):
    def test_the_last_fenced_block_wins(self):
        text = "intro\n```\nfirst\n```\nthen\n```latex\nsecond\nline\n```\nbye"
        self.assertEqual(LX._last_fenced_block(text), "second\nline\n")

    def test_no_fence_or_an_unclosed_fence_means_no_block(self):
        self.assertEqual(LX._last_fenced_block("plain text only"), "")
        self.assertEqual(LX._last_fenced_block("```latex\nnever closed"), "")
        self.assertEqual(LX._last_fenced_block(None), "")


class RemovedShareTests(unittest.TestCase):
    def test_share_is_measured_in_typeset_text_not_in_block_counts(self):
        blocks = ["a" * 10, "b" * 10, "c" * 80]
        self.assertAlmostEqual(LX._removed_body_fraction(blocks, [2]), 0.8)
        self.assertAlmostEqual(LX._removed_body_fraction(blocks, [0, 1]), 0.2)
        self.assertEqual(LX._removed_body_fraction(blocks, []), 0.0)

    def test_comments_and_bad_input_never_invent_a_removal(self):
        self.assertEqual(
            LX._removed_body_fraction(["% only a comment", "real words here"], [0]), 0.0)
        self.assertEqual(LX._removed_body_fraction([], [0]), 0.0)
        self.assertEqual(LX._removed_body_fraction(["abc"], [9]), 0.0)
        self.assertEqual(LX._removed_body_fraction(None, [0]), 0.0)

    def test_only_a_degraded_build_has_a_removed_share(self):
        self.assertEqual(
            LX._removed_body_share({"degraded": False, "removed_fraction": 0.9}), 0.0)
        self.assertAlmostEqual(
            LX._removed_body_share({"degraded": True, "removed_fraction": 0.9}), 0.9)
        self.assertEqual(
            LX._removed_body_share({"degraded": True, "removed_fraction": "junk"}), 0.0)
        self.assertEqual(LX._removed_body_share({"degraded": True}), 0.0)


class DeliveryNameTests(unittest.TestCase):
    def _fake_pdf(self, folder):
        path = os.path.join(folder, "built.pdf")
        with open(path, "wb") as handle:
            handle.write(b"%PDF-1.4 fake")
        return path

    def test_suffix_goes_before_the_extension_and_the_plain_name_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            pdf = self._fake_pdf(tmp)
            config = {"output_dir": out, "filename": "Doc.pdf"}
            final, _note = LX._deliver_pdf(pdf, config, LX.DEGRADED_NAME_SUFFIX)
            self.assertEqual(os.path.basename(final), "Doc.DEGRADED.pdf")
            self.assertTrue(os.path.isfile(final))
            self.assertFalse(os.path.exists(os.path.join(out, "Doc.pdf")),
                             "the requested name must stay free")
            plain, _note = LX._deliver_pdf(pdf, config)
            self.assertEqual(os.path.basename(plain), "Doc.pdf")

    def test_a_name_without_an_extension_still_gets_the_suffix_before_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            final, _note = LX._deliver_pdf(
                self._fake_pdf(tmp), {"output_dir": os.path.join(tmp, "out"),
                                      "filename": "Doc"}, LX.DEGRADED_NAME_SUFFIX)
            self.assertEqual(os.path.basename(final), "Doc.DEGRADED.pdf")


class FinishCompileNamingTests(unittest.TestCase):
    """The decision itself: which file name does the finished build wear?"""

    def _finish(self, tmp, degraded, fraction, ok=False):
        built = os.path.join(tmp, "built.pdf")
        with open(built, "wb") as handle:
            handle.write(b"%PDF-1.4 fake")
        diag = LX._parse_latex_log("")
        diag["pages"] = 1
        result = {
            "ok": ok, "produced": True, "pdf": built, "passes": 1, "steps": [],
            "diag": diag, "log": "", "returncode": 0, "work_dir": tmp,
            "jobname": "built", "bibliography": "none", "ladder": [],
            "degraded": degraded, "quarantined": [7] if degraded else [],
            "removed_fraction": fraction,
        }
        out = os.path.join(tmp, "out")
        config = {"output_dir": out, "filename": "Doc.pdf", "keep_aux": True}
        outcome, notes = {}, []
        LX._finish_compile(result, config, {"distribution": "miktex"}, outcome, notes)
        return outcome, notes, out

    def test_a_mostly_deleted_build_does_not_take_the_requested_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome, notes, out = self._finish(tmp, degraded=True, fraction=0.9)
            self.assertEqual(outcome["status"], "degraded")
            self.assertEqual(outcome["filename"], "Doc.DEGRADED.pdf")
            self.assertFalse(os.path.exists(os.path.join(out, "Doc.pdf")))
            major = [note for note in notes if "MAJOR REMOVAL" in note]
            self.assertEqual(len(major), 1, "the reason must be stated, once")
            self.assertIn("90%", major[0])
            self.assertIn("Doc.DEGRADED.pdf", major[0])
            self.assertIn("Doc.pdf", major[0])

    def test_the_threshold_itself_counts_as_major(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome, _notes, _out = self._finish(
                tmp, degraded=True, fraction=LX.MAJOR_REMOVAL_FRACTION)
            self.assertEqual(outcome["filename"], "Doc.DEGRADED.pdf")

    def test_a_small_removal_keeps_the_requested_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome, notes, _out = self._finish(tmp, degraded=True, fraction=0.10)
            self.assertEqual(outcome["status"], "degraded")
            self.assertEqual(outcome["filename"], "Doc.pdf")
            self.assertFalse(any("MAJOR REMOVAL" in note for note in notes))

    def test_a_clean_build_is_never_renamed_even_with_a_stale_fraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome, _notes, _out = self._finish(tmp, degraded=False, fraction=0.9, ok=True)
            self.assertEqual(outcome["status"], "compiled")
            self.assertEqual(outcome["filename"], "Doc.pdf")


class LadderCarriesTheShareTests(unittest.TestCase):
    def test_bisect_reports_how_much_it_cut_into_the_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            tex = os.path.join(tmp, "doc.tex")
            with open(tex, "w", encoding="utf-8") as handle:
                handle.write("\\documentclass{article}\n\\begin{document}\nx\n"
                             "\\end{document}\n")
            pdf = os.path.join(tmp, "doc.latexer-fixed.pdf")
            calls = []

            def fake_compile(path, config, tools, env):
                calls.append(path)
                produced = len(calls) > 1
                if produced:
                    with open(pdf, "wb") as handle:
                        handle.write(b"%PDF-1.4 fake")
                return {"ok": False, "produced": produced, "passes": 1,
                        "pdf": pdf if produced else "", "steps": [],
                        "diag": {"errors": ["boom"], "warnings": [], "pages": 1,
                                 "output_bytes": 13, "missing_packages": []},
                        "log": "", "returncode": 1, "work_dir": tmp, "jobname": "doc",
                        "bibliography": "none"}

            bisected = {"ok": True, "quarantined": [7], "removed_fraction": 0.9,
                        "source": "\\documentclass{article}\n\\begin{document}\nq\n"
                                  "\\end{document}\n"}
            with mock.patch.object(LX, "_enabled_rungs", return_value=("bisect",)), \
                 mock.patch.object(LX, "_bisect_failing_blocks", return_value=bisected), \
                 mock.patch.object(LX, "_compile", side_effect=fake_compile):
                result = LX._compile_with_ladder(tex, {}, {"engine": "pdflatex"}, {})
            self.assertTrue(result["degraded"])
            self.assertAlmostEqual(result["removed_fraction"], 0.9)


if __name__ == "__main__":
    unittest.main()
