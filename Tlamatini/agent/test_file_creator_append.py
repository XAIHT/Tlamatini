# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Deterministic proof for File-Creator's ``append`` option (Angela, 2026-10-08).

``append: true`` ADDS the content to the end of a file instead of overwriting it, so a
file can be built step by step.  It is OFFERED to the model, not ordered: measured the
same day, writing a 36K-character document in pieces was not faster than one call (the
reasoning tokens dominate), so no prompt imposes a piece size.  These tests prove, by
running the REAL agent script in a scratch copy:

* the default is unchanged (create / overwrite), and ``append`` adds to the end;
* appending is byte-exact (CRLF, non-ASCII, backslashes, base64 payloads);
* every sensible spelling of "true" appends - including a trailing remark after it,
  which must never flip the switch off and OVERWRITE what is already written;
* a document written in several appended pieces comes back identical;
* the model is TOLD (tool description) and the request parser keeps ``append`` apart
  from the content - and no fixed piece size is pushed on it.

Run: python manage.py test agent.test_file_creator_append
"""

from __future__ import annotations

import base64
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
from agent.tools import _apply_requested_assignments_to_config, _recover_swallowed_assignments

AGENT_DIR = pathlib.Path(__file__).resolve().parent
TEMPLATE = AGENT_DIR / "agents" / "file_creator"
CR, LF = chr(13), chr(10)
PIECE_CHARS = 7000


def _template_config():
    return yaml.safe_load((TEMPLATE / "config.yaml").read_text(encoding="utf-8")) or {}


class FileCreatorAppendTests(unittest.TestCase):
    """Runs the real ``file_creator.py`` in a scratch copy of its template folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.folder = self.root / "file_creator_1"
        shutil.copytree(
            TEMPLATE, self.folder,
            ignore=shutil.ignore_patterns("__pycache__", "*.log", "*.pid", "reanim*"))
        self.target = self.root / "out" / "doc.txt"

    def _run(self, **config):
        """One agent run. Returns ``(exit_code, log_text)``."""
        base = {"file_path": str(self.target), "content": "", "content_b64": "",
                "append": False, "source_agents": [], "target_agents": []}
        base.update(config)
        (self.folder / "config.yaml").write_text(
            yaml.safe_dump(base, allow_unicode=True), encoding="utf-8")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        env.pop("AGENT_REANIMATED", None)
        done = subprocess.run([sys.executable, "file_creator.py"], cwd=self.folder, env=env,
                              capture_output=True, timeout=90)
        log = (self.folder / "file_creator_1.log").read_text(encoding="utf-8", errors="replace")
        return done.returncode, log

    def _seed(self, data=b"A"):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(data)

    # ── the default is untouched ──────────────────────────────────────────────
    def test_the_default_still_creates_then_overwrites(self):
        code, log = self._run(content="first" + LF)
        self.assertEqual(code, 0)
        self.assertEqual(self.target.read_bytes(), b"first" + LF.encode())
        self.assertIn("File: created", log)
        self._run(content="second" + LF)
        self.assertEqual(self.target.read_bytes(), b"second" + LF.encode(),
                         "without append the file is overwritten, exactly as before")

    def test_the_template_ships_append_off(self):
        config = _template_config()
        self.assertIn("append", config)
        self.assertIs(config["append"], False)

    # ── append adds to the end ────────────────────────────────────────────────
    def test_append_adds_to_the_end(self):
        self._run(content="one" + LF)
        code, log = self._run(content="two" + LF, append=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.target.read_bytes(), ("one" + LF + "two" + LF).encode())
        self.assertIn("File: appended", log)
        self.assertIn("Appended 4 chars", log)
        self.assertIn("file is now 8 bytes", log)

    def test_append_creates_a_missing_file(self):
        self.assertFalse(self.target.exists())
        code, log = self._run(content="only piece" + LF, append=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.target.read_bytes(), ("only piece" + LF).encode())

    def test_append_is_byte_exact(self):
        first = "caf\u00e9 \\ \"q\" " + CR + LF + "line2" + LF
        second = "\u00f1 tail" + CR + LF
        self._run(content=first)
        self._run(content=second, append=True)
        self.assertEqual(self.target.read_bytes(), (first + second).encode("utf-8"),
                         "CRLF, accents and backslashes must survive appending untouched")

    def test_append_works_for_the_base64_channel(self):
        self._run(content="text" + LF)
        payload = bytes([0, 1, 2, 250, 251]) + b" binary"
        code, log = self._run(content_b64=base64.b64encode(payload).decode("ascii"), append=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.target.read_bytes(), ("text" + LF).encode() + payload)
        self.assertIn("Appended (binary/base64", log)

    # ── every spelling of true appends; nothing else does ─────────────────────
    def test_every_spelling_of_true_appends_even_with_a_remark_after_it(self):
        for value in (True, "true", "TRUE - the second piece", "yes", 1, "'true'"):
            with self.subTest(append=value):
                self._seed(b"A")
                self._run(content="B", append=value)
                self.assertEqual(self.target.read_bytes(), b"AB", repr(value))

    def test_anything_else_overwrites(self):
        for value in ("false", "false - overwrite it", 0, "", None):
            with self.subTest(append=value):
                self._seed(b"A")
                self._run(content="B", append=value)
                self.assertEqual(self.target.read_bytes(), b"B", repr(value))

    # ── advice, never a change to the model's bytes ───────────────────────────
    def test_it_warns_when_two_pieces_meet_in_the_middle_of_a_line(self):
        self._run(content="abc")
        code, log = self._run(content="def", append=True)
        self.assertEqual(self.target.read_bytes(), b"abcdef", "the bytes are never edited")
        self.assertIn("SAME line", log)

    def test_it_stays_quiet_when_the_pieces_meet_on_a_line_boundary(self):
        self._run(content="abc" + LF)
        code, log = self._run(content="def" + LF, append=True)
        self.assertEqual(self.target.read_bytes(), ("abc" + LF + "def" + LF).encode())
        self.assertNotIn("SAME line", log)

    # ── the whole point ───────────────────────────────────────────────────────
    def test_a_long_document_written_in_pieces_comes_back_identical(self):
        lines = ["line %04d %s%s" % (number, "x" * 40, LF) for number in range(600)]
        document = "".join(lines)
        pieces, current = [], ""
        for line in lines:
            if current and len(current) + len(line) > PIECE_CHARS:
                pieces.append(current)
                current = ""
            current += line
        pieces.append(current)
        self.assertGreaterEqual(len(pieces), 4, "the fixture must really need several pieces")
        self.assertTrue(all(len(piece) <= PIECE_CHARS for piece in pieces))
        log = ""
        for index, piece in enumerate(pieces):
            code, log = self._run(content=piece, append=index > 0)
            self.assertEqual(code, 0, "piece %d failed" % index)
        self.assertEqual(self.target.read_bytes(), document.encode("utf-8"))
        self.assertIn("File: appended", log)


