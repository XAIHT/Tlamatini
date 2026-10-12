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
    STYLESHEETS = ('agent_page.css', 'agentic_control_panel.css')

    def test_pill_is_the_vertical_pill_turned_on_its_side(self):
        for name in self.STYLESHEETS:
            css = (CSS / name).read_text(encoding='utf-8')
            pill = _rule(css, '#drag-divider::before')
            self.assertTrue(pill, f'{name}: #drag-divider::before is missing')
            for declaration in ('content: ""', 'top: calc(50% - 21px)', 'width: 4px',
                                'height: 42px', 'border-radius: 2px', 'background: #55BBAA'):
                self.assertIn(declaration, pill, f'{name}: pill lacks {declaration!r}')

    def test_chat_pill_matches_its_vertical_twin(self):
        css = (CSS / 'agent_page.css').read_text(encoding='utf-8')
        vertical = _rule(css, '#vertical-drag-divider::before')
        side = _rule(css, '#drag-divider::before')
        self.assertIn('width: 42px', vertical)
        self.assertIn('height: 4px', vertical)
        self.assertIn('width: 4px', side)
        self.assertIn('height: 42px', side)
        for shared in ('border-radius: 2px', 'background: #55BBAA', 'z-index: 1'):
            self.assertIn(shared, vertical)
            self.assertIn(shared, side)

    def test_line_turns_teal_on_hover_focus_and_drag(self):
        for name in self.STYLESHEETS:
            css = (CSS / name).read_text(encoding='utf-8')
            self.assertRegex(
                css, r'#drag-divider:hover::after,\s*#drag-divider:focus-visible::after,\s*'
                     r'body\.resizing #drag-divider::after\s*\{[^}]*background: #55BBAA;[^}]*opacity: 1;',
                f'{name}: the teal hover/focus/drag line is missing')
            ring = _rule(css, '#drag-divider:focus-visible')
            self.assertIn('outline: 2px solid #55BBAA', ring, name)
            self.assertIn('outline-offset: -2px', ring, name)

    def test_idle_line_is_unchanged(self):
        for name in self.STYLESHEETS:
            line = _rule((CSS / name).read_text(encoding='utf-8'), '#drag-divider::after')
            self.assertIn('background: #8a8c98', line, name)
            self.assertIn('opacity: 0.8', line, name)

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
