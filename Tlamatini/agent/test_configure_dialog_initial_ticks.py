# Tlamatini Author Banner — Angela López Mendoza
"""Configure Agents / Configure MCPs start from the rows the server sent.

Both dialogs used to draw every checkbox UNTICKED - they tested a field,
``enabled``, that the cached rows never carry (the rows hold ``content``,
'true'/'false') - and then ticked the boxes one HTTP request at a time, 85
requests in a row for the agents. A Continue pressed during that reload saved
most agents as OFF. Found on 2026-10-18 by scripts/agent_catalog_visible.py:
its photo showed 17 of 85 agents ticked while the database held all 85.
"""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

AGENT_DIR = Path(__file__).resolve().parent
SOURCE_JS = AGENT_DIR / "static" / "agent" / "js"
COLLECTED_JS = AGENT_DIR.parent / "staticfiles" / "agent" / "js"
FILES = ("agent_page_dialogs.js", "agent_page_init.js")


def _read(folder: Path, name: str) -> str:
    return (folder / name).read_text(encoding="utf-8")


class ConfigureDialogsStartFromServerRowsTests(SimpleTestCase):
    def test_agents_dialog_ticks_from_the_cached_row(self):
        self.assertIn("String(agent.content).toLowerCase() === 'true'",
                      _read(SOURCE_JS, "agent_page_dialogs.js"))

    def test_tools_dialog_ticks_from_the_cached_row(self):
        self.assertIn("String(tool.content).toLowerCase() === 'true'",
                      _read(SOURCE_JS, "agent_page_dialogs.js"))

    def test_continue_refreshes_the_cached_rows(self):
        init = _read(SOURCE_JS, "agent_page_init.js")
        self.assertIn("agent.content = checked ? 'true' : 'false'", init)
        self.assertIn("tool.content = checked ? 'true' : 'false'", init)

    def test_cached_rows_carry_content(self):
        # The premise of the two tests above: the establishment handlers store
        # the row's state under `content`. Renaming it silently unticks again.
        chat = _read(SOURCE_JS, "agent_page_chat.js")
        self.assertIn("content: agentContent", chat)
        self.assertIn("content: toolContent", chat)

    def test_collected_static_carries_the_same_fix(self):
        # A frozen build serves staticfiles/, not the source tree.
        if not COLLECTED_JS.is_dir():
            self.skipTest("staticfiles/ has not been collected in this checkout")
        for name in FILES:
            with self.subTest(name=name):
                self.assertEqual(_read(SOURCE_JS, name), _read(COLLECTED_JS, name))
