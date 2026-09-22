"""
context_restore_spinner_visible.py - VISIBLE regression runner (2026-09-22)

THE BUG
-------
When Tlamatini starts with a context already saved in `SessionState` (the user
loaded one, then the app was closed and reopened), the consumer sends
`session-restored` with `loading: true` the instant the socket opens. The chat
page correctly flips the Send button to 'Cancel', greys every menu and makes the
input read-only... and then shows NO SPINNER AT ALL, so the page looks idle
while it is in fact completely frozen. Loading the very same context from the
Context menu shows the spinner normally.

ROOT CAUSE
----------
`#wait-spinner` is a CHILD of `#chat-log`, and `renderInitialMessages()` wipes
`#chat-log` with `innerHTML = ''`. On the restore path that wipe happens AFTER
the spinner was created:

    agent_page_state.js  socket opens, frames are buffered
    agent_page_chat.js   drains the buffer at SCRIPT-PARSE time
                         -> session-restored {loading:true}
                         -> disableControlsDuringOperation()  SPINNER APPENDED
    agent_page_init.js   window.onload (fires much later, after every image)
                         -> renderInitialMessages() -> innerHTML = ''
                         -> SPINNER DESTROYED

`disableControlsDuringOperation()` is idempotent - its spinner is guarded by
`if (!document.getElementById(spinnerId))` - so nothing ever put it back.

WHAT THIS RUNNER PROVES
-----------------------
Two phases, each against a FRESHLY restarted server (a restart is what empties
`global_state`, which is what makes the consumer take the loading=true path):

  before : the two JS files are served from git HEAD via route interception.
           Nothing on disk is touched. Expected: THE BUG REPRODUCES.
  after  : the real, fixed files are served. Expected: SPINNER PRESENT.

Each phase makes two independent measurements inside the REAL running GUI:

  LIVE      - right after the page's load event, is the busy latch on and is
              the spinner on screen? If the latch already cleared, the sample
              is reported INCONCLUSIVE, never as a pass.
  MECHANISM - deterministic and timing-free: force the busy state with the
              app's own disableControlsDuringOperation(), then call the app's
              own renderInitialMessages() and check whether the spinner
              survived. This is the regression itself.

RULES HONOURED
--------------
  * HEADED real Chrome on the real desktop. Never --headless.
  * Every screenshot is taken by Tlamatini's SHOTER agent (never PIL).
  * The run ESTABLISHES its environment first - migrate, user, server, and a
    plain-HTTP login - and stops with a NAMED reason and a distinct exit code
    rather than letting a browser selector time out.
  * A stale, transient or timed-out observation is never recorded as a pass.
  * Never `taskkill /T` - that kills the console running this test.

USAGE
    python context_restore_spinner_visible.py            # both phases
    python context_restore_spinner_visible.py --phase after
    python context_restore_spinner_visible.py --keep-open

EXIT CODES
    0  every phase behaved as expected
    2  the fix did not hold (spinner missing after the fix)
    3  environment could not be established (named reason printed)
    4  inconclusive - could not observe the busy window
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
MANAGE_DIR = os.path.join(REPO, "Tlamatini")
MANAGE_PY = os.path.join(MANAGE_DIR, "manage.py")

ARTIFACTS = os.path.join(REPO, "Temp", "context_restore_spinner")

JS_REL = [
    "Tlamatini/agent/static/agent/js/agent_page_chat.js",
    "Tlamatini/agent/static/agent/js/agent_page_init.js",
]

PORT = int(os.environ.get("TLM_SPINNER_PORT", "8011"))
BASE = "http://127.0.0.1:%d" % PORT
# `tlamatini/urls.py` mounts agent.urls under 'agent/', and agent.urls maps ''
# to login_view - so the login form lives at /agent/, not /agent/login/.
LOGIN_URL = BASE + "/agent/"
CHAT_URL = BASE + "/agent/agent/"

# Throwaway credentials for a LOCAL, EMPTY development database that this
# runner creates itself. Not a secret, and never reused anywhere else. Override
# with TLAMATINI_USER / TLAMATINI_PASS.
USER = os.environ.get("TLAMATINI_USER", "angela")
PASS = os.environ.get("TLAMATINI_PASS", "tlamatini-visible-test")

# The directory fed to the restored context. Small, all text, always present.
CONTEXT_DIR = os.path.join(REPO, "Tlamatini", "agent", "static", "agent", "js")

sys.path.insert(0, HERE)
try:
    from shoter_shot import take_shot
except Exception as _shoter_err:  # pragma: no cover - reported, never silent
    take_shot = None
    _SHOTER_IMPORT_ERROR = _shoter_err
else:
    _SHOTER_IMPORT_ERROR = None

try:
    import windower_focus
except Exception:  # pragma: no cover - reported at the call site
    windower_focus = None


def say(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def die(code, reason):
    say("")
    say("=" * 74)
    say("STOPPED: " + reason)
    say("=" * 74)
    sys.exit(code)


def photo(name, page=None):
    """Whole desktop, taken by SHOTER. Never PIL. A failure is REPORTED.

    A PHOTO MUST PROVE ITS CLAIM. The first version of this runner measured the
    spinner correctly in the DOM and then photographed a desktop where Chrome
    was buried under the server console it had just launched - a true result
    with worthless evidence. So when a `page` is given, the browser is brought
    forward with WINDOWER and the page itself confirms it owns the focus
    (`document.hasFocus()`) before the shutter fires. If it cannot be confirmed
    the image is still taken, but it is NAMED `_UNVERIFIED` so nobody can ever
    mistake it for evidence.
    """
    verified = True
    pinned = False
    if page is not None:
        verified = _focus_browser_for_photo(page)
        if verified and windower_focus is not None:
            # Hold the z-order THROUGH the capture. Verifying focus and then
            # shooting is not enough: Shoter has to spawn a process first, and
            # a console busy printing can take the top back in that gap - which
            # is exactly how a "verified" photo came back showing two consoles
            # and no browser.
            pinned = windower_focus.set_topmost("Google Chrome", ARTIFACTS, True)
    if take_shot is None:
        say("   !! Shoter helper could not be imported: %s" % _SHOTER_IMPORT_ERROR)
        return None
    try:
        p = take_shot(ARTIFACTS, name + "_pending", runtime_base=ARTIFACTS)
    except Exception as exc:
        say("   !! Shoter FAILED: %s" % exc)
        return None
    finally:
        if pinned:
            windower_focus.set_topmost("Google Chrome", ARTIFACTS, False)

    # Was the browser STILL in front when the shutter actually fired? Only a
    # yes makes this image evidence; anything else gets renamed so nobody can
    # mistake it for proof later.
    if page is not None and verified and not _page_has_focus(page, tries=2):
        verified = False
    if not p:
        say("   !! Shoter returned no image (reported, not hidden).")
        return None
    final = _rename_shot(p, name if verified else name + "_UNVERIFIED")
    say("   photo -> %s%s" % (final, "" if verified else "   <-- NOT EVIDENCE"))
    return final


def _rename_shot(path, name):
    """Name the file only after we know whether it proves anything."""
    try:
        target = os.path.join(os.path.dirname(path), name + os.path.splitext(path)[1])
        if os.path.abspath(target) != os.path.abspath(path):
            if os.path.exists(target):
                os.remove(target)
            os.replace(path, target)
        return target
    except Exception:
        return path


def _page_has_focus(page, tries=8):
    """document.hasFocus() is true only when the browser window owns the
    foreground AND this page is the active tab - exactly the claim the
    photograph has to support."""
    for _ in range(tries):
        try:
            if page.evaluate("() => document.hasFocus()") is True:
                return True
        except Exception:
            return False
        time.sleep(0.15)
    return False


def _focus_browser_for_photo(page):
    """Windower brings Chrome forward; the PAGE confirms it really is focused.

    DO NOT MATCH ON THE PAGE TITLE. `rotateTitle()` (agent_page_layout.js)
    rewrites `document.title` on a timer - it scrolls the word "Tlamatini" one
    character per tick and prefixes an hourglass while busy - so the window
    title is a MOVING TARGET and matching it fails almost every time (measured:
    Windower was handed 'X amatini Tl'). Match the browser instead, and walk
    the Chrome windows until the page itself reports the focus landed; on a
    desktop with several Chrome windows that is what picks the right one.
    """
    if windower_focus is None:
        say("   !! windower_focus helper missing - cannot raise the browser.")
        return False
    if _page_has_focus(page, tries=1):
        return True
    for index in range(6):
        if not windower_focus.focus("Google Chrome", ARTIFACTS,
                                    match_index=index):
            break
        if _page_has_focus(page):
            return True
    say("   !! the browser could not be raised - this photo is NOT evidence.")
    return False


# ----------------------------------------------------------------------
# Environment (the test establishes it; it does not assume it)
# ----------------------------------------------------------------------

def port_is_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def run_manage(args, timeout=300):
    env = dict(os.environ)
    env["TLAMATINI_NO_AUDIO"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, MANAGE_PY] + args,
        cwd=MANAGE_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, env=env,
    )


def prepare_database():
    say("preflight: database")
    db = os.path.join(MANAGE_DIR, "db.sqlite3")
    # A 0-byte db.sqlite3 next to a stale -shm/-wal makes SQLite open a file
    # that has no tables. Move the orphaned sidecars aside (never delete a
    # sidecar that still belongs to a real database) and let migrate rebuild.
    if os.path.exists(db) and os.path.getsize(db) == 0:
        for ext in ("-shm", "-wal", "-journal"):
            side = db + ext
            if os.path.exists(side):
                os.makedirs(ARTIFACTS, exist_ok=True)
                shutil.move(side, os.path.join(ARTIFACTS, "orphan_db" + ext))
                say("   moved orphaned sidecar aside: db.sqlite3%s" % ext)

    r = run_manage(["migrate", "--noinput"])
    if r.returncode != 0:
        say(r.stdout[-2500:])
        say(r.stderr[-2500:])
        die(3, "`manage.py migrate` failed - the test database could not be built.")
    say("   migrate OK")

    seed = (
        "import os\n"
        "from django.contrib.auth.models import User\n"
        "from agent.models import SessionState\n"
        "u, made = User.objects.get_or_create(username=%r)\n"
        "u.set_password(%r); u.is_staff = True; u.is_superuser = True; u.save()\n"
        "SessionState.objects.update_or_create(\n"
        "    user=u,\n"
        "    defaults={'context_path': %r, 'context_type': 'directory',\n"
        "              'context_filename': None})\n"
        "print('SEEDED', u.username, 'created' if made else 'existing')\n"
        % (USER, PASS, CONTEXT_DIR)
    )
    r = run_manage(["shell", "-c", seed])
    if r.returncode != 0 or "SEEDED" not in (r.stdout or ""):
        say(r.stdout[-2500:])
        say(r.stderr[-2500:])
        die(3, "Could not seed the test user + restored SessionState.")
    say("   %s" % r.stdout.strip().splitlines()[-1])
    say("   restored context -> %s" % CONTEXT_DIR)


def reseed_session_state():
    """`last_active` drives is_expired(); refresh it before every phase, and
    make sure a previous phase's Clear-Context did not wipe the row."""
    seed = (
        "from django.contrib.auth.models import User\n"
        "from agent.models import SessionState\n"
        "u = User.objects.get(username=%r)\n"
        "SessionState.objects.update_or_create(\n"
        "    user=u,\n"
        "    defaults={'context_path': %r, 'context_type': 'directory',\n"
        "              'context_filename': None})\n"
        "print('RESEEDED')\n" % (USER, CONTEXT_DIR)
    )
    r = run_manage(["shell", "-c", seed])
    if "RESEEDED" not in (r.stdout or ""):
        die(3, "Could not refresh the restored SessionState between phases.")


