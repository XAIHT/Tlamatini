# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Her voice must be unstoppable (Angela, 2026-11-11).

* host_voice.py: settings are clamped, pages are counted per account, an
  answer that finishes with no page open is announced on this computer's
  speakers, the Windows voice runs hidden and female-only, Stop and Silent
  always win.
* host_voice_views.py: the four endpoints, including the form a closing page
  posts with ``navigator.sendBeacon``.
* voice_runtime.js: the browser engine, run against a fake speaker by
  ``scripts/voice_runtime_cases.mjs`` (no browser, no audio).

Silent by design: nothing here starts PowerShell or plays a sound.
"""

import base64
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.middleware.csrf import _get_new_csrf_string
from django.test import Client, SimpleTestCase, TestCase

from agent import host_voice
from agent.constants import display_name, say

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parents[1]
JS_DIR = AGENT_DIR / "static" / "agent" / "js"


def _reset():
    with host_voice._LOCK:
        host_voice._QUEUE.clear()
        host_voice._JOBS.clear()
        host_voice._SETTINGS.clear()
        host_voice._PAGES.clear()
        host_voice._CURRENT.update({"job": None, "proc": None})


class _StopWorker(BaseException):
    """Ends a test's worker thread; the real worker never sees it."""


class _QuietRun:
    """A stand-in for the PowerShell child: records the jobs, makes no sound."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job_id, job):
        if job["text"] == "__stop-the-test-worker__":
            raise _StopWorker()
        self.jobs.append(job["text"])
        return True


class HostVoiceStateTests(TestCase):
    def setUp(self):
        _reset()
        self.run = _QuietRun()
        for target, value in (("_run", self.run), ("_ensure_worker_locked", lambda: None)):
            patcher = mock.patch.object(host_voice, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(_reset)

    def _audible(self):
        patcher = mock.patch.object(host_voice, "available", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_settings_are_clamped_and_cleaned(self):
        clean = host_voice.update_settings(1, {"mode": "loud", "volume": 500, "rate": 9, "pitch": -1,
                                               "voice": "x" * 500, "lang": "es-MX<script>"})
        self.assertEqual(clean["mode"], "notify")
        self.assertEqual((clean["volume"], clean["rate"], clean["pitch"]), (100.0, 2.0, 0.0))
        self.assertEqual(len(clean["voice"]), 120)
        self.assertNotIn("<", clean["lang"])
        self.assertEqual(host_voice.update_settings(1, {"volume": "nan"})["volume"], 100.0)

    def test_pages_are_counted_per_account(self):
        host_voice.page_opened(1)
        host_voice.page_opened(1)
        host_voice.page_closed(1)
        self.assertTrue(host_voice.has_page(1))
        self.assertFalse(host_voice.has_page(2))
        host_voice.page_closed(1)
        host_voice.page_closed(1)
        self.assertFalse(host_voice.has_page(1))
        host_voice.page_opened(1)
        self.assertTrue(host_voice.has_page(1), "a stray close must never leave a negative count")

    def test_test_runs_never_speak(self):
        with mock.patch.dict(os.environ, {"TLAMATINI_NO_AUDIO": "1"}):
            self.assertFalse(host_voice.available())
            self.assertIsNone(host_voice.speak(1, "Hello"))
        self.assertFalse(host_voice._QUEUE)

    def test_one_job_per_message_and_only_its_own_account_sees_it(self):
        self._audible()
        job = host_voice.speak(1, "Hello   Angela.\n")
        self.assertTrue(job)
        self.assertEqual(host_voice._JOBS[job]["text"], "Hello Angela.")
        self.assertEqual(host_voice.status(1, job)["state"], "queued")
        self.assertTrue(host_voice.status(1)["busy"])
        self.assertEqual(host_voice.status(2, job)["state"], "unknown")
        self.assertFalse(host_voice.status(2)["busy"])

    def test_silent_mode_and_zero_volume_never_speak(self):
        self._audible()
        self.assertIsNone(host_voice.speak(1, "Hi", {"mode": "silent"}))
        self.assertIsNone(host_voice.speak(2, "Hi", {"volume": 0}))
        self.assertFalse(host_voice._QUEUE)

    def test_stop_stops_only_this_account(self):
        self._audible()
        mine, theirs = host_voice.speak(1, "Mine"), host_voice.speak(2, "Theirs")
        host_voice.stop(1)
        self.assertEqual(host_voice._JOBS[mine]["state"], "stopped")
        self.assertEqual(host_voice._JOBS[theirs]["state"], "queued")
        self.assertEqual(list(host_voice._QUEUE), [theirs])

    def test_stop_and_silent_kill_the_child_that_is_speaking(self):
        proc = mock.Mock()
        host_voice._JOBS["j"] = {"user": 1, "text": "x", "settings": dict(host_voice.DEFAULTS), "state": "speaking", "at": 0}
        host_voice._CURRENT.update({"job": "j", "proc": proc})
        host_voice.update_settings(1, {"mode": "silent"})
        proc.kill.assert_called_once()
        self.assertEqual(host_voice._JOBS["j"]["state"], "stopped")

    def test_plain_text_drops_markup_and_the_exec_report(self):
        answer = ('<p>Done &amp; <b>dusted</b>.</p><table class="exec-report-table"><tr><td>rm -rf</td></tr></table>'
                  '<script>alert(1)</script>END-RESPONSE')
        self.assertEqual(host_voice.plain_text(answer), "Done & dusted .")

    def test_the_worker_speaks_queued_jobs_in_order(self):
        self._audible()
        _reset()
        self.addCleanup(_reset)
        hook = threading.excepthook
        threading.excepthook = lambda args: None if args.exc_type is _StopWorker else hook(args)
        self.addCleanup(setattr, threading, "excepthook", hook)
        worker = threading.Thread(target=host_voice._worker, daemon=True)
        worker.start()
        first, second = host_voice.speak(1, "One."), host_voice.speak(1, "Two.")
        with host_voice._LOCK:
            host_voice._LOCK.notify_all()
        deadline = time.time() + 10
        while time.time() < deadline and host_voice.status(1, second)["state"] != "done":
            time.sleep(0.05)
        self.assertEqual(host_voice.status(1, first)["state"], "done")
        self.assertEqual(host_voice.status(1, second)["state"], "done")
        self.assertEqual(self.run.jobs, ["One.", "Two."])
        host_voice.speak(1, "__stop-the-test-worker__")
        with host_voice._LOCK:
            host_voice._LOCK.notify_all()
        worker.join(10)
        self.assertFalse(worker.is_alive())


class AnswerWithNoPageTests(TestCase):
    """An answer that finishes while no chat page of that account is open."""

    def setUp(self):
        _reset()
        self.addCleanup(_reset)
        self.user = SimpleNamespace(id=7, first_name="Angela", last_name="", username="angela")
        self.spoken = []
        patcher = mock.patch.object(host_voice, "speak", side_effect=lambda uid, text, *a, **k: self.spoken.append((uid, text)) or "job")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_open_page_speaks_for_herself(self):
        host_voice.page_opened(7)
        self.assertIsNone(host_voice.answer_finished(self.user, "<p>The answer</p>"))
        self.assertEqual(self.spoken, [])

    def test_notify_mode_announces_the_finished_request(self):
        self.assertEqual(host_voice.answer_finished(self.user, "<p>The answer</p>"), "job")
        expected = host_voice.prepare(say(host_voice.COMPLETE_PHRASE, display_name(self.user)), self.user)
        self.assertEqual(self.spoken, [(7, expected)])

    def test_speak_mode_reads_the_answer_itself(self):
        host_voice.update_settings(7, {"mode": "speak"})
        host_voice.answer_finished(self.user, "<p>The answer is <b>42</b>.</p>END-RESPONSE")
        self.assertEqual(self.spoken, [(7, host_voice.prepare("The answer is 42 .", self.user))])

    def test_silent_mode_says_nothing(self):
        host_voice.update_settings(7, {"mode": "silent"})
        self.assertIsNone(host_voice.answer_finished(self.user, "x"))
        self.assertEqual(self.spoken, [])

    def test_a_broken_announcement_never_costs_the_answer(self):
        self.assertIsNone(host_voice.answer_finished(object(), "x"))


class _FakeProc:
    def __init__(self, out, code):
        self.out, self.returncode, self.stdin = out, code, None
        self.killed = False

    def communicate(self, data=None, timeout=None):
        self.stdin = data
        return self.out, b""

    def kill(self):
        self.killed = True


class WindowsVoiceCallTests(SimpleTestCase):
    def setUp(self):
        _reset()
        self.addCleanup(_reset)

    def _run(self, out, code, settings=None):
        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            calls.append(_FakeProc(out, code))
            return calls[-1]

        s = dict(host_voice.DEFAULTS, **(settings or {}))
        job = {"user": 1, "text": "Hello <Angela> & you", "settings": s, "state": "speaking", "at": 0}
        host_voice._JOBS["j"] = job
        with mock.patch.object(host_voice.subprocess, "Popen", popen):
            ok = host_voice._run("j", job)
        (args, kwargs), proc = calls
        return ok, args, kwargs, json.loads(base64.b64decode(proc.stdin))

    def test_the_child_is_hidden_and_gets_the_user_settings(self):
        ok, args, kwargs, payload = self._run(b"VOICE Microsoft Zira Desktop en-US\r\nDONE\r\n", 0,
                                              {"volume": 40, "rate": 2.0, "pitch": 1.5, "voice": "Zira"})
        self.assertTrue(ok)
        self.assertEqual(kwargs["creationflags"] & getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertNotIn("shell", kwargs)
        script = base64.b64decode(args[args.index("-EncodedCommand") + 1]).decode("utf-16-le")
        self.assertEqual(script, host_voice._SAPI_SCRIPT)
        self.assertEqual((payload["volume"], payload["rate"], payload["voice"]), (40, 10, "Zira"))
        self.assertEqual(payload["lang"], host_voice.EDITION_LANG)
        self.assertEqual(payload["any"], host_voice.ANY_LANGUAGE_FALLBACK)
        self.assertIn("Hello &lt;Angela&gt; &amp; you", payload["ssml"])
        self.assertIn('<prosody pitch="high">', payload["ssml"])

    def test_no_female_voice_means_silence_not_a_substitute(self):
        ok, *_ = self._run(b"NO-FEMALE-VOICE\r\n", 3)
        self.assertFalse(ok)
        self.assertIn("VoiceGender]::Female", host_voice._SAPI_SCRIPT)
        self.assertIn("exit 3", host_voice._SAPI_SCRIPT)

    def test_rate_and_pitch_map_onto_sapi(self):
        self.assertEqual([host_voice._sapi_rate(r) for r in (0.5, 1.0, 1.5, 2.0, 9)], [-10, 0, 6, 10, 10])
        self.assertNotIn("prosody", host_voice._ssml("a", 1.05))
        self.assertIn('pitch="low"', host_voice._ssml("a", 0.5))
        self.assertIn('xml:lang="__LANG__"', host_voice._ssml("a", 1.0))


class HostVoiceEndpointTests(TestCase):
    def setUp(self):
        _reset()
        self.addCleanup(_reset)
        self.user = get_user_model().objects.create_user(username="voice_tester", password="not-used")
        self.calls = []
        patcher = mock.patch.object(host_voice, "speak", side_effect=lambda *a, **k: self.calls.append(a) or "job42")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _client(self, csrf=False):
        client = Client(enforce_csrf_checks=csrf)
        client.force_login(self.user)
        return client

    def test_signed_out_pages_get_nothing(self):
        response = Client().post("/agent/voice/host/speak/", {"payload": "{}"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.calls, [])

    def test_settings_are_stored_for_this_account(self):
        response = self._client().post("/agent/voice/host/settings/", json.dumps({"mode": "speak", "volume": 70}),
                                       content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["settings"]["mode"], "speak")
        self.assertEqual(host_voice.settings_for(self.user.id)["volume"], 70.0)

    def test_speak_from_a_page(self):
        body = {"text": "Hello", "settings": {"volume": 50}, "reason": "no browser speech"}
        response = self._client().post("/agent/voice/host/speak/", json.dumps(body), content_type="application/json")
        self.assertEqual(response.json()["job_id"], "job42")
        self.assertEqual(self.calls, [(self.user.id, "Hello", {"volume": 50}, "no browser speech")])

    def test_the_closing_page_beacon_is_accepted_with_its_form_token(self):
        token = _get_new_csrf_string()
        client = self._client(csrf=True)
        client.cookies[settings.CSRF_COOKIE_NAME] = token  # each edition has its own cookie
        payload = json.dumps({"text": "the rest of the sentence", "settings": {"mode": "notify"}, "reason": "page closed"})
        response = client.post("/agent/voice/host/speak/", {"csrfmiddlewaretoken": token, "payload": payload})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(self.calls[0][1], "the rest of the sentence")

    def test_a_beacon_without_the_token_is_refused(self):
        client = self._client(csrf=True)
        response = client.post("/agent/voice/host/speak/", {"payload": json.dumps({"text": "x"})})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])

    def test_oversized_bodies_are_refused(self):
        body = json.dumps({"text": "x" * 300_000})
        response = self._client().post("/agent/voice/host/speak/", body, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.calls, [])

    def test_status_and_stop(self):
        client = self._client()
        self.assertEqual(client.get("/agent/voice/host/status/?job=nope").json()["state"], "unknown")
        self.assertEqual(client.post("/agent/voice/host/stop/").json(), {"stopped": False})
        self.assertEqual(client.get("/agent/voice/host/speak/").status_code, 405)


class VoiceWiringTests(SimpleTestCase):
    """The pieces that make her unstoppable stay connected."""

    def test_the_chat_consumer_reports_pages_and_finished_answers(self):
        source = (AGENT_DIR / "consumers.py").read_text(encoding="utf-8")
        for hook in ("host_voice.page_opened", "host_voice.page_closed", "host_voice.answer_finished"):
            self.assertIn(hook, source)

    def test_nothing_pauses_her_when_the_page_is_hidden(self):
        for name in ("voice_runtime.js", "interaction_speech.js"):
            source = (JS_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("speechSynthesis.pause(", source, name)
            self.assertNotIn("speechSynthesis?.pause(", source, name)

    def test_the_completion_line_queues_behind_what_she_is_saying(self):
        source = (JS_DIR / "avatar.js").read_text(encoding="utf-8")
        start = source.index("function doComplete")
        self.assertIn("queue:true", source[start:start + 900].replace(" ", ""))


class VoiceEngineCasesTests(SimpleTestCase):
    """Runs the real voice_runtime.js against a fake speaker and a fake clock."""

    def test_she_finishes_what_she_starts(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        cases = REPO_ROOT / "scripts" / "voice_runtime_cases.mjs"
        result = subprocess.run(
            [node, str(cases), str(JS_DIR / "voice_runtime.js"), str(JS_DIR / "interaction_speech.js"),
             host_voice.EDITION_LANG],
            capture_output=True, text=True, encoding="utf-8", timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("12/12 passed", result.stdout)
