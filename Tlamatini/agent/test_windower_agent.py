# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Windower workflow agent.

Windower is the window manager of the desktop-UI trio (Windower=the window
itself, Mouser=clicks-inside, Keyboarder=types-into). It is a standalone pool
agent under ``agent/agents/windower/`` that runs as a separate Python
subprocess, so — exactly like the De-Compresser / Ender / Parametrizer test
modules — it is loaded through ``importlib.util.spec_from_file_location`` with
a cwd save/restore so its module-level ``os.chdir`` + ``open(LOG_FILE_PATH)``
side effects land in its own directory.

The agent talks to the Win32 API (pywin32 win32gui/win32con/win32process +
ctypes). Tests NEVER touch real windows: ``enum_windows`` and the win32 call
surface are mocked, so every action verb, the cross-process ``bring_to_front``
focus-transfer dance (ported from Microsoft's Windows-MCP), the arrange/tile
geometry math, and the title-matching modes are exercised deterministically.

Covers:
- match_windows: substring / exact / regex / regex-fallback / empty-title-all
- compute_arrange_rect: every snap region + center + unknown-mode fallback
- _window_state: minimized / maximized / normal / hidden mapping
- bring_to_front: no-foreground / same-thread / full-AttachThreadInput paths
- dispatch: win32-unavailable, list, no-title, no-match (+fail_if_absent),
  and every action verb routing to the right Win32 primitive
- _emit_section: single atomic INI_SECTION_WINDOWER block, KV header + body
- main() end-stage: target_agents always started + exactly one section
- Registry integration: ChatWrappedAgentSpec, Exec Report row, contract
  discovery, Parametrizer fields, URL route, JS classMap, CSS gradient,
  config.yaml defaults
- Migration presence: Agent row (0093) + Tool row (0094)
"""

import importlib.util
import logging
import os
import tempfile
import unittest
from functools import lru_cache
from unittest.mock import MagicMock, patch

import yaml
from django.test import SimpleTestCase, TestCase


@lru_cache(maxsize=1)
def _load_windower_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'windower', 'windower.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_windower_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Windower module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        # Drop the file/console handlers the agent attaches to the root logger
        # on import so the wider test suite's stderr stays readable. Tests that
        # need to assert on log output attach their own handler to the root
        # logger (which still receives INFO records since basicConfig set the
        # root level to INFO).
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


_FAKE_WINDOWS = [
    {"hwnd": 0x00130C, "title": "Untitled - Notepad", "left": 10, "top": 20,
     "width": 800, "height": 600, "state": "normal", "pid": 4242},
    {"hwnd": 0x00220D, "title": "report.txt - Notepad", "left": 50, "top": 60,
     "width": 640, "height": 480, "state": "normal", "pid": 4243},
    {"hwnd": 0x00330E, "title": "Calculator", "left": 0, "top": 0,
     "width": 320, "height": 480, "state": "minimized", "pid": 4244},
]


# ---------------------------------------------------------------------------
# Title matching — pure function, no win32 needed
# ---------------------------------------------------------------------------


class MatchWindowsTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()

    def test_substring_is_case_insensitive_and_default(self):
        matched = self.win.match_windows(_FAKE_WINDOWS, "notepad", "substring")
        self.assertEqual([w["hwnd"] for w in matched], [0x00130C, 0x00220D])

    def test_exact_match_requires_full_title(self):
        matched = self.win.match_windows(_FAKE_WINDOWS, "calculator", "exact")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["title"], "Calculator")
        # A substring of the title must NOT match in exact mode.
        self.assertEqual(self.win.match_windows(_FAKE_WINDOWS, "Calc", "exact"), [])

    def test_regex_match(self):
        matched = self.win.match_windows(_FAKE_WINDOWS, r"^report.*Notepad$", "regex")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["hwnd"], 0x00220D)

    def test_invalid_regex_falls_back_to_substring(self):
        # An unterminated group is invalid regex; the agent must NOT crash —
        # it falls back to substring matching of the literal pattern.
        matched = self.win.match_windows(_FAKE_WINDOWS, "Calc(ulator", "regex")
        # 'Calc(ulator' is not a substring of any title, so substring fallback
        # yields no matches (and crucially does not raise).
        self.assertEqual(matched, [])

    def test_empty_title_returns_all_windows(self):
        matched = self.win.match_windows(_FAKE_WINDOWS, "", "substring")
        self.assertEqual(len(matched), len(_FAKE_WINDOWS))

    def test_no_match_returns_empty_list(self):
        self.assertEqual(self.win.match_windows(_FAKE_WINDOWS, "Firefox", "substring"), [])


# ---------------------------------------------------------------------------
# Arrange / tile geometry — pure math against a known work area
# ---------------------------------------------------------------------------


class ComputeArrangeRectTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()
        # Pin a deterministic 1920x1080 work area at origin.
        self._patch = patch.object(self.win, 'get_work_area', return_value=(0, 0, 1920, 1080))
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_left_and_right_halves(self):
        self.assertEqual(self.win.compute_arrange_rect("left", 0, 0), (0, 0, 960, 1080))
        self.assertEqual(self.win.compute_arrange_rect("right", 0, 0), (960, 0, 960, 1080))

    def test_top_and_bottom_halves(self):
        self.assertEqual(self.win.compute_arrange_rect("top", 0, 0), (0, 0, 1920, 540))
        self.assertEqual(self.win.compute_arrange_rect("bottom", 0, 0), (0, 540, 1920, 540))

    def test_quadrants(self):
        self.assertEqual(self.win.compute_arrange_rect("top-left", 0, 0), (0, 0, 960, 540))
        self.assertEqual(self.win.compute_arrange_rect("top-right", 0, 0), (960, 0, 960, 540))
        self.assertEqual(self.win.compute_arrange_rect("bottom-left", 0, 0), (0, 540, 960, 540))
        self.assertEqual(self.win.compute_arrange_rect("bottom-right", 0, 0), (960, 540, 960, 540))

    def test_full_fills_work_area(self):
        self.assertEqual(self.win.compute_arrange_rect("full", 0, 0), (0, 0, 1920, 1080))

    def test_center_uses_requested_size_and_centres(self):
        # 1280x800 centred in 1920x1080 -> x=(1920-1280)/2=320, y=(1080-800)/2=140
        self.assertEqual(self.win.compute_arrange_rect("center", 1280, 800), (320, 140, 1280, 800))

    def test_underscore_alias_normalizes_to_hyphen(self):
        self.assertEqual(
            self.win.compute_arrange_rect("top_left", 0, 0),
            self.win.compute_arrange_rect("top-left", 0, 0),
        )

    def test_unknown_mode_defaults_to_left(self):
        self.assertEqual(
            self.win.compute_arrange_rect("diagonal", 0, 0),
            self.win.compute_arrange_rect("left", 0, 0),
        )


# ---------------------------------------------------------------------------
# Window-state classification
# ---------------------------------------------------------------------------


class WindowStateTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()

    def _state_with(self, iconic, zoomed, visible):
        fake = MagicMock()
        fake.IsIconic.return_value = iconic
        fake.IsWindowVisible.return_value = visible
        # The hardened impl detects maximized via GetWindowPlacement()[1]
        # (showCmd) — present in every pywin32 build — not win32gui.IsZoomed
        # (which pywin32 311 does not export). Mirror that here.
        show_cmd = self.win.SW_MAXIMIZE if zoomed else self.win.SW_SHOWNORMAL
        fake.GetWindowPlacement.return_value = (0, show_cmd, (0, 0), (-1, -1), (0, 0, 100, 100))
        fake.IsZoomed.return_value = zoomed
        with patch.object(self.win, 'win32gui', fake):
            return self.win._window_state(0xABCD)

    def test_minimized(self):
        self.assertEqual(self._state_with(True, False, True), "minimized")

    def test_maximized(self):
        self.assertEqual(self._state_with(False, True, True), "maximized")

    def test_normal(self):
        self.assertEqual(self._state_with(False, False, True), "normal")

    def test_hidden(self):
        self.assertEqual(self._state_with(False, False, False), "hidden")

    def test_maximized_detected_without_win32gui_iszoomed(self):
        # REGRESSION: pywin32 311 does NOT export win32gui.IsZoomed. The state
        # classifier must still report 'maximized' purely via GetWindowPlacement.
        # `spec=` makes hasattr(win32gui, 'IsZoomed') False, matching pywin32 311.
        fake = MagicMock(spec=['IsIconic', 'IsWindowVisible', 'GetWindowPlacement'])
        fake.IsIconic.return_value = False
        fake.IsWindowVisible.return_value = True
        fake.GetWindowPlacement.return_value = (0, self.win.SW_MAXIMIZE, (0, 0), (-1, -1), (0, 0, 100, 100))
        self.assertFalse(hasattr(fake, 'IsZoomed'))
        with patch.object(self.win, 'win32gui', fake):
            self.assertEqual(self.win._window_state(0xABCD), 'maximized')

    def test_is_maximized_ctypes_fallback_is_hwnd_safe(self):
        # Last-resort path: GetWindowPlacement raises AND win32gui has no
        # IsZoomed -> fall back to a ctypes user32.IsZoomed call that is
        # HWND-typed so a 64-bit handle is never truncated.
        fake_gui = MagicMock(spec=['GetWindowPlacement'])
        fake_gui.GetWindowPlacement.side_effect = RuntimeError('no placement')
        fake_ct = MagicMock()
        fake_ct.windll.user32.IsZoomed.return_value = 1
        with patch.object(self.win, 'win32gui', fake_gui), \
             patch.object(self.win, 'ctypes', fake_ct), \
             patch.object(self.win, '_CTYPES_OK', True):
            self.assertTrue(self.win._is_maximized(0x123456789))  # 64-bit handle
        # argtypes/restype were declared so ctypes marshals the HWND correctly.
        self.assertEqual(fake_ct.windll.user32.IsZoomed.restype, fake_ct.c_int)


# ---------------------------------------------------------------------------
# bring_to_front — the ported Windows-MCP AttachThreadInput focus dance
# ---------------------------------------------------------------------------


class BringToFrontTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()
        self.g = MagicMock()          # win32gui
        self.proc = MagicMock()       # win32process
        # Default: target is not minimized.
        self.g.IsIconic.return_value = False
        self.g.IsWindow.return_value = True
        self._patches = [
            patch.object(self.win, 'win32gui', self.g),
            patch.object(self.win, 'win32process', self.proc),
            patch.object(self.win, '_current_thread_id', return_value=1000),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_restores_minimized_window_first(self):
        self.g.IsIconic.return_value = True
        self.g.GetForegroundWindow.return_value = 0  # no valid foreground
        self.g.IsWindow.side_effect = lambda h: h != 0
        self.win.bring_to_front(0x55)
        self.g.ShowWindow.assert_any_call(0x55, self.win.SW_RESTORE)

    def test_no_valid_foreground_uses_direct_path(self):
        self.g.GetForegroundWindow.return_value = 0
        self.g.IsWindow.side_effect = lambda h: h != 0
        self.win.bring_to_front(0x55)
        self.g.SetForegroundWindow.assert_called_once_with(0x55)
        self.g.BringWindowToTop.assert_called_once_with(0x55)
        self.proc.AttachThreadInput.assert_not_called()

    def test_same_thread_skips_attach_dance(self):
        self.g.GetForegroundWindow.return_value = 0x99
        self.g.IsWindow.return_value = True
        # Foreground and target live on the SAME thread -> no attach needed.
        self.proc.GetWindowThreadProcessId.return_value = (2000, 4242)
        self.win.bring_to_front(0x55)
        self.proc.AttachThreadInput.assert_not_called()
        self.g.SetForegroundWindow.assert_called_once_with(0x55)

    def test_cross_thread_runs_attach_then_detach(self):
        self.g.GetForegroundWindow.return_value = 0x99
        self.g.IsWindow.return_value = True
        # Foreground thread (2000) != target thread (3000) != our tid (1000).
        self.proc.GetWindowThreadProcessId.side_effect = [(2000, 1), (3000, 2)]
        self.win.bring_to_front(0x55)
        # Both foreign threads attached True then detached False.
        attach_calls = self.proc.AttachThreadInput.call_args_list
        self.assertIn(((1000, 2000, True),), [(c.args,) for c in attach_calls])
        self.assertIn(((1000, 3000, True),), [(c.args,) for c in attach_calls])
        self.assertIn(((1000, 2000, False),), [(c.args,) for c in attach_calls])
        self.assertIn(((1000, 3000, False),), [(c.args,) for c in attach_calls])
        self.g.SetForegroundWindow.assert_called_with(0x55)
        self.g.SetWindowPos.assert_called_once()


# ---------------------------------------------------------------------------
# dispatch() — full action routing, all dependencies mocked
# ---------------------------------------------------------------------------


class DispatchTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()
        self.g = MagicMock()
        self.g.GetWindowRect.return_value = (100, 200, 1380, 1000)  # -> 1280x800 @ (100,200)
        self._patches = [
            patch.object(self.win, 'enum_windows', return_value=list(_FAKE_WINDOWS)),
            patch.object(self.win, 'win32gui', self.g),
            patch.object(self.win, '_window_state', return_value='normal'),
            patch.object(self.win, 'bring_to_front', return_value=True),
            patch.object(self.win, 'set_window_pos'),
            patch.object(self.win, 'set_topmost'),
            patch.object(self.win, 'close_window'),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _run(self, **cfg):
        return self.win.dispatch(cfg)

    def test_win32_unavailable_short_circuits(self):
        with patch.object(self.win, '_WIN32_OK', False):
            res = self._run(action='focus', window_title='Notepad')
        self.assertFalse(res["ok"])
        self.assertEqual(res["outcome"]["state"], "win32_unavailable")

    def test_list_enumerates_all_windows(self):
        res = self._run(action='list')
        self.assertTrue(res["ok"])
        self.assertEqual(res["outcome"]["matched"], "true")
        self.assertEqual(res["outcome"]["match_count"], len(_FAKE_WINDOWS))
        self.assertIn("Notepad", res["body"])

    def test_list_with_filter(self):
        res = self._run(action='list', window_title='Calculator')
        self.assertEqual(res["outcome"]["match_count"], 1)

    def test_missing_window_title_is_reported(self):
        res = self._run(action='focus', window_title='')
        self.assertEqual(res["outcome"]["state"], "no_window_title")
        # ok is True (soft) when fail_if_absent is not set.
        self.assertTrue(res["ok"])

    def test_no_match_soft_by_default(self):
        res = self._run(action='focus', window_title='Firefox')
        self.assertEqual(res["outcome"]["state"], "no_match")
        self.assertEqual(res["outcome"]["matched"], "false")
        self.assertTrue(res["ok"])

    def test_no_match_hard_when_fail_if_absent(self):
        res = self._run(action='focus', window_title='Firefox', fail_if_absent=True)
        self.assertFalse(res["ok"])

    def test_focus_calls_bring_to_front(self):
        res = self._run(action='focus', window_title='Untitled')
        self.win.bring_to_front.assert_called_once_with(0x00130C)
        self.assertEqual(res["outcome"]["matched"], "true")
        self.assertEqual(res["outcome"]["window_title"], "Untitled - Notepad")

    def test_minimize_maximize_restore_call_showwindow(self):
        self._run(action='minimize', window_title='Calculator')
        self.g.ShowWindow.assert_any_call(0x00330E, self.win.SW_MINIMIZE)
        self.g.reset_mock()
        self._run(action='maximize', window_title='Calculator')
        self.g.ShowWindow.assert_any_call(0x00330E, self.win.SW_MAXIMIZE)
        self.g.reset_mock()
        self._run(action='restore', window_title='Calculator')
        self.g.ShowWindow.assert_any_call(0x00330E, self.win.SW_RESTORE)

    def test_move_passes_position_only(self):
        self._run(action='move', window_title='Calculator', pos_x=300, pos_y=400)
        _args, kwargs = self.win.set_window_pos.call_args
        self.assertEqual(kwargs.get('x'), 300)
        self.assertEqual(kwargs.get('y'), 400)
        self.assertNotIn('w', kwargs)

    def test_resize_passes_size_only(self):
        self._run(action='resize', window_title='Calculator', width=1024, height=768)
        _args, kwargs = self.win.set_window_pos.call_args
        self.assertEqual(kwargs.get('w'), 1024)
        self.assertEqual(kwargs.get('h'), 768)
        self.assertNotIn('x', kwargs)

    def test_move_resize_restores_then_sets_all(self):
        self._run(action='move_resize', window_title='Calculator',
                  pos_x=5, pos_y=6, width=700, height=500)
        self.g.ShowWindow.assert_any_call(0x00330E, self.win.SW_RESTORE)
        _args, kwargs = self.win.set_window_pos.call_args
        self.assertEqual((kwargs.get('x'), kwargs.get('y'), kwargs.get('w'), kwargs.get('h')),
                         (5, 6, 700, 500))

    def test_close_posts_wm_close(self):
        self._run(action='close', window_title='Calculator')
        self.win.close_window.assert_called_once_with(0x00330E)

    def test_topmost_and_untopmost(self):
        self._run(action='topmost', window_title='Calculator')
        self.win.set_topmost.assert_called_with(0x00330E, True)
        self._run(action='untopmost', window_title='Calculator')
        self.win.set_topmost.assert_called_with(0x00330E, False)

    def test_arrange_uses_computed_rect(self):
        with patch.object(self.win, 'compute_arrange_rect', return_value=(0, 0, 960, 1080)) as car:
            self._run(action='arrange', window_title='Calculator', arrange_mode='left')
        car.assert_called_once()
        _args, kwargs = self.win.set_window_pos.call_args
        self.assertEqual((kwargs.get('x'), kwargs.get('y'), kwargs.get('w'), kwargs.get('h')),
                         (0, 0, 960, 1080))

    def test_unknown_action_is_rejected(self):
        res = self._run(action='teleport', window_title='Calculator')
        self.assertFalse(res["ok"])
        self.assertEqual(res["outcome"]["state"], "unknown_action")

    def test_match_index_out_of_range_falls_back_to_zero(self):
        res = self._run(action='focus', window_title='Notepad', match_index=99)
        # Two Notepad windows match; index 99 is clamped to 0 (first match).
        self.win.bring_to_front.assert_called_once_with(0x00130C)
        self.assertEqual(res["outcome"]["window_title"], "Untitled - Notepad")

    def test_match_index_selects_specific_window(self):
        self._run(action='focus', window_title='Notepad', match_index=1)
        self.win.bring_to_front.assert_called_once_with(0x00220D)

    def test_outcome_geometry_reread_after_op(self):
        res = self._run(action='maximize', window_title='Calculator')
        # GetWindowRect (100,200,1380,1000) -> left/top/width/height
        self.assertEqual(res["outcome"]["left"], 100)
        self.assertEqual(res["outcome"]["top"], 200)
        self.assertEqual(res["outcome"]["width"], 1280)
        self.assertEqual(res["outcome"]["height"], 800)
        self.assertEqual(res["outcome"]["state"], "normal")


# ---------------------------------------------------------------------------
# Structured-output emission
# ---------------------------------------------------------------------------


class EmitSectionTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()

    def test_emits_single_atomic_block_with_header_and_body(self):
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = _H()
        logging.getLogger().addHandler(h)
        try:
            self.win._emit_section(
                {"action": "focus", "window_title": "Notepad", "matched": "true"},
                "Focused 'Untitled - Notepad'.",
            )
        finally:
            logging.getLogger().removeHandler(h)

        blocks = [r for r in records if "INI_SECTION_WINDOWER" in r]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIn("INI_SECTION_WINDOWER<<<", block)
        self.assertIn(">>>END_SECTION_WINDOWER", block)
        self.assertIn("action: focus", block)
        self.assertIn("window_title: Notepad", block)
        self.assertIn("Focused 'Untitled - Notepad'.", block)


# ---------------------------------------------------------------------------
# main() end-stage contract — target_agents always start, one section per run
# ---------------------------------------------------------------------------


class MainEndStageTests(SimpleTestCase):
    def setUp(self):
        self.win = _load_windower_module()
        self.tmp = tempfile.mkdtemp()
        self.cwd_before = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture_main(self, cfg_dict):
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)

        started = []
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _H()
        logging.getLogger().addHandler(handler)

        g = MagicMock()
        g.GetWindowRect.return_value = (100, 200, 1380, 1000)
        exit_code = None
        with patch.object(self.win, 'enum_windows', return_value=list(_FAKE_WINDOWS)), \
             patch.object(self.win, 'win32gui', g), \
             patch.object(self.win, '_window_state', return_value='normal'), \
             patch.object(self.win, 'bring_to_front', return_value=True), \
             patch.object(self.win, 'set_window_pos'), \
             patch.object(self.win, 'set_topmost'), \
             patch.object(self.win, 'close_window'), \
             patch.object(self.win, '_WIN32_OK', True), \
             patch.object(self.win, 'start_agent', side_effect=lambda n: (started.append(n) or True)), \
             patch.object(self.win, 'wait_for_agents_to_stop'), \
             patch.object(self.win, 'time') as time_mock:
            time_mock.sleep = lambda _s: None
            try:
                self.win.main()
            except SystemExit as e:
                exit_code = e.code

        logging.getLogger().removeHandler(handler)
        return exit_code, started, records

    def test_targets_started_and_single_section_on_success(self):
        code, started, records = self._capture_main({
            'action': 'focus',
            'window_title': 'Untitled',
            'target_agents': ['keyboarder_1', 'shoter_1'],
        })
        self.assertEqual(started, ['keyboarder_1', 'shoter_1'])
        blocks = [r for r in records if 'INI_SECTION_WINDOWER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_WINDOWER', blocks[0])
        self.assertEqual(code, 0)

    def test_targets_started_even_when_no_window_matches(self):
        code, started, records = self._capture_main({
            'action': 'focus',
            'window_title': 'NoSuchWindowEver',
            'target_agents': ['downstream_1'],
        })
        # Soft no-op: chain is never stranded.
        self.assertEqual(started, ['downstream_1'])
        self.assertEqual(code, 0)
        self.assertTrue(any('matched: false' in r for r in records))

    def test_fail_if_absent_exits_nonzero_but_still_starts_targets(self):
        code, started, _ = self._capture_main({
            'action': 'focus',
            'window_title': 'NoSuchWindowEver',
            'fail_if_absent': True,
            'target_agents': ['downstream_1'],
        })
        # Hard fail exit code, yet downstream still launched first.
        self.assertEqual(code, 1)
        self.assertEqual(started, ['downstream_1'])

    def test_list_action_emits_section_and_starts_targets(self):
        code, started, records = self._capture_main({
            'action': 'list',
            'target_agents': ['logger_1'],
        })
        self.assertEqual(started, ['logger_1'])
        blocks = [r for r in records if 'INI_SECTION_WINDOWER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# Registry integration — pins every wiring step in the agent-creation recipe
# ---------------------------------------------------------------------------


class RegistryIntegrationTests(SimpleTestCase):
    def test_chat_wrapped_agent_spec_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_windower')
        self.assertIsNotNone(spec, "chat_agent_windower must be registered")
        self.assertEqual(spec.key, 'windower')
        self.assertEqual(spec.template_dir, 'windower')
        self.assertEqual(spec.tool_description, 'Chat-Agent-Windower')
        self.assertEqual(spec.display_name, 'Windower')

    def test_exec_report_tool_row_is_registered(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get('chat_agent_windower'), ('windower', 'Windower'))

    def test_agent_contract_disk_discovery_picks_up_windower(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('windower')
        self.assertEqual(contract.agent_type, 'windower')
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')
        self.assertFalse(contract.never_starts_targets)

    def test_parametrizer_fields_registered(self):
        from agent.services.agent_contracts import get_parametrizer_source_fields
        fields = get_parametrizer_source_fields().get('windower')
        self.assertIsNotNone(fields)
        for expected in ('action', 'window_title', 'matched', 'state',
                         'left', 'top', 'width', 'height', 'response_body'):
            self.assertIn(expected, fields)

    def test_url_route_exists(self):
        from django.urls import reverse
        url = reverse('update_windower_connection', kwargs={'agent_name': 'windower-1'})
        self.assertIn('update_windower_connection', url)

    def test_canvas_classmap_contains_windower(self):
        js_path = os.path.join(os.path.dirname(__file__), 'static', 'agent', 'js', 'acp-canvas-core.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js_source = f.read()
        self.assertIn("'windower': 'windower-agent'", js_source)

    def test_css_gradient_is_unique(self):
        css_path = os.path.join(os.path.dirname(__file__), 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as f:
            css_source = f.read()
        gradient = '#0F2C4D 0%, #1E6FB8 33%, #4FC3F7 66%, #E1F5FE 100%'
        self.assertEqual(css_source.count(gradient), 1,
                         "The Windower canvas gradient must be unique to its rule")

    def test_config_yaml_defaults(self):
        cfg_path = os.path.join(os.path.dirname(__file__), 'agents', 'windower', 'config.yaml')
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg.get('action'), 'focus')
        self.assertEqual(cfg.get('match_mode'), 'substring')
        self.assertEqual(cfg.get('match_index'), 0)
        self.assertTrue(cfg.get('activate_after'))
        self.assertFalse(cfg.get('fail_if_absent'))
        self.assertEqual(cfg.get('target_agents'), [])


class MigrationPresenceTests(TestCase):
    def test_agent_row_seeded_by_migration_0093(self):
        from agent.models import Agent
        self.assertTrue(
            Agent.objects.filter(agentDescription='Windower').exists(),
            "Migration 0093 must seed an Agent row with agentDescription='Windower'",
        )

    def test_tool_row_seeded_by_migration_0094(self):
        from agent.models import Tool
        self.assertTrue(
            Tool.objects.filter(toolDescription='Chat-Agent-Windower').exists(),
            "Migration 0094 must seed a Tool row with toolDescription='Chat-Agent-Windower'",
        )


if __name__ == '__main__':
    unittest.main()