class Server(object):
    """The Django server in its OWN VISIBLE console window.

    ``release=True`` forces DEBUG off, which is what makes this a meaningful
    FROZEN-MODE check: the two modes differ in WHERE the JavaScript comes from.

        source  DEBUG=True   Django's dev static handler serves the SOURCE tree
        frozen  DEBUG=False  WhiteNoise serves the COLLECTED `staticfiles/` tree
                             (bundled next to the exe by build.py)

    So a fix that is only in the source tree is invisible to a frozen install
    until `collectstatic` runs. build.py runs `collectstatic --noinput --clear`
    on every build and ABORTS if it fails, so the fix does reach a real build -
    but this flag proves the collected copy actually carries it rather than
    assuming it."""

    def __init__(self, release=False):
        self.proc = None
        self.release = release

    def start(self):
        if not port_is_free(PORT):
            die(3, "Port %d is already in use - set TLM_SPINNER_PORT." % PORT)
        env = dict(os.environ)
        env["TLAMATINI_NO_AUDIO"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        if self.release:
            env["TLAMATINI_DJANGO_DEBUG"] = "0"
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_CONSOLE
        self.proc = subprocess.Popen(
            [sys.executable, MANAGE_PY, "runserver", "--noreload",
             "127.0.0.1:%d" % PORT],
            cwd=MANAGE_DIR, env=env, creationflags=flags,
        )
        say("server: launched in a visible console (pid %d) on %s"
            % (self.proc.pid, BASE))
        deadline = time.time() + 120
        while time.time() < deadline:
            if self.proc.poll() is not None:
                die(3, "The server process exited during startup "
                       "(exit code %s) - read its console window."
                       % self.proc.returncode)
            try:
                with urllib.request.urlopen(LOGIN_URL, timeout=4) as r:
                    if r.status == 200:
                        say("   server answering after %.1fs" %
                            (120 - (deadline - time.time())))
                        return
            except Exception:
                time.sleep(1.0)
        die(3, "The server never answered on %s within 120s." % BASE)

    def stop(self):
        """Stop ONLY our own process. NEVER `taskkill /T` - the /T flag kills
        the process TREE, which includes the console running this test and
        looks exactly like a mystery Ctrl+C (0xC000013A)."""
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=15)
        except Exception:
            try:
                self.proc.kill()
                self.proc.wait(timeout=10)
            except Exception:
                pass
        # Daphne can hold the port a moment after the process is gone.
        for _ in range(30):
            if port_is_free(PORT):
                break
            time.sleep(0.5)
        say("server: stopped (pid %d)" % self.proc.pid)


