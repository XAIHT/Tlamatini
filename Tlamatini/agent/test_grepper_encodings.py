# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Grepper must not go BLIND on non-UTF-8 text.

THE BUG (Angela, 2026-08-16). Grepper read every candidate with a bare
``open(fpath, "r", encoding="utf-8", errors="strict")`` and swallowed the
``UnicodeDecodeError`` with ``continue  # skip binary``. So any file that was not
valid UTF-8 was never opened at all, ``files_searched`` stayed 0, and Grepper
reported a confident ``status: no_matches``. A search tool that answers "nothing
there" about a file it refused to read is worse than one that errors, because
the caller believes it.

Two real classes of TEXT vanished that way:

* **UTF-16** — what Windows PowerShell writes by default (``Tee-Object`` /
  ``Out-File``), so every captured build/test log was invisible to Grepper. This
  is exactly how the bug was caught: a PowerShell-captured Django test log came
  back ``files_searched: 0``.
* **cp1252 / latin-1** — legacy Windows encodings, i.e. Angela's accented
  Spanish sources. A single ``ó`` byte was enough to erase the whole file from
  every search.

The fix mirrors the ordering contract already documented for
``agent/rag/binary_guard.py``: **the BOM test must run BEFORE the NUL test**,
because UTF-16/UTF-32 text is legitimately full of ``0x00`` bytes and would
otherwise be condemned as binary. Decoding then falls back UTF-8 → cp1252 →
latin-1 and can never fail, because losing a real file is far worse than a few
mojibake characters on one line. Genuine binaries are still skipped.
"""

from __future__ import annotations

import ast
import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

_GREPPER_PY = Path(__file__).resolve().parent / "agents" / "grepper" / "grepper.py"
_LIFTED_NAMES = ("_BOM_CODECS", "_NUL_SAMPLE_BYTES", "_read_text_lines")

TOKEN = "TLAMATINI_ENC_PROBE"
SPANISH = "Angela López Mendoza — acentós: canción, niño, LaTeXer"


def _lift_grepper_decoder() -> dict:
    """AST-lift the decoder out of grepper.py WITHOUT importing the agent.

    A pool agent is a standalone SCRIPT, not a module: importing it truncates its
    log file and installs a ``subprocess.Popen`` monkey-patch. So the decoder is
    lifted instead — the same trick ``test_temp_dir_policy.py`` uses for
    ``manage.py``.
    """
    tree = ast.parse(_GREPPER_PY.read_text(encoding="utf-8"))
    picked: list = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _LIFTED_NAMES:
            picked.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _LIFTED_NAMES:
                    picked.append(node)
                    break
    namespace: dict = {}
    block = ast.Module(body=picked, type_ignores=[])
    exec(compile(block, "<grepper-decoder>", "exec"), namespace)  # noqa: S102
    return namespace


_NS = _lift_grepper_decoder()
_read_text_lines = _NS["_read_text_lines"]
_BOM_CODECS = _NS["_BOM_CODECS"]


class _TempFileMixin(SimpleTestCase):
    """One temp dir per file, torn down by TemporaryDirectory itself.

    Deliberately NOT two separate ``addCleanup`` calls: cleanups run LIFO, so a
    later-registered ``os.rmdir`` would fire BEFORE the file removal and raise on
    a non-empty directory.
    """

    def write_bytes(self, payload: bytes, name: str = "probe.txt") -> str:
        holder = tempfile.TemporaryDirectory(prefix="tlm_grepper_")
        self.addCleanup(holder.cleanup)
        path = os.path.join(holder.name, name)
        with open(path, "wb") as handle:
            handle.write(payload)
        return path

    def make_dir(self) -> str:
        holder = tempfile.TemporaryDirectory(prefix="tlm_grepper_dir_")
        self.addCleanup(holder.cleanup)
        return holder.name


class GrepperDecoderLiftTests(SimpleTestCase):
    def test_the_decoder_was_actually_lifted(self):
        self.assertIn("_read_text_lines", _NS)
        self.assertIn("_BOM_CODECS", _NS)
        self.assertIn("_NUL_SAMPLE_BYTES", _NS)


class GrepperEncodingTests(_TempFileMixin):
    """Every one of these files is TEXT and MUST be searchable."""

    def _assert_token_found(self, payload: bytes, label: str) -> str:
        lines = _read_text_lines(self.write_bytes(payload))
        self.assertIsNotNone(lines, f"{label} was dropped - Grepper is blind to it again.")
        joined = "".join(lines)
        self.assertIn(TOKEN, joined, f"{label} decoded but the token was lost.")
        return joined

    def test_plain_utf8_still_works(self):
        self._assert_token_found(f"{TOKEN} {SPANISH}\n".encode("utf-8"), "utf-8")

    def test_utf8_bom_is_stripped_not_glued_onto_the_first_match(self):
        joined = self._assert_token_found(f"{TOKEN} {SPANISH}\n".encode("utf-8-sig"), "utf-8-sig")
        self.assertFalse(joined.startswith("﻿"), "the UTF-8 BOM leaked into the first line")
        self.assertTrue(joined.startswith(TOKEN))

    def test_utf16le_text_is_searched(self):
        # PowerShell's default output encoding. This is the file that exposed the bug.
        self._assert_token_found(f"{TOKEN} {SPANISH}\n".encode("utf-16"), "utf-16-le (PowerShell)")

    def test_utf16be_text_is_searched(self):
        payload = b"\xfe\xff" + f"{TOKEN} {SPANISH}\n".encode("utf-16-be")
        self._assert_token_found(payload, "utf-16-be")

    def test_utf32le_text_is_searched(self):
        self._assert_token_found(f"{TOKEN} {SPANISH}\n".encode("utf-32"), "utf-32-le")

    def test_cp1252_spanish_source_is_never_dropped(self):
        # Angela's accented sources. One 'ó' byte used to erase the whole file.
        payload = f"{TOKEN} Angela Lopez Mendoza - canción, niño\n".encode("cp1252")
        joined = self._assert_token_found(payload, "cp1252 (Spanish)")
        self.assertIn("canción", joined)


class GrepperBinaryStillSkippedTests(_TempFileMixin):
    """Widening the decoder must NOT start dumping real binaries into results."""

    def test_real_binary_with_an_ascii_token_is_still_skipped(self):
        payload = b"MZ\x90\x00\x03\x00\x00\x00" + TOKEN.encode() + b"\x00\x00\xff\x01"
        self.assertIsNone(_read_text_lines(self.write_bytes(payload, "blob.bin")))

    def test_missing_file_returns_none_and_never_raises(self):
        self.assertIsNone(_read_text_lines(os.path.join(self.make_dir(), "nope.txt")))

    def test_a_directory_returns_none_and_never_raises(self):
        self.assertIsNone(_read_text_lines(self.make_dir()))

    def test_empty_file_is_text_not_binary(self):
        self.assertEqual(_read_text_lines(self.write_bytes(b"")), [])


class GrepperDecoderOrderingContractTests(_TempFileMixin):
    """The ordering rules that make the decoder correct. Do NOT reorder."""

    def test_bom_is_decided_before_the_nul_test(self):
        # A UTF-16 file is FULL of 0x00. If the NUL test ran first, every UTF-16
        # document on Angela's disk would silently vanish from every search.
        payload = ("x" * 5000 + TOKEN + "\n").encode("utf-16")
        self.assertIn(b"\x00", payload[:64], "fixture is not actually NUL-heavy")
        lines = _read_text_lines(self.write_bytes(payload))
        self.assertIsNotNone(lines, "the NUL test overtook the BOM test")
        self.assertIn(TOKEN, "".join(lines))

    def test_utf32le_bom_is_tested_before_its_utf16le_prefix(self):
        # b"\xff\xfe\x00\x00" (UTF-32-LE) STARTS WITH b"\xff\xfe" (UTF-16-LE).
        order = [bom for bom, _codec in _BOM_CODECS]
        self.assertLess(
            order.index(b"\xff\xfe\x00\x00"),
            order.index(b"\xff\xfe"),
            "_BOM_CODECS must list the longest prefix first",
        )


class GrepperSourceContractTests(SimpleTestCase):
    """Pin the source so the strict-UTF-8 read can never come back."""

    def setUp(self):
        self.source = _GREPPER_PY.read_text(encoding="utf-8")

    def test_no_open_call_reads_with_strict_utf8(self):
        # Checked on the AST, NOT on the raw text: _read_text_lines' docstring
        # deliberately QUOTES the old bad call to explain the bug, so a naive
        # substring search matches its own explanation and fails forever.
        offenders = []
        for node in ast.walk(ast.parse(self.source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name != "open":
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "errors"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == "strict"
                ):
                    offenders.append(node.lineno)
        self.assertEqual(
            offenders,
            [],
            f"grepper.py line(s) {offenders} open a file with errors='strict' again - "
            "non-UTF-8 TEXT will be silently skipped and reported as no_matches.",
        )

    def test_the_search_loop_goes_through_the_decoder(self):
        self.assertIn("lines = _read_text_lines(fpath)", self.source)

    def test_the_bom_before_nul_contract_is_documented(self):
        self.assertIn("BOM", self.source)
        self.assertIn("_NUL_SAMPLE_BYTES", self.source)
