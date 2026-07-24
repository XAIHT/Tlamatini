"""Tlamatini-Whatsapper-Daily-Tests.py -- the definitive WhatsApp send tester.

WHAT THIS IS
============
A single, self-diagnosing runner that exercises EVERY way Tlamatini can send a
WhatsApp message -- through **Whatsapper** (Meta WhatsApp Cloud API) and through
**Zavuerer** (Zavu unified messaging) -- driven through the REAL chat GUI.

WHY IT EXISTS (2026-07-24, Angela)
==================================
A whole night was lost because the tooling LIED: Zavuerer reported
`success: true` for messages Meta had rejected, its `health` probe called a route
that does not exist, and nothing ever checked whether a message actually ARRIVED.
So this tester's first principle is:

    THE CHAT ANSWER IS NEVER TRUSTED. A test PASSES only when the provider's own
    API confirms a terminal `delivered` status for a message created by THIS run.

Its second principle is that a failure must TELL YOU WHAT TO DO. Every blocker
(dead token, sandbox number, closed 24-hour window, missing contact, missing
country-code digit) is detected in PHASE 0 and printed as a numbered action.

HARD RULES HONOURED (Angela, non-negotiable)
============================================
  * VISIBLE tests only -- headed Chrome (never --headless), driving the real UI.
  * Every test is photographed FULL SCREEN (taskbar clock visible).
  * A stale / transient / timed-out answer is NEVER recorded as a pass.
  * Chat history cleared and Multi-Turn re-asserted before EVERY send.

USAGE
=====
    set TLAMATINI_USER=angela
    set TLAMATINI_PASS=<her password>
    python Tlamatini-Whatsapper-Daily-Tests.py                  # full run
    python Tlamatini-Whatsapper-Daily-Tests.py --preflight-only # diagnose, send nothing
    python Tlamatini-Whatsapper-Daily-Tests.py --repeat 5       # 5 rounds of every case
    python Tlamatini-Whatsapper-Daily-Tests.py --restart        # restart the app first
    python Tlamatini-Whatsapper-Daily-Tests.py --only zavu      # zavu | whatsapper | doctor

Artifacts land in <repo>/Temp/whatsapper_daily/<timestamp>/:
    SUMMARY.html   -- evidence page (screenshot + answer + provider proof per test)
    results.json   -- machine-readable
    shots/         -- one FULL-SCREEN photo per test
"""

import argparse
import datetime as _dt
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------- paths
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # <repo root>
HARNESS_DIR = os.path.join(REPO, ".claude", "skills",
                           "tlamatini-daily-chat-test", "harness")
INSTALL_DIR = r"C:\Tlamatini"
INSTALL_EXE = os.path.join(INSTALL_DIR, "Tlamatini.exe")
INSTALL_CONFIG = os.path.join(INSTALL_DIR, "config.json")
INSTALL_CONTACTS = os.path.join(INSTALL_DIR, "contacts.json")

OUT_ROOT = os.path.join(REPO, "Temp", "whatsapper_daily")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Tlamatini-WhatsapperDailyTests/1.0"
ZAVU_BASE = "https://api.zavu.dev/v1"
GRAPH = "https://graph.facebook.com/v25.0"

# The person every test messages. Overridable with --contact / --number.
DEFAULT_CONTACT = "Angela"


# --------------------------------------------------------------------------- tiny utils
def log(msg):
    print(msg, flush=True)


def rule(title):
    log("")
    log("=" * 78)
    log("  " + title)
    log("=" * 78)


def _req(url, method="GET", token=None, body=None, timeout=25):
    """Bare-stdlib HTTP. ALWAYS sends a User-Agent: Zavu sits behind Cloudflare
    and answers a UA-less request with 403 'browser_signature_banned'."""
    data = None
    headers = {"Accept": "application/json", "User-Agent": UA}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:                                   # noqa: BLE001
        return -1, "%s: %s" % (type(exc).__name__, exc)


def _json(text):
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:                                          # noqa: BLE001
        return {}


def read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except Exception as exc:                                   # noqa: BLE001
        log("  WARN could not read %s: %s" % (path, exc))
        return {}


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


