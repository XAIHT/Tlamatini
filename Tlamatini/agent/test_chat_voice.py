# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Direct dictation regressions. Run in a verified visible foreground console.

No live microphone, model download or playback: hardware evidence is separate.
"""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import numpy as np
from asgiref.testing import ApplicationCommunicator

from agent import chat_voice_consumer as consumer
from agent import chat_voice_runtime as voice
from agent.chat_voice_runtime import VoiceRuntime
from agent.test_whisperer_agent import _load_whisperer_module, _FakeSounddevice


def load_worker():
    path = Path(__file__).parent / "agents/whisperer/chat_worker.py"
    spec = importlib.util.spec_from_file_location("dictation_worker_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DirectCaptureTests(unittest.TestCase):
    def setUp(self):
        self.w = _load_whisperer_module()

    def test_cancelled_before_start_never_opens_device(self):
        cancel = threading.Event()
        cancel.set()
        fake = _FakeSounddevice()
        with patch.dict(sys.modules, sounddevice=fake):
            with patch.object(self.w, "resolve_input_device") as resolve:
                with self.assertRaises(self.w.CaptureCancelled):
                    self.w.record_from_microphone({}, cancel_event=cancel, strict_stream=True)
                resolve.assert_not_called()

    def test_strict_stream_refuses_the_ungated_fallback(self):
        fake = _FakeSounddevice()
        with patch.dict(sys.modules, sounddevice=fake):
            with patch.object(fake, "InputStream", side_effect=OSError("no live stream")):
                with patch.object(fake, "rec") as rec:
                    with self.assertRaisesRegex(RuntimeError, "Live microphone capture"):
                        self.w.record_from_microphone({}, progress=Mock(), strict_stream=True)
                    rec.assert_not_called()

    def test_live_progress_reuses_the_real_gate_without_console_io_in_callback(self):
        fake = _FakeSounddevice()
        fake.script = [.2] * 5 + [0.0] * 30
        progress = Mock()
        with patch.dict(sys.modules, sounddevice=fake):
            with patch.object(self.w.MicRecIndicator, "on") as console:
                audio, meta = self.w.record_from_microphone(
                    {"silence_timeout_seconds": .1}, progress=progress, strict_stream=True)
        self.assertGreater(len(audio), 0)
        self.assertEqual(meta["stop_reason"], "silence")
        self.assertGreater(meta["speech_seconds"], 0)
        self.assertEqual(progress.call_args.args[0]["event"], "recording")
        self.assertEqual(progress.call_args.args[0]["silence_timeout"], .1)
        console.assert_not_called()

    def test_cancellation_from_progress_closes_stream_and_drops_audio(self):
        fake = _FakeSounddevice()
        fake.script = [.2] * 5 + [0.0] * 30
        cancel = threading.Event()
        with patch.dict(sys.modules, sounddevice=fake):
            with self.assertRaises(self.w.CaptureCancelled):
                self.w.record_from_microphone(
                    {"silence_timeout_seconds": .1}, progress=lambda data: cancel.set(),
                    cancel_event=cancel, strict_stream=True)

    def test_model_cache_reuses_weights_and_evicts_an_old_selection(self):
        constructor = Mock(side_effect=lambda *a, **kw: SimpleNamespace(model=a[0], device=kw["device"]))
        with patch.dict(sys.modules, faster_whisper=SimpleNamespace(WhisperModel=constructor)):
            cache = {}
            first = self.w.load_recognition_model("base", "cpu", "int8", cache)
            self.assertIs(first, self.w.load_recognition_model("base", "cpu", "int8", cache))
            self.w.load_recognition_model("small", "cpu", "int8", cache)
            self.assertEqual(constructor.call_count, 2)
            self.assertEqual(list(cache), [("small", "cpu", "int8")])

    def test_model_cache_gpu_failure_retains_cpu_fallback(self):
        def constructor(*a, **kw):
            if kw["device"] == "cuda":
                raise RuntimeError("GPU unavailable")
            return SimpleNamespace()
        with patch.dict(sys.modules, faster_whisper=SimpleNamespace(WhisperModel=Mock(side_effect=constructor))):
            cache = {}
            model = self.w.warm_recognition_model({"device": "cuda", "model": "base"}, cache)
            self.assertIs(model, cache[("base", "cpu", "int8")])


class WorkerPipelineTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.module = load_worker()
        self.cancelled = threading.Event()
        self.w = SimpleNamespace(
            __file__=str(Path(__file__).parent / "agents/whisperer/whisperer.py"),
            CaptureCancelled=type("CaptureCancelled", (Exception,), {}),
            load_config=Mock(return_value={"engine": "faster-whisper", "model": "base",
                                          "silence_timeout_seconds": 3.5}),
            warm_recognition_model=Mock(),
            transcribe_faster_whisper=Mock(return_value={"text": "  Build my project.  "}),
        )
        def capture(config, *, progress, cancel_event, strict_stream):
            self.assertTrue(strict_stream)
            self.assertEqual(config["record_seconds"], 0)
            self.assertEqual(config["silence_gate"], "on")
            self.assertFalse(config["ollama_cleanup"])
            self.assertIs(cancel_event, self.cancelled)
            progress({"event": "recording", "level": .5, "elapsed": .02,
                      "silence": 0, "silence_timeout": 3.5})
            return np.zeros(1600, np.float32), {
                "speech_seconds": .1, "stop_reason": "silence", "duration_seconds": 3.6}
        self.w.record_from_microphone = Mock(side_effect=capture)
        self.worker = self.module.DictationWorker(self.events.append, self.w)

    def test_gated_transcript_is_trimmed_and_emitted_once_after_capture(self):
        self.worker.run("one", self.cancelled)
        self.assertEqual([e["event"] for e in self.events], ["recording", "transcribing", "result"])
        self.assertEqual(self.events[-1]["text"], "Build my project.")
        self.assertEqual(self.events[-1]["stop_reason"], "silence")
        self.w.transcribe_faster_whisper.assert_called_once()
        self.assertIs(self.w.transcribe_faster_whisper.call_args.kwargs["model_cache"], self.worker.cache)
        self.assertFalse(self.worker.busy)

    def test_silent_capture_never_invokes_asr(self):
        self.w.record_from_microphone.return_value = (
            np.zeros(100), {"speech_seconds": 0, "stop_reason": "silence", "duration_seconds": 3.5})
        self.w.record_from_microphone.side_effect = None
        self.worker.run("one", self.cancelled)
        self.w.transcribe_faster_whisper.assert_not_called()
        self.assertEqual(self.events[-1]["event"], "empty")

    def test_cancel_during_decode_discards_even_a_valid_transcript(self):
        def transcribe(*args, **kwargs):
            self.cancelled.set()
            return {"text": "Never execute this."}
        self.w.transcribe_faster_whisper.side_effect = transcribe
        self.worker.run("one", self.cancelled)
        self.assertEqual(self.events[-1]["event"], "cancelled")
        self.assertNotIn("result", [e["event"] for e in self.events])

    def test_config_loader_exit_is_a_terminal_error_and_releases_the_worker(self):
        self.w.load_config.side_effect = SystemExit(1)
        self.worker.busy = True
        self.worker.run("one", self.cancelled)
        self.assertEqual(self.events[-1]["event"], "error")
        self.assertFalse(self.worker.busy)
        self.w.record_from_microphone.assert_not_called()

    def test_unknown_engine_is_an_error_and_does_not_call_an_llm(self):
        self.w.load_config.return_value["engine"] = "unknown"
        self.worker.run("one", self.cancelled)
        self.assertEqual(self.events[-1]["event"], "error")
        self.w.transcribe_faster_whisper.assert_not_called()

    def test_duplicate_start_does_not_replace_an_active_capture(self):
        self.worker.busy = True
        self.worker.run_id = "first"
        self.worker.start("second")
        self.assertEqual(self.worker.run_id, "first")
        self.assertEqual(self.events[-1]["event"], "error")


    def test_capture_preferences_reach_capture_and_recognition_without_changing_template(self):
        source = self.w.load_config.return_value.copy()
        overrides = {"input_gain_percent": 150, "silence_timeout_seconds": 2,
                     "language": "es", "task": "translate", "vad_filter": False}
        self.worker.run("configured", self.cancelled, overrides)
        capture = self.w.record_from_microphone.call_args.args[0]
        for key, value in overrides.items():
            self.assertEqual(capture[key], value)
        self.assertEqual(self.w.transcribe_faster_whisper.call_args.args[1]["language"], "es")
        self.assertFalse(capture["ollama_cleanup"])
        # The real loader gives a new dict per run; no persistent config file is written.
        self.assertEqual(source["silence_timeout_seconds"], 3.5)

    def test_removed_device_cannot_silently_record_another_microphone(self):
        with patch.object(self.module, "input_devices", return_value=[]):
            self.worker.run("missing", self.cancelled,
                            {"device_index": 7, "device_name": "USB", "device_hostapi": "WASAPI"})
        self.w.record_from_microphone.assert_not_called()
        self.assertEqual(self.events[-1]["event"], "error")

    def test_device_identity_survives_changed_portaudio_index(self):
        options = [{"index": 9, "name": "USB", "hostapi": "WASAPI"}]
        with patch.object(self.module, "input_devices", return_value=options):
            self.worker.run("moved", self.cancelled,
                            {"device_index": 7, "device_name": "USB", "device_hostapi": "WASAPI"})
        capture = self.w.record_from_microphone.call_args.args[0]
        self.assertEqual(capture["device_index"], 9)
        self.assertNotIn("device_hostapi", capture)
        self.assertEqual(self.events[-1]["event"], "result")

    def test_invalid_preferences_do_not_open_the_microphone(self):
        self.worker.run("bad", self.cancelled, {"input_gain_percent": 10000})
        self.w.record_from_microphone.assert_not_called()
        self.assertEqual(self.events[-1]["event"], "error")


class BrokerTests(unittest.TestCase):
    def test_two_tabs_cannot_share_a_microphone_job(self):
        runtime = VoiceRuntime()
        runtime.ensure_ready = Mock()
        runtime._send = Mock()
        runtime.start("first", Mock())
        with self.assertRaisesRegex(RuntimeError, "already in use"):
            runtime.start("second", Mock())
        self.assertEqual(runtime.active[0], "first")
        runtime.cancel("second")
        self.assertEqual(runtime._send.call_count, 1)
        runtime.cancel("first")
        self.assertEqual(runtime._send.call_args.args[0]["action"], "cancel")

    def test_send_failure_releases_ownership(self):
        runtime = VoiceRuntime()
        runtime.ensure_ready = Mock()
        runtime._send = Mock(side_effect=OSError("closed"))
        with self.assertRaises(OSError):
            runtime.start("first", Mock())
        self.assertIsNone(runtime.active)


class WorkerLifecycleTests(unittest.TestCase):
    def launch(self, ready="ready"):
        runtime = VoiceRuntime()
        process = Mock(stdout=io.StringIO("worker ready\n"))
        connection = Mock()
        connection.makefile.return_value = io.BytesIO(
            (json.dumps({"token": "test-token"}) + "\n" +
             json.dumps({"event": ready}) + "\n").encode())
        listener = MagicMock()
        listener.__enter__.return_value = listener
        listener.getsockname.return_value = ("127.0.0.1", 12345)
        listener.accept.return_value = (connection, ("127.0.0.1", 12346))
        script = Path(__file__).parent / "agents/whisperer/chat_worker.py"
        with patch.object(voice, "worker_launch", return_value=(sys.executable, script)), \
                patch.object(voice, "get_app_temp_root", return_value=str(script.parent)), \
                patch.object(voice.secrets, "token_hex", return_value="test-token"), \
                patch.object(voice.socket, "socket", return_value=listener), \
                patch.object(voice.subprocess, "Popen", return_value=process) as launch, \
                patch.object(voice.threading, "Thread"):
            if ready == "ready":
                runtime.ensure_ready()
            else:
                with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                    runtime.ensure_ready()
        return runtime, process, connection, launch

    def test_worker_launch_has_no_shell_window_or_automatic_recording(self):
        runtime, process, connection, launch = self.launch()
        args = launch.call_args.args[0]
        options = launch.call_args.kwargs
        self.assertEqual(args[0], sys.executable)
        self.assertEqual(args[1], "-u")
        self.assertEqual(Path(args[2]).name, "chat_worker.py")
        self.assertEqual(args[3], "12345")
        expected = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.assertEqual(options["creationflags"], expected)
        self.assertFalse(options.get("shell", False))
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["stdout"], subprocess.PIPE)
        self.assertEqual(options["stderr"], subprocess.STDOUT)
        self.assertEqual(options["encoding"], "utf-8")
        connection.sendall.assert_not_called()
        self.assertIs(runtime.process, process)

    def test_failed_startup_reaps_the_child(self):
        runtime, process, connection, _ = self.launch("error")
        process.wait.assert_called_once_with(timeout=2)
        connection.close.assert_called_once()
        self.assertIsNone(runtime.process)
        self.assertIsNone(runtime.connection)

    def test_close_sends_shutdown_and_reaps_only_its_child(self):
        runtime, process, connection, _ = self.launch()
        runtime.close()
        self.assertEqual(json.loads(connection.sendall.call_args.args[0]), {"action": "shutdown"})
        process.wait.assert_called_once_with(timeout=2)
        process.terminate.assert_not_called()
        self.assertIsNone(runtime.process)

    def test_stuck_worker_has_bounded_shutdown(self):
        process = Mock()
        process.wait.side_effect = [
            subprocess.TimeoutExpired("worker", 2),
            subprocess.TimeoutExpired("worker", 2), 0]
        VoiceRuntime._stop_process(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 3)

    def test_worker_output_reaches_main_application_logger(self):
        output = io.StringIO("READY\n\nTraceback: diagnostic\n")
        with self.assertLogs("agent.chat_voice_runtime", level="INFO") as records:
            VoiceRuntime._relay_output(SimpleNamespace(stdout=output))
        self.assertEqual(len(records.output), 2)
        self.assertIn("[Whisperer] READY", records.output[0])
        self.assertIn("[Whisperer] Traceback: diagnostic", records.output[1])
        self.assertTrue(output.closed)


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.emit = None

    def ensure_ready(self):
        self.calls.append("prepare")

    def get_options(self, refresh=False):
        return {"devices": [], "defaults": {"input_gain_percent": 100}}

    def start(self, run_id, emit, capture_settings=None):
        self.settings = capture_settings
        self.calls.append(("start", run_id))
        self.emit = emit

    def cancel(self, run_id):
        self.calls.append(("cancel", run_id))


class VoiceSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = FakeRuntime()
        self.patch = patch.object(consumer, "runtime", self.runtime)
        self.patch.start()
        self.sockets = []

    async def asyncTearDown(self):
        for socket in self.sockets:
            await socket.send_input({"type": "websocket.disconnect", "code": 1000})
            await socket.wait(timeout=2)
        self.patch.stop()

    async def connect(self, authenticated=True, origin="http://localhost:8000"):
        socket = ApplicationCommunicator(consumer.ChatVoiceConsumer.as_asgi(), {
            "type": "websocket", "path": "/ws/chat-voice/",
            "user": SimpleNamespace(is_authenticated=authenticated, pk=1),
            "headers": [(b"origin", origin.encode()), (b"host", b"localhost:8000")]})
        self.sockets.append(socket)
        await socket.send_input({"type": "websocket.connect"})
        first = await socket.receive_output(timeout=2)
        if first["type"] == "websocket.accept":
            self.assertEqual((await self.event(socket))["event"], "preparing")
            self.assertEqual((await self.event(socket))["event"], "ready")
        return socket, first

    async def send(self, socket, **data):
        await socket.send_input({"type": "websocket.receive", "text": json.dumps(data)})

    async def event(self, socket):
        return json.loads((await socket.receive_output(timeout=2))["text"])

    async def start(self, socket, run_id="one"):
        await self.send(socket, action="start", run_id=run_id)
        self.assertEqual((await self.event(socket))["event"], "starting")
        for _ in range(100):
            if self.runtime.emit:
                return
            await asyncio.sleep(.01)
        self.fail("No direct worker start")

    async def test_anonymous_and_foreign_origin_are_rejected_before_worker_start(self):
        _, anonymous = await self.connect(authenticated=False)
        _, foreign = await self.connect(origin="https://attacker.example")
        self.assertEqual(anonymous["code"], 4401)
        self.assertEqual(foreign["code"], 4403)
        self.assertEqual(self.runtime.calls, [])

    async def test_connect_only_prepares_and_never_opens_microphone(self):
        await self.connect()
        self.assertEqual(self.runtime.calls, ["prepare"])

    async def test_start_uses_direct_worker_and_rejects_overlapping_start(self):
        socket, _ = await self.connect()
        await self.start(socket)
        await self.send(socket, action="start", run_id="two")
        self.assertEqual((await self.event(socket))["event"], "rejected")
        self.assertEqual(self.runtime.calls, ["prepare", ("start", "one")])

    async def test_malformed_command_does_not_break_socket(self):
        socket, _ = await self.connect()
        for text in ("{", "[]", "null", "x" * 1025):
            await socket.send_input({"type": "websocket.receive", "text": text})
            self.assertEqual((await self.event(socket))["event"], "rejected")
        await self.start(socket)

    async def test_cancel_drops_a_late_result_and_allows_next_turn(self):
        socket, _ = await self.connect()
        await self.start(socket)
        await self.send(socket, action="cancel", run_id="one")
        self.assertEqual((await self.event(socket))["event"], "cancelling")
        self.runtime.emit({"event": "result", "run_id": "one", "text": "Do not send"})
        self.assertEqual((await self.event(socket))["event"], "cancelled")
        self.runtime.emit = None
        await self.start(socket, "two")

    async def test_stale_results_are_ignored(self):
        socket, _ = await self.connect()
        await self.start(socket)
        self.runtime.emit({"event": "result", "run_id": "old", "text": "Do not send"})
        self.runtime.emit({"event": "recording", "run_id": "one", "level": .2})
        self.assertEqual((await self.event(socket))["event"], "recording")

    async def test_invalid_settings_rejected_before_capture_and_socket_recovers(self):
        socket, _ = await self.connect()
        await self.send(socket, action="start", run_id="bad", settings={"record_seconds": 999})
        event = await self.event(socket)
        self.assertEqual(event["event"], "rejected")
        self.assertEqual(event["run_id"], "bad")
        self.assertEqual(self.runtime.calls, ["prepare"])
        await self.start(socket, "valid")

    async def test_settings_forwarded_to_owned_job(self):
        socket, _ = await self.connect()
        options = {"input_gain_percent": 125, "silence_timeout_seconds": 1.5}
        await self.send(socket, action="start", run_id="configured", settings=options)
        self.assertEqual((await self.event(socket))["event"], "starting")
        for _ in range(100):
            if self.runtime.emit:
                break
            await asyncio.sleep(.01)
        self.assertEqual(self.runtime.settings, options)

    async def test_options_refresh_never_starts_recording(self):
        socket, _ = await self.connect()
        await self.send(socket, action="options")
        event = await self.event(socket)
        self.assertEqual(event["event"], "options")
        self.assertIn("defaults", event)
        self.assertEqual(self.runtime.calls, ["prepare"])
        self.assertIsNone(self.runtime.emit)

    async def test_disconnect_cancels_only_its_owned_run(self):
        socket, _ = await self.connect()
        await self.start(socket)
        await socket.send_input({"type": "websocket.disconnect", "code": 1000})
        await socket.wait(timeout=2)
        self.sockets.remove(socket)
        self.assertIn(("cancel", "one"), self.runtime.calls)

class MicSettingsValidationTests(unittest.TestCase):
    def test_untrusted_capture_options_are_rejected(self):
        from agent.chat_voice_settings import validate_capture_settings
        invalid = [
            {"input_source": "file"}, {"cloud_api_key": "injected"},
            {"record_seconds": 9}, {"target_agents": ["executer"]},
            {"input_gain_percent": float("nan")}, {"input_gain_percent": 301},
            {"silence_timeout_seconds": 0}, {"max_record_seconds": 99999},
            {"silence_threshold_db": -1}, {"sample_rate": 96000},
            {"channels": True}, {"vad_filter": "true"}, {"beam_size": 1.5},
            {"language": "en-US"}, {"task": "run"}, {"device_index": 3},
            {"device_name": "\nnot-a-device"}, [], None,
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_capture_settings(value)

    def test_defaults_never_expose_provider_secrets(self):
        from agent.chat_voice_settings import public_defaults
        result = public_defaults({"cloud_api_key": "private", "ollama_token": "private",
                                  "input_gain_percent": 150, "language": "es"})
        self.assertNotIn("cloud_api_key", result)
        self.assertNotIn("ollama_token", result)
        self.assertEqual(result["input_gain_percent"], 150)
        self.assertEqual(result["language"], "es")

    def test_valid_capture_options_are_copied(self):
        from agent.chat_voice_settings import validate_capture_settings
        options = {"input_gain_percent": 0, "silence_threshold_db": -60,
                   "silence_timeout_seconds": .3, "max_record_seconds": 5,
                   "sample_rate": 48000, "channels": 2, "language": "es",
                   "task": "translate", "beam_size": 1, "vad_filter": False}
        result = validate_capture_settings(options)
        self.assertEqual(result, options)
        self.assertIsNot(result, options)
