# -*- coding: utf-8 -*-
"""Pins the AGENT DISPLAY-NAME contract (Angela, 2026-07-26).

WHY THIS FILE EXISTS
--------------------
``AgentConfig.ready()`` DELETES the whole ``Agent`` table on every startup and
rebuilds it from the ``agents/`` folder listing. So the name that function
computes IS the display name the sidebar renders verbatim — a migration's
``agentDescription`` is overwritten on the very next launch. The old logic was
``str.title()`` + five ad-hoc overrides, and it shipped two live defects:

1. 22 of 86 agents were mis-cased — "Pdfer" (not PDFer), "Sqler", "Ssher",
   "Esp32Er", "Videoplayer", "Flowcreator", ... violating the naming convention.
2. Six agents got SPACED names although ``acp-canvas-core.js`` lowercases the
   display name WITHOUT collapsing spaces and only ever tests the HYPHENATED
   literal — so Kyber-KeyGen / Kyber-Cipher / Kyber-DeCipher / J-Decompiler /
   Video-Analyzer / De-Compresser canvas connections were silently never saved.

The fix routes the boot repopulate through the single source of truth,
``services.agent_paths.display_name_from_agent_type``. These tests fail if
anyone reverts to ``.title()`` or adds an agent whose display name the canvas
cannot match.
"""
import os
import re

from django.test import SimpleTestCase

from agent.apps import _canonical_agent_display_name
from agent.services.agent_paths import display_name_from_agent_type

_AGENT_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENTS_DIR = os.path.join(_AGENT_APP_DIR, 'agents')
_JS_DIR = os.path.join(_AGENT_APP_DIR, 'static', 'agent', 'js')
_APPS_PY = os.path.join(_AGENT_APP_DIR, 'apps.py')

# The canvas compares a DISPLAY name lowercased, WITHOUT collapsing whitespace.
_CONNECTION_LITERAL_RE = re.compile(
    r"(?:target|source)AgentName\.toLowerCase\(\)\s*===\s*'([^']+)'")
_FLW_CASE_RE = re.compile(r"case\s+'([a-z0-9 _-]+)':\s*await\s+update", re.I)


def _agent_folders():
    if not os.path.isdir(_AGENTS_DIR):          # pragma: no cover - dev safety
        return []
    return sorted(
        name for name in os.listdir(_AGENTS_DIR)
        if os.path.isdir(os.path.join(_AGENTS_DIR, name))
        and name.lower() not in ('pools', '__pycache__')
    )


def _canvas_connection_literals():
    literals = set()
    if not os.path.isdir(_JS_DIR):              # pragma: no cover - dev safety
        return literals
    for name in os.listdir(_JS_DIR):
        if not name.endswith('.js'):
            continue
        with open(os.path.join(_JS_DIR, name), encoding='utf-8', errors='replace') as fh:
            body = fh.read()
        literals.update(_CONNECTION_LITERAL_RE.findall(body))
        literals.update(m.lower() for m in _FLW_CASE_RE.findall(body))
    return literals


def _normalize(value):
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


