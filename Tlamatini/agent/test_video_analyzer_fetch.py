# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Video-Analyzer web links: video_fetch.py, the chat request parser and carriage.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.

WHY (2026-10-11, installed build): asked to transcribe a YouTube video,
Video-Analyzer failed three times in a row --
  1. "Parameter 'v' was not found"  (the ``?v=`` of the link read as a setting)
  2. robotics mode on an empty path  (the link written in plain words)
  3. "No video resolved from 'https://youtu.be/...'"  (links were not inputs)
-- and the chat then installed yt-dlp by hand, once into the user's own Python.
These tests pin every repair. No network, no downloads: yt-dlp and pip are
simulated at the subprocess boundary.
"""
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
TEMPLATE = ROOT / 'agents' / 'video_analyzer'


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = _load(TEMPLATE / 'video_fetch.py', 'video_fetch_test')
content = _load(TEMPLATE / 'video_content.py', 'video_content_fetch_test')


def load_agent():
    spec = importlib.util.spec_from_file_location('video_analyzer_fetch_test', TEMPLATE / 'video_analyzer.py')
    module = importlib.util.module_from_spec(spec)
    with (patch.object(os, 'chdir'), patch.object(logging, 'basicConfig'),
          patch.object(logging.getLogger(), 'addHandler'),
          patch.dict(os.environ, {'AGENT_REANIMATED': '1'})):
        spec.loader.exec_module(module)
    return module


def template_config():
    return yaml.safe_load((TEMPLATE / 'config.yaml').read_text(encoding='utf-8'))


# The three requests that failed on the installed build, verbatim.
HISTORICAL_REQUESTS = (
    "Transcribe the spoken audio of the YouTube video at https://www.youtube.com/watch?v=NdlzdPs0QBQ "
    "with analysis_type='transcription' and audio_tracks='all' and transcription.task='transcribe'. "
    "I need the full verbatim speech-to-text transcript of this video about AI Engineering.",
    "Transcribe the spoken audio track of this YouTube video: https://youtu.be/NdlzdPs0QBQ \u2014 use "
    "analysis_type transcription and audio_tracks all and transcription.task transcribe. Return the full "
    "verbatim speech-to-text transcript.",
    "Transcribe the spoken audio of this YouTube video. Use video_pathfilenames='https://youtu.be/NdlzdPs0QBQ' "
    "and analysis_type='transcription' and audio_tracks='all' and transcription.task='transcribe'. Return "
    "the full verbatim transcript of the video about the AI Engineer role.",
)


class LinkRecognitionTests(SimpleTestCase):
    def test_links_are_recognised_and_paths_are_not(self):
        for value in ('https://www.youtube.com/watch?v=ID', 'http://x.org/a.mp4', 'youtu.be/ID',
                      'www.youtube.com/watch?v=ID', "'https://vimeo.com/1'", ' https://a.b/c '):
            self.assertTrue(fetch.is_url(value), value)
        for value in ('C:\\clips\\a.mp4', 'camcorder_1', 'C:/clips/*.mp4', '', None, 'clip.mp4'):
            self.assertFalse(fetch.is_url(value), value)

    def test_normalize_adds_scheme_and_strips_quotes_and_punctuation(self):
        self.assertEqual(fetch.normalize_url("'youtu.be/ID'."), 'https://youtu.be/ID')
        self.assertEqual(fetch.normalize_url('<https://x.org/v?a=1&b=2>'), 'https://x.org/v?a=1&b=2')

    def test_find_url_in_prose_keeps_the_query_string(self):
        text = 'Transcribe https://www.youtube.com/watch?v=NdlzdPs0QBQ&t=5s, please.'
        self.assertEqual(fetch.find_url(text), 'https://www.youtube.com/watch?v=NdlzdPs0QBQ&t=5s')

    def test_transcription_downloads_only_sound(self):
        self.assertEqual(fetch.media_kind('transcription'), 'audio')
        self.assertEqual(fetch.media_kind('summary'), 'video')
        self.assertEqual(fetch.media_kind('robotics'), 'video')


class CommandTests(SimpleTestCase):
    def test_audio_needs_no_ffmpeg_and_never_converts(self):
        self.assertEqual(fetch.format_selector('audio', 720, False), 'bestaudio/best')
        command = fetch.build_command('https://x/v', 'audio', 'C:\\d', {}, '', '')
        self.assertNotIn('-x', command)
        self.assertNotIn('--extract-audio', command)
        self.assertNotIn('--merge-output-format', command)

    def test_video_without_ffmpeg_never_asks_for_a_merge(self):
        # YouTube has no single sound+picture file any more (2026-10-11): without
        # ffmpeg both are fetched apart (``,``) and joined by PyAV, never merged by yt-dlp.
        selector = fetch.format_selector('video', 720, False)
        self.assertNotIn('+', selector)
        self.assertIn(',ba', selector)
        self.assertIn('+ba', fetch.format_selector('video', 720, True))
        robotics = fetch.format_selector('video', 720, False, need_audio=False)
        self.assertNotIn(',', robotics)
        self.assertNotIn('+', robotics)

    def test_separate_streams_get_one_file_name_per_format(self):
        command = fetch.build_command('https://youtu.be/ID', 'video', 'C:\\d', {}, '', '', need_audio=True)
        self.assertIn('%(extractor_key)s_%(id)s_video-f%(format_id)s.%(ext)s', command)
        merged = fetch.build_command('https://youtu.be/ID', 'video', 'C:\\d', {}, '', 'C:\\ffmpeg.exe')
        self.assertIn('%(extractor_key)s_%(id)s_video.%(ext)s', merged)

    def test_command_is_safe_and_complete(self):
        command = fetch.build_command('https://youtu.be/ID', 'video', 'C:\\dl',
                                      {'cookies_from_browser': 'firefox', 'max_filesize_mb': 50},
                                      'node:C:\\node.exe', 'C:\\ffmpeg.exe')
        self.assertEqual(command[1:3], ['-m', 'yt_dlp'])
        self.assertEqual(command[-2:], ['--', 'https://youtu.be/ID'])  # a link can never be read as an option
        for flag in ('--no-playlist', '--playlist-items', '--no-simulate', '--js-runtimes',
                     '--cookies-from-browser', '--max-filesize', '--merge-output-format'):
            self.assertIn(flag, command)
        printed = ' '.join(command)
        self.assertIn(fetch.FETCH_INFO_MARKER, printed)
        self.assertIn(fetch.FETCH_PATH_MARKER, printed)

    def test_failures_are_named(self):
        cases = {
            'ERROR: [youtube] ID: Private video. Sign in if you have access': 'video_unavailable',
            "ERROR: [youtube] ID: Sign in to confirm you're not a bot": 'login_required',
            'ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>': 'network',
            'ERROR: Unsupported URL: https://example.com/page': 'unsupported_url',
            'ERROR: [youtube] ID: Requested format is not available': 'download_failed',
        }
        for text, code in cases.items():
            self.assertEqual(fetch.classify_failure(text), code, text)


class FetchFlowTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPO / 'Temp')
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.config = {'download': {'download_dir': str(self.dir)}}
        self.downloader = {'source': 'bundled', 'env': {}, 'version': '2026.08.19'}

    def _success_lines(self, kind='audio', name='Youtube_ID_audio.webm'):
        target = self.dir / name
        target.write_bytes(b'media')
        info = {'id': 'ID', 'title': 'Me at the zoo', 'uploader': 'jawed', 'duration': 19,
                'webpage_url': 'https://www.youtube.com/watch?v=ID', 'extractor_key': 'Youtube'}
        return [fetch.FETCH_INFO_MARKER + json.dumps(info), '[download] 100% of 1KiB',
                fetch.FETCH_PATH_MARKER + str(target)]

    def test_success_returns_the_file_and_where_it_came_from(self):
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', return_value=(0, self._success_lines()))):
            result = fetch.fetch('https://youtu.be/ID', 'transcription', self.config)
        self.assertEqual(Path(result['path']).name, 'Youtube_ID_audio.webm')
        self.assertEqual(result['title'], 'Me at the zoo')
        self.assertEqual(result['webpage_url'], 'https://www.youtube.com/watch?v=ID')
        self.assertEqual(result['kind'], 'audio')
        self.assertGreater(result['bytes'], 0)

    def test_missing_printed_path_is_found_by_id(self):
        lines = self._success_lines()[:2]  # no TLM_FETCH_PATH line
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', return_value=(0, lines))):
            result = fetch.fetch('https://youtu.be/ID', 'transcription', self.config)
        self.assertTrue(result['path'].endswith('Youtube_ID_audio.webm'))

    def test_success_with_no_file_on_disk_is_never_reported(self):
        lines = [fetch.FETCH_INFO_MARKER + '{"id": "GONE"}', fetch.FETCH_PATH_MARKER + str(self.dir / 'gone.webm')]
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', return_value=(0, lines))):
            with self.assertRaises(fetch.FetchError) as caught:
                fetch.fetch('https://youtu.be/GONE', 'transcription', self.config)
        self.assertEqual(caught.exception.code, 'empty_file')

    def test_private_video_fails_fast_without_updating(self):
        lines = ['ERROR: [youtube] ID: Private video. Sign in if you have access']
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', return_value=(1, lines)),
              patch.object(fetch, 'install_private') as install):
            with self.assertRaises(fetch.FetchError) as caught:
                fetch.fetch('https://youtu.be/ID', 'transcription', self.config)
        self.assertEqual(caught.exception.code, 'video_unavailable')
        self.assertIn('private', str(caught.exception))
        install.assert_not_called()

    def test_site_change_updates_yt_dlp_once_and_retries(self):
        results = [(1, ['ERROR: [youtube] ID: Requested format is not available']), (0, self._success_lines())]
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', side_effect=results),
              patch.object(fetch, '_update_allowed', return_value=True),
              patch.object(fetch, 'install_private', return_value='2026.10.01') as install,
              patch.object(fetch, '_probe_version', return_value='2026.10.01')):
            result = fetch.fetch('https://youtu.be/ID', 'transcription', self.config)
        install.assert_called_once()
        self.assertEqual(result['downloader'], 'private')

    def test_update_respects_its_cooldown(self):
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', return_value=(1, ['ERROR: something new broke'])),
              patch.object(fetch, '_update_allowed', return_value=False),
              patch.object(fetch, 'install_private') as install):
            with self.assertRaises(fetch.FetchError) as caught:
                fetch.fetch('https://youtu.be/ID', 'transcription', self.config)
        install.assert_not_called()
        self.assertEqual(caught.exception.code, 'download_failed')

    def test_timeout_is_named(self):
        with (patch.object(fetch, 'resolve_downloader', return_value=self.downloader),
              patch.object(fetch, '_run', return_value=(None, ['[download] 3%']))):
            with self.assertRaises(fetch.FetchError) as caught:
                fetch.fetch('https://youtu.be/ID', 'transcription', self.config)
        self.assertEqual(caught.exception.code, 'timeout')

    def test_direct_media_link_survives_a_missing_yt_dlp(self):
        target = self.dir / 'direct.mp4'
        target.write_bytes(b'mp4')
        with (patch.object(fetch, 'resolve_downloader',
                           side_effect=fetch.FetchError('ytdlp_unavailable', 'no pip')),
              patch.object(fetch, '_download_direct', return_value=str(target)) as direct):
            result = fetch.fetch('https://cdn.example.com/talk.mp4', 'summary', self.config)
        direct.assert_called_once()
        self.assertEqual(result['downloader'], 'urllib')
        self.assertEqual(result['path'], str(target))

    def test_page_link_without_yt_dlp_fails_with_a_named_cause(self):
        with patch.object(fetch, 'resolve_downloader',
                          side_effect=fetch.FetchError('ytdlp_unavailable', 'no pip')):
            with self.assertRaises(fetch.FetchError) as caught:
                fetch.fetch('https://www.youtube.com/watch?v=ID', 'transcription', self.config)
        self.assertEqual(caught.exception.code, 'ytdlp_unavailable')

    def test_disabled_downloads_say_so(self):
        with self.assertRaises(fetch.FetchError) as caught:
            fetch.fetch('https://youtu.be/ID', 'transcription', {'download': {'enabled': False}})
        self.assertEqual(caught.exception.code, 'disabled')


class JoinWithoutFfmpegTests(SimpleTestCase):
    """Real (synthetic) media through PyAV -- the path every machine without
    ffmpeg takes for a YouTube summary."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPO / 'Temp')
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def _picture(self, name='Site_ID_video-f1.mp4'):
        import av
        import numpy as np
        path = self.dir / name
        with av.open(str(path), 'w') as output:
            stream = output.add_stream('mpeg4', rate=5)
            stream.width, stream.height, stream.pix_fmt = 64, 48, 'yuv420p'
            for index in range(10):
                frame = av.VideoFrame.from_ndarray(np.full((48, 64, 3), index * 20, np.uint8), format='rgb24')
                frame.pts = index
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        return path

    def _sound(self, name='Site_ID_video-f2.wav'):
        import av
        import numpy as np
        path = self.dir / name
        with av.open(str(path), 'w') as output:
            stream = output.add_stream('pcm_s16le', rate=16000)
            stream.layout = 'mono'
            frame = av.AudioFrame.from_ndarray(np.full((1, 32000), 1000, np.int16), format='s16', layout='mono')
            frame.sample_rate, frame.pts = 16000, 0
            for packet in stream.encode(frame):
                output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        return path

    def test_picture_and_sound_become_one_file_with_both(self):
        import av
        joined = fetch.combine_streams([str(self._picture()), str(self._sound())])
        self.assertTrue(joined.endswith('Site_ID_video.mkv'), joined)  # mpeg4 + pcm -> Matroska
        with av.open(joined) as media:
            self.assertEqual(len(media.streams.video), 1)
            self.assertEqual(len(media.streams.audio), 1)
            self.assertGreater(sum(1 for _ in media.demux(media.streams.video[0]) if _.size), 5)
        self.assertFalse(Path(joined + '.joining').exists())

    def test_a_file_that_already_has_both_is_used_as_is(self):
        joined = fetch.combine_streams([str(self._picture()), str(self._sound())])
        self.assertEqual(fetch.combine_streams([joined]), joined)

    def test_no_picture_is_a_named_failure(self):
        with self.assertRaises(fetch.FetchError) as caught:
            fetch.combine_streams([str(self._sound())])
        self.assertEqual(caught.exception.code, 'download_failed')

    def test_attempt_joins_the_two_printed_files(self):
        picture, sound = self._picture(), self._sound()
        lines = [fetch.FETCH_INFO_MARKER + '{"id": "ID", "title": "T"}',
                 fetch.FETCH_PATH_MARKER + str(picture), fetch.FETCH_PATH_MARKER + str(sound)]
        downloader = {'source': 'bundled', 'env': {}, 'version': 'x'}
        with patch.object(fetch, '_run', return_value=(0, lines)):
            attempt = fetch._attempt('https://youtu.be/ID', 'video', str(self.dir), {}, downloader,
                                     '', '', 60, logging.getLogger(), need_audio=True)
        self.assertTrue(attempt['ok'], attempt)
        self.assertTrue(attempt['path'].endswith('Site_ID_video.mkv'))


class DownloaderResolutionTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPO / 'Temp')
        self.addCleanup(self.temp.cleanup)
        patcher = patch.dict(os.environ, {'TLAMATINI_RUNTIMES': self.temp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_private_copy_lives_beside_the_private_runtimes(self):
        self.assertTrue(fetch.private_dir().startswith(self.temp.name))
        self.assertIn('yt-dlp-py%d%d' % sys.version_info[:2], fetch.private_dir())

    def test_bundled_copy_is_used_when_no_private_copy_exists(self):
        with (patch.object(fetch, '_bundled_is_present', return_value=True),
              patch.object(fetch, '_probe_version', return_value='2026.08.19')):
            result = fetch.resolve_downloader({})
        self.assertEqual(result['source'], 'bundled')

    def test_private_copy_wins_once_it_exists(self):
        package = Path(fetch.private_dir()) / 'yt_dlp'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('', encoding='utf-8')
        with patch.object(fetch, '_probe_version', return_value='2026.10.01'):
            result = fetch.resolve_downloader({})
        self.assertEqual(result['source'], 'private')
        self.assertIn(fetch.private_dir(), result['env']['PYTHONPATH'])

    def test_missing_everywhere_installs_privately_unless_told_not_to(self):
        with (patch.object(fetch, '_bundled_is_present', return_value=False),
              patch.object(fetch, 'install_private', return_value='2026.10.01') as install):
            self.assertEqual(fetch.resolve_downloader({})['source'], 'private')
        install.assert_called_once()
        with patch.object(fetch, '_bundled_is_present', return_value=False):
            with self.assertRaises(fetch.FetchError) as caught:
                fetch.resolve_downloader({'auto_install': False})
        self.assertEqual(caught.exception.code, 'ytdlp_unavailable')

    def test_install_is_atomic_and_never_targets_the_users_site_packages(self):
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            staging = Path(command[command.index('--target') + 1])
            (staging / 'yt_dlp').mkdir(parents=True)
            (staging / 'yt_dlp' / '__init__.py').write_text('', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='Successfully installed yt-dlp', stderr='')

        with (patch.object(fetch.subprocess, 'run', side_effect=fake_run),
              patch.object(fetch, '_probe_version', return_value='2026.10.01')):
            self.assertEqual(fetch.install_private(), '2026.10.01')
        self.assertTrue((Path(fetch.private_dir()) / 'yt_dlp' / '__init__.py').is_file())
        self.assertIn('--target', commands[0])
        self.assertNotIn('--user', commands[0])
        leftovers = [p.name for p in Path(self.temp.name).iterdir() if '.partial-' in p.name or '.old-' in p.name]
        self.assertEqual(leftovers, [])

    def test_failed_update_leaves_the_working_copy_untouched(self):
        package = Path(fetch.private_dir()) / 'yt_dlp'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('# working copy', encoding='utf-8')
        failed = SimpleNamespace(returncode=1, stdout='', stderr='ERROR: No matching distribution')
        with patch.object(fetch.subprocess, 'run', return_value=failed):
            with self.assertRaises(fetch.FetchError):
                fetch.install_private()
        self.assertEqual((package / '__init__.py').read_text(encoding='utf-8'), '# working copy')

    def test_js_runtime_prefers_explicit_then_private_node(self):
        self.assertEqual(fetch.find_js_runtime({'js_runtime': 'none'}), '')
        self.assertEqual(fetch.find_js_runtime({'js_runtime': 'C:\\tools\\node.exe'}), 'node:C:\\tools\\node.exe')
        node_dir = Path(self.temp.name) / 'node' / 'node-v22.20.0-win-x64'
        node_dir.mkdir(parents=True)
        node = node_dir / ('node.exe' if os.name == 'nt' else 'node')
        if os.name != 'nt':
            node = node_dir / 'bin' / 'node'
            node.parent.mkdir()
        node.write_bytes(b'')
        with patch.object(fetch.shutil, 'which', return_value=None):
            self.assertEqual(fetch.find_js_runtime({}), 'node:' + str(node))


class AgentIntegrationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = load_agent()

    def test_links_are_routed_to_the_downloader(self):
        self.assertTrue(self.agent.is_web_link('https://youtu.be/ID'))
        self.assertFalse(self.agent.is_web_link('C:\\clips\\a.mp4'))

    def test_transcription_accepts_plain_audio_files(self):
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            audio = Path(temp) / 'talk.mp3'
            audio.write_bytes(b'mp3')
            self.assertIsNone(self.agent.resolve_video_path(str(audio)))
            self.assertEqual(self.agent.resolve_video_path(str(audio), allow_audio=True), str(audio))

    def test_download_failure_becomes_a_named_fatal(self):
        error = fetch.FetchError('login_required', 'The site wants a signed-in user.')
        fake = SimpleNamespace(FetchError=fetch.FetchError, fetch=lambda *a, **k: (_ for _ in ()).throw(error))
        with patch.object(self.agent, '_load_sibling', return_value=fake):
            with self.assertRaises(self.agent.VideoAnalyzerFatal) as caught:
                self.agent.fetch_web_video('https://youtu.be/ID', 'transcription', {})
        self.assertIn('[login_required]', str(caught.exception))

    def test_result_sections_append_the_source_fields(self):
        pipeline = {'model_1': 'a', 'model_2': 'b', 'merging_model': 'm'}
        source = {'webpage_url': 'https://www.youtube.com/watch?v=ID', 'title': 'Me at the zoo'}
        with self.assertLogs(level='INFO') as logs:
            self.agent.emit_content_result('C:\\x.webm', {
                'analysis_type': 'transcription', 'status': 'transcribed',
                'analysis_token': 'TLM_ANALYSIS::TRANSCRIBED', 'report': 'r', 'source': source}, pipeline)
            self.agent.emit_verdict('C:\\x.mp4', 'UNCLEAR', 0.5, 'analyzed', 1.0, 4, pipeline, 'r', source=source)
        text = '\n'.join(logs.output)
        self.assertEqual(text.count('source_url: https://www.youtube.com/watch?v=ID'), 2)
        self.assertEqual(text.count('source_title: Me at the zoo'), 2)
        content_header = text.split('metadata_json:')[1]
        self.assertIn('source_url:', content_header)  # appended AFTER the existing fields

    def test_content_report_names_the_web_page(self):
        public = content._public_source({'webpage_url': 'https://v/1', 'title': 'T', 'path': 'C:\\secret',
                                         'uploader': 'U', 'bytes': 10})
        self.assertEqual(public, {'webpage_url': 'https://v/1', 'title': 'T', 'uploader': 'U'})


class TranscriberHardwareTests(SimpleTestCase):
    def test_explicit_cpu_threads_are_obeyed(self):
        self.assertEqual(content.cpu_threads({'cpu_threads': 3})[0], 3)

    def test_auto_threads_leave_the_desktop_a_core(self):
        with patch.dict(sys.modules, {'psutil': SimpleNamespace(cpu_count=lambda logical=True: 4)}):
            self.assertEqual(content.cpu_threads({})[0], 3)
        with patch.dict(sys.modules, {'psutil': SimpleNamespace(cpu_count=lambda logical=True: 1)}):
            self.assertEqual(content.cpu_threads({})[0], 1)
        with patch.dict(sys.modules, {'psutil': SimpleNamespace(cpu_count=lambda logical=True: 64)}):
            self.assertEqual(content.cpu_threads({})[0], 16)

    def test_no_gpu_goes_straight_to_cpu(self):
        fake_ct2 = SimpleNamespace(get_cuda_device_count=lambda: 0, __version__='4.8.0')
        with patch.dict(sys.modules, {'ctranslate2': fake_ct2}):
            self.assertEqual(content.cuda_unavailable_reason(), 'no NVIDIA GPU detected')
            engine = content.Transcriber({'device': 'auto', 'model': 'base'})
        self.assertEqual(engine.device, 'cpu')
        self.assertEqual(engine.compute, 'int8')

    def test_missing_cublas_is_named_and_skips_the_gpu(self):
        fake_ct2 = SimpleNamespace(get_cuda_device_count=lambda: 1, __version__='4.8.0')

        def no_dll(name, winmode=None):
            raise OSError(name)

        with (patch.dict(sys.modules, {'ctranslate2': fake_ct2}), patch.object(content.os, 'name', 'nt'),
              patch('ctypes.WinDLL', side_effect=no_dll, create=True)):
            reason = content.cuda_unavailable_reason()
        self.assertIn('cublas64_12.dll', reason)

    def test_glued_prose_still_selects_the_task(self):
        captured = {}

        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, audio, **kwargs):
                captured.update(kwargs)
                return iter(()), SimpleNamespace(language='en')

        with patch.dict(sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=Model)}):
            engine = content.Transcriber({'device': 'cpu', 'model': 'base',
                                          'task': "transcribe'. I need the full transcript"})
            engine.transcribe([0.0])
        self.assertEqual(captured['task'], 'transcribe')