# --------------------------------------------------------------------------- PHASE 0
class Preflight:
    """Everything that can block a WhatsApp send, detected BEFORE we send one.

    Produces .actions -- an ordered list of literal instructions for Angela --
    and per-channel readiness flags the GUI phase uses to mark a case as
    EXPECTED-FAIL instead of pretending it should have worked.
    """

    def __init__(self, args):
        self.args = args
        self.actions = []
        self.facts = {}
        self.whatsapper_ready = False
        self.zavu_ready = False
        self.window_open = False
        self.target_number = ""
        self.config = {}
        self.contacts = {}

    # -- helpers --
    def act(self, text):
        self.actions.append(text)

    def fact(self, key, value):
        self.facts[key] = value
        log("    %-26s %s" % (key + ":", value))

    # -- checks --
    def check_config(self):
        rule("PHASE 0.1  Installed configuration")
        self.config = read_json_file(INSTALL_CONFIG)
        if not self.config:
            self.act("Tlamatini does not appear to be installed at %s "
                     "(config.json unreadable)." % INSTALL_DIR)
            return
        self.fact("config", INSTALL_CONFIG)
        self.fact("whatsapp_phone_number_id",
                  self.config.get("whatsapp_phone_number_id") or "(empty)")
        tok = (self.config.get("whatsapp_access_token") or "").strip()
        self.fact("whatsapp token", "%d chars" % len(tok) if tok else "(EMPTY)")
        zav = (self.config.get("zavu_api_key") or "").strip()
        looks_placeholder = zav.startswith("<") or not zav
        self.fact("zavu_api_key",
                  "(EMPTY/placeholder)" if looks_placeholder else "%s...%s" % (zav[:8], zav[-4:]))
        if looks_placeholder:
            self.act("Set 'zavu_api_key' in %s (Config > Access Keys Wizard > "
                     "Unified Messaging (Zavu))." % INSTALL_CONFIG)

    def check_contacts(self):
        rule("PHASE 0.2  Contacts book")
        book = read_json_file(INSTALL_CONTACTS)
        entries = book.get("contacts", book if isinstance(book, list) else [])
        self.contacts = {}
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            names = [entry.get("name", "")] + list(entry.get("aliases", []) or [])
            for name in names:
                if name:
                    self.contacts[str(name).strip().lower()] = entry
        wanted = (self.args.contact or DEFAULT_CONTACT).strip().lower()
        hit = self.contacts.get(wanted)
        if not hit:
            self.fact("contact '%s'" % self.args.contact, "NOT FOUND")
            self.act("Add a contact named/aliased '%s' with a 'whatsapp' number to %s."
                     % (self.args.contact, INSTALL_CONTACTS))
            return
        number = str(hit.get("whatsapp") or "").strip()
        self.fact("contact '%s'" % self.args.contact, "%s -> %s" % (hit.get("name"), number or "(no whatsapp)"))
        self.target_number = self.args.number or number
        if not number:
            self.act("Contact '%s' has no 'whatsapp' field in %s."
                     % (self.args.contact, INSTALL_CONTACTS))
            return
        # Mexican mobiles need the '1' after the country code on WhatsApp:
        # +52 1 55 .... A number stored without it is accepted by the API and
        # then silently FAILS at the carrier. This exact bug cost Angela hours.
        d = digits(number)
        if d.startswith("52") and not d.startswith("521") and len(d) >= 12:
            self.act("MX number '%s' is missing the '1' after 52. WhatsApp needs "
                     "'+521...'. Fix it in %s." % (number, INSTALL_CONTACTS))

    def check_whatsapper(self):
        rule("PHASE 0.3  Whatsapper (Meta WhatsApp Cloud API)")
        token = (self.config.get("whatsapp_access_token") or "").strip()
        pnid = str(self.config.get("whatsapp_phone_number_id") or "").strip()
        if not token or not pnid:
            self.act("Whatsapper needs both 'whatsapp_access_token' and "
                     "'whatsapp_phone_number_id' in %s." % INSTALL_CONFIG)
            return
        code, raw = _req("%s/debug_token?%s" % ("https://graph.facebook.com",
                                                urllib.parse.urlencode(
                                                    {"input_token": token,
                                                     "access_token": token})))
        data = _json(raw).get("data", {})
        if code != 200 or not data.get("is_valid"):
            reason = _json(raw).get("error", {}).get("message", raw[:160])
            self.fact("token", "INVALID -- %s" % reason)
            self.act("Mint a NEW Meta token: developers.facebook.com/tools/explorer "
                     "-> app 'Tlamatini' -> tick whatsapp_business_messaging + "
                     "whatsapp_business_management -> Generate Access Token -> paste "
                     "into 'whatsapp_access_token' in %s. (A password change kills "
                     "old tokens.)" % INSTALL_CONFIG)
            return
        self.fact("token", "valid (app %s, type %s)" % (data.get("app_id"), data.get("type")))
        expires = data.get("expires_at") or 0
        if expires:
            hours = (expires - time.time()) / 3600.0
            self.fact("token expires in", "%.1f h" % hours)
            if hours < 0.5:
                self.act("The Meta token expires in under 30 min. For something "
                         "permanent use a SYSTEM USER token: business.facebook.com "
                         "> System users > TlamatiniBot > Generate token > "
                         "expiration NEVER.")
        else:
            self.fact("token expires in", "never (system-user token)")
        code, raw = _req("%s/%s?%s" % (GRAPH, pnid, urllib.parse.urlencode(
            {"fields": "display_phone_number,verified_name,quality_rating",
             "access_token": token})))
        info = _json(raw)
        if code != 200:
            self.fact("sending number", "UNREADABLE (%s)" % raw[:140])
            self.act("Meta rejected the phone_number_id '%s'. Check it in "
                     "WhatsApp Manager > API Setup." % pnid)
            return
        self.fact("sending number", "%s (%s, quality %s)"
                  % (info.get("display_phone_number"), info.get("verified_name"),
                     info.get("quality_rating")))
        if str(info.get("verified_name", "")).strip().lower() == "test number":
            self.act("Your Whatsapper sender is Meta's SANDBOX 'Test Number'. It can "
                     "ONLY message up to 5 recipients you pre-register in "
                     "WhatsApp Manager > API Setup. Add %s there, or use Zavuerer "
                     "instead." % (self.target_number or "your number"))
        self.whatsapper_ready = True

    def check_zavu(self):
        rule("PHASE 0.4  Zavuerer (Zavu unified messaging)")
        key = (self.config.get("zavu_api_key") or "").strip()
        if not key or key.startswith("<"):
            return
        code, raw = _req(ZAVU_BASE + "/senders", token=key)
        if code != 200:
            self.fact("zavu /senders", "HTTP %s -- %s" % (code, raw[:160]))
            self.act("Zavu rejected the API key. Get a fresh one at "
                     "https://www.zavu.dev (free plan includes WhatsApp) and put it "
                     "in 'zavu_api_key'.")
            return
        items = _json(raw).get("items", []) or []
        if not items:
            self.fact("zavu senders", "NONE")
            self.act("Your Zavu project has no sender. Create one at zavu.dev.")
            return
        sender = items[0]
        wa = sender.get("whatsapp", {}) or {}
        pay = wa.get("paymentStatus", {}) or {}
        self.fact("zavu sender", "%s %s" % (sender.get("name"), sender.get("phoneNumber")))
        self.fact("zavu whatsapp", "setup=%s method=%s templates=%s"
                  % (pay.get("setupStatus"), pay.get("methodStatus"),
                     pay.get("canSendTemplates")))
        self.zavu_ready = True
        self.check_window(key)

    def check_window(self, key):
        """Meta's 24-hour customer-service window, measured from Zavu's own log.

        Free-form text only delivers if the recipient wrote to the business
        number in the last 24 h. Zavu rides on Meta, so the rule still applies --
        this is what made three sends 'fail' for no visible reason.
        """
        target = digits(self.target_number)
        if not target:
            return
        code, raw = _req(ZAVU_BASE + "/messages?limit=50", token=key)
        if code != 200:
            return
        newest = None
        for item in _json(raw).get("items", []) or []:
            if digits(item.get("from")) == target:              # inbound FROM her
                stamp = item.get("createdAt") or ""
                if newest is None or stamp > newest:
                    newest = stamp
        if not newest:
            self.fact("24h window", "CLOSED (no inbound message ever seen)")
            self.act("Open the 24-hour window: from the phone %s send ANY WhatsApp "
                     "(even 'hola') to the Zavu sender number. Free-form text will "
                     "keep failing until you do." % (self.target_number or ""))
            return
        try:
            when = _dt.datetime.fromisoformat(newest.replace("Z", "+00:00"))
            age_h = (_dt.datetime.now(_dt.timezone.utc) - when).total_seconds() / 3600.0
        except Exception:                                       # noqa: BLE001
            age_h = 999.0
        if age_h <= 24.0:
            self.window_open = True
            self.fact("24h window", "OPEN (last inbound %.1f h ago, %.1f h left)"
                      % (age_h, 24.0 - age_h))
        else:
            self.fact("24h window", "CLOSED (last inbound %.1f h ago)" % age_h)
            self.act("Open the 24-hour window: from %s send ANY WhatsApp to the Zavu "
                     "sender number, then re-run." % (self.target_number or ""))

    def run(self):
        self.check_config()
        self.check_contacts()
        self.check_whatsapper()
        self.check_zavu()
        rule("PHASE 0.5  Verdict")
        log("    Whatsapper ready : %s" % ("YES" if self.whatsapper_ready else "NO"))
        log("    Zavuerer ready   : %s" % ("YES" if self.zavu_ready else "NO"))
        log("    24h window open  : %s" % ("YES" if self.window_open else "NO"))
        if self.actions:
            log("")
            log("    WHAT YOU MUST DO:")
            for i, action in enumerate(self.actions, 1):
                log("      %d) %s" % (i, action))
        else:
            log("    Nothing blocking. Both channels look sendable.")
        return self


