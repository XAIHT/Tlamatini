"""Process gates for the browser JavaScript -- two silent, total failure modes.

The Spanish tree hit both:

  * A module that EXPORTS an identifier it never declared
    (``window.TlamatiniDialogPolicy = { ..., bindSeal: bindSeal }`` with no
    ``bindSeal`` anywhere). The object literal is evaluated AT LOAD, so the file
    throws ``ReferenceError``, ``window.TlamatiniDialogPolicy`` is never assigned,
    and the whole chat page silently loses Escape-to-close / ``tlmAlert`` /
    ``tlmConfirm``. Caught by eslint's ``no-undef`` (enforced as an error).

  * A file that does not PARSE at all (statements pasted into an object literal).
    A completely dead page, no error until the browser console. Caught by
    ``node --check``.

Both are invisible from any log. The config assertion below always runs (pure
Python); the parse gate runs wherever ``node`` is on PATH (the dev machine and CI).
"""
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_DIR = REPO_ROOT / "Tlamatini" / "agent" / "static" / "agent" / "js"
ESLINT_CONFIG = REPO_ROOT / "eslint.config.mjs"


class NoUndefEnforcedTests(unittest.TestCase):
    def test_eslint_config_keeps_no_undef_as_error(self):
        text = ESLINT_CONFIG.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(
            text, r'"no-undef"\s*:\s*"error"',
            "eslint.config.mjs must keep no-undef as an ERROR so an undeclared "
            "identifier in a window.Tlamatini* export literal fails the lint gate.",
        )


class JavaScriptParsesTests(unittest.TestCase):
    def test_every_js_file_parses_with_node_check(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH; run `npm run lint` to parse-check the JS")
        self.assertTrue(JS_DIR.is_dir(), f"missing {JS_DIR}")
        js_files = sorted(JS_DIR.glob("*.js"))
        self.assertGreater(len(js_files), 0, "no JS modules found to parse-check")
        failures = []
        for js in js_files:
            proc = subprocess.run(
                [node, "--check", str(js)],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                failures.append(f"{js.name}: {proc.stderr.strip()[:300]}")
        self.assertEqual(failures, [], "JS files that do NOT parse:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
