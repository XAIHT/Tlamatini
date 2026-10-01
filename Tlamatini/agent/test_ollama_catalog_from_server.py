"""The Config -> Models dialog must ask the CONFIGURED Ollama, not the local one.

Angela pointed Tlamatini at a rented GPU server (Config -> URLs, with its
token) and the Models dialog kept listing the LOCAL Ollama's models: it marked
deepseek-coder-v2:236b red and refused to save it, although `ollama ls` on the
remote server showed it installed. The page fetched <ollama_base_url>/api/tags
by itself, with a URL baked into the HTML when the page loaded and no token.

These tests pin the fix: the SERVER asks Ollama (/agent/ollama_models/), reads
config.json on every call, sends ollama_token, asks every configured Ollama URL
and names the one that failed.

Every Ollama here is a fake HTTP server on 127.0.0.1: no model, no network.
"""
import contextlib
import io
import json
import pathlib
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

AGENT_DIR = pathlib.Path(__file__).resolve().parent


class _FakeOllama:
    """A tiny /api/tags server that records the Authorization header it receives."""

    def __init__(self, models, required_token=None):
        self.models = list(models)
        self.required_token = required_token
        self.seen_auth = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                auth = self.headers.get("Authorization")
                fake.seen_auth.append(auth)
                if fake.required_token and auth != "Bearer " + fake.required_token:
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.path != "/api/tags":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({"models": [{"name": n} for n in fake.models]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _dead_url():
    """A loopback URL nothing listens on (connection refused at once)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return "http://127.0.0.1:%d" % port


class OllamaCatalogEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="catalog_tester", password="x")
        self.client.force_login(self.user)
        self.fakes = []

    def tearDown(self):
        for fake in self.fakes:
            fake.close()

    def fake(self, models, required_token=None):
        server = _FakeOllama(models, required_token)
        self.fakes.append(server)
        return server

    def get_catalog(self, config):
        """GET the catalog as if `config` were config.json.

        The view's own console line ([OLLAMA-CATALOG] ...) is captured into
        self.printed instead of the test window, so a server that is down ON
        PURPOSE never prints an error-looking line during a passing run.
        """
        self.printed = io.StringIO()
        with mock.patch("agent.views.load_config", return_value=config):
            with contextlib.redirect_stdout(self.printed):
                return self.client.get(reverse("ollama_models"))

    def get_failing_catalog(self, config):
        """Like get_catalog, for a call that MUST fail: Django logs the 502 as
        'ERROR Bad Gateway'. assertLogs both proves that line is written and
        keeps it off the test window."""
        with self.assertLogs("django.request", level="ERROR") as logged:
            response = self.get_catalog(config)
        self.assertIn("Bad Gateway: /agent/ollama_models/", "\n".join(logged.output))
        return response

    def test_remote_server_is_asked_with_the_token(self):
        remote = self.fake(["deepseek-coder-v2:236b", "qwen3.5:35b"], required_token="vast-secret")
        response = self.get_catalog({"ollama_base_url": remote.url, "ollama_token": "vast-secret"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["models"], ["deepseek-coder-v2:236b", "qwen3.5:35b"])
        self.assertEqual(remote.seen_auth, ["Bearer vast-secret"])
        self.assertEqual(data["servers"], [{"url": remote.url, "ok": True, "count": 2, "error": ""}])

    def test_a_url_changed_after_the_page_loaded_is_used_on_the_next_call(self):
        # THE BUG: the page kept asking the server it was loaded with.
        local = self.fake(["glm-5.3:cloud", "gemma4:cloud"])
        remote = self.fake(["deepseek-coder-v2:236b"])
        first = self.get_catalog({"ollama_base_url": local.url})
        second = self.get_catalog({"ollama_base_url": remote.url})
        self.assertEqual(first.json()["models"], ["glm-5.3:cloud", "gemma4:cloud"])
        self.assertEqual(second.json()["models"], ["deepseek-coder-v2:236b"])
        self.assertEqual(len(local.seen_auth), 1, "the old server must not be asked again")

    def test_config_json_is_read_fresh_on_every_call(self):
        remote = self.fake(["m:1"])
        with mock.patch("agent.views.load_config", return_value={"ollama_base_url": remote.url}) as loader:
            with contextlib.redirect_stdout(io.StringIO()):
                self.client.get(reverse("ollama_models"))
                self.client.get(reverse("ollama_models"))
        self.assertEqual(loader.call_count, 2)
        loader.assert_called_with(force_reload=True)

    def test_a_placeholder_token_is_not_sent(self):
        remote = self.fake(["m:1"])
        response = self.get_catalog({"ollama_base_url": remote.url,
                                     "ollama_token": "<ollama_token goes here>"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(remote.seen_auth, [None])

    def test_a_rejected_token_is_named(self):
        remote = self.fake(["m:1"], required_token="right")
        response = self.get_failing_catalog({"ollama_base_url": remote.url, "ollama_token": "wrong"})
        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("401", data["servers"][0]["error"])
        self.assertIn("ollama_token", data["servers"][0]["error"])
        self.assertNotIn("wrong", json.dumps(data), "the token itself must never be echoed")

    def test_every_configured_url_is_asked_once_and_merged(self):
        chat = self.fake(["a:1"])
        multi_turn = self.fake(["b:1", "a:1"])
        response = self.get_catalog({"ollama_base_url": chat.url,
                                     "unified_agent_base_url": multi_turn.url + "/",
                                     "image_interpreter_base_url": chat.url})
        data = response.json()
        self.assertEqual(data["models"], ["a:1", "b:1"])
        self.assertEqual([s["url"] for s in data["servers"]], [chat.url, multi_turn.url])
        self.assertEqual(len(chat.seen_auth), 1, "a URL shared by two settings is asked once")

    def test_one_dead_server_does_not_hide_the_others(self):
        chat = self.fake(["a:1"])
        dead = _dead_url()
        response = self.get_catalog({"ollama_base_url": chat.url, "unified_agent_base_url": dead})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["models"], ["a:1"])
        self.assertFalse(data["servers"][1]["ok"])
        self.assertTrue(data["servers"][1]["error"])
        self.assertIn("[OLLAMA-CATALOG] %s: UNREACHABLE" % dead, self.printed.getvalue())
        self.assertIn("[OLLAMA-CATALOG] %s: 1 model(s)" % chat.url, self.printed.getvalue())

    def test_no_server_answering_is_a_502_with_the_reason(self):
        response = self.get_failing_catalog({"ollama_base_url": _dead_url()})
        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["models"], [])
        self.assertTrue(data["servers"][0]["error"])

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(reverse("ollama_models"))
        self.assertEqual(response.status_code, 302)


class GpuPerfSendsTheTokenTests(SimpleTestCase):
    """The startup GPU step talks to the configured Ollama too.

    Found by the visible deepseek run (2026-10-01): pin_ollama_model and
    detect_ollama_serving_issues sent NO token, so a token-protected remote
    Ollama answered 401 to both on every start.
    """

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, *args):
            return b'{"models": []}'

    def capture(self, call):
        from agent import gpu_perf
        seen = []

        def fake_urlopen(request, timeout=None):
            seen.append(request)
            return self._Response()

        with mock.patch.object(gpu_perf.urllib.request, "urlopen", fake_urlopen):
            with contextlib.redirect_stdout(io.StringIO()):
                call(gpu_perf)
        return seen

    def test_pin_sends_the_token(self):
        seen = self.capture(lambda g: g.pin_ollama_model("m:1", "http://remote:1", token="tok"))
        self.assertEqual([r.get_header("Authorization") for r in seen], ["Bearer tok"])

    def test_serving_probe_sends_the_token(self):
        seen = self.capture(lambda g: g.detect_ollama_serving_issues("http://remote:1", token="tok"))
        self.assertEqual([r.full_url for r in seen],
                         ["http://remote:1/api/version", "http://remote:1/api/tags"])
        self.assertEqual({r.get_header("Authorization") for r in seen}, {"Bearer tok"})

    def test_a_placeholder_token_is_not_sent(self):
        seen = self.capture(lambda g: g.pin_ollama_model(
            "m:1", "http://remote:1", token="<ollama_token goes here>"))
        self.assertIsNone(seen[0].get_header("Authorization"))

    def test_startup_passes_the_configured_token(self):
        config = {"ollama_base_url": "http://remote:1", "ollama_token": "tok",
                  "embeding-model": "e:1", "unified_agent_model": "u:1"}
        seen = self.capture(lambda g: self._apply_network_steps_only(g, config))
        self.assertTrue(seen)
        self.assertEqual({r.get_header("Authorization") for r in seen}, {"Bearer tok"})

    @staticmethod
    def _apply_network_steps_only(gpu_perf, config):
        # Skip the machine-changing steps (power plan, setx, nvidia-smi):
        # only the Ollama calls are under test.
        names = ("_set_ollama_env_vars", "_set_windows_high_performance_plan",
                 "_set_self_priority_high", "_apply_nvidia_levers",
                 "persist_ollama_env_for_user")
        with contextlib.ExitStack() as stack:
            for name in names:
                stack.enter_context(mock.patch.object(gpu_perf, name, lambda *a, **k: None))
            gpu_perf.apply_gpu_max_performance(config)


class BrowserNoLongerAsksOllamaDirectlyTests(SimpleTestCase):
    def test_the_page_asks_tlamatini_not_ollama(self):
        js = (AGENT_DIR / "static" / "agent" / "js" / "agent_page_init.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/agent/ollama_models/'", js)
        # No browser fetch of <ollama>/api/tags (the comment explaining the
        # old bug may still name the path).
        self.assertNotRegex(js, r"fetch\([^)]*api/tags")
        self.assertNotIn("getConfiguredOllamaBaseUrl", js)

    def test_no_ollama_url_is_baked_into_the_pages(self):
        for name in ("agent_page.html", "agentic_control_panel.html"):
            html = (AGENT_DIR / "templates" / "agent" / name).read_text(encoding="utf-8")
            self.assertNotIn('json_script:"ollama_config"', html, name)