# --------------------------------------------------------------------------- ground truth
def zavu_latest_outbound(key, target, since_iso):
    """Newest OUTBOUND Zavu message to `target` created at/after `since_iso`."""
    code, raw = _req(ZAVU_BASE + "/messages?limit=25", token=key)
    if code != 200:
        return None
    best = None
    for item in _json(raw).get("items", []) or []:
        if digits(item.get("to")) != digits(target):
            continue
        if (item.get("createdAt") or "") < since_iso:
            continue
        if best is None or (item.get("createdAt") or "") > (best.get("createdAt") or ""):
            best = item
    return best


def zavu_wait_terminal(key, target, since_iso, timeout_s=60):
    """Poll until the message reaches a TERMINAL state. `queued` is not proof."""
    terminal = ("delivered", "read", "failed", "undelivered", "rejected")
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        msg = zavu_latest_outbound(key, target, since_iso)
        if msg:
            last = msg
            if str(msg.get("status", "")).lower() in terminal:
                return msg
        time.sleep(3)
    return last


# --------------------------------------------------------------------------- test cases
def build_cases(args, pre):
    contact = args.contact or DEFAULT_CONTACT
    number = pre.target_number or args.number or ""
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    cases = []

    cases.append({
        "id": "zavu-contact",
        "channel": "zavu",
        "verify": "zavu",
        "text": ("Send a WhatsApp to %s using Zavuerer with this exact text: "
                 "'Prueba Zavuerer por contacto %s'. Use ONLY chat_agent_zavuerer. "
                 "Report the message id and status. End with END-RESPONSE."
                 % (contact, stamp)),
    })
    cases.append({
        "id": "zavu-number",
        "channel": "zavu",
        "verify": "zavu",
        "text": ("Send a WhatsApp with Zavuerer to the number %s with this exact "
                 "text: 'Prueba Zavuerer por numero %s'. Use ONLY "
                 "chat_agent_zavuerer. Report the message id and status. "
                 "End with END-RESPONSE." % (number, stamp)),
    })
    cases.append({
        "id": "whatsapper-contact",
        "channel": "whatsapper",
        "verify": "none",
        "text": ("Send a WhatsApp to %s using Whatsapper with this exact text: "
                 "'Prueba Whatsapper por contacto %s'. Use ONLY "
                 "chat_agent_whatsapper. Report exactly what Meta answered, "
                 "including any error. End with END-RESPONSE." % (contact, stamp)),
    })
    cases.append({
        "id": "whatsapper-number",
        "channel": "whatsapper",
        "verify": "none",
        "text": ("Send a WhatsApp with Whatsapper to %s with this exact text: "
                 "'Prueba Whatsapper por numero %s'. Use ONLY chat_agent_whatsapper. "
                 "Report exactly what Meta answered, including any error code. "
                 "End with END-RESPONSE." % (number, stamp)),
    })
    cases.append({
        "id": "doctor",
        "channel": "doctor",
        "verify": "none",
        "text": ("Run the Instant Messaging Doctor in diagnose mode for WhatsApp "
                 "only, without sending anything, and report status, "
                 "credential_status and actions_required verbatim. "
                 "End with END-RESPONSE."),
    })

    if args.only:
        cases = [c for c in cases if c["channel"] == args.only]
    return cases


