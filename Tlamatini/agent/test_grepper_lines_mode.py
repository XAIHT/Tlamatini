# ══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
"""HARD real-scenario tests for Grepper's ``output_mode: "lines"`` VERBATIM READ.

This mode is the raw-read capability the agent pool did not have: File-Interpreter
interprets a file through an LLM, File-Extractor unpacks binary containers, and the
three search modes all require a regex — so lifting the exact bytes of a region (to
author an Editor ``old_string``) used to mean leaving Tlamatini for a shell.

⚠️ THE CONTRACT THESE TESTS EXIST TO DEFEND — the agent log is NOT a byte-exact
channel. ``logging``'s FileHandler opens its file in text mode, so on Windows every
``\\n`` it writes becomes ``\\r\\n`` and a CRLF source line arrives as CR-CR-LF.
Measured before the fix: ``b"alpha\\r\\nbeta\\r\\n"`` came back ``b"alpha\\r\\r\\nbeta\\r\\r\\n"``.
An Editor ``old_string`` built from that carries a stray ``\\r`` per line and fails to
match — silent, plausible and WRONG. The exact bytes therefore ride the ``content_b64``
base64 side-channel (the same ``*_b64`` idiom Editor and LaTeXer already use), which is
pure ASCII and cannot be altered by the logging path.

The behaviour tests run the REAL ``agent/agents/grepper/grepper.py`` as a subprocess
over throwaway files — no mocking. The wiring tests pin the contract surfaces and the
LLM-facing description (a default whose description is not updated ships invisible).
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml
from django.test import SimpleTestCase

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GREPPER_DIR = os.path.join(_THIS_DIR, "agents", "grepper")
GREPPER_PY = os.path.join(GREPPER_DIR, "grepper.py")
GREPPER_YAML = os.path.join(GREPPER_DIR, "config.yaml")


def _run(path, **over):
    """Run the real agent against ``path`` and return its emitted section."""
    tmp = tempfile.mkdtemp(prefix="grepper_lines_")
    gdir = os.path.join(tmp, "grepper")
    os.makedirs(gdir, exist_ok=True)
    try:
        shutil.copy(GREPPER_PY, os.path.join(gdir, "grepper.py"))
        cfg = {
            "pattern": over.get("pattern", ""),
            "path": path,
            "glob": over.get("glob", ""),
            "case_insensitive": over.get("case_insensitive", False),
            "output_mode": over.get("output_mode", "lines"),
            "max_results": over.get("max_results", 200),
            "start_line": over.get("start_line", 0),
            "end_line": over.get("end_line", 0),
            "line_numbers": over.get("line_numbers", True),
            "source_agents": [],
            "target_agents": [],
        }
        with open(os.path.join(gdir, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        subprocess.run([sys.executable, "grepper.py"], cwd=gdir, timeout=60,
                       capture_output=True)
        with open(os.path.join(gdir, "grepper.log"), encoding="utf-8",
                  errors="replace") as f:
            return _section(f.read())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _section(log):
    m = re.search(r"INI_SECTION_GREPPER<<<(.*?)>>>END_SECTION_GREPPER", log, re.S)
    assert m, f"no INI_SECTION_GREPPER in log:\n{log}"
    raw = m.group(1)
    head, _, body = raw.partition("\n\n")
    out = {"_raw": raw, "_body": body}
    for line in head.splitlines():
        if ": " in line or line.endswith(":"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def _b64_text(sec):
    """Decode the byte-exact side-channel."""
    return base64.b64decode(sec["content_b64"]).decode("utf-8")


class LinesModeBehaviorTests(SimpleTestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="grepper_lines_tree_")
        self.addCleanup(shutil.rmtree, self.tree, True)

    def _write(self, name, data):
        p = os.path.join(self.tree, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    # ---------------------------------------------------------------- reading

    def test_reads_an_inclusive_1_based_range(self):
        p = self._write("r.txt", b"one\ntwo\nthree\nfour\nfive\n")
        sec = _run(p, start_line=2, end_line=4)
        self.assertEqual(sec["status"], "listed")
        self.assertEqual(sec["lines_returned"], "3")
        self.assertEqual(sec["total_lines"], "5")
        self.assertIn("2: two", sec["_body"])
        self.assertIn("4: four", sec["_body"])
        self.assertNotIn("5: five", sec["_body"])

    def test_zero_bounds_mean_the_whole_file(self):
        p = self._write("w.txt", b"a\nb\nc\n")
        sec = _run(p, start_line=0, end_line=0)
        self.assertEqual(sec["lines_returned"], "3")
        self.assertEqual(sec["total_lines"], "3")

    def test_out_of_range_end_is_clamped_not_an_error(self):
        p = self._write("c.txt", b"a\nb\n")
        sec = _run(p, start_line=1, end_line=999)
        self.assertEqual(sec["status"], "listed")
        self.assertEqual(sec["lines_returned"], "2")

    def test_no_pattern_is_required(self):
        p = self._write("n.txt", b"only line\n")
        sec = _run(p, pattern="")
        self.assertEqual(sec["status"], "listed")
        self.assertNotIn("No pattern configured", sec["_body"])

    def test_empty_file_lists_zero_lines(self):
        p = self._write("e.txt", b"")
        sec = _run(p)
        self.assertEqual(sec["status"], "listed")
        self.assertEqual(sec["total_lines"], "0")

    def test_max_results_truncates_and_says_so(self):
        p = self._write("t.txt", b"".join(b"l%d\n" % i for i in range(50)))
        sec = _run(p, max_results=5)
        self.assertEqual(sec["lines_returned"], "5")
        self.assertEqual(sec["truncated"], "True")
        self.assertIn("truncated at max_results=5", sec["_body"])

    # ------------------------------------------------- the byte-exact channel

    def test_content_b64_survives_crlf_which_the_log_alone_does_not(self):
        """THE regression this whole side-channel exists for."""
        payload = b"alpha\r\nbeta  \r\ngamma\r\n"
        p = self._write("crlf.txt", payload)
        sec = _run(p, line_numbers=False)
        self.assertEqual(_b64_text(sec).encode("utf-8"), payload)
        # ...and prove the plain body is NOT trustworthy. Read in TEXT mode the
        # damage hides (universal newlines fold \r\r\n back to \r\n), so the
        # corruption shows up as SPURIOUS BLANK LINES between every source line.
        self.assertIn("alpha", sec["_body"])
        self.assertNotEqual(
            sec["_body"].split("... (truncated")[0].rstrip("\n"),
            payload.decode("utf-8").rstrip("\r\n"),
            "if the plain body ever becomes trustworthy, content_b64 can be "
            "reconsidered - until then it is the only exact channel",
        )

    def test_content_b64_round_trips_lf_accents_and_no_trailing_newline(self):
        for name, payload in (
            ("lf.txt", b"one\ntwo\t\nthree\n"),
            ("acc.txt", "café niño áéíóú\r\nsegunda\r\n".encode("utf-8")),
            ("notrail.txt", b"no trailing newline"),
        ):
            with self.subTest(name):
                sec = _run(self._write(name, payload), line_numbers=False)
                self.assertEqual(_b64_text(sec).encode("utf-8"), payload)

    def test_utf16_source_is_decoded_not_treated_as_binary(self):
        payload = "primera\r\nsegunda\r\n".encode("utf-16")
        sec = _run(self._write("u16.txt", payload), line_numbers=False)
        self.assertEqual(_b64_text(sec), payload.decode("utf-16"))

    def test_line_numbers_true_emits_no_b64_channel(self):
        p = self._write("ln.txt", b"a\nb\n")
        sec = _run(p, line_numbers=True)
        self.assertEqual(sec.get("content_b64", ""), "")

    # ------------------------------------------------------------- refusals

    def test_a_directory_is_refused_not_guessed_at(self):
        sec = _run(self.tree)
        self.assertEqual(sec["status"], "refused")
        self.assertIn("Globber", sec["_body"])

    def test_a_binary_file_is_refused(self):
        p = self._write("b.bin", bytes([0, 1, 2, 3]) * 60)
        sec = _run(p)
        self.assertEqual(sec["status"], "refused")

    def test_a_missing_path_is_not_found(self):
        sec = _run(os.path.join(self.tree, "absent.txt"))
        self.assertEqual(sec["status"], "not_found")

    # -------------------------------------------- the search modes still work

    def test_search_modes_are_untouched_by_the_new_mode(self):
        p = self._write("s.py", b"# TODO one\nx = 1\n# TODO two\n")
        sec = _run(p, pattern="TODO", output_mode="content")
        self.assertEqual(sec["status"], "matches")
        self.assertEqual(sec["matches"], "2")
        self.assertEqual(sec["lines_returned"], "0")
        self.assertEqual(sec.get("content_b64", ""), "")

    def test_empty_pattern_still_errors_in_content_mode(self):
        p = self._write("s2.py", b"anything\n")
        sec = _run(p, pattern="", output_mode="content")
        self.assertEqual(sec["status"], "error")


class LinesModeWiringTests(SimpleTestCase):
    def test_config_yaml_declares_the_new_keys(self):
        with open(GREPPER_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        for key in ("start_line", "end_line", "line_numbers"):
            self.assertIn(key, cfg, f"config.yaml must declare {key}")
        self.assertIs(cfg["line_numbers"], True)
        self.assertEqual(cfg["start_line"], 0)
        self.assertEqual(cfg["end_line"], 0)

    def test_emitted_header_matches_the_parametrizer_contract(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        registered = set(_PARAMETRIZER_OUTPUT_FIELDS["grepper"]) - {"response_body"}
        with open(GREPPER_PY, encoding="utf-8") as f:
            src = f.read()
        # ONLY the emit function - the module logs other "Label: {value}" strings
        emit = src.split("def emit_grepper_section(", 1)[1].split("\ndef ", 1)[0]
        emitted = set(re.findall(r'f"(\w+): \{', emit))
        self.assertIn("content_b64", emitted, "the b64 channel must be emitted")
        missing = emitted - registered
        self.assertFalse(
            missing,
            f"grepper emits {sorted(missing)} but _PARAMETRIZER_OUTPUT_FIELDS "
            f"does not list them - keep both sides in step",
        )

    def test_views_mirror_stays_derived(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        from agent.views import PARAMETRIZER_SOURCE_OUTPUT_FIELDS
        self.assertEqual(
            tuple(PARAMETRIZER_SOURCE_OUTPUT_FIELDS["grepper"]),
            tuple(_PARAMETRIZER_OUTPUT_FIELDS["grepper"]),
        )

    def test_status_tokens_belong_to_the_shared_vocabulary(self):
        from agent.agent_verdict import KNOWN_STATUSES
        for token in ("listed", "refused", "not_found", "matches", "no_matches", "error"):
            self.assertIn(token, KNOWN_STATUSES, f"{token} is not a known status")

    def test_the_model_is_told_to_decode_content_b64(self):
        """A default whose DESCRIPTION is not updated ships invisible.

        The model only ever sees ``purpose``/``example_request``. If those still
        describe the old surface it will keep reaching for a shell to read files
        and the whole capability is dead on arrival while appearing to work.
        """
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_grepper"]
        text = (spec.purpose + " " + spec.example_request).lower()
        self.assertIn("content_b64", text)
        self.assertIn("decode", text)
        self.assertIn("lines", text)
        self.assertIn("start_line", text)

    def test_read_lines_mode_reuses_the_encoding_aware_reader(self):
        """It must NOT grow a second decoder - the BOM-before-NUL order is a contract."""
        with open(GREPPER_PY, encoding="utf-8") as f:
            src = f.read()
        body = src.split("def _read_lines_mode(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_read_text_lines(path)", body)
        self.assertNotIn("open(", body)
