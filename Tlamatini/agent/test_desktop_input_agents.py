"""Desktop-input regressions. All native input/window operations are mocked."""

import ctypes
import ast
import importlib.util
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch


ROOT = Path(__file__).parent


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COORDS = load_file('test_mouser_coordinates', ROOT / 'agents/mouser/mouser_coordinates.py')
INPUT = load_file('test_keyboarder_input', ROOT / 'agents/keyboarder/keyboarder_input.py')


def load_agent(name):
    fake = MagicMock()
    fake.FailSafeException = type('FailSafeException', (Exception,), {})
    fake.ImageNotFoundException = type('ImageNotFoundException', (Exception,), {})
    helpers = {'pyautogui': fake, 'mouser_coordinates': COORDS, 'keyboarder_input': INPUT}
    with (patch.dict(sys.modules, helpers), patch.object(COORDS, 'configure_dpi_awareness'),
          patch.object(os, 'chdir'), patch('builtins.open', mock_open()),
          patch.object(logging, 'basicConfig'), patch.object(logging.getLogger(), 'addHandler'),
          patch.object(subprocess, '_conhost_guard_applied', True, create=True)):
        return load_file(f'test_{name}_agent', ROOT / f'agents/{name}/{name}.py')


GEOMETRY = {'left': -1920, 'top': 0, 'width': 4480, 'height': 1440,
            'monitors': [(-1920, 0, 0, 1080), (0, 0, 2560, 1440)]}


class CoordinateTests(unittest.TestCase):
    def test_physical_negative_screen_position(self):
        self.assertEqual(COORDS.resolve_point(-1500, 400, {}, GEOMETRY), (-1500, 400))

    def test_desktop_origin_is_not_primary_origin(self):
        self.assertEqual(COORDS.resolve_point(20, 30, {'coordinate_space': 'desktop'}, GEOMETRY),
                         (-1900, 30))

    def test_resized_screenshot_maps_to_physical_desktop(self):
        config = dict(coordinate_space='screenshot', capture_left=-1920, capture_top=0,
                      capture_width=4480, capture_height=1440, image_width=2240, image_height=720)
        self.assertEqual(COORDS.resolve_point(480, 270, config, GEOMETRY), (-960, 540))

    def test_cropped_screenshot_uses_its_own_physical_origin(self):
        config = dict(coordinate_space='screenshot', capture_left=400, capture_top=200,
                      capture_width=600, capture_height=300, image_width=300, image_height=150)
        self.assertEqual(COORDS.resolve_point(100, 50, config, GEOMETRY), (600, 300))

    def test_window_client_normalized_bounds(self):
        self.assertEqual(COORDS.resolve_point(1, 1, {'coordinate_space': 'window_normalized'},
                                             GEOMETRY, (100, 200, 600, 400)), (699, 599))

    def test_window_pixels_use_client_origin(self):
        self.assertEqual(COORDS.resolve_point(20, 30, {'coordinate_space': 'window'},
                                             GEOMETRY, (-900, 150, 800, 600)), (-880, 180))

    def test_monitor_gap_and_invalid_coordinates_are_refused(self):
        for x, y, cfg in [(-1000, 1200, {}), (float('nan'), 0, {}),
                          (1.1, 0.5, {'coordinate_space': 'normalized'}),
                          (4, 5, {'coordinate_space': 'screenshot'}),
                          (4, 5, {'coordinate_space': 'guessed'})]:
            with self.subTest(x=x, y=y, cfg=cfg), self.assertRaises(ValueError):
                COORDS.resolve_point(x, y, cfg, GEOMETRY)

    def test_ambiguous_window_does_not_pick_first(self):
        gui = MagicMock()
        gui.IsWindowVisible.return_value = True
        gui.GetWindowText.return_value = 'Notepad'
        gui.EnumWindows.side_effect = lambda callback, _: [callback(1, None), callback(2, None)]
        with patch.dict(sys.modules, {'win32gui': gui}), self.assertRaisesRegex(ValueError, 'Ambiguous'):
            COORDS.select_window({'window_title': 'Notepad'})


