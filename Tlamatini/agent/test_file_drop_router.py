# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Guards the page-wide file-drop router (Angela, 2026-10-14).

Every Tlamatini page used to carry its OWN blind drop handler and they fought each
other: a dropped MCP ``.json`` was reported as an error by the chat's image handler,
OPENED AS TEXT by the canvas handler (which swallowed the event, so the import never
saw it), and on the Agentic Control Panel / Prompt Flow Panel / welcome page the
browser simply NAVIGATED AWAY to the file.

``static/agent/js/file_drop_router.js`` is now the ONE listener. It claims every file
drag in the capture phase, classifies each dropped file by its bytes, and dispatches
each kind to a different mechanism. This module pins four layers, because each breaks
on its own:

1. BEHAVIOUR  - ``scripts/file_drop_router_cases.mjs`` loads the REAL router into a
   stub browser and drives classification, every MCP config shape and the dispatch.
2. SOURCE CONTRACT - the invariants a careless edit could silently undo.
3. PAGE WIRING - a router nobody loads does nothing: every page must load it, BEFORE
   the scripts that register handlers with it.
4. THE OLD HANDLERS ARE GONE - two competing listeners is the original bug.
5. COLLECTED STATIC - ``staticfiles/`` is what the browser downloads.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parent
PROJECT = AGENT.parent
REPO = PROJECT.parent
STATIC = AGENT / "static" / "agent"
JS = STATIC / "js"
TEMPLATES = AGENT / "templates"
COLLECTED = PROJECT / "staticfiles" / "agent"

ROUTER = JS / "file_drop_router.js"
CASES = REPO / "scripts" / "file_drop_router_cases.mjs"
# Matches both the template form ("agent/js/...") and the PDF frame's relative form ("../js/...").
ROUTER_FRAGMENT = "js/file_drop_router.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _index(text: str, fragment: str) -> int:
    position = text.find(fragment)
    assert position != -1, f"{fragment!r} not found"
    return position


