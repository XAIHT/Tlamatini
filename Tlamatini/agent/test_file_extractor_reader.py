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
HARD tests for the **File-Extractor Reader upgrade** (line_numbers + offset/limit).

Runs the REAL ``agent/agents/file_extractor/file_extractor.py`` as a subprocess over
a known 6-line file and asserts the new Claude-Read-style view options, INCLUDING the
backward-compatibility guarantee (all defaults = the full original text, unchanged).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml
from django.test import SimpleTestCase

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FE_PY = os.path.join(_THIS_DIR, "agents", "file_extractor", "file_extractor.py")
FE_CFG = os.path.join(_THIS_DIR, "agents", "file_extractor", "config.yaml")


def _run(target, **over):
    tmp = tempfile.mkdtemp(prefix="reader_test_")
    fdir = os.path.join(tmp, "file_extractor")
    os.makedirs(fdir, exist_ok=True)
    try:
        shutil.copy(FE_PY, os.path.join(fdir, "file_extractor.py"))
        cfg = {
            "path_filenames": target,
            "recursive": False,
            "filetype_exclusions": "",
            "line_numbers": over.get("line_numbers", False),
            "offset": over.get("offset", 0),
            "limit": over.get("limit", 0),
            "source_agents": [],
            "target_agents": [],
        }
        with open(os.path.join(fdir, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        subprocess.run([sys.executable, "file_extractor.py"], cwd=fdir, timeout=60, capture_output=True)
        with open(os.path.join(fdir, "file_extractor.log"), encoding="utf-8") as f:
            log = f.read()
        m = re.search(r"INI_SECTION_FILE_EXTRACTOR<<<\n.*?\n\n(.*?)\n>>>END_SECTION_FILE_EXTRACTOR", log, re.S)
        assert m, f"no section body:\n{log}"
        return m.group(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class FileExtractorReaderTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reader_target_")
        self.target = os.path.join(self.tmp, "six.txt")
        with open(self.target, "w", encoding="utf-8") as f:
            f.write("L1\nL2\nL3\nL4\nL5\nL6\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backward_compatible_default(self):
        # All defaults -> the full original text, with NO line-number prefixes.
        body = _run(self.target)
        self.assertIn("L1", body)
        self.assertIn("L6", body)
        self.assertNotRegex(body, r"\b1\tL1")  # no numbering by default

    def test_line_numbers_only(self):
        body = _run(self.target, line_numbers=True)
        self.assertRegex(body, r"\b1\tL1")
        self.assertRegex(body, r"\b6\tL6")

    def test_offset_and_limit(self):
        body = _run(self.target, offset=2, limit=3)
        self.assertIn("L2", body)
        self.assertIn("L4", body)
        self.assertNotIn("L1", body)
        self.assertNotIn("L5", body)

    def test_line_numbers_with_slice(self):
        body = _run(self.target, line_numbers=True, offset=2, limit=3)
        # real file line numbers preserved on the slice
        self.assertRegex(body, r"\b2\tL2")
        self.assertRegex(body, r"\b4\tL4")
        self.assertNotIn("L1", body)

    def test_offset_beyond_eof_empty(self):
        body = _run(self.target, offset=99, limit=5)
        self.assertEqual(body.strip(), "")

    def test_config_has_reader_keys(self):
        with open(FE_CFG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        for k in ("line_numbers", "offset", "limit"):
            self.assertIn(k, cfg)