class AgentDisplayNameContractTests(SimpleTestCase):
    """The boot repopulate must produce canvas-correct, convention-correct names."""

    # Names that were provably wrong before the fix. Locked one by one so a
    # regression names the exact agent it broke.
    EXPECTED = {
        'pdfer': 'PDFer',
        'latexer': 'LaTeXer',
        'sqler': 'SQLer',
        'ssher': 'SSHer',
        'pser': 'PSer',
        'scper': 'SCPer',
        'acpxer': 'ACPXer',
        'stm32er': 'STM32er',
        'esp32er': 'ESP32er',
        'esphomer': 'ESPHomer',
        'audioplayer': 'AudioPlayer',
        'videoplayer': 'VideoPlayer',
        'flowcreator': 'FlowCreator',
        'flowhypervisor': 'FlowHypervisor',
        'flowbacker': 'FlowBacker',
        'teletlamatini': 'TeleTlamatini',
        'recmailer': 'RecMailer',
        'mcp_doctor': 'MCP Doctor',
        'video_analyzer': 'Video-Analyzer',
        'netspeed_calculator': 'NetSpeed-Calculator',
        'de_compresser': 'De-Compresser',
        'j_decompiler': 'J-Decompiler',
        'kyber_keygen': 'Kyber-KeyGen',
        'kyber_cipher': 'Kyber-Cipher',
        'kyber_decipher': 'Kyber-DeCipher',
        'node_manager': 'Node Manager',
        # Fixed 2026-07-26 in BOTH agent_paths AND chat_agent_registry:
        'file_creator': 'File-Creator',
        'file_extractor': 'File-Extractor',
        'file_interpreter': 'File-Interpreter',
        'image_interpreter': 'Image-Interpreter',
        'monitor_log': 'Monitor-Log',
        'and': 'AND',
        'or': 'OR',
    }

    def test_pdfer_is_exactly_PDFer(self):
        """The bug Angela hit: the canvas showed 'Pdfer'."""
        self.assertEqual(_canonical_agent_display_name('pdfer', 'Pdfer'), 'PDFer')
        self.assertEqual(display_name_from_agent_type('pdfer'), 'PDFer')

    def test_latexer_is_exactly_LaTeXer(self):
        """LaTeX is written L-a-T-e-X, so the agent is 'LaTeXer'.

        str.title() renders 'Latexer', which is why agents/latexer MUST carry an
        explicit override in display_name_from_agent_type. Every other casing is
        wrong on the canvas, in the sidebar and in the Configure-Agents gate.
        """
        self.assertEqual(_canonical_agent_display_name('latexer', 'Latexer'), 'LaTeXer')
        self.assertEqual(display_name_from_agent_type('latexer'), 'LaTeXer')
        for wrong in ('Latexer', 'LaTexer', 'LATEXER', 'latexer', 'Latexer '):
            self.assertNotEqual(display_name_from_agent_type('latexer'), wrong)

    def test_known_display_names_are_exact(self):
        for folder, expected in self.EXPECTED.items():
            with self.subTest(folder=folder):
                self.assertEqual(
                    _canonical_agent_display_name(folder, 'FALLBACK'), expected,
                    "boot repopulate would render %r for agents/%s" % (
                        _canonical_agent_display_name(folder, 'FALLBACK'), folder))

    # NOTE: the 2026-07-26 second pass closed the last hyphen gap
    # (file_creator / file_extractor / file_interpreter / image_interpreter /
    # monitor_log) by changing agent_paths AND chat_agent_registry TOGETHER,
    # so the enable gate agent_<display>_status keeps matching. There is no
    # allow-list any more: EVERY agent must be matchable by the canvas.

    def test_no_display_name_is_str_title_mangled(self):
        """str.title() capitalises after a digit ('stm32er' -> 'Stm32Er')."""
        for folder in _agent_folders():
            name = _canonical_agent_display_name(folder, folder)
            with self.subTest(folder=folder):
                self.assertNotIn('32Er', name)

    def test_every_agent_is_matchable_by_the_canvas(self):
        """THE hyphen bug: a spaced name can never match a hyphen-only literal.

        For every agent that the canvas has connection handlers for, its exact
        lowercased display name MUST be one of the literals the JS tests.
        """
        literals = _canvas_connection_literals()
        self.assertTrue(literals, "no canvas connection literals parsed")
        by_norm = {}
        for literal in literals:
            by_norm.setdefault(_normalize(literal), set()).add(literal)

        unmatched = []
        for folder in _agent_folders():
            name = _canonical_agent_display_name(folder, folder)
            candidates = by_norm.get(_normalize(name))
            if not candidates:
                continue                      # canvas has no handler for this agent
            if name.lower() not in candidates:
                unmatched.append(
                    "agents/%s -> %r (canvas only accepts %s)"
                    % (folder, name, sorted(candidates)))
        self.assertEqual(
            [], unmatched,
            "these display names can NEVER match their canvas connection "
            "handler, so the wiring is silently dropped:\n  " + "\n  ".join(unmatched))

    def test_boot_repopulate_calls_the_canonical_resolver(self):
        """Source contract: apps.py must not go back to inline .title()."""
        with open(_APPS_PY, encoding='utf-8') as fh:
            body = fh.read()
        self.assertIn('_canonical_agent_display_name(', body)
        self.assertIn('display_name_from_agent_type', body)

    def test_resolver_is_fail_open(self):
        """An unknown folder must still yield a usable name, never an exception."""
        self.assertEqual(
            _canonical_agent_display_name('totally_unknown_agent', 'Fallback'),
            'Totally Unknown Agent')
        self.assertEqual(_canonical_agent_display_name('', 'Fallback'), 'Fallback')

    def test_registry_display_names_match_the_canonical_resolver(self):
        """The DB row and chat_agent_registry MUST agree for the hyphen-fixed set.

        They drive two different things - the canvas connection handler (DB row)
        and the per-agent enable gate ``agent_<display>_status`` (registry). If
        they disagree, unchecking the agent in Configure Agents silently stops
        working, which is why the 2026-07-26 pass changed both together.
        """
        import re
        src_path = os.path.join(_AGENT_APP_DIR, 'chat_agent_registry.py')
        with open(src_path, encoding='utf-8') as fh:
            src = fh.read()
        registry = {}
        for block in src.split('ChatWrappedAgentSpec(')[1:]:
            td = re.search(r'template_dir\s*=\s*"([^"]+)"', block)
            dn = re.search(r'display_name\s*=\s*"([^"]+)"', block)
            if td and dn:
                registry[td.group(1)] = dn.group(1)
        for folder in ('file_creator', 'file_extractor', 'file_interpreter',
                       'image_interpreter', 'monitor_log', 'video_analyzer',
                       'de_compresser', 'pdfer', 'latexer', 'stm32er', 'esp32er',
                       'esphomer', 'audioplayer', 'videoplayer',
                       'netspeed_calculator'):
            if folder not in registry:
                continue
            with self.subTest(folder=folder):
                self.assertEqual(
                    registry[folder],
                    _canonical_agent_display_name(folder, registry[folder]),
                    "chat_agent_registry says %r but the canvas/DB name is %r"
                    % (registry[folder],
                       _canonical_agent_display_name(folder, registry[folder])))

    def _live_display_names(self):
        return {_canonical_agent_display_name(f, f) for f in _agent_folders()}

    def test_css_data_content_selectors_match_live_display_names(self):
        """The sidebar CSS keys some rules on the EXACT display name.

        `.agent-tool-item[data-content="X"]` is a CSS attribute selector and its
        value is CASE-SENSITIVE, so a renamed agent silently stops matching. (The
        icon colour itself comes from `.canvas-item.<x>-agent` via
        getAgentToolIconStyle(), which is casing-proof — but these rules must not
        be left pointing at names that no longer exist.)
        """
        css_path = os.path.join(_AGENT_APP_DIR, 'static', 'agent', 'css',
                                'agentic_control_panel.css')
        with open(css_path, encoding='utf-8') as fh:
            css = fh.read()
        live = self._live_display_names()
        stale = sorted({v for v in re.findall(
            r'\.agent-tool-item\[data-content="([^"]+)"\]', css) if v not in live})
        self.assertEqual(
            [], stale,
            "these data-content selectors name agents that no longer exist: %s" % stale)

    def test_agent_purpose_map_keys_match_live_display_names(self):
        """agent_page_chat.js::_agentPurpose is keyed by the canonical name.

        A stale key means the generated .flw node gets no agentPurpose text.
        """
        js_path = os.path.join(_JS_DIR, 'agent_page_chat.js')
        with open(js_path, encoding='utf-8') as fh:
            js = fh.read()
        start = js.find('function _agentPurpose')
        self.assertGreater(start, 0, '_agentPurpose not found')
        block = js[start:js.find('\n}', start)]
        live = self._live_display_names()
        stale = sorted({k for k in re.findall(r"^\s*'([^']+)':\s*'", block, re.M)
                        if k not in live})
        self.assertEqual(
            [], stale,
            "these _agentPurpose keys name agents that no longer exist: %s" % stale)