class RouterBehaviourTests(unittest.TestCase):
    """Run the real router in Node (vm + stub browser) and demand every check passes."""

    def test_node_cases_pass(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed; scripts/file_drop_router_cases.mjs not run")
        if not CASES.exists():
            self.skipTest("scripts/ is not part of this checkout")
        result = subprocess.run(
            [node, str(CASES)], cwd=str(REPO), capture_output=True, text=True,
            encoding="utf-8", timeout=180,
        )
        self.assertEqual(
            result.returncode, 0,
            f"file_drop_router_cases.mjs failed:\n{result.stdout}\n{result.stderr}",
        )
        self.assertIn("FILE_DROP_ROUTER_CASES_OK", result.stdout)


class RouterSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = _read(ROUTER)

    def test_it_is_one_self_contained_iife(self):
        # A top-level const/let would be a cross-file global (const-poison contract).
        self.assertIn("(function () {", self.js)
        self.assertIn("'use strict';", self.js)
        for line in self.js.splitlines():
            self.assertFalse(
                line.startswith(("const ", "let ", "var ")),
                f"top-level binding leaks out of the IIFE: {line!r}",
            )

    def test_every_file_drag_event_is_claimed_in_the_capture_phase(self):
        # Bubble phase would let a page handler see the drag first - the original bug.
        for event in ("dragenter", "dragover", "dragleave", "drop"):
            self.assertRegex(
                self.js,
                r"(?s)window\.addEventListener\('%s', function \(event\) \{.*?\}, true\);" % event,
                f"{event} must be registered on window in the capture phase",
            )
        self.assertIn("window.addEventListener('dragend', hideOverlay, true);", self.js)

    def test_only_file_drags_are_claimed(self):
        # Text drags (agent sidebar) and palette drags (Prompt Flow Panel) must pass untouched.
        self.assertIn("types[i] === 'Files'", self.js)
        self.assertIn("if (!isFileDrag(event) || overNativeFileInput(event)) return;", self.js)
        self.assertIn('input[type="file"]', self.js)

    def test_an_mcp_import_is_never_silent(self):
        # The config carries an executable command: confirm first, always.
        self.assertIn("launch programs on this computer", self.js)
        self.assertLess(
            _index(self.js, "const proceed = await ask("),
            _index(self.js, "data = await importServers(merged);"),
        )

    def test_flow_tab_is_reserved_inside_the_drop_task(self):
        # window.open after an await is refused by popup blockers.
        body = self.js[_index(self.js, "async function run(entries)"):]
        self.assertLess(body.find("openPlaceholderTab(entry.file)"), body.find("await classify("))

    def test_bom_is_tested_before_the_nul_byte(self):
        # UTF-16 text is legitimately full of 0x00 (same contract as rag/binary_guard.py).
        start = _index(self.js, "function looksBinary(head)")
        self.assertLess(self.js.find("if (bomOf(head)) return false;", start),
                        self.js.find("if (b === 0) return true;", start))

    def test_login_page_mode_exists(self):
        self.assertIn("data-auth", self.js)
        self.assertIn("Sign in first", self.js)

    def test_the_router_is_fail_open(self):
        self.assertIn("if (window.TlamatiniFileDrop) return;", self.js)
        self.assertIn("a lost toast must never break the page", self.js)


class PageWiringTests(unittest.TestCase):
    def test_every_page_loads_the_router(self):
        pages = {
            "chat": TEMPLATES / "agent" / "agent_page.html",
            "agentic control panel": TEMPLATES / "agent" / "agentic_control_panel.html",
            "prompt flow panel": TEMPLATES / "agent" / "prompt_flow_panel.html",
            "welcome": TEMPLATES / "agent" / "welcome.html",
            "login": TEMPLATES / "agent" / "login.html",
            "admin": TEMPLATES / "admin" / "base_site.html",
            "pdf canvas frame": STATIC / "pdf" / "canvas.html",
        }
        for name, path in pages.items():
            with self.subTest(page=name):
                self.assertIn(ROUTER_FRAGMENT, _read(path), f"{name} does not load the router")

    def test_the_router_loads_before_the_scripts_that_register_with_it(self):
        order = {
            TEMPLATES / "agent" / "agent_page.html": ("chat_image_paste.js", "agent_page_canvas.js"),
            TEMPLATES / "agent" / "agentic_control_panel.html": ("acp-file-io.js",),
            TEMPLATES / "agent" / "prompt_flow_panel.html": ("prompt-flow-panel.js",),
        }
        for path, later in order.items():
            text = _read(path)
            for fragment in later:
                with self.subTest(page=path.name, script=fragment):
                    self.assertLess(_index(text, ROUTER_FRAGMENT), _index(text, "agent/js/" + fragment))

    def test_login_marks_itself_unauthenticated(self):
        self.assertRegex(_read(TEMPLATES / "agent" / "login.html"),
                         r"file_drop_router\.js[^>]*data-auth=\"none\"")

    def test_welcome_has_the_themed_popups_the_router_asks_with(self):
        welcome = _read(TEMPLATES / "agent" / "welcome.html")
        self.assertIn("agent/js/dialog_policy.js", welcome)
        self.assertIn("agent/css/dialog_theme.css", welcome)

    def test_pages_register_what_they_can_do(self):
        expectations = {
            JS / "chat_image_paste.js": "register('image'",
            JS / "agent_page_canvas.js": "register(['pdf', 'markdown', 'text']",
            JS / "prompt-flow-panel.js": "register('flow-prompt'",
            JS / "acp-file-io.js": "register('flow-agent'",
        }
        for path, fragment in expectations.items():
            with self.subTest(file=path.name):
                self.assertIn(fragment, _read(path))


class OldCompetingHandlersAreGoneTests(unittest.TestCase):
    """Two listeners on the same drop is the original bug."""

    def test_external_mcps_dialog_no_longer_owns_a_document_drop_handler(self):
        text = _read(JS / "external_mcps_dialog.js")
        self.assertNotIn("addEventListener('drop'", text)
        self.assertNotIn("_emxImportServers", text)
        self.assertIn("tlm:external-mcps-imported", text)  # it only refreshes when told

    def test_chat_image_paste_has_no_private_drag_listeners(self):
        text = _read(JS / "chat_image_paste.js")
        for fragment in ("zone.addEventListener", "dragCarriesFiles", "dropOverlay", "Only image files can be dropped"):
            self.assertNotIn(fragment, text)

    def test_canvas_has_no_private_drop_target(self):
        text = _read(JS / "agent_page_canvas.js")
        self.assertNotIn("canvasDropTarget", text)
        self.assertNotIn("event.dataTransfer?.files", text)

    def test_the_private_chat_overlay_is_gone(self):
        self.assertNotIn("chat-drop-overlay", _read(TEMPLATES / "agent" / "agent_page.html"))
        self.assertNotIn("chat-drop-overlay", _read(STATIC / "css" / "agent_page.css"))

    def test_prompt_flow_panel_leaves_files_to_the_router(self):
        text = _read(JS / "prompt-flow-panel.js")
        self.assertIn("if (event.dataTransfer.files.length) return;", text)
        self.assertNotIn("await openFile(event.dataTransfer.files[0])", text)


class CollectedStaticTests(unittest.TestCase):
    """staticfiles/ is what the browser downloads - a stale copy ships nothing."""

    FILES = (
        "js/file_drop_router.js", "js/chat_image_paste.js", "js/agent_page_canvas.js",
        "js/external_mcps_dialog.js", "js/prompt-flow-panel.js", "js/acp-file-io.js",
        "pdf/canvas.html", "css/agent_page.css", "css/external_mcps_dialog.css",
    )

    def test_collected_copies_match_the_source(self):
        if not COLLECTED.exists():
            self.skipTest("staticfiles/ not collected in this checkout")
        stale = [
            name for name in self.FILES
            if not (COLLECTED / name).exists() or _read(COLLECTED / name) != _read(STATIC / name)
        ]
        self.assertEqual(stale, [], "run `python manage.py collectstatic --noinput` - stale in staticfiles/: %s" % stale)


class NoRegressionInSiblingFilesTests(unittest.TestCase):
    def test_banners_survive(self):
        for path in (ROUTER, CASES, Path(__file__)):
            if not path.exists():
                continue
            text = _read(path)
            self.assertIn("Tlamatini Author Banner", text, path.name)
            self.assertIn("Angela López Mendoza", text, path.name)

    def test_no_literal_bom_slipped_into_the_router(self):
        # A literal U+FEFF inside a regex trips no-irregular-whitespace (it did, once).
        self.assertIsNone(re.search(chr(0xFEFF), _read(ROUTER)))


if __name__ == "__main__":
    unittest.main()