class ChatRequestTests(SimpleTestCase):
    """The wrapped chat tool must turn every historical request into a valid run."""

    def setUp(self):
        from agent import tools
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        self.tools = tools
        self.spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_video_analyzer']

    def _apply(self, request):
        config, error, notes = self.tools._apply_requested_assignments_to_config(template_config(), request)
        self.assertIsNone(error, error)
        notes = list(notes) + self.tools._apply_prose_fallbacks(self.spec, config, request, notes)
        return config, notes

    def test_a_link_query_string_is_never_a_setting(self):
        text = "Transcribe https://www.youtube.com/watch?v=ID&list=PL1 with analysis_type='transcription'"
        self.assertEqual(text[self.tools._find_first_assignment_index(text):][:14], 'analysis_type=')
        self.assertEqual(self.tools._find_first_assignment_index('Watch https://x.org/a?v=1 now'), -1)
        quoted = "url='https://x.org/a?v=1'"
        self.assertEqual(self.tools._find_first_assignment_index(quoted), 0)

    def test_every_historical_request_now_runs_a_transcription_of_the_video(self):
        for request in HISTORICAL_REQUESTS:
            with self.subTest(request=request[:60]):
                config, _ = self._apply(request)
                self.assertTrue(config['video_pathfilenames'].startswith('https://'))
                self.assertIn('NdlzdPs0QBQ', config['video_pathfilenames'])
                self.assertEqual(config['analysis_type'], 'transcription')
                self.assertEqual(config['transcription']['task'], 'transcribe')
                self.assertEqual(config['audio_tracks'], 'all')

    def test_an_explicit_choice_is_never_overridden(self):
        config, _ = self._apply("Transcribe and summarize video_pathfilenames='C:\\a.mp4' and analysis_type='summary'")
        self.assertEqual(config['video_pathfilenames'], 'C:\\a.mp4')
        self.assertEqual(config['analysis_type'], 'summary')

    def test_a_robotics_request_stays_robotics(self):
        config, _ = self._apply('Check that the servo swept in C:\\clips\\servo test.mp4')
        self.assertEqual(config['video_pathfilenames'], 'C:\\clips\\servo test.mp4')
        self.assertEqual(config['analysis_type'], 'robotics')

    def test_summary_wins_over_transcript_words(self):
        config, _ = self._apply('Summarize https://vimeo.com/76979871 and include the transcript')
        self.assertEqual(config['analysis_type'], 'summary')

    def test_trailing_prose_is_cut_at_the_real_closing_quote(self):
        coerce = self.tools._coerce_assignment_value
        self.assertEqual(coerce("'transcribe'. I need the full transcript."), 'transcribe')
        self.assertEqual(coerce("'I'm done'. Thanks"), "I'm done")
        self.assertEqual(coerce("'Angela's report"), "Angela's report")
        self.assertEqual(coerce("'He said 'yes', then left"), "He said 'yes', then left")

    def test_prose_fallbacks_never_raise(self):
        self.assertEqual(self.tools._apply_prose_fallbacks(self.spec, None, 'x', []), [])


