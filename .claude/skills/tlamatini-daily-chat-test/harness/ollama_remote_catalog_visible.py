#!/usr/bin/env python
# Tlamatini Author Banner - do not remove
"""VISIBLE proof: Config > Models asks the CONFIGURED (remote) Ollama.

Angela, 2026-09-30: she pointed Tlamatini at a rented vast.ai GPU server
(Config > URLs + ollama_token), pulled deepseek-coder-v2:236b there, and
Config > Models marked it red and refused to save it: "it keeps asking the
local ollama its models, not the remote super-server". She does not believe
the fix until she SEES it in the real chat page.

What this run does, all on her real desktop:
  0. Starts a FAKE "remote" Ollama on this PC that has ONLY
     deepseek-coder-v2:236b and qwen3.5:35b and answers 401 without the token.
     Writes a COPY of the dev config.json (URLs = local Ollama, token set) and
     starts the SOURCE server on :8017 with CONFIG_PATH = that copy. Her real
     config.json is fingerprinted before and after: it must not change.
  1. Headed real Chrome: log in, open the chat page.
  2. BEFORE: Config > Models lists the LOCAL Ollama (that is what is configured).
  3. Config > URLs: point the three Ollama URLs at the fake remote, Save.
     The MCP entry points must stay local.
  4. AFTER, WITHOUT RELOADING THE PAGE (her exact bug): Config > Models must
     list exactly the 2 remote models, from the remote URL.
  5. Save deepseek-coder-v2:236b - it must be accepted and written.
  6. Opposite check: a model that exists ONLY on the local Ollama must be
     REJECTED, and the warning must name the remote server.
  7. Every catalog request reached the fake WITH "Bearer <token>", and
     tlamatini.log shows the [OLLAMA-CATALOG] lines.
Every step is photographed by Shoter (whole desktop).

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

import hashlib
import json
import os
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
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RUN_DIR = os.path.join(REPO, "Temp", "ollama_remote_catalog")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
CONFIG_COPY = os.path.join(RUN_DIR, "config.json")
REAL_CONFIG = os.path.join(REPO, "Tlamatini", "agent", "config.json")
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")

LOCAL_OLLAMA = "http://127.0.0.1:11434"
TOKEN = "fake-vast-token-7d3f"
REMOTE_MODELS = ["deepseek-coder-v2:236b", "qwen3.5:35b"]
OLLAMA_URL_KEYS = ("ollama_base_url", "unified_agent_base_url", "image_interpreter_base_url")
MCP_KEYS = ("mcp_system_server_host", "mcp_system_server_port", "mcp_system_client_uri",
            "mcp_files_search_server_host", "mcp_files_search_server_port",
            "mcp_files_search_client_uri")
URL_FIELD_IDS = {
    "ollama_base_url": "#config-urls-ollama-base-url",
    "unified_agent_base_url": "#config-urls-unified-agent-base-url",
    "image_interpreter_base_url": "#config-urls-image-interpreter-base-url",
}

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
    """Photograph the WHOLE desktop with Shoter - the browser in front first."""
    try:
        page.bring_to_front()
        time.sleep(0.6)
    except Exception:                               # noqa: BLE001
        pass
    path = take_shot(PHOTOS_DIR, "%s.png" % name, runtime_base=RUN_DIR)
    PHOTOS.append((name, path))
    say("   PHOTO %s -> %s" % (name, path))
    return path


# ------------------------------------------------------------------ the fake remote Ollama
class FakeRemoteOllama:
    """A token-protected Ollama stand-in for the vast.ai server.

    It answers 401 to any request without "Bearer <TOKEN>", and records every
    request it receives so the run can prove the token was really sent.
    """

    def __init__(self, models, token):
        self.models = list(models)
        self.token = token
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self):
                auth = self.headers.get("Authorization")
                fake.requests.append((self.command, self.path, auth))
                if auth != "Bearer " + fake.token:
                    self._reply(401, {"error": "unauthorized"})
                    return False
                return True

            def do_GET(self):
                if not self._authorized():
                    return
                if self.path == "/api/tags":
                    self._reply(200, {"models": [{"name": n, "model": n} for n in fake.models]})
                elif self.path == "/api/version":
                    self._reply(200, {"version": "0.0.0-fake-remote"})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                if not self._authorized():
                    return
                if self.path == "/api/show":
                    self._reply(200, {"model_info": {"general.architecture": "fake",
                                                     "fake.context_length": 32768}})
                else:
                    self._reply(404, {"error": "the fake remote only lists models"})

            def log_message(self, *args):
                pass

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 32236), Handler)
        except OSError:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tag_requests(self):
        return [r for r in self.requests if r[1] == "/api/tags"]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


# ------------------------------------------------------------------ helpers
def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_copy():
    with open(CONFIG_COPY, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def http_json(url, headers=None, timeout=5):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def local_models():
    try:
        _, data = http_json(LOCAL_OLLAMA + "/api/tags")
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception as exc:                        # noqa: BLE001
        say("   (local Ollama not answering: %s)" % exc)
        return None


IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        time.sleep(0.5)
    return False


def dialog_visible(page, body_id):
    return page.locator(".ui-dialog:has(#%s)" % body_id).is_visible()


def dialog_button(page, body_id, label):
    return page.locator(".ui-dialog:has(#%s) .ui-dialog-buttonpane button:has-text('%s')"
                        % (body_id, label))


def open_config_entry(page, entry_id, body_id):
    page.click("#config-menu-button")
    page.click("#" + entry_id)
    page.wait_for_selector("#" + body_id, state="visible", timeout=20000)


def open_models(page):
    """Open Config > Models and return the catalog status line once it settles."""
    open_config_entry(page, "config-models", "config-models-dialog-message")
    deadline = time.time() + 30
    text = ""
    while time.time() < deadline:
        text = page.inner_text("#config-models-catalog-status").strip()
        if text and not text.startswith("Loading"):
            break
        page.wait_for_timeout(300)
    options = page.eval_on_selector_all("#config-models-ollama-options option",
                                        "els => els.map(e => e.value)")
    return text, options


def set_model_field(page, label_query, field_id, value):
    page.fill("#config-models-search", label_query)
    page.wait_for_selector(field_id, state="visible", timeout=10000)
    page.fill(field_id, value)


def wait_reconnect_notice_and_ok(page, photo_name):
    try:
        page.wait_for_selector("#config-reconnect-required-dialog-message", state="visible",
                               timeout=10000)
    except Exception:                               # noqa: BLE001
        return False
    shot(page, photo_name)
    dialog_button(page, "config-reconnect-required-dialog-message", "OK").click()
    return True


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
    say("CONFIG > MODELS ASKS THE CONFIGURED OLLAMA - VISIBLE E2E   (Angela Lopez Mendoza)")
    say("=" * 78)

    # 0. the environment ------------------------------------------------
    real_sha_before = sha256(REAL_CONFIG)
    say("your real config.json  %s  sha256 %s..." % (REAL_CONFIG, real_sha_before[:16]))

    local = local_models()
    current = None
    with open(REAL_CONFIG, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    current = config.get("unified_agent_model", "")
    local_only = next((m for m in (local or []) if m not in REMOTE_MODELS and m != current),
                      "gemma4:cloud")
    say("local Ollama models: %s" % (len(local) if local is not None else "not reachable"))
    say("model that exists ONLY on the local Ollama (must be rejected later): %s" % local_only)

    fake = FakeRemoteOllama(REMOTE_MODELS, TOKEN)
    say("fake REMOTE Ollama listening at %s (only %s)" % (fake.url, ", ".join(REMOTE_MODELS)))
    try:
        http_json(fake.url + "/api/tags")
        no_token_code = 200
    except urllib.error.HTTPError as exc:
        no_token_code = exc.code
    _, with_token = http_json(fake.url + "/api/tags", {"Authorization": "Bearer " + TOKEN})
    check("0a the fake remote refuses a request without the token", no_token_code == 401,
          "HTTP %s" % no_token_code)
    check("0b the fake remote lists its 2 models with the token",
          [m["name"] for m in with_token["models"]] == REMOTE_MODELS, with_token)
    fake.requests.clear()

    for key in OLLAMA_URL_KEYS:
        config[key] = LOCAL_OLLAMA
    config["ollama_token"] = TOKEN
    with open(CONFIG_COPY, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
    mcp_before = {key: config.get(key) for key in MCP_KEYS}
    say("config COPY for this run: %s (URLs = local Ollama, token set)" % CONFIG_COPY)
    os.environ["CONFIG_PATH"] = CONFIG_COPY

    if stop_server(PORT):
        time.sleep(2.0)
    log_offset = os.path.getsize(SERVER_LOG) if os.path.isfile(SERVER_LOG) else 0
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        fake.close()
        return 4
    if os.path.isfile(SERVER_LOG) and os.path.getsize(SERVER_LOG) < log_offset:
        log_offset = 0                          # the new server truncated its log

    alert_shots = []

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
            name = "alert_%d" % len(ALERTS)
            say("   ALERT shown: %s" % dialog.message.replace("\n", " | ")[:300])
            alert_shots.append(take_shot(PHOTOS_DIR, name + ".png", runtime_base=RUN_DIR))
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
            if not wait_idle(page, 240):
                check("1 the chat page became ready", False, "still busy after 240 s")
                shot(page, "01_not_ready")
                return finish(browser, fake, real_sha_before, log_offset)
            check("1 logged in and the chat page is ready", True)
            page.evaluate("window.__noReloadMarker = 'same-page-load'")
            shot(page, "01_chat_ready")

            # 2. BEFORE: the dialog lists the LOCAL Ollama ---------------
            status, options = open_models(page)
            say("   status: %s" % status)
            check("2 BEFORE: Config > Models asks the configured (local) Ollama",
                  LOCAL_OLLAMA in status, status)
            shot(page, "02_models_before_local")
            dialog_button(page, "config-models-dialog-message", "Cancel").click()

            # 3. point the Ollama URLs at the remote, through the real dialog
            open_config_entry(page, "config-urls", "config-urls-dialog-message")
            for key, field in URL_FIELD_IDS.items():
                page.fill(field, fake.url)
            shot(page, "03_urls_pointed_at_remote")
            dialog_button(page, "config-urls-dialog-message", "Save").click()
            check("3a the URLs were saved (the reconnect notice appeared)",
                  wait_reconnect_notice_and_ok(page, "03_urls_saved_notice"))
            saved = read_copy()
            check("3b the three Ollama URLs now point at the remote",
                  all(saved.get(k) == fake.url for k in OLLAMA_URL_KEYS),
                  {k: saved.get(k) for k in OLLAMA_URL_KEYS})
            check("3c the MCP entry points stayed local and unchanged",
                  {k: saved.get(k) for k in MCP_KEYS} == mcp_before,
                  {k: saved.get(k) for k in MCP_KEYS})

            # 4. AFTER, same page, no reload ----------------------------
            check("4a the page was NOT reloaded (her exact situation)",
                  page.evaluate("window.__noReloadMarker") == "same-page-load")
            status, options = open_models(page)
            say("   status: %s" % status)
            say("   suggestions: %s" % options)
            check("4b AFTER: the dialog lists the REMOTE server, not the local one",
                  fake.url in status and LOCAL_OLLAMA not in status, status)
            check("4c the suggestions are exactly the 2 remote models",
                  sorted(options) == sorted(REMOTE_MODELS), options)
            shot(page, "04_models_after_remote")

            # 5. deepseek-coder-v2:236b is accepted and saved ------------
            alerts_before = len(ALERTS)
            set_model_field(page, "Chained reasoning", "#config-models-chained-model",
                            "deepseek-coder-v2:236b")
            shot(page, "05_deepseek_typed")
            dialog_button(page, "config-models-dialog-message", "Save").click()
            notice = wait_reconnect_notice_and_ok(page, "05_deepseek_saved_notice")
            new_alerts = ALERTS[alerts_before:]
            check("5a saving deepseek-coder-v2:236b raised NO 'not installed' warning",
                  not any("NOT installed" in a for a in new_alerts), new_alerts)
            check("5b the Models dialog closed and the reconnect notice appeared", notice)
            check("5c chained-model = deepseek-coder-v2:236b was written to the config",
                  read_copy().get("chained-model") == "deepseek-coder-v2:236b",
                  read_copy().get("chained-model"))

            # 6. the opposite: a LOCAL-only model is rejected -------------
            alerts_before = len(ALERTS)
            open_models(page)
            set_model_field(page, "Unified / Multi-Turn", "#config-models-unified-agent-model",
                            local_only)
            dialog_button(page, "config-models-dialog-message", "Save").click()
            deadline = time.time() + 30
            # page.wait_for_timeout, NOT time.sleep: Playwright only delivers
            # the native alert to on_alert while the script is inside a
            # Playwright call. A plain sleep would leave the alert unanswered
            # and the page frozen.
            while time.time() < deadline and len(ALERTS) == alerts_before:
                page.wait_for_timeout(300)
            new_alerts = ALERTS[alerts_before:]
            rejection = next((a for a in new_alerts if "NOT installed" in a), "")
            check("6a a model that exists only on the LOCAL Ollama is REJECTED",
                  bool(rejection) and local_only in rejection, new_alerts)
            check("6b the warning names the remote server", fake.url in rejection, rejection)
            check("6c the dialog stayed open so it can be corrected",
                  dialog_visible(page, "config-models-dialog-message"))
            shot(page, "06_local_only_rejected")
            dialog_button(page, "config-models-dialog-message", "Cancel").click()
            check("6d the rejected model was NOT written",
                  read_copy().get("unified_agent_model") == current,
                  read_copy().get("unified_agent_model"))

            # 7. the token, and the server's own log --------------------
            tags = fake.tag_requests()
            check("7a the remote was asked for its catalog through Tlamatini (%d times)" % len(tags),
                  len(tags) >= 3, tags)
            check("7b every catalog request carried 'Bearer <token>'",
                  bool(tags) and all(r[2] == "Bearer " + TOKEN for r in tags),
                  sorted({r[2] for r in tags}, key=str))
            with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(log_offset)
                server_lines = [ln.strip() for ln in fh if "[OLLAMA-CATALOG]" in ln]
            for ln in server_lines:
                say("   tlamatini.log: %s" % ln)
            check("7c tlamatini.log: the remote answered with 2 models",
                  any(("%s: 2 model(s)" % fake.url) in ln for ln in server_lines), server_lines[-3:])
            shot(page, "07_done")
        except Exception:                           # noqa: BLE001
            check("the run itself crashed", False, traceback.format_exc()[-600:])
            shot(page, "99_crash")
        return finish(browser, fake, real_sha_before, log_offset)


def finish(browser, fake, real_sha_before, log_offset):
    try:
        browser.close()
    except Exception:                               # noqa: BLE001
        pass
    stop_server(PORT)
    fake.close()
    check("8 your real config.json was NOT changed", sha256(REAL_CONFIG) == real_sha_before)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [name for name, ok, _ in RESULTS if not ok]
    say("=" * 78)
    say("photos: %s" % PHOTOS_DIR)
    if failed:
        say("VERDICT: FAILED - %d of %d checks failed:" % (len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
    say("VERDICT: ALL %d CHECKS PASSED" % passed)
    say("=" * 78)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:                               # noqa: BLE001
        say("!! the harness crashed before it could finish:")
        say(traceback.format_exc())
        code = 1
    shutil.rmtree(os.path.join(RUN_DIR, "_shoter_runtime"), ignore_errors=True)
    sys.exit(code)
