# Tlamatini Author Banner — Angela López Mendoza
"""#drag-divider has the same look and feel as #vertical-drag-divider (2026-10-11).

Angela asked for the side divider (chat <-> canvas, and the Agents / Operations
bar divider of the two panels) to look and behave like the composer's
#vertical-drag-divider: a teal grip pill in the middle, a line that turns teal on
hover, keyboard focus and drag, a teal focus ring, a tooltip, and Shift+arrow for
larger steps. These are SOURCE contracts; the visible proof that the pill is
really painted is scripts/drag_divider_look_visible.py.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

AGENT = Path(__file__).resolve().parent
CSS = AGENT / 'static' / 'agent' / 'css'
TEMPLATES = AGENT / 'templates' / 'agent'


def _rule(css, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    return match.group(1) if match else ''


class DragDividerLookTests(SimpleTestCase):
    def test_shared_pills_rotate_with_orientation(self):
        css = (CSS / 'ui_splitters.css').read_text(encoding='utf-8')
        side = _rule(css, ".tlm-splitter[aria-orientation='vertical']::before")
        across = _rule(css, ".tlm-splitter[aria-orientation='horizontal']::before")
        for declaration in ('width: 4px', 'height: 42px', 'top: calc(50% - 21px)'):
            self.assertIn(declaration, side)
        for declaration in ('width: 42px', 'height: 4px', 'left: calc(50% - 21px)'):
            self.assertIn(declaration, across)
        shared = _rule(css, '.tlm-splitter::before')
        self.assertIn('background: var(--tlm-accent)', shared)
        self.assertIn('border-radius: 2px', shared)

    def test_focus_hover_and_drag_share_the_accent(self):
        css = (CSS / 'ui_splitters.css').read_text(encoding='utf-8')
        active = _rule(css, '.tlm-splitter:is(:hover, :focus-visible, [data-resizing])::after')
        self.assertIn('background: var(--tlm-accent)', active)
        self.assertIn('outline-offset: -2px', _rule(css, '.tlm-splitter:focus-visible'))
        self.assertIn('--splitter-line: #8a8c98', css)

    def test_every_workspace_loads_shared_assets_before_the_dialog_theme(self):
        for name in ('agent_page.html', 'agentic_control_panel.html', 'prompt_flow_panel.html'):
            html = (TEMPLATES / name).read_text(encoding='utf-8')
            sheets = re.findall(r"agent/css/([A-Za-z0-9_]+\.css)' %}\?v=", html)
            self.assertLess(sheets.index('ui_splitters.css'), sheets.index('dialog_theme.css'), name)
            self.assertLess(html.index('ui_splitters.js'), html.index('flow-canvas-interactions.js') if 'flow-canvas-interactions.js' in html else html.index('agent_page_layout.js'), name)
            self.assertIn('class="tlm-splitter"', html)

    def test_every_drag_divider_is_an_accessible_separator_with_a_tooltip(self):
        for name in ('agent_page.html', 'agentic_control_panel.html', 'prompt_flow_panel.html'):
            html = (TEMPLATES / name).read_text(encoding='utf-8')
            tag = re.search(r'<div id="drag-divider"[^>]*>', html)
            self.assertIsNotNone(tag, name)
            tag = tag.group(0)
            for attribute in ('tabindex="0"', 'role="separator"', 'aria-orientation="vertical"',
                              'aria-label="', 'title="Drag to resize'):
                self.assertIn(attribute, tag, f'{name}: #drag-divider lacks {attribute}')
            self.assertIn('Shift for larger steps', tag, name)

    def test_chat_divider_shift_arrow_moves_five_steps(self):
        js = (AGENT / 'static' / 'agent' / 'js' / 'agent_page_layout.js').read_text(encoding='utf-8')
        block = js[js.index("// --- Horizontal drag divider"):js.index("// --- Vertical drag divider")]
        self.assertIn('const step = e.shiftKey ? 5 : 1;', block)
        self.assertIn('apply(seamPct - step)', block)
        self.assertIn('apply(seamPct + step)', block)