class LlmFacingTextTests(SimpleTestCase):
    """The tool text IS the contract the model obeys (CLAUDE.md pitfall 13)."""

    def test_video_analyzer_tells_the_model_to_pass_links_straight_in(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_video_analyzer']
        self.assertIn('DOWNLOADED BY', spec.purpose)
        self.assertIn('NEVER install yt-dlp', spec.purpose)
        self.assertIn("video_pathfilenames='https://www.youtube.com/watch?v=VIDEO_ID'", spec.example_request)

    def test_whisperer_sends_videos_to_video_analyzer(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_whisperer']
        self.assertIn('call chat_agent_video_analyzer', spec.purpose)

    def test_system_prompt_forbids_hand_installing_a_downloader(self):
        prompt = (ROOT / 'prompt.pmt').read_text(encoding='utf-8')
        self.assertIn('goes STRAIGHT into Video-Analyzer', prompt)
        self.assertIn('Never install yt-dlp', prompt)


class CarriageTests(SimpleTestCase):
    """Default install, self-update and self-modify must all carry the repair."""

    def test_yt_dlp_ships_inside_tlamatinis_own_python(self):
        requirements = (REPO / 'requirements.txt').read_text(encoding='utf-8')
        self.assertRegex(requirements, r'(?m)^yt-dlp==\d{4}\.\d+\.\d+$')
        build = (REPO / 'build.py').read_text(encoding='utf-8')
        # The tuple's comments contain parentheses: cut at its closing line instead.
        runtime_imports = build.split('_AGENT_RUNTIME_IMPORTS = (', 1)[1].split('\n)', 1)[0]
        self.assertIn('"yt_dlp"', runtime_imports)

    def test_existing_pools_receive_the_new_sibling(self):
        knowledge = (ROOT / 'services' / 'flow_knowledge.py').read_text(encoding='utf-8')
        self.assertIn('"video_fetch.py"', knowledge)

    def test_parametrizer_sees_the_appended_fields(self):
        contracts = (ROOT / 'services' / 'agent_contracts.py').read_text(encoding='utf-8')
        block = contracts.split('"video_analyzer": (', 1)[1].split(')', 1)[0]
        self.assertLess(block.index('"metadata_json"'), block.index('"source_url"'))
        self.assertIn('"source_title"', block)

    def test_config_keys_resolve_without_ambiguity(self):
        config = template_config()
        self.assertIn('download_dir', config['download'])
        self.assertNotIn('output_dir', config['download'])  # top-level output_dir already exists