class MouserTests(unittest.TestCase):
    def setUp(self):
        self.agent = load_agent('mouser')
        self.agent.pyautogui.position.return_value = (10, 20)

    def test_skipped_click_is_not_reported_as_clicked(self):
        self.assertFalse(self.agent.issue_click_after_reaching_target(100, 200, 'left'))
        self.agent.pyautogui.click.assert_not_called()

    def test_failed_click_is_not_reported_as_clicked(self):
        self.agent.pyautogui.click.side_effect = RuntimeError('blocked')
        self.assertFalse(self.agent.issue_click_after_reaching_target(10, 20, 'left'))

    def test_inspect_never_sends_input(self):
        with patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY):
            result = self.agent.dispatch({'movement_type': 'inspect'})
        self.assertEqual(result['desktop_left'], -1920)
        self.assertEqual(result['status'], 'observed')
        self.agent.pyautogui.moveTo.assert_not_called()
        self.agent.pyautogui.click.assert_not_called()

    def test_screenshot_point_sent_to_backend_after_conversion(self):
        self.agent.pyautogui.position.return_value = (-960, 540)
        cfg = dict(movement_type='localized', button_click='left', coordinate_space='screenshot',
                   capture_left=-1920, capture_top=0, capture_width=4480, capture_height=1440,
                   image_width=2240, image_height=720, end_posx=480, end_posy=270)
        with patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY):
            result = self.agent.dispatch(cfg)
        self.agent.pyautogui.moveTo.assert_called_once_with(-960, 540, duration=0.3)
        self.assertEqual(result['end_posx'], -960)
        self.assertEqual(result['clicked'], 'true')

    def test_offscreen_request_sends_nothing(self):
        cfg = dict(movement_type='localized', end_posx=5000, end_posy=10, button_click='left')
        with patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY), self.assertRaises(ValueError):
            self.agent.dispatch(cfg)
        self.agent.pyautogui.moveTo.assert_not_called()

    def test_template_match_includes_negative_capture_origin(self):
        from collections import namedtuple
        box = namedtuple('Box', 'left top width height')(100, 100, 40, 20)
        self.agent.pyautogui.locateAll.return_value = iter([box])
        self.agent.pyautogui.position.return_value = (-1800, 110)
        capture = MagicMock(size=(4480, 1440))
        with (patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY),
              patch('PIL.ImageGrab.grab', return_value=capture),
              patch.object(os.path, 'isfile', return_value=True)):
            result = self.agent.click_at_located_image('button.png', 0.8, 'left')
        self.assertEqual(result[:3], (-1800, 110, True))

    def test_template_ambiguity_does_not_move_or_click(self):
        from collections import namedtuple
        box = namedtuple('Box', 'left top width height')
        self.agent.pyautogui.locateAll.return_value = iter([box(100, 100, 40, 20), box(400, 100, 40, 20)])
        capture = MagicMock(size=(4480, 1440))
        with (patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY),
              patch('PIL.ImageGrab.grab', return_value=capture), patch.object(os.path, 'isfile', return_value=True),
              self.assertRaisesRegex(ValueError, 'ambiguous')):
            self.agent.click_at_located_image('button.png', 0.8, 'left')
        self.agent.pyautogui.moveTo.assert_not_called()

    def test_failed_focus_does_not_move_or_click(self):
        with (patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY),
              patch.object(self.agent, 'select_window', return_value=10),
              patch.object(self.agent, 'focus_window', side_effect=RuntimeError('focus denied')),
              self.assertRaisesRegex(RuntimeError, 'focus denied')):
            self.agent.dispatch({'movement_type': 'click_at_window', 'window_title': 'Notepad'})
        self.agent.pyautogui.moveTo.assert_not_called()

    def test_drag_failure_releases_owned_button(self):
        self.agent.pyautogui.moveTo.side_effect = RuntimeError('movement failed')
        api = MagicMock()
        with patch.dict(sys.modules, {'win32api': api}):
            self.assertFalse(self.agent.drag_mouse(10, 20, 100, 200, True, 'left'))
        api.mouse_event.assert_called_once_with(4, 0, 0, 0, 0)

    def test_fail_safe_stops_random_motion(self):
        self.agent.pyautogui.moveTo.side_effect = self.agent.pyautogui.FailSafeException()
        with (patch.object(self.agent, 'desktop_geometry', return_value=GEOMETRY),
              self.assertRaises(self.agent.pyautogui.FailSafeException)):
            self.agent.move_mouse_random(1)

    def test_failure_emits_nonzero_result_and_notifies_downstream(self):
        with (patch.object(self.agent, 'load_config', return_value={'target_agents': ['next']}),
              patch.object(self.agent, 'write_pid_file'), patch.object(self.agent, 'remove_pid_file'),
              patch.object(self.agent, 'wait_for_agents_to_stop'), patch.object(self.agent, 'start_agent') as start,
              patch.object(self.agent, 'dispatch', side_effect=ValueError('outside monitor')),
              patch.object(self.agent, '_emit_section') as emit, self.assertRaises(SystemExit) as cm):
            self.agent.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(emit.call_args.args[0]['action_status'], 'error')
        start.assert_called_once_with('next')


