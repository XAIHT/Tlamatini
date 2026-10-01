#!/usr/bin/env python
# Tlamatini Author Banner - do not remove
"""VISIBLE proof: the whole chat works against a REMOTE Ollama serving deepseek-coder.

Angela, 2026-10-01: "make it seem there is a deepseek coder, and show me the
real ok in everything". She rents a vast.ai GPU server, pulls
deepseek-coder-v2:236b there and points Tlamatini at it with a token. This run
simulates that server on this PC and drives the REAL chat page, headed Chrome.

THE ONLY SIMULATION IS THE SERVER BELOW (FakeDeepseekServer). Nothing in
Tlamatini is changed or special-cased for this test. The fake behaves like a
token-protected Ollama: /api/tags, /api/show, /api/chat and /api/generate
(streamed NDJSON, with prompt_eval_count), /api/embed. It answers 401 without
the token and 404 for a model it does not have. It answers the way a real model
would: a classifier prompt ("Answer ONLY with YES or NO", "INTENT or
NOT-INTENT") gets the one word it asks for, the question rewriter gets the
question back, and a coding question gets a deepseek-style code answer.

Steps:
  0. Back up the dev config.json, then set it the way Angela sets it for the
     rented server: the three Ollama URLs, ollama_token, and the 7 Core models
     (deepseek-coder-v2:236b, embeddings on nomic-embed-text:latest). Start the
     SOURCE server on :8017.
  1. Chrome: log in, chat page ready.
  2. Config > Models lists the remote's models; the 7 Core fields hold them;
     Save is accepted with no warning.
  3. Clean History, then a ONE-SHOT coding question is answered by deepseek.
  4. MULTI-TURN on, a second coding question is answered by deepseek.
  5. The fake saw every request WITH the token, never a model it lacks.
  6. tlamatini.log has no Traceback / ERROR / failed open / ResponseError.
  7. The dev config.json is restored byte for byte (checksum compared).
Every step is photographed by Shoter (whole desktop).

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

import atexit
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8017
os.environ["TLAMATINI_BASE_URL"] = "http://127.0.0.1:%d" % PORT
os.environ.pop("CONFIG_PATH", None)          # the chat must read the real dev config
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RUN_DIR = os.path.join(REPO, "Temp", "deepseek_remote_chat")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
REAL_CONFIG = os.path.join(REPO, "Tlamatini", "agent", "config.json")
BACKUP = os.path.join(RUN_DIR, "config.backup.json")
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")

TOKEN = "fake-vast-token-7d3f"
CODER = "deepseek-coder-v2:236b"
EMBEDDER = "nomic-embed-text:latest"
REMOTE_MODELS = [CODER, "qwen3.5:35b", EMBEDDER]
OLLAMA_URL_KEYS = ("ollama_base_url", "unified_agent_base_url", "image_interpreter_base_url")
CORE_MODELS = {
    "embeding-model": EMBEDDER,
    "chained-model": CODER,
    "access_aimed_prompt_model": CODER,
    "unified_agent_model": CODER,
    "mcp_files_search_model": CODER,
    "internet_classifier_model": CODER,
    "web_summarizer_model": CODER,
}
Q1 = "Write a Python function add_numbers(a, b) that returns the sum of two numbers."
Q2 = "Write a Python function is_even(n) that tells whether a number is even."
SIGNATURE_1 = "return a + b"          # only the ANSWER contains these, never the question
SIGNATURE_2 = "return n % 2 == 0"
# Anything that means Tlamatini and the remote did not get along. 401 /
# Unauthorized / "Could not reach" were missed on the first run: the startup
# GPU step was talking to the remote WITHOUT the token and only said so there.
ERROR_PATTERN = re.compile(r"Traceback|\bERROR\b|failed open|ResponseError|Exception:"
                           r"|Unauthorized|\b401\b|Could not reach|SERVING-LAYER PROBLEM")

RESULTS: list = []
PHOTOS: list = []
ALERTS: list = []


# ------------------------------------------------------------------ output
def say(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:400]))
    say(("[PASS] " if ok else "[FAIL] ") + name + (("   -> " + str(detail)[:300]) if detail else ""))
    return bool(ok)


def shot(page, name):
    try:
        page.bring_to_front()
        page.wait_for_timeout(600)
    except Exception:                               # noqa: BLE001
        pass
    path = take_shot(PHOTOS_DIR, "%s.png" % name, runtime_base=RUN_DIR)
    PHOTOS.append((name, path))
    say("   PHOTO %s -> %s" % (name, path))
    return path


# ------------------------------------------------------------------ the dev config, restored no matter what
_RESTORED = {"done": False}


def restore_config():
    if _RESTORED["done"] or not os.path.isfile(BACKUP):
        return
    shutil.copyfile(BACKUP, REAL_CONFIG)
    _RESTORED["done"] = True
    say("dev config.json restored from %s" % BACKUP)


atexit.register(restore_config)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ------------------------------------------------------------------ the simulated vast.ai server
def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _vector(text, dims=64):
    digest = hashlib.sha256(text.encode("utf-8", "replace")).digest()
    raw = [((digest[i % len(digest)] + i * 7) % 256) / 255.0 - 0.5 for i in range(dims)]
    norm = sum(v * v for v in raw) ** 0.5 or 1.0
    return [v / norm for v in raw]


def coder_answer(question):
    q = question.lower()
    if "add_numbers" in q:
        return ("Here is a clean, tested implementation:\n\n"
                "BEGIN-CODE<<<add_numbers.py>>>\n"
                "def add_numbers(a, b):\n"
                "    \"\"\"Return the sum of a and b.\"\"\"\n"
                "    return a + b\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    print(add_numbers(2, 3))  # 5\n"
                "END-CODE\n\n"
                "It works for integers and floats alike.\nEND-RESPONSE")
    if "is_even" in q:
        return ("Use the remainder of a division by 2:\n\n"
                "BEGIN-CODE<<<is_even.py>>>\n"
                "def is_even(n):\n"
                "    \"\"\"True when n is even.\"\"\"\n"
                "    return n % 2 == 0\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    print(is_even(4), is_even(7))  # True False\n"
                "END-CODE\n\nEND-RESPONSE")
    return "I am deepseek-coder-v2:236b. Ask me for code and I will write it.\nEND-RESPONSE"


def model_reply(request_text, last_user):
    """Answer the way a real model would, given what the prompt asks for."""
    if "INTENT or NOT-INTENT" in request_text:
        return "NOT-INTENT"
    if "YES or NO" in request_text:
        return "NO"
    if "Return ONLY the reformulated question" in request_text:
        return last_user.strip().splitlines()[-1] if last_user.strip() else last_user
    # Answer the LATEST question. The conversation history still carries the
    # earlier ones, so "the first question found" would answer the wrong one.
    asked = [(request_text.rfind(q), q) for q in (Q1, Q2) if q in request_text]
    if asked:
        return coder_answer(max(asked)[1])
    return coder_answer(last_user)


class FakeDeepseekServer:
    def __init__(self, models, token):
        self.models = list(models)
        self.token = token
        self.requests = []          # (method, path, model, auth)
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, code, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _stream(self, objects):
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for obj in objects:
                    self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
                    self.wfile.flush()

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                if not length:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                except ValueError:
                    return {}

            def _gate(self, model=""):
                auth = self.headers.get("Authorization")
                fake.requests.append((self.command, self.path, model, auth))
                if auth != "Bearer " + fake.token:
                    self._json(401, {"error": "unauthorized"})
                    return False
                if model and model not in fake.models:
                    self._json(404, {"error": "model \"%s\" not found, try pulling it first" % model})
                    return False
                return True

            def do_GET(self):
                if not self._gate():
                    return
                if self.path == "/api/tags":
                    self._json(200, {"models": [{"name": n, "model": n, "size": 1,
                                                 "details": {"format": "gguf"}} for n in fake.models]})
                elif self.path == "/api/version":
                    self._json(200, {"version": "0.12.0"})
                elif self.path == "/api/ps":
                    self._json(200, {"models": []})
                elif self.path == "/":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Ollama is running")
                else:
                    self._json(404, {"error": "not found"})

            def do_HEAD(self):
                self.send_response(200)
                self.end_headers()

            def do_POST(self):
                data = self._body()
                model = str(data.get("model") or data.get("name") or "")
                if not self._gate(model):
                    return
                if self.path == "/api/show":
                    embed = model == EMBEDDER
                    arch = "nomic-bert" if embed else "deepseek2"
                    self._json(200, {
                        "details": {"family": arch, "format": "gguf",
                                    "parameter_size": "137M" if embed else "236B",
                                    "quantization_level": "F16" if embed else "Q4_0"},
                        "model_info": {"general.architecture": arch,
                                       "%s.context_length" % arch: 8192 if embed else 163840},
                        "capabilities": ["embedding"] if embed else ["completion", "tools"],
                    })
                elif self.path in ("/api/embed", "/api/embeddings"):
                    items = data.get("input", data.get("prompt", ""))
                    items = items if isinstance(items, list) else [items]
                    vectors = [_vector(str(x)) for x in items]
                    if self.path == "/api/embed":
                        self._json(200, {"model": model, "embeddings": vectors,
                                         "prompt_eval_count": sum(len(str(x)) // 4 for x in items)})
                    else:
                        self._json(200, {"embedding": vectors[0]})
                elif self.path in ("/api/chat", "/api/generate"):
                    self._generate(data, model)
                else:
                    self._json(404, {"error": "not found"})

            def _generate(self, data, model):
                chat = self.path == "/api/chat"
                if chat:
                    messages = data.get("messages") or []
                    texts = [str(m.get("content") or "") for m in messages]
                    users = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
                    last_user = users[-1] if users else ""
                else:
                    texts = [str(data.get("system") or ""), str(data.get("prompt") or "")]
                    last_user = str(data.get("prompt") or "")
                request_text = "\n".join(texts)
                answer = model_reply(request_text, last_user)
                prompt_tokens = max(1, len(request_text) // 4)
                done = {"model": model, "created_at": _now(), "done": True, "done_reason": "stop",
                        "total_duration": 900000000, "load_duration": 1000000,
                        "prompt_eval_count": prompt_tokens, "prompt_eval_duration": 300000000,
                        "eval_count": max(1, len(answer) // 4), "eval_duration": 500000000}
                if data.get("stream", True) is False:
                    if chat:
                        done["message"] = {"role": "assistant", "content": answer}
                    else:
                        done["response"] = answer
                    self._json(200, done)
                    return
                pieces = [answer[i:i + 40] for i in range(0, len(answer), 40)] or [""]
                chunks = []
                for piece in pieces:
                    chunk = {"model": model, "created_at": _now(), "done": False}
                    if chat:
                        chunk["message"] = {"role": "assistant", "content": piece}
                    else:
                        chunk["response"] = piece
                    chunks.append(chunk)
                if chat:
                    done["message"] = {"role": "assistant", "content": ""}
                else:
                    done["response"] = ""
                chunks.append(done)
                self._stream(chunks)

            def log_message(self, *args):
                pass

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 32236), Handler)
        except OSError:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


# ------------------------------------------------------------------ page helpers
IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        page.wait_for_timeout(500)
    return False


def dialog_button(page, body_id, label):
    return page.locator(".ui-dialog:has(#%s) .ui-dialog-buttonpane button:has-text('%s')"
                        % (body_id, label))


def open_models(page):
    page.click("#config-menu-button")
    page.click("#config-models")
    page.wait_for_selector("#config-models-dialog-message", state="visible", timeout=20000)
    deadline = time.time() + 30
    text = ""
    while time.time() < deadline:
        text = page.inner_text("#config-models-catalog-status").strip()
        if text and not text.startswith("Loading"):
            break
        page.wait_for_timeout(300)
    return text


def set_toggle(page, selector, wanted):
    if page.locator(selector).count() and page.is_checked(selector) != wanted:
        page.click(selector, force=True)
        page.wait_for_timeout(300)


def ask(page, question, filename_part, signature, label):
    """Send one question and open its code the way a user does.

    Tlamatini saves a code answer as a program and puts a "Load in canvas"
    link in the chat; the code itself appears only once that link is clicked.
    Returns (finished, link_text, code_on_screen).
    """
    links = page.locator("#chat-log a:has-text('Load in canvas')")
    links_before = links.count()
    page.fill(C.SEL["chat_input"], question)
    page.click(C.SEL["chat_submit"])
    page.wait_for_timeout(1500)
    idle = wait_idle(page, 240)
    deadline = time.time() + 30
    while time.time() < deadline and links.count() <= links_before:
        page.wait_for_timeout(500)
    link_text = links.last.inner_text().strip() if links.count() > links_before else ""
    found = False
    if filename_part in link_text:
        links.last.click()
        deadline = time.time() + 20
        while time.time() < deadline:
            if signature in page.inner_text("body"):
                found = True
                break
            page.wait_for_timeout(500)
    shot(page, label)
    return idle, link_text, found


# ------------------------------------------------------------------ main
def main():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    for old in os.listdir(PHOTOS_DIR):
        if old.lower().endswith(".png"):
            try:
                os.remove(os.path.join(PHOTOS_DIR, old))
            except OSError:
                pass
    try:
        os.remove(RUN_LOG)
    except OSError:
        pass

    say("=" * 78)
    say("THE CHAT ON A REMOTE OLLAMA SERVING deepseek-coder - VISIBLE E2E   (Angela Lopez Mendoza)")
    say("=" * 78)

    # 0. the environment ------------------------------------------------
    shutil.copyfile(REAL_CONFIG, BACKUP)
    sha_before = sha256(REAL_CONFIG)
    say("dev config.json backed up to %s (sha256 %s...)" % (BACKUP, sha_before[:16]))

    fake = FakeDeepseekServer(REMOTE_MODELS, TOKEN)
    say("simulated vast.ai Ollama at %s serving %s" % (fake.url, ", ".join(REMOTE_MODELS)))
    try:
        urllib.request.urlopen(fake.url + "/api/tags", timeout=5)
        no_token = 200
    except urllib.error.HTTPError as exc:
        no_token = exc.code
    check("0a the simulated server refuses a request without the token", no_token == 401,
          "HTTP %s" % no_token)
    fake.requests.clear()

    with open(REAL_CONFIG, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    for key in OLLAMA_URL_KEYS:
        config[key] = fake.url
    config["ollama_token"] = TOKEN
    config.update(CORE_MODELS)
    with open(REAL_CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
    say("dev config set for the remote: URLs -> %s, token set, Core models -> %s / %s"
        % (fake.url, CODER, EMBEDDER))

    if stop_server(PORT):
        time.sleep(2.0)
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return finish(None, fake, sha_before, code_if_ok=4)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception as exc:                    # noqa: BLE001
            say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.set_default_timeout(C.NAV_TIMEOUT_MS)

        def on_alert(dialog):
            ALERTS.append(dialog.message)
            say("   ALERT shown: %s" % dialog.message.replace("\n", " | ")[:300])
            take_shot(PHOTOS_DIR, "alert_%d.png" % len(ALERTS), runtime_base=RUN_DIR)
            dialog.accept()

        page.on("dialog", on_alert)

        try:
            # 1. log in, open the chat ---------------------------------
            page.goto(C.BASE_URL + C.LOGIN_PATH)
            page.fill(C.SEL["login_user"], C.USERNAME)
            page.fill(C.SEL["login_pass"], C.PASSWORD)
            page.click(C.SEL["login_submit"])
            page.wait_for_load_state("networkidle")
            page.goto(C.BASE_URL + C.CHAT_PATH)
            page.wait_for_selector(C.SEL["chat_input"])
            page.bring_to_front()
            if not check("1 logged in and the chat page is ready", wait_idle(page, 240)):
                shot(page, "01_not_ready")
                return finish(browser, fake, sha_before)
            shot(page, "01_chat_ready")

            # 2. Config > Models shows the remote, the Core fields hold it --
            status = open_models(page)
            say("   status: %s" % status)
            check("2a Config > Models lists the REMOTE server's 3 models",
                  ("3 Ollama models available on %s" % fake.url) in status, status)
            page.fill("#config-models-search", "")
            values = {}
            for key in CORE_MODELS:
                values[key] = page.input_value("#config-models-" + key.replace("_", "-"))
            check("2b the 7 Core settings hold the remote models", values == CORE_MODELS, values)
            shot(page, "02_models_remote")
            alerts_before = len(ALERTS)
            dialog_button(page, "config-models-dialog-message", "Save").click()
            page.wait_for_selector("#config-models-dialog-message", state="hidden", timeout=30000)
            check("2c Save accepted with no warning", len(ALERTS) == alerts_before, ALERTS[alerts_before:])

            # 3. one-shot question --------------------------------------
            page.click(C.SEL["clean_history"])
            page.locator(".ui-dialog-buttonpane button:has-text('Continue')").last.click()
            page.wait_for_timeout(2500)
            wait_idle(page, 240)
            for key in ("t_multi_turn", "t_acpx", "t_ask_execs", "t_internet", "t_exec_report"):
                set_toggle(page, C.SEL[key], False)
            say("   asking (one-shot): %s" % Q1)
            idle, link, found = ask(page, Q1, "add_numbers.py", SIGNATURE_1, "03_one_shot_answer")
            check("3a the one-shot answer finished", idle)
            check("3b the answer offers add_numbers.py", "add_numbers.py" in link, link)
            check("3c the code from deepseek-coder is on screen", found,
                  "canvas shows %r" % SIGNATURE_1)

            # 4. Multi-Turn question -------------------------------------
            set_toggle(page, C.SEL["t_multi_turn"], True)
            say("   asking (Multi-Turn): %s" % Q2)
            idle, link, found = ask(page, Q2, "is_even.py", SIGNATURE_2, "04_multi_turn_answer")
            check("4a the Multi-Turn answer finished", idle)
            check("4b the answer offers is_even.py", "is_even.py" in link, link)
            check("4c the code from deepseek-coder is on screen", found,
                  "canvas shows %r" % SIGNATURE_2)

            # 5. what the simulated server saw --------------------------
            asked = [r for r in fake.requests if r[1] in ("/api/chat", "/api/generate")]
            embeds = [r for r in fake.requests if r[1] in ("/api/embed", "/api/embeddings")]
            say("   the remote received %d requests: %d chat/generate (%s), %d embed"
                % (len(fake.requests), len(asked), sorted({r[2] for r in asked}), len(embeds)))
            check("5a the chat questions went to the remote deepseek-coder",
                  any(r[2] == CODER for r in asked), sorted({r[2] for r in asked}))
            tokenless = [(r[0], r[1], r[2]) for r in fake.requests if r[3] != "Bearer " + TOKEN]
            check("5b every request to the remote carried 'Bearer <token>'",
                  bool(fake.requests) and not tokenless,
                  "requests WITHOUT the token: %s" % tokenless if tokenless else "all %d had it"
                  % len(fake.requests))
            unknown = sorted({r[2] for r in fake.requests if r[2] and r[2] not in REMOTE_MODELS})
            check("5c Tlamatini never asked the remote for a model it does not have",
                  not unknown, unknown)
        except Exception:                           # noqa: BLE001
            check("the run itself crashed", False, traceback.format_exc()[-600:])
            shot(page, "99_crash")
        return finish(browser, fake, sha_before)


def finish(browser, fake, sha_before, code_if_ok=0):
    if browser is not None:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    stop_server(PORT)
    fake.close()

    # 6. the app's own log, from the top -------------------------------
    if os.path.isfile(SERVER_LOG):
        with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        bad = [ln.strip() for ln in lines if ERROR_PATTERN.search(ln)]
        for ln in bad[:12]:
            say("   tlamatini.log: %s" % ln[:260])
        check("6 tlamatini.log: no Traceback / ERROR / failed open / ResponseError (%d lines read)"
              % len(lines), not bad, "%d bad line(s)" % len(bad))

    # 7. the dev config comes back exactly ------------------------------
    restore_config()
    check("7 the dev config.json is back byte for byte", sha256(REAL_CONFIG) == sha_before)

    failed = [name for name, ok, _ in RESULTS if not ok]
    say("=" * 78)
    say("photos: %s" % PHOTOS_DIR)
    if failed:
        say("VERDICT: FAILED - %d of %d checks failed:" % (len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
    if code_if_ok:
        return code_if_ok
    say("VERDICT: ALL %d CHECKS PASSED" % len(RESULTS))
    say("=" * 78)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:                               # noqa: BLE001
        say("!! the harness crashed before it could finish:")
        say(traceback.format_exc())
        code = 1
    restore_config()
    shutil.rmtree(os.path.join(RUN_DIR, "_shoter_runtime"), ignore_errors=True)
    sys.exit(code)