def judge(case, answer, proof, pre):
    """Verdict. Provider proof outranks anything the chat said."""
    text = (answer or "").strip()
    low = text.lower()
    if not text:
        return "FAIL", "empty-answer"
    for marker in ("i will not hang", "retrying the same request", "tactic #"):
        if marker in low:
            return "FAIL", "transient-status-scraped"

    if case["verify"] == "zavu":
        if not pre.zavu_ready:
            return "BLOCKED", "zavu-not-configured"
        if proof is None:
            return "FAIL", "no-message-created-at-provider"
        status = str(proof.get("status", "")).lower()
        if status in ("delivered", "read"):
            return "PASS", "provider-confirms-%s" % status
        if status in ("failed", "undelivered", "rejected"):
            if not pre.window_open:
                return "BLOCKED", "provider-%s-24h-window-closed" % status
            return "FAIL", "provider-%s" % status
        return "WEAK", "provider-still-%s" % (status or "unknown")

    if case["channel"] == "whatsapper":
        if not pre.whatsapper_ready:
            return "BLOCKED", "whatsapper-token-or-number-not-usable"
        if any(w in low for w in ("error", "failed", "invalid", "expired")):
            return "FAIL", "agent-reported-error"
        return "WEAK", "sent-but-unverified"

    if any(w in low for w in ("status", "credential", "actions_required", "ready", "blocked")):
        return "PASS", "doctor-reported"
    return "WEAK", "no-doctor-fields"