class KeyboardInputTests(unittest.TestCase):
    def test_unicode_emoji_sends_utf16_surrogates_with_matching_keyups(self):
        with patch.object(INPUT, '_send') as send:
            INPUT.send_character('🐈', lambda: None)
        events = send.call_args.args[0]
        self.assertEqual([e.data.ki.wScan for e in events], [0xD83D, 0xD83D, 0xDC08, 0xDC08])
        self.assertEqual([e.data.ki.dwFlags for e in events], [4, 6, 4, 6])

    def test_sendinput_uses_complete_union_size_and_detects_partial_delivery(self):
        self.assertEqual(ctypes.sizeof(INPUT._Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        api = MagicMock()
        api.SendInput.return_value = 1
        with patch.object(INPUT, '_user32', return_value=api), self.assertRaisesRegex(RuntimeError, '1/2'):
            INPUT._send([INPUT._event(vk=65), INPUT._event(vk=65, flags=2)])

    def test_focus_loss_releases_held_modifier_without_sending_next_key(self):
        guard = MagicMock(side_effect=[None, RuntimeError('focus lost')])
        with patch.object(INPUT, '_send') as send, self.assertRaisesRegex(RuntimeError, 'focus lost'):
            INPUT.send_keys(['ctrl', 's'], guard)
        events = [call.args[0][0].data.ki for call in send.call_args_list]
        self.assertEqual([(e.wVk, e.dwFlags) for e in events], [(0x11, 0), (0x11, 2)])

    def test_repeated_arrows_are_tapped_with_modifier_held(self):
        with patch.object(INPUT, '_send') as send:
            INPUT.send_keys(['shift', 'left', 'left'], lambda: None)
        events = [call.args[0][0].data.ki for call in send.call_args_list]
        self.assertEqual([(e.wVk, e.dwFlags) for e in events],
                         [(0x10, 0), (0x25, 1), (0x25, 3), (0x25, 1), (0x25, 3), (0x10, 2)])

    def test_target_guard_detects_focus_theft(self):
        gui = MagicMock()
        gui.GetForegroundWindow.return_value = 20
        with patch.dict(sys.modules, {'win32gui': gui}), self.assertRaisesRegex(RuntimeError, 'lost focus'):
            INPUT.verify_target((10, 1234))

    def test_cleanup_attempts_every_held_modifier_even_if_release_fails(self):
        guard = MagicMock(side_effect=[None, None, RuntimeError('focus lost')])
        with (patch.object(INPUT, '_send', side_effect=[None, None, RuntimeError('release failed'), None]) as send,
              self.assertRaisesRegex(RuntimeError, 'release failed')):
            INPUT.send_keys(['ctrl', 'shift', 's'], guard)
        self.assertEqual(send.call_count, 4)
        self.assertEqual(send.call_args.args[0][0].data.ki.wVk, 0x11)

    def test_ambiguous_keyboard_target_is_not_activated(self):
        gui = MagicMock()
        gui.IsWindowVisible.return_value = True
        gui.GetWindowText.return_value = 'Notepad'
        gui.EnumWindows.side_effect = lambda callback, _: [callback(1, None), callback(2, None)]
        with patch.dict(sys.modules, {'win32gui': gui}), self.assertRaisesRegex(ValueError, 'found 2'):
            INPUT.bind_target({'window_title': 'Notepad'})
        gui.SetForegroundWindow.assert_not_called()


class KeyboarderTests(unittest.TestCase):
    def setUp(self):
        self.agent = load_agent('keyboarder')

    def test_literal_mode_preserves_punctuation_and_unicode(self):
        sent = []
        outcome = {'characters_sent': 0, 'commands_sent': 0}
        with (patch.object(self.agent, 'bind_target', return_value=(10, 100)),
              patch.object(self.agent, 'verify_target'), patch.object(self.agent, 'ensure_modifiers_released'),
              patch.object(self.agent, 'send_character', side_effect=lambda ch, guard: sent.append(ch))):
            self.agent.execute_sequence({'input_mode': 'text', 'text': "Ángela, '猫' 🐈",
                                         'stride_delay': 0, 'typing_interval_ms': 0}, outcome)
        self.assertEqual(''.join(sent), "Ángela, '猫' 🐈")
        self.assertEqual(outcome['status'], 'input_sent')

    def test_invalid_mixed_sequence_is_preflighted_before_any_input(self):
        with patch.object(self.agent, 'bind_target') as bind, self.assertRaises(ValueError):
            self.agent.execute_sequence({'input_sequence': "'hello', ctrl+bogus"}, {})
        bind.assert_not_called()

    def test_unterminated_quote_is_not_typed(self):
        with self.assertRaisesRegex(ValueError, 'Unterminated'):
            self.agent.split_sequence("'hello")

    def test_legacy_escaped_literals_still_work(self):
        self.assertEqual(self.agent.split_sequence("'Hi, I''m Tlamatini', enter"),
                         [('string', "Hi, I'm Tlamatini"), ('keys', ['enter'])])

    def test_unquoted_prose_apostrophe_keeps_legacy_literal_fallback(self):
        self.assertEqual(self.agent.split_sequence("Hi!, I'm Tlamatini"),
                         [('string', "Hi!, I'm Tlamatini")])

    def test_focus_loss_stops_remaining_sequence(self):
        outcome = {'characters_sent': 0, 'commands_sent': 0}
        with (patch.object(self.agent, 'bind_target', return_value=(10, 100)),
              patch.object(self.agent, 'ensure_modifiers_released'),
              patch.object(self.agent, 'verify_target', side_effect=RuntimeError('focus lost')),
              patch.object(self.agent, 'send_character') as send, self.assertRaises(RuntimeError)):
            self.agent.execute_sequence({'input_mode': 'text', 'text': 'hello'}, outcome)
        send.assert_not_called()
        self.assertEqual(outcome['characters_sent'], 0)

    def test_failure_emits_section_and_nonzero_exit_and_starts_downstream(self):
        with (patch.object(self.agent, 'load_config', return_value={'target_agents': ['next']}),
              patch.object(self.agent, 'write_pid_file'), patch.object(self.agent, 'remove_pid_file'),
              patch.object(self.agent, 'wait_for_agents_to_stop'),
              patch.object(self.agent, 'start_agent') as start,
              patch.object(self.agent, 'execute_sequence', side_effect=RuntimeError('blocked')),
              patch.object(self.agent.logging, 'info') as log, self.assertRaises(SystemExit) as cm):
            self.agent.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('action_status: error', log.call_args.args[0])
        start.assert_called_once_with('next')


class ShoterGeometryTests(unittest.TestCase):
    def test_capture_emits_physical_origin_and_restores_dpi_context(self):
        agent = load_agent('shoter')
        picture = MagicMock(size=(4480, 1440), width=4480, height=1440)
        api = MagicMock()
        api.SetThreadDpiAwarenessContext.return_value = 123
        win32api = MagicMock()
        win32api.EnumDisplayMonitors.return_value = [(1, None, r) for r in GEOMETRY['monitors']]
        metadata = {}
        with (tempfile.TemporaryDirectory() as folder, patch('PIL.ImageGrab.grab', return_value=picture),
              patch.object(agent.ctypes, 'WinDLL', return_value=api),
              patch.dict(sys.modules, {'win32api': win32api})):
            agent.capture_screenshot(folder, filename='evidence.png', metadata=metadata)
        self.assertEqual(metadata['capture_left'], -1920)
        self.assertEqual(metadata['capture_width'], 4480)
        self.assertEqual(metadata['coordinate_space'], 'physical_screen')
        api.SetThreadDpiAwarenessContext.assert_called_with(123)

    def test_geometry_mismatch_never_claims_physical_mapping(self):
        agent = load_agent('shoter')
        picture = MagicMock(size=(1920, 1080), width=1920, height=1080)
        api = MagicMock()
        api.SetThreadDpiAwarenessContext.return_value = 123
        win32api = MagicMock()
        win32api.EnumDisplayMonitors.return_value = [(1, None, r) for r in GEOMETRY['monitors']]
        metadata = {}
        with (tempfile.TemporaryDirectory() as folder, patch('PIL.ImageGrab.grab', return_value=picture),
              patch.object(agent.ctypes, 'WinDLL', return_value=api),
              patch.dict(sys.modules, {'win32api': win32api})):
            agent.capture_screenshot(folder, filename='evidence.png', metadata=metadata)
        self.assertEqual(metadata['coordinate_space'], 'unknown')
        self.assertNotIn('capture_left', metadata)


class ToolContractTests(unittest.TestCase):
    def test_failed_input_is_not_told_to_retry_as_a_script(self):
        tree = ast.parse((ROOT / 'tools.py').read_text(encoding='utf-8'))
        launcher = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == '_launch_wrapped_chat_agent')
        result_branch = next(n for n in launcher.body if isinstance(n, ast.If)
                             and ast.unparse(n.test) == "run.status == 'running'")
        code = compile(ast.Module(body=[result_branch], type_ignores=[]), '<wrapper result>', 'exec')
        for name in ('mouser', 'keyboarder'):
            payload = {}
            namespace = dict(payload=payload, run=SimpleNamespace(status='failed', exitCode=1),
                             spec=SimpleNamespace(template_dir=name, display_name=name))
            exec(code, namespace)
            self.assertFalse(payload['retryable'])
            self.assertTrue(payload['needs_observation'])
            self.assertNotIn('REWRITE', payload['message'])

    def test_new_results_are_promoted_without_overwriting_runtime_status(self):
        tree = ast.parse((ROOT / 'tools.py').read_text(encoding='utf-8'))
        fields = next(ast.literal_eval(n.value) for n in tree.body
                      if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                      and n.target.id == '_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR')
        self.assertIn('capture_left', fields['shoter'])
        self.assertIn('coordinate_space', fields['mouser'])
        self.assertIn('action_status', fields['mouser'])
        self.assertIn('action_status', fields['keyboarder'])
        self.assertNotIn('status', fields['keyboarder'])

    def test_new_helpers_are_present_in_isolated_template_copies(self):
        import shutil
        for name, helper in [('mouser', 'mouser_coordinates.py'), ('keyboarder', 'keyboarder_input.py')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                dest = Path(folder) / name
                shutil.copytree(ROOT / 'agents' / name, dest, ignore=shutil.ignore_patterns('*.log', '__pycache__'))
                self.assertTrue((dest / helper).is_file())
                compile((dest / f'{name}.py').read_text(encoding='utf-8'), str(dest / f'{name}.py'), 'exec')


if __name__ == '__main__':
    unittest.main()