class RequestParsingTests(unittest.TestCase):
    """The model asks for ``append=true`` inside a request string."""

    def test_append_is_a_real_key_of_the_template(self):
        request = "Create file with filepath='C:/x/doc.txt' and content='abc' and append=true"
        config, error, _ = _apply_requested_assignments_to_config(_template_config(), request)
        self.assertIsNone(error, error)
        self.assertIn(str(config["append"]).strip().lower(), ("true", "1"))
        self.assertEqual(config["content"], "abc")

    def test_an_append_tail_is_split_off_a_multi_line_body(self):
        """The reason ``append`` MUST be a key of config.yaml: a trailing ``', append=true``
        is cut off the document body only when every key in the tail is a real config key -
        otherwise it would be typeset into the user's file."""
        body = "line one" + LF + "line two" + LF
        runtime = _template_config()
        clean, recovered = _recover_swallowed_assignments(body + "', append=true", runtime)
        self.assertEqual(clean, body)
        self.assertEqual(recovered, ("append",))
        self.assertIn(str(runtime["append"]).strip().lower(), ("true", "1"))
        stripped = {key: value for key, value in _template_config().items() if key != "append"}
        glued, nothing = _recover_swallowed_assignments(body + "', append=true", stripped)
        self.assertEqual(nothing, ())
        self.assertIn("append=true", glued, "without the key the tail would be glued into the file")


class GuidanceTests(unittest.TestCase):
    """The model reads the descriptions - an invisible feature is a missing feature."""

    def test_file_creator_names_the_append_option(self):
        purpose = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_file_creator"].purpose
        for needle in ("append=true", "ADD to the end of an existing file"):
            self.assertIn(needle, purpose)

    def test_no_fixed_piece_size_is_imposed_on_the_model(self):
        """Measured 2026-10-08 (glm-5.3, one 36K-character LaTeX document): one call 260 s,
        the same document in ~7,000-character pieces 298 s - the reasoning tokens dominate,
        not the size of the call.  So the prompts offer append, they do not order pieces."""
        for tool in ("chat_agent_file_creator", "chat_agent_latexer"):
            purpose = WRAPPED_CHAT_AGENT_BY_TOOL_NAME[tool].purpose
            self.assertNotIn("7,000", purpose, tool)
        source = (AGENT_DIR / "mcp_agent.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("is written in PIECES", source)

    def test_flowcreator_knows_the_new_parameter(self):
        text = (AGENT_DIR / "agents" / "flowcreator" / "agentic_skill.md").read_text(
            encoding="utf-8-sig")
        self.assertIn("`append`: false", text)

    def test_create_flow_keeps_the_append_setting(self):
        script = (AGENT_DIR / "static" / "agent" / "js" / "agent_page_chat.js").read_text(
            encoding="utf-8-sig")
        marker = "lower === 'file creator'"
        start = script.index(marker)
        branch = script[start:start + 900]
        self.assertIn("config.append", branch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