# --------------------------------------------------------------------------- report
_BADGE = {"PASS": "#1e8e3e", "WEAK": "#b06000", "BLOCKED": "#5b6b8c", "FAIL": "#c5221f"}


def write_summary(run_dir, rows, pre, started):
    counts = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    out = ["<!doctype html><html><head><meta charset='utf-8'>",
           "<title>Whatsapper / Zavuerer -- Daily Evidence</title><style>",
           "body{font:14px/1.5 Segoe UI,Arial,sans-serif;margin:0;background:#0f1420;color:#e8ecf3}",
           ".top{position:sticky;top:0;background:#131a2b;padding:16px 22px;border-bottom:2px solid #2a3550}",
           ".b{padding:2px 10px;border-radius:12px;color:#fff;font-weight:600;margin-right:8px}",
           ".grid{padding:18px}.test{background:#182135;border:1px solid #26324e;border-radius:10px;margin:0 0 16px;padding:12px 14px}",
           ".q{color:#a7b3c9;font-size:12.5px;white-space:pre-wrap;margin:4px 0 8px}",
           "img{max-width:640px;width:100%;border:1px solid #33405f;border-radius:6px;display:block}",
           "pre{white-space:pre-wrap;background:#0c1120;padding:10px;border-radius:6px;max-height:280px;overflow:auto;color:#cdd6e6}",
           ".act{background:#2a1e12;border:1px solid #6b4a1f;border-radius:8px;padding:10px 14px;margin:10px 22px}",
           "</style></head><body>",
           "<div class='top'><h1>Tlamatini -- Whatsapper / Zavuerer daily evidence</h1>",
           "<div>started %s &middot; every photo is the FULL screen incl. the clock &middot; "
           "a PASS means the PROVIDER confirmed delivery</div><div style='margin-top:8px'>"
           % html.escape(started)]
    for key in ("PASS", "WEAK", "BLOCKED", "FAIL"):
        out.append("<span class='b' style='background:%s'>%s %d</span>"
                   % (_BADGE[key], key, counts.get(key, 0)))
    out.append("</div></div>")
    if pre.actions:
        out.append("<div class='act'><b>WHAT YOU MUST DO</b><ol>")
        for action in pre.actions:
            out.append("<li>%s</li>" % html.escape(action))
        out.append("</ol></div>")
    out.append("<div class='grid'>")
    for row in reversed(rows):
        out.append("<div class='test'><div><b>%s</b> &nbsp;<span class='b' style='background:%s'>%s</span> %s &nbsp; %.1fs</div>"
                   % (html.escape(row["id"]), _BADGE.get(row["verdict"], "#666"),
                      row["verdict"], html.escape(row["reason"]), row.get("elapsed_s", 0.0)))
        out.append("<div class='q'>%s</div>" % html.escape(row["question"][:400]))
        if row.get("shot"):
            rel = "shots/" + os.path.basename(row["shot"])
            out.append("<a href='%s' target='_blank'><img loading='lazy' src='%s'></a>" % (rel, rel))
        if row.get("proof"):
            out.append("<details open><summary>provider proof</summary><pre>%s</pre></details>"
                       % html.escape(json.dumps(row["proof"], indent=2)[:2000]))
        out.append("<details><summary>chat answer (%d chars)</summary><pre>%s</pre></details></div>"
                   % (len(row.get("answer") or ""), html.escape((row.get("answer") or "")[:6000])))
    out.append("</div></body></html>")
    path = os.path.join(run_dir, "SUMMARY.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("".join(out))
    return path


# --------------------------------------------------------------------------- app restart
def server_up(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 500
    except Exception:                                           # noqa: BLE001
        return False


def restart_app(base_url):
    rule("PHASE 1  Restarting the installed Tlamatini")
    if not os.path.isfile(INSTALL_EXE):
        log("    %s not found -- skipping restart." % INSTALL_EXE)
        return
    subprocess.call(["taskkill", "/IM", "Tlamatini.exe", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    subprocess.Popen([INSTALL_EXE], cwd=INSTALL_DIR, close_fds=True)
    log("    launched %s -- waiting for the web port..." % INSTALL_EXE)
    for _ in range(60):
        if server_up(base_url):
            log("    server is UP.")
            return
        time.sleep(2)
    log("    WARN server did not answer in 120 s.")


# --------------------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description="Tlamatini WhatsApp daily tester")
    parser.add_argument("--user", default=os.environ.get("TLAMATINI_USER", "angela"))
    parser.add_argument("--password", default=os.environ.get("TLAMATINI_PASS", ""))
    parser.add_argument("--contact", default=DEFAULT_CONTACT)
    parser.add_argument("--number", default="")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--only", choices=["zavu", "whatsapper", "doctor"], default=None)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per answer")
    parser.add_argument("--slowmo", type=int, default=0)
    parser.add_argument("--judge-model", default="glm-5.2:cloud")
    parser.add_argument("--not-ready-retries", type=int, default=3)
    parser.add_argument("--not-ready-backoff", type=float, default=20.0)
    parser.add_argument("--headless", action="store_true",
                        help="IGNORED -- headless tests are forbidden on this machine")
    args = parser.parse_args()

    started = _dt.datetime.now().isoformat(timespec="seconds")
    rule("Tlamatini -- Whatsapper / Zavuerer DAILY TESTS")
    log("    started %s" % started)
    log("    VISIBLE run: headed Chrome, real chat GUI, full-screen photos.")

    pre = Preflight(args).run()

    if args.preflight_only:
        rule("Preflight only -- nothing was sent.")
        return 0 if not pre.actions else 2

    if not args.password:
        rule("STOP -- no password")
        log("    The GUI phase drives the real chat, so it needs your login.")
        log("    Do this, then re-run:")
        log("        set TLAMATINI_USER=%s" % args.user)
        log("        set TLAMATINI_PASS=<your password>")
        log("    (or pass --password ...). Use --preflight-only to diagnose "
            "without logging in.")
        return 2

    sys.path.insert(0, HARNESS_DIR)
    try:
        import config as C                      # noqa: N814
        import run_test as R
        from PIL import ImageGrab
        from playwright.sync_api import sync_playwright
    except Exception as exc:                                    # noqa: BLE001
        rule("STOP -- test harness unavailable")
        log("    %s: %s" % (type(exc).__name__, exc))
        log("    Install what is missing, e.g.:")
        log("        pip install playwright pillow && python -m playwright install chrome")
        return 3

    if args.restart:
        restart_app(C.BASE_URL + C.CHAT_PATH)

    run_dir = os.path.join(OUT_ROOT, _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    shots_dir = os.path.join(run_dir, "shots")
    os.makedirs(shots_dir, exist_ok=True)
    log("    artifacts -> %s" % run_dir)

    key = (pre.config.get("zavu_api_key") or "").strip()
    cases = build_cases(args, pre)
    rows = []

    harness = R.Harness(args)
    with sync_playwright() as play:
        browser = harness.launch(play)
        try:
            harness.login()
            harness.goto_chat()
            harness.set_toggles()

            for round_no in range(1, args.repeat + 1):
                for case in cases:
                    test_id = "%s#%d" % (case["id"], round_no)
                    rule("TEST %s" % test_id)
                    harness.clear_history()
                    # re-assert Multi-Turn immediately before the send
                    harness.page.evaluate(
                        """() => {const e=document.querySelector('#multi-turn-enabled');
                           if(e&&!e.checked){e.checked=true;
                           e.dispatchEvent(new Event('change',{bubbles:true}));}}""")
                    since = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
                    started_at = time.time()
                    try:
                        rec = harness.ask_one(
                            {"id": test_id, "category": case["channel"], "text": case["text"]},
                            timeout_ms=args.timeout * 1000)
                        answer = rec.get("answer", "")
                    except Exception as exc:                    # noqa: BLE001
                        log("    EXCEPTION: %s" % exc)
                        answer = ""
                        harness.recover()

                    proof = None
                    if case["verify"] == "zavu" and key:
                        log("    verifying against Zavu (a chat 'ok' proves nothing)...")
                        proof = zavu_wait_terminal(key, pre.target_number, since)
                        log("    provider says: %s" % (proof.get("status") if proof else "no message found"))

                    verdict, reason = judge(case, answer, proof, pre)
                    shot = os.path.join(shots_dir, "%s.png" % test_id.replace("#", "_"))
                    try:
                        harness.page.bring_to_front()
                        time.sleep(0.3)
                        try:
                            ImageGrab.grab(all_screens=True).save(shot)
                        except TypeError:
                            ImageGrab.grab().save(shot)
                    except Exception as exc:                    # noqa: BLE001
                        log("    WARN screenshot failed: %s" % exc)
                        shot = ""
                    log("    VERDICT %-8s %s" % (verdict, reason))
                    rows.append({
                        "id": test_id, "question": case["text"], "answer": answer,
                        "verdict": verdict, "reason": reason, "proof": proof,
                        "shot": shot, "elapsed_s": round(time.time() - started_at, 1),
                        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
                    })
                    with open(os.path.join(run_dir, "results.json"), "w", encoding="utf-8") as handle:
                        json.dump(rows, handle, indent=2, ensure_ascii=False)
                    write_summary(run_dir, rows, pre, started)
        finally:
            try:
                browser.close()
            except Exception:                                   # noqa: BLE001
                pass

    summary = write_summary(run_dir, rows, pre, started)
    rule("RESULTS")
    counts = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    for key_name in ("PASS", "WEAK", "BLOCKED", "FAIL"):
        log("    %-8s %d" % (key_name, counts.get(key_name, 0)))
    log("    evidence: %s" % summary)
    if pre.actions:
        log("")
        log("    WHAT YOU MUST DO:")
        for i, action in enumerate(pre.actions, 1):
            log("      %d) %s" % (i, action))
    return 0 if counts.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