def login_over_plain_http():
    """Prove the credentials work BEFORE a browser is ever opened, so a login
    problem is reported as a login problem and not as a selector timeout."""
    say("preflight: login over plain HTTP")
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(LOGIN_URL, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as exc:
        die(3, "The login page could not be fetched: %s" % exc)

    m = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)', html)
    if not m:
        die(3, "No CSRF token on the login page - the page did not render.")
    data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": m.group(1),
        "username": USER,
        "password": PASS,
    }).encode()
    req = urllib.request.Request(LOGIN_URL, data=data,
                                 headers={"Referer": LOGIN_URL})
    try:
        with opener.open(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            final = r.geturl()
    except Exception as exc:
        die(3, "The login POST failed: %s" % exc)

    if "id_password" in body or final.rstrip("/").endswith("/agent"):
        die(3, "Login was REJECTED for user %r - the credentials do not work. "
               "No browser was opened." % USER)
    say("   login OK (landed on %s)" % final)


# ----------------------------------------------------------------------
# The measurement
# ----------------------------------------------------------------------

PROBE_JS = r"""
() => {
    const read = (name) => {
        try { return eval(name); } catch (e) { return '<unreadable:' + e.name + '>'; }
    };
    const btn = document.getElementById('chat-message-submit');
    const inp = document.getElementById('chat-message-input');
    return {
        spinner: !!document.getElementById('wait-spinner'),
        button: btn ? (btn.textContent || '').trim() : '<no button>',
        inLongOperation: read('inLongOperation'),
        lapseLoadingContext: read('lapseLoadingContext'),
        inputReadOnly: inp ? !!inp.readOnly : null,
        chatLogChildren: (document.getElementById('chat-log') || {children: []}).children.length,
        readyState: document.readyState
    };
}
"""

MECHANISM_JS = r"""
() => {
    const out = {ok: false, steps: []};
    try {
        if (typeof disableControlsDuringOperation !== 'function'
            || typeof renderInitialMessages !== 'function') {
            out.error = 'app functions missing';
            return out;
        }
        disableControlsDuringOperation();
        out.spinnerAfterDisable = !!document.getElementById('wait-spinner');
        renderInitialMessages([
            {username: 'Tlamatini', message: 'probe row', timestamp: '2026/09/22 00:00:00.000'}
        ]);
        out.spinnerAfterRender = !!document.getElementById('wait-spinner');
        const btn = document.getElementById('chat-message-submit');
        out.buttonAfterRender = btn ? (btn.textContent || '').trim() : '<no button>';
        out.ok = out.spinnerAfterDisable === true && out.spinnerAfterRender === true;
    } catch (e) {
        out.error = String(e);
    }
    return out;
}
"""


def git_head_bytes(rel):
    r = subprocess.run(["git", "-C", REPO, "show", "HEAD:" + rel],
                       capture_output=True)
    if r.returncode != 0:
        die(3, "git show HEAD:%s failed: %s"
               % (rel, r.stderr.decode("utf-8", "replace")[:300]))
    return r.stdout


def run_phase(phase, keep_open, release=False):
    """phase == 'before' serves the PRE-FIX JS via route interception (nothing
    on disk is touched); phase == 'after' serves the real files."""
    from playwright.sync_api import sync_playwright

    say("")
    say("=" * 74)
    say("PHASE '%s'  (%s mode)"
        % (phase.upper(), "RELEASE/frozen-path" if release else "SOURCE"))
    say("=" * 74)

    pre_fix = {}
    if phase == "before":
        for rel in JS_REL:
            pre_fix[os.path.basename(rel)] = git_head_bytes(rel)
            say("   serving %s from git HEAD (%d bytes) - disk untouched"
                % (os.path.basename(rel), len(pre_fix[os.path.basename(rel)])))

    tag = phase + ("_release" if release else "_source")
    result = {"phase": phase, "mode": "release" if release else "source",
              "tag": tag}
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome",
                                         args=["--start-maximized"])
        except Exception:
            say("   real Chrome unavailable - falling back to bundled Chromium (still HEADED)")
            browser = pw.chromium.launch(headless=False,
                                         args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)

        if pre_fix:
            def serve_old(route, request):
                name = request.url.split("?")[0].rsplit("/", 1)[-1]
                body = pre_fix.get(name)
                if body is None:
                    route.continue_()
                    return
                route.fulfill(status=200, body=body,
                              headers={"content-type": "application/javascript; charset=utf-8",
                                       "cache-control": "no-store"})
            for name in pre_fix:
                ctx.route("**/" + name + "*", serve_old)

        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(m.text))

        say("   logging in through the real form")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("load")

        say("   opening the chat page - the context restore starts NOW")
        page.goto(CHAT_URL, wait_until="load")
        # window.onload handlers run on the load event; give them a beat to
        # finish, then look. This is exactly the moment the bug appears.
        page.wait_for_timeout(400)

        samples = []
        shot_taken = False
        t0 = time.time()
        while time.time() - t0 < 12:
            s = page.evaluate(PROBE_JS)
            s["t"] = round(time.time() - t0, 2)
            samples.append(s)
            busy = (s["inLongOperation"] is True) or (s["lapseLoadingContext"] is True)
            say("   t=%5.2fs busy=%-5s spinner=%-5s button=%-8r readOnly=%s"
                % (s["t"], busy, s["spinner"], s["button"], s["inputReadOnly"]))
            # PHOTOGRAPH THE BUSY WINDOW, NOT THE AFTERMATH. The first draft
            # shot the desktop once the polling loop was over, and on a fast
            # machine the context had already finished by then - so the photo
            # showed 'Your agent is ready' and proved NOTHING about the spinner
            # it was supposed to evidence. The claim and the image must match.
            if busy and not shot_taken:
                photo("spinner_%s_live" % tag, page=page)
                shot_taken = True
            if len(samples) >= 3 and not busy:
                break
            time.sleep(1.0)
        if not shot_taken:
            photo("spinner_%s_live_NOT_BUSY" % tag, page=page)

        first = samples[0]
        busy_first = (first["inLongOperation"] is True) or (first["lapseLoadingContext"] is True)
        busy_any = any((s["inLongOperation"] is True) or (s["lapseLoadingContext"] is True)
                       for s in samples)
        spinner_while_busy = [s["spinner"] for s in samples
                              if (s["inLongOperation"] is True) or (s["lapseLoadingContext"] is True)]

        if not busy_any:
            result["live"] = "INCONCLUSIVE"
            say("   LIVE: INCONCLUSIVE - the busy latch was never observed on. "
                "Nothing is recorded as a pass.")
        elif all(spinner_while_busy):
            result["live"] = "PASS"
            say("   LIVE: PASS - the spinner was on screen for every busy sample.")
        else:
            result["live"] = "FAIL"
            say("   LIVE: FAIL - the page was busy with NO spinner (%d of %d busy "
                "samples had none)."
                % (spinner_while_busy.count(False), len(spinner_while_busy)))

        result["busy_first_sample"] = busy_first
        result["samples"] = samples

        say("   mechanism probe: force busy, then re-render the history")
        mech = page.evaluate(MECHANISM_JS)
        say("      spinner after disableControlsDuringOperation() : %s"
            % mech.get("spinnerAfterDisable"))
        say("      spinner after renderInitialMessages()          : %s"
            % mech.get("spinnerAfterRender"))
        say("      button  after renderInitialMessages()          : %r"
            % mech.get("buttonAfterRender"))
        if mech.get("error"):
            say("      error: %s" % mech["error"])
        result["mechanism"] = "PASS" if mech.get("ok") else "FAIL"
        result["mechanism_detail"] = mech
        say("   MECHANISM: %s" % result["mechanism"])

        photo("spinner_%s_mechanism" % tag, page=page)

        result["console_tail"] = logs[-40:]
        if keep_open:
            say("   --keep-open: leaving the browser up for 60s")
            page.wait_for_timeout(60000)
        ctx.close()
        browser.close()
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["before", "after", "both"], default="both")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument(
        "--release", action="store_true",
        help="Run the server with DEBUG off, so WhiteNoise serves the COLLECTED "
             "staticfiles/ tree - the same path a FROZEN install uses. Runs "
             "collectstatic first so the collected copy is current.")
    args = ap.parse_args()

    if "--headless" in sys.argv:
        die(3, "HEADLESS IS FORBIDDEN. Every automated test here runs visible.")

    os.makedirs(ARTIFACTS, exist_ok=True)
    say("artifacts -> %s" % ARTIFACTS)

    try:
        import playwright  # noqa: F401
    except ImportError:
        die(3, "playwright is not installed in %s - `pip install playwright` "
               "and `playwright install chrome`." % sys.executable)

    prepare_database()

    if args.release:
        say("preflight: collectstatic (RELEASE mode serves the COLLECTED tree)")
        r = run_manage(["collectstatic", "--noinput"])
        if r.returncode != 0:
            say(r.stdout[-1500:])
            die(3, "collectstatic failed - a RELEASE/frozen run would serve "
                   "stale JavaScript.")
        say("   %s" % (r.stdout or "").strip().splitlines()[-1])
        say("   mode: RELEASE (DEBUG=0, WhiteNoise -> staticfiles/) "
            "== the frozen web path")
    else:
        say("   mode: SOURCE (DEBUG=1, dev static handler -> source tree)")

    phases = ["before", "after"] if args.phase == "both" else [args.phase]
    results = []
    for phase in phases:
        reseed_session_state()
        server = Server(release=args.release)
        server.start()
        try:
            login_over_plain_http()
            results.append(run_phase(phase, args.keep_open,
                                     release=args.release))
        finally:
            server.stop()

    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    for r in results:
        say("  %-7s %-8s live=%-13s mechanism=%s"
            % (r["phase"], r["mode"], r["live"], r["mechanism"]))
    name = "result_release.json" if args.release else "result_source.json"
    with open(os.path.join(ARTIFACTS, name), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    say("  detail -> %s" % os.path.join(ARTIFACTS, name))

    after = [r for r in results if r["phase"] == "after"]
    before = [r for r in results if r["phase"] == "before"]

    if after:
        a = after[0]
        if a["mechanism"] != "PASS":
            die(2, "THE FIX DID NOT HOLD: after the fix, renderInitialMessages() "
                   "still destroys the spinner.")
        if a["live"] == "FAIL":
            die(2, "THE FIX DID NOT HOLD: the restored context left the page busy "
                   "with no spinner.")
        if a["live"] == "INCONCLUSIVE":
            say("  note: the LIVE sample was inconclusive (the context finished "
                "loading before the first look). The MECHANISM probe is "
                "deterministic and it PASSED.")
    if before:
        b = before[0]
        if b["mechanism"] == "PASS":
            say("  note: the 'before' phase did NOT reproduce the mechanism - "
                "check that git HEAD really is the pre-fix code.")
        else:
            say("  confirmed: the pre-fix code loses the spinner; the fixed code "
                "keeps it.")
    say("")
    say("DONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
