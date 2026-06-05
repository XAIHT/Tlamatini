"""Automated tests for the VideoPlayer workflow agent and its surrounding infrastructure.

VideoPlayer plays a VIDEO FILE (with audio) on a chosen DISPLAY via ``ffpyplayer`` (decode +
audio + volume) and OpenCV (``cv2``) for the window. It is the on-screen sibling of AudioPlayer
(speakers). It is a standalone pool agent under ``agent/agents/videoplayer/`` loaded here through
``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore so its
module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side effects do not
leak.

No screen, no GPU, no ffmpeg/SDL and no hardware are required: the truncate/loop DRIVER is exercised
with a pure-Python fake backend + fake clock; the ffpyplayer and OpenCV backends are exercised with
fake ``ffpyplayer.player`` / ``cv2`` modules; monitor enumeration and the cv2 window are mocked out.

Covers:
- Helpers: resolve_video_file (abs/rel/empty/quoted), _coerce_bool, classify_play_mode,
  compute_window_geometry (native size, forced size, clamp, center, fullscreen),
  resolve_display (default primary / explicit / out-of-range), emit sections (atomic INI round-trip)
- drive_playback (the core): whole-file-once, TRUNCATION (stops at time_played), LOOP (re-seeks +
  counts), partial segment, user-stop (pump), played_seconds accounting — all with a fake clock
- Backends: _FfpyplayerBackend rgb24->bgr conversion + eof/wait; _OpenCvBackend via a fake cv2;
  open_backend selection (ffpyplayer present -> ffpyplayer; absent -> silent OpenCV fallback)
- main(): section emitted + targets triggered (success); failure emits an error section AND still
  triggers targets; missing cv2 reported not crashed
- Registry integration: ChatWrappedAgentSpec, tools.py promotion, agent contract + parametrizer
  fields, Exec-Report ABSENCE, config.yaml defaults, CSS gradient, URL route + view, JS wiring,
  parametrizer SECTION_AGENT_TYPES, migrations, requirements pin, build.py collect-all
"""

import builtins
import importlib.util
import logging
import os
import sys
import tempfile
import unittest
import unittest.mock
from functools import lru_cache

import numpy as np
import yaml
from django.test import SimpleTestCase


_REPO_AGENT_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_videoplayer_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'videoplayer', 'videoplayer.py')
    spec = importlib.util.spec_from_file_location(
        'agent_videoplayer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load VideoPlayer module from {module_path}')
    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


class _LogCapture:
    def __init__(self):
        self.records = []

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                outer.records.append(record.getMessage())

        self._handler = _H()
        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(self, *_a):
        logging.getLogger().removeHandler(self._handler)
        return False


def _parse_ini_section(text, agent_type='VIDEOPLAYER'):
    start = f"INI_SECTION_{agent_type}<<<"
    end = f">>>END_SECTION_{agent_type}"
    body = text.split(start, 1)[1].split(end, 1)[0].strip('\n')
    head, _, tail = body.partition('\n\n')
    fields = {}
    for line in head.split('\n'):
        if ': ' in line:
            key, val = line.split(': ', 1)
            fields[key.strip()] = val.strip()
        elif line.endswith(':'):
            fields[line[:-1].strip()] = ''
    fields['response_body'] = tail.strip()
    return fields


# ---------------------------------------------------------------------------
# Fakes for the playback driver
# ---------------------------------------------------------------------------


class _FakeClock:
    """A clock that only advances on sleep() — fully deterministic."""

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, d):
        self.t += max(0.0, float(d))


class _FakeBackend:
    backend_name = 'fake'
    has_audio = True
    width = 320
    height = 240
    duration = 1.0

    def __init__(self, frames_per_play=10, dt=0.1):
        self.fpp = frames_per_play
        self.dt = dt
        self.i = 0
        self.seeks = 0
        self.closed = False

    def next_frame(self):
        if self.i >= self.fpp:
            return ('eof', None, 0.0)
        self.i += 1
        return ('frame', ('F', self.i), self.dt)

    def seek_start(self):
        self.seeks += 1
        self.i = 0

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# Pure helpers + geometry
# ---------------------------------------------------------------------------


class VideoPlayerHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_videoplayer_module()

    def test_resolve_video_file_empty(self):
        self.assertEqual(self.mod.resolve_video_file({}), '')
        self.assertEqual(self.mod.resolve_video_file({'video_file': '  '}), '')

    def test_resolve_video_file_absolute_quoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'a.mp4')
            out = self.mod.resolve_video_file({'video_file': f'"{target}"'})
            self.assertEqual(os.path.normpath(out), os.path.normpath(target))

    def test_resolve_video_file_relative_anchored(self):
        out = self.mod.resolve_video_file({'video_file': 'sub/clip.mov'})
        self.assertTrue(os.path.isabs(out))
        self.assertTrue(out.endswith(os.path.join('sub', 'clip.mov')))

    def test_coerce_bool(self):
        for v in (True, 'true', 'True', '1', 'yes', 'on'):
            self.assertTrue(self.mod._coerce_bool(v, False))
        for v in (False, 'false', '0', 'no', 'off', ''):
            self.assertFalse(self.mod._coerce_bool(v, True))
        self.assertTrue(self.mod._coerce_bool('garbage', True))
        self.assertFalse(self.mod._coerce_bool(None, False))

    def test_classify_play_mode(self):
        self.assertEqual(self.mod.classify_play_mode(0, 10), 'full')
        self.assertEqual(self.mod.classify_play_mode(5, 10), 'truncated')
        self.assertEqual(self.mod.classify_play_mode(10, 10), 'full')
        self.assertEqual(self.mod.classify_play_mode(20, 10), 'looped')
        self.assertEqual(self.mod.classify_play_mode(7, 0), 'looped')   # unknown duration

    def test_window_geometry_native_size_centered(self):
        mon = {'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080, 'primary': True}
        g = self.mod.compute_window_geometry({}, 640, 480, mon)
        self.assertFalse(g['fullscreen'])
        self.assertEqual((g['win_w'], g['win_h']), (640, 480))
        self.assertEqual(g['pos_x'], (1920 - 640) // 2)
        self.assertEqual(g['pos_y'], (1080 - 480) // 2)

    def test_window_geometry_forced_size_and_monitor_offset(self):
        mon = {'index': 1, 'left': 1920, 'top': 0, 'width': 1280, 'height': 720, 'primary': False}
        g = self.mod.compute_window_geometry(
            {'window_width': 800, 'window_height': 600}, 640, 480, mon)
        self.assertEqual((g['win_w'], g['win_h']), (800, 600))
        self.assertEqual(g['pos_x'], 1920 + (1280 - 800) // 2)   # offset onto monitor 1
        self.assertEqual(g['pos_y'], (720 - 600) // 2)

    def test_window_geometry_clamped_to_monitor(self):
        mon = {'index': 0, 'left': 0, 'top': 0, 'width': 800, 'height': 600, 'primary': True}
        g = self.mod.compute_window_geometry(
            {'window_width': 5000, 'window_height': 5000}, 640, 480, mon)
        self.assertEqual((g['win_w'], g['win_h']), (800, 600))

    def test_window_geometry_fullscreen_fills_monitor(self):
        mon = {'index': 2, 'left': 100, 'top': 50, 'width': 1366, 'height': 768, 'primary': False}
        g = self.mod.compute_window_geometry({'fullscreen': True, 'window_width': 200}, 640, 480, mon)
        self.assertTrue(g['fullscreen'])
        self.assertEqual((g['win_w'], g['win_h']), (1366, 768))
        self.assertEqual((g['pos_x'], g['pos_y']), (100, 50))

    def test_resolve_display_default_picks_primary(self):
        mons = [
            {'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080, 'primary': False},
            {'index': 1, 'left': 1920, 'top': 0, 'width': 1280, 'height': 720, 'primary': True},
        ]
        self.assertEqual(self.mod.resolve_display({'display_index': -1}, mons)['index'], 1)

    def test_resolve_display_explicit_index(self):
        mons = [
            {'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080, 'primary': True},
            {'index': 1, 'left': 1920, 'top': 0, 'width': 1280, 'height': 720, 'primary': False},
        ]
        self.assertEqual(self.mod.resolve_display({'display_index': 1}, mons)['index'], 1)

    def test_resolve_display_out_of_range_falls_back_to_primary(self):
        mons = [{'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080, 'primary': True}]
        self.assertEqual(self.mod.resolve_display({'display_index': 9}, mons)['index'], 0)

    def test_emit_section_round_trip(self):
        result = {
            'input_path': r'C:\Videos\demo.mp4', 'display_index': 1,
            'display_geometry': '1280x720@(1920,0)', 'video_width': 1920, 'video_height': 1080,
            'window_width': 1280, 'window_height': 720, 'fullscreen': True, 'volume_percent': 80.0,
            'backend': 'ffpyplayer', 'has_audio': True, 'file_duration_seconds': 12.5,
            'time_played_requested': 30.0, 'played_seconds': 30.0, 'play_mode': 'looped',
            'loops': 2, 'partial_segment': True, 'format': 'mp4',
        }
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(result)
        block = next(r for r in cap.records if 'INI_SECTION_VIDEOPLAYER<<<' in r)
        self.assertEqual(cap.records.count(block), 1)
        f = _parse_ini_section(block)
        self.assertEqual(f['input_path'], r'C:\Videos\demo.mp4')
        self.assertEqual(f['filename'], 'demo.mp4')
        self.assertEqual(f['display_index'], '1')
        self.assertEqual(f['fullscreen'], 'true')
        self.assertEqual(f['volume_percent'], '80')
        self.assertEqual(f['played_seconds'], '30')
        self.assertEqual(f['play_mode'], 'looped')
        self.assertEqual(f['loops'], '2')
        self.assertEqual(f['partial_segment'], 'true')
        self.assertEqual(f['backend'], 'ffpyplayer')
        self.assertEqual(f['has_audio'], 'true')
        self.assertEqual(f['status'], 'played')
        self.assertIn('Played', f['response_body'])

    def test_emit_error_section_round_trip(self):
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_error_section(
                r'C:\Videos\missing.mp4', 'Video file not found:\nx', 30.0)
        block = next(r for r in cap.records if 'INI_SECTION_VIDEOPLAYER<<<' in r)
        f = _parse_ini_section(block)
        self.assertEqual(f['status'], 'error')
        self.assertEqual(f['play_mode'], 'error')
        self.assertEqual(f['filename'], 'missing.mp4')
        self.assertEqual(f['time_played_requested'], '30')
        self.assertIn('FAILED', f['response_body'])


# ---------------------------------------------------------------------------
# drive_playback — the truncate / loop / full core
# ---------------------------------------------------------------------------


class VideoPlayerDriveTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_videoplayer_module()

    def _run(self, time_played, frames_per_play=10, dt=0.1, stop_after=None):
        backend = _FakeBackend(frames_per_play=frames_per_play, dt=dt)
        clk = _FakeClock()
        shown = []
        calls = {'n': 0}

        def _display(frame):
            shown.append(frame)

        def _pump():
            calls['n'] += 1
            if stop_after is not None and len(shown) >= stop_after:
                return True
            return False

        stats = self.mod.drive_playback(
            backend, _display, _pump, time_played, clock=clk.now, sleep=clk.sleep)
        return backend, shown, stats, clk

    def test_full_plays_whole_file_once(self):
        backend, shown, stats, _clk = self._run(0)
        self.assertEqual(len(shown), 10)              # one full play
        self.assertEqual(stats['loops_completed'], 1)
        self.assertFalse(stats['partial_segment'])
        self.assertEqual(backend.seeks, 0)            # never looped
        self.assertAlmostEqual(stats['played_seconds'], 1.0, places=3)

    def test_truncation_stops_at_time_played(self):
        backend, shown, stats, _clk = self._run(0.5)   # half of a 1.0s file
        self.assertEqual(len(shown), 5)
        self.assertTrue(stats['partial_segment'])
        self.assertEqual(backend.seeks, 0)
        self.assertAlmostEqual(stats['played_seconds'], 0.5, places=3)

    def test_loop_partial_reseeks_and_counts(self):
        backend, shown, stats, _clk = self._run(1.5)   # 1.5x a 1.0s file
        self.assertEqual(len(shown), 15)               # 10 + 5
        self.assertEqual(stats['loops_completed'], 1)  # one COMPLETE play
        self.assertEqual(backend.seeks, 1)             # looped once
        self.assertTrue(stats['partial_segment'])
        self.assertAlmostEqual(stats['played_seconds'], 1.5, places=3)

    def test_user_stop_via_pump(self):
        backend, shown, stats, _clk = self._run(100, stop_after=3)
        self.assertTrue(stats['stopped_by_user'])
        self.assertEqual(len(shown), 3)

    def test_backend_closed_is_callers_job(self):
        # drive_playback itself does NOT close the backend (play_video's finally does).
        backend, _shown, _stats, _clk = self._run(0)
        self.assertFalse(backend.closed)


# ---------------------------------------------------------------------------
# Decode backends
# ---------------------------------------------------------------------------


class _FakeFfImage:
    def __init__(self, w, h):
        self.w, self.h = w, h

    def get_size(self):
        return (self.w, self.h)

    def get_pixel_format(self):
        return 'rgb24'

    def to_bytearray(self):
        # Each pixel R=1, G=2, B=3 so the RGB->BGR swap is observable.
        px = np.tile(np.array([1, 2, 3], np.uint8), self.w * self.h)
        return [bytes(px.tobytes())]


class _FakeMediaPlayer:
    def __init__(self, path, ff_opts=None):
        self.path = path
        self.n = 3
        self.i = 0
        self.volume = None
        self.seeks = 0

    def set_volume(self, v):
        self.volume = v

    def get_metadata(self):
        return {'src_vid_size': (4, 2), 'duration': 1.0}

    def get_frame(self):
        if self.i >= self.n:
            return (None, 'eof')
        self.i += 1
        return ((_FakeFfImage(4, 2), 0.0), 0.0)

    def seek(self, *_a, **_k):
        self.seeks += 1
        self.i = 0

    def set_pause(self, *_a):
        pass

    def close_player(self):
        pass


def _install_fake_ffpyplayer():
    import types
    pkg = types.ModuleType('ffpyplayer')
    player_mod = types.ModuleType('ffpyplayer.player')
    player_mod.MediaPlayer = _FakeMediaPlayer
    pkg.player = player_mod
    sys.modules['ffpyplayer'] = pkg
    sys.modules['ffpyplayer.player'] = player_mod


def _remove_fake_ffpyplayer():
    sys.modules.pop('ffpyplayer', None)
    sys.modules.pop('ffpyplayer.player', None)


class _FakeCap:
    def __init__(self, frames=5):
        self.frames = frames
        self.i = 0

    def isOpened(self):
        return True

    def get(self, prop):
        return {3: 4, 4: 2, 5: 10.0, 7: float(self.frames)}.get(prop, 0)

    def read(self):
        if self.i >= self.frames:
            return (False, None)
        self.i += 1
        return (True, np.zeros((2, 4, 3), np.uint8))

    def set(self, _prop, _val):
        self.i = 0

    def release(self):
        pass


class _FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    CAP_PROP_FRAME_COUNT = 7
    CAP_PROP_POS_FRAMES = 1

    def __init__(self):
        self.last_cap = None

    def VideoCapture(self, _path):
        self.last_cap = _FakeCap()
        return self.last_cap


class VideoPlayerBackendTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_videoplayer_module()

    def test_ffpyplayer_backend_rgb_to_bgr_and_eof(self):
        _install_fake_ffpyplayer()
        self.addCleanup(_remove_fake_ffpyplayer)
        backend = self.mod._FfpyplayerBackend('x.mp4', 0.5)
        self.assertEqual(backend.width, 4)
        self.assertEqual(backend.height, 2)
        self.assertEqual(backend.duration, 1.0)
        kind, frame, _delay = backend.next_frame()
        self.assertEqual(kind, 'frame')
        self.assertEqual(frame.shape, (2, 4, 3))
        # RGB (1,2,3) -> BGR (3,2,1)
        self.assertEqual(list(frame[0, 0]), [3, 2, 1])
        # Drain to EOF.
        for _ in range(5):
            kind, _f, _d = backend.next_frame()
            if kind == 'eof':
                break
        self.assertEqual(kind, 'eof')
        backend.seek_start()
        self.assertEqual(backend.player.seeks, 1)

    def test_ffpyplayer_backend_sets_volume(self):
        _install_fake_ffpyplayer()
        self.addCleanup(_remove_fake_ffpyplayer)
        backend = self.mod._FfpyplayerBackend('x.mp4', 0.5)
        self.assertEqual(backend.player.volume, 0.5)

    def test_opencv_backend_reads_frames_and_eof(self):
        fake_cv2 = _FakeCv2()
        sys.modules['cv2'] = fake_cv2
        self.addCleanup(lambda: sys.modules.pop('cv2', None))
        backend = self.mod._OpenCvBackend('x.mp4')
        self.assertEqual(backend.width, 4)
        self.assertEqual(backend.height, 2)
        self.assertEqual(backend.fps, 10.0)
        self.assertAlmostEqual(backend.duration, 0.5, places=3)   # 5 frames / 10 fps
        self.assertFalse(backend.has_audio)
        count = 0
        while True:
            kind, _f, _d = backend.next_frame()
            if kind == 'eof':
                break
            count += 1
        self.assertEqual(count, 5)

    def test_open_backend_prefers_ffpyplayer(self):
        _install_fake_ffpyplayer()
        self.addCleanup(_remove_fake_ffpyplayer)
        backend = self.mod.open_backend('x.mp4', 1.0)
        self.assertEqual(backend.backend_name, 'ffpyplayer')
        self.assertTrue(backend.has_audio)

    def test_open_backend_falls_back_to_opencv_when_ffpyplayer_absent(self):
        _remove_fake_ffpyplayer()
        fake_cv2 = _FakeCv2()
        sys.modules['cv2'] = fake_cv2
        self.addCleanup(lambda: sys.modules.pop('cv2', None))
        real_import = builtins.__import__

        def _no_ff(name, *a, **k):
            if name.startswith('ffpyplayer'):
                raise ImportError('no ffpyplayer')
            return real_import(name, *a, **k)

        with _LogCapture() as cap, unittest.mock.patch('builtins.__import__', side_effect=_no_ff):
            backend = self.mod.open_backend('x.mp4', 1.0)
        self.assertEqual(backend.backend_name, 'opencv')
        self.assertFalse(backend.has_audio)
        self.assertTrue(any('SILENT' in r or 'ffpyplayer' in r for r in cap.records))


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class VideoPlayerMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_videoplayer_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'clip.mp4')
        with open(self.path, 'wb') as handle:
            handle.write(b'\x00\x00\x00\x18ftypmp42')

    def _fake_result(self):
        return {
            'input_path': self.path, 'display_index': 0, 'display_geometry': '1920x1080@(0,0)',
            'video_width': 1920, 'video_height': 1080, 'window_width': 1920, 'window_height': 1080,
            'fullscreen': False, 'volume_percent': 100.0, 'backend': 'ffpyplayer', 'has_audio': True,
            'file_duration_seconds': 2.0, 'time_played_requested': 0.0, 'played_seconds': 2.0,
            'play_mode': 'full', 'loops': 1, 'partial_segment': False, 'format': 'mp4',
        }

    def test_main_success_emits_section_and_triggers_targets(self):
        mod = self.mod
        sys.modules['cv2'] = type('C', (), {})()
        self.addCleanup(lambda: sys.modules.pop('cv2', None))
        cfg = {'video_file': self.path, 'time_played': 0, 'target_agents': ['sleeper_1']}
        started = []
        orig = os.getcwd()
        with _LogCapture() as cap, \
                unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                unittest.mock.patch.object(mod, 'write_pid_file'), \
                unittest.mock.patch.object(mod, 'remove_pid_file'), \
                unittest.mock.patch.object(mod, 'wait_for_agents_to_stop'), \
                unittest.mock.patch.object(mod, 'play_video', return_value=self._fake_result()), \
                unittest.mock.patch.object(mod, 'start_agent',
                                           side_effect=lambda n: started.append(n) or True):
            with self.assertRaises(SystemExit) as ctx:
                mod.main()
        os.chdir(orig)
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(started, ['sleeper_1'])
        block = next(r for r in cap.records if 'INI_SECTION_VIDEOPLAYER<<<' in r)
        self.assertIn('status: played', block)

    def test_main_failure_emits_error_section_and_still_triggers(self):
        mod = self.mod
        sys.modules['cv2'] = type('C', (), {})()
        self.addCleanup(lambda: sys.modules.pop('cv2', None))
        cfg = {'video_file': self.path, 'time_played': 5, 'target_agents': ['cleaner_1']}
        started = []
        orig = os.getcwd()
        with _LogCapture() as cap, \
                unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                unittest.mock.patch.object(mod, 'write_pid_file'), \
                unittest.mock.patch.object(mod, 'remove_pid_file'), \
                unittest.mock.patch.object(mod, 'wait_for_agents_to_stop'), \
                unittest.mock.patch.object(mod, 'play_video',
                                           side_effect=RuntimeError('boom decoding')), \
                unittest.mock.patch.object(mod, 'start_agent',
                                           side_effect=lambda n: started.append(n) or True):
            with self.assertRaises(SystemExit) as ctx:
                mod.main()
        os.chdir(orig)
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(started, ['cleaner_1'])
        block = next(r for r in cap.records if 'INI_SECTION_VIDEOPLAYER<<<' in r)
        self.assertIn('status: error', block)

    def test_main_missing_cv2_is_reported_not_crashed(self):
        mod = self.mod
        sys.modules.pop('cv2', None)
        real_import = builtins.__import__

        def _no_cv2(name, *a, **k):
            if name == 'cv2':
                raise ImportError('No module named cv2')
            return real_import(name, *a, **k)

        cfg = {'video_file': self.path, 'time_played': 0, 'target_agents': []}
        orig = os.getcwd()
        with _LogCapture() as cap, \
                unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                unittest.mock.patch.object(mod, 'write_pid_file'), \
                unittest.mock.patch.object(mod, 'remove_pid_file'), \
                unittest.mock.patch('builtins.__import__', side_effect=_no_cv2):
            with self.assertRaises(SystemExit) as ctx:
                mod.main()
        os.chdir(orig)
        self.assertEqual(ctx.exception.code, 1)
        self.assertTrue(any('cv2' in r or 'OpenCV' in r for r in cap.records))


# ---------------------------------------------------------------------------
# Registry / integration contracts
# ---------------------------------------------------------------------------


class VideoPlayerRegistryTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next((s for s in WRAPPED_CHAT_AGENT_SPECS
                     if s.tool_name == 'chat_agent_videoplayer'), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, 'videoplayer')
        self.assertEqual(spec.template_dir, 'videoplayer')
        self.assertEqual(spec.display_name, 'VideoPlayer')

    def test_tools_promote_section_fields(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        fields = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR.get('videoplayer')
        self.assertIsNotNone(fields)
        for expected in ('input_path', 'played_seconds', 'play_mode', 'status',
                         'display_index', 'fullscreen', 'backend'):
            self.assertIn(expected, fields)

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import (
            get_agent_contract,
            get_parametrizer_source_fields,
        )
        fields = get_parametrizer_source_fields().get('videoplayer')
        self.assertIsNotNone(fields)
        for expected in ('input_path', 'input_dir', 'filename', 'display_index',
                         'display_geometry', 'video_width', 'video_height', 'window_width',
                         'window_height', 'fullscreen', 'volume_percent', 'backend',
                         'played_seconds', 'play_mode', 'status', 'response_body'):
            self.assertIn(expected, fields)
        contract = get_agent_contract('videoplayer')
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')

    def test_config_yaml_defaults(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'videoplayer', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        self.assertEqual(cfg['video_file'], '')
        self.assertEqual(cfg['display_index'], -1)
        self.assertEqual(cfg['volume_percent'], 100)
        self.assertEqual(cfg['time_played'], 0)
        self.assertEqual(cfg['window_width'], 0)
        self.assertEqual(cfg['window_height'], 0)
        self.assertEqual(cfg['fullscreen'], False)
        self.assertEqual(cfg['keep_aspect'], True)
        self.assertIn('target_agents', cfg)

    def test_not_in_exec_report(self):
        mcp_path = os.path.join(_REPO_AGENT_DIR, 'mcp_agent.py')
        with open(mcp_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertNotIn('chat_agent_videoplayer', text)

    def test_parametrizer_section_type_registered(self):
        param_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        with open(param_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn("'videoplayer'", text)

    def test_url_route_and_view_present(self):
        with open(os.path.join(_REPO_AGENT_DIR, 'urls.py'), 'r', encoding='utf-8') as handle:
            urls = handle.read()
        self.assertIn('update_videoplayer_connection', urls)
        with open(os.path.join(_REPO_AGENT_DIR, 'views.py'), 'r', encoding='utf-8') as handle:
            views = handle.read()
        self.assertIn('def update_videoplayer_connection_view', views)

    def test_migrations_present(self):
        mig_dir = os.path.join(_REPO_AGENT_DIR, 'migrations')
        self.assertTrue(os.path.exists(os.path.join(mig_dir, '0118_add_videoplayer.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0119_add_chat_agent_videoplayer_tool.py')))

    def test_css_gradient_present(self):
        css_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('.canvas-item.videoplayer-agent', css)

    def test_js_classmap_and_connector_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        with open(os.path.join(js_dir, 'acp-canvas-core.js'), 'r', encoding='utf-8') as handle:
            core = handle.read()
        self.assertIn("'videoplayer': 'videoplayer-agent'", core)
        self.assertIn("=== 'videoplayer') updateVideoPlayerConnection", core)
        with open(os.path.join(js_dir, 'acp-agent-connectors.js'), 'r', encoding='utf-8') as handle:
            conn = handle.read()
        self.assertIn('async function updateVideoPlayerConnection', conn)
        with open(os.path.join(js_dir, 'acp-file-io.js'), 'r', encoding='utf-8') as handle:
            fileio = handle.read()
        self.assertIn("case 'videoplayer':", fileio)

    def test_requirements_and_build_pin_ffpyplayer(self):
        repo_root = os.path.dirname(os.path.dirname(_REPO_AGENT_DIR))
        with open(os.path.join(repo_root, 'requirements.txt'), 'r', encoding='utf-8') as handle:
            self.assertIn('ffpyplayer', handle.read())
        with open(os.path.join(repo_root, 'build.py'), 'r', encoding='utf-8') as handle:
            build = handle.read()
        self.assertIn('ffpyplayer', build)               # _agent_libs verify + collect-all


if __name__ == '__main__':
    unittest.main()
