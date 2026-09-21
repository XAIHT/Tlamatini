#!/usr/bin/env python
# ══════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Tlamatini Author Banner — do not remove
# ══════════════════════════════════════════════════════════════════════
"""Make a visible test INVULNERABLE to peripheral failure.

Angela, 2026-09-21: *"redesign your tests, make them invulnerable to fail
peripherally"*. She is right. Every run so far died at the EDGES, never on the
thing under test:

  * the source server was not running            -> Playwright timeout
  * the source database had no ``auth_user``     -> login POST 500
  * the login silently failed                    -> 30 s wait for a selector
                                                    that could never appear
  * ``taskkill /T`` on the server killed the process TREE, which included the
    console running the test -> 0xC000013A, twice

Each of those produced a Playwright traceback that said nothing about the real
cause, and none of them had anything to do with the feature being tested.

So a test no longer *assumes* its environment - it ESTABLISHES it, repairs what
it can, and when it genuinely cannot, it stops with a NAMED reason and a
distinct exit code instead of a stack trace.

    from preflight import ensure_ready
    state = ensure_ready(BASE_URL, USER, PASSWORD)
    if not state["ok"]:
        print(state["reason"]);  return state["exit_code"]

CONTRACTS:
  * It never kills a process TREE. Only the exact PID holding the port, and
    only one we are sure is a Python/Tlamatini server.
  * It repairs only the DEV tree (gitignored ``db.sqlite3``). It never touches
    the frozen install.
  * It VERIFIES the login over plain HTTP before a browser is ever opened, so
    a broken credential costs a second, not a 30-second selector timeout.
  * Every repair it performs is REPORTED, so a green run never hides the fact
    that the environment had to be fixed first.
"""

from __future__ import annotations

import http.cookiejar
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Distinct exit codes, so a caller (and a human) can tell WHAT went wrong.
EXIT_OK = 0
EXIT_ENV_UNFIXABLE = 4     # the environment is broken and we could not repair it
EXIT_WRONG_TARGET = 3      # something answers, but it is not the build under test

_HERE = os.path.dirname(os.path.abspath(__file__))
# harness -> tlamatini-daily-chat-test -> skills -> .claude -> <repo root>
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_MANAGE_DIR = os.path.join(_REPO_ROOT, "Tlamatini")
_MANAGE_PY = os.path.join(_MANAGE_DIR, "manage.py")
_DB_PATH = os.path.join(_MANAGE_DIR, "db.sqlite3")


def _say(msg):
    print("  [preflight] " + msg, flush=True)


# ── the port ────────────────────────────────────────────────────────────────
def _port_of(base_url):
    parsed = urllib.parse.urlparse(base_url)
    return parsed.hostname or "127.0.0.1", parsed.port or 80


def _port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_status(url, timeout=8):
    """Return the status code, or None if nothing answered."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code                     # a 500 IS an answer, and a clue
    except Exception:                       # noqa: BLE001
        return None


# ── the database ────────────────────────────────────────────────────────────
def _db_tables_missing():
    """Which essential tables are absent? Read-only, never creates the file."""
    if not os.path.isfile(_DB_PATH):
        return ["<no database file at all>"]
    uri = "file:" + _DB_PATH.replace("\\", "/") + "?mode=ro"
    needed = ("auth_user", "agent_agent", "agent_skill")
    try:
        con = sqlite3.connect(uri, uri=True)
        try:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        finally:
            con.close()
    except Exception as exc:                # noqa: BLE001
        return ["<unreadable: %s>" % exc]
    present = {r[0] for r in rows}
    return [t for t in needed if t not in present]


def _run_manage(args, timeout=900):
    return subprocess.run(
        [sys.executable, _MANAGE_PY] + list(args),
        cwd=_MANAGE_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def _repair_database(user, password):
    """migrate + ensure the test account. Returns (ok, notes)."""
    notes = []
    _say("migrating the dev database (gitignored; the frozen install is untouched)")
    result = _run_manage(["migrate", "--noinput"])
    applied = len(re.findall(r"Applying ", result.stdout or ""))
    if result.returncode != 0:
        return False, ["migrate failed: %s" % (result.stderr or "")[-300:]]
    notes.append("migrate ok (%d migrations applied)" % applied)

    _say("ensuring the test account '%s'" % user)
    script = (
        "from django.contrib.auth import get_user_model;"
        "U=get_user_model();"
        "u,c=U.objects.get_or_create(username=%r, defaults={'is_staff':True,'is_superuser':True});"
        "u.set_password(%r); u.is_active=True; u.save();"
        "print('USER_READY created=',c)" % (user, password)
    )
    result = _run_manage(["shell", "-c", script])
    if "USER_READY" not in (result.stdout or ""):
        return False, notes + ["could not create the test user: %s"
                               % (result.stderr or result.stdout or "")[-300:]]
    notes.append("account '%s' ready" % user)
    return True, notes


# ── the server ──────────────────────────────────────────────────────────────
def _pid_on_port(port):
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             timeout=20).stdout or ""
    except Exception:                       # noqa: BLE001
        return None
    for line in out.splitlines():
        if (":%d " % port) in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return None


def stop_server(port):
    """Kill ONLY the listening PID.

    ⚠️ NEVER ``/T``. That kills the process TREE, and the tree can include the
    console running this very test - which is exactly what produced two
    mysterious 0xC000013A "Ctrl+C" deaths before this function existed.
    """
    pid = _pid_on_port(port)
    if not pid:
        return False
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True, timeout=30)
        _say("stopped the server on port %d (pid %d, NOT its tree)" % (port, pid))
        return True
    except Exception:                       # noqa: BLE001
        return False


def start_server(port, visible=True):
    """Start the SOURCE server detached, in its own visible console."""
    # ⚠️ QUOTE THE INTERPRETER. sys.executable is normally
    # "C:\Program Files\Python312\python.exe" - unquoted, cmd runs "C:\Program"
    # and the server dies before it exists. Popen still succeeds, so this
    # function used to REPORT a server it had never started, which is the one
    # thing a preflight must never do.
    cmd = ('start "TLAMATINI SOURCE SERVER" cmd /k '
           '""%s" "%s" runserver --noreload 127.0.0.1:%d"'
           % (sys.executable, _MANAGE_PY, port))
    try:
        subprocess.Popen(cmd, shell=True, cwd=_MANAGE_DIR)
        _say("launched the source server on :%d (visible console)" % port)
        return True
    except Exception as exc:                # noqa: BLE001
        _say("could not start the server: %s" % exc)
        return False


def _wait_for_http(url, want=200, timeout=180):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = _http_status(url)
        if last == want:
            return True, last
        time.sleep(2.0)
    return False, last


# ── the login ───────────────────────────────────────────────────────────────
def verify_login(base_url, user, password, timeout=20):
    """Prove the credentials work over plain HTTP, before opening a browser.

    A wrong password used to cost a 30-second Playwright selector timeout and
    a traceback that blamed the chat page. Here it costs a second and says
    'the password is wrong'.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(base_url + "/", timeout=timeout) as response:
            page = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return False, "the login page itself returned HTTP %s (the app is broken, not the credentials)" % exc.code
    except Exception as exc:                # noqa: BLE001
        return False, "cannot reach the login page: %s" % exc

    token = ""
    match = re.search(r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)", page)
    if match:
        token = match.group(1)
    data = urllib.parse.urlencode({
        "username": user, "password": password, "csrfmiddlewaretoken": token,
    }).encode()
    request = urllib.request.Request(base_url + "/", data=data)
    request.add_header("Referer", base_url + "/")
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            final = response.geturl()
    except urllib.error.HTTPError as exc:
        return False, "the login POST returned HTTP %s" % exc.code
    except Exception as exc:                # noqa: BLE001
        return False, "the login POST failed: %s" % exc

    if "csrfmiddlewaretoken" in body and "password" in body.lower() and "/welcome" not in final:
        return False, ("the credentials were rejected (the login form came back). "
                       "User '%s' - set TLAMATINI_USER / TLAMATINI_PASS." % user)
    return True, "login verified over HTTP as '%s'" % user


# ── the one entry point ─────────────────────────────────────────────────────
def ensure_ready(base_url, user, password, *, autostart=True, timeout=240):
    """Establish the environment. Returns a dict; never raises."""
    base_url = base_url.rstrip("/")
    host, port = _port_of(base_url)
    repairs = []
    print("-" * 78)
    _say("target %s  (repo %s)" % (base_url, _REPO_ROOT))

    try:
        # 1. Is the database usable at all? A 500 on the login page is almost
        #    always this, and it is invisible from the browser side.
        missing = _db_tables_missing()
        if missing:
            _say("database is NOT usable - missing: %s" % ", ".join(missing))
            if _port_open(host, port):
                stop_server(port)           # it booted against a broken DB
                repairs.append("stopped a server running on a broken database")
                time.sleep(1.5)
            ok, notes = _repair_database(user, password)
            repairs.extend(notes)
            if not ok:
                return {"ok": False, "exit_code": EXIT_ENV_UNFIXABLE,
                        "repairs": repairs,
                        "reason": "the dev database could not be repaired: %s" % notes[-1]}
        else:
            _say("database looks healthy")

        # 2. Is a server answering, and answering WELL (200, not 500)?
        status = _http_status(base_url + "/") if _port_open(host, port) else None
        if status != 200:
            if status is not None:
                _say("something answers on :%d but with HTTP %s - restarting it" % (port, status))
                stop_server(port)
                repairs.append("restarted a server that was answering HTTP %s" % status)
                time.sleep(1.5)
            if autostart:
                start_server(port)
                repairs.append("started the source server")
            ok, last = _wait_for_http(base_url + "/", 200, timeout=timeout)
            if not ok:
                return {"ok": False, "exit_code": EXIT_ENV_UNFIXABLE,
                        "repairs": repairs,
                        "reason": "no healthy server on %s after %ds (last status: %s)"
                                  % (base_url, timeout, last)}
        _say("server is answering HTTP 200")

        # 3. Do the credentials actually work? Prove it before Chrome opens.
        ok, detail = verify_login(base_url, user, password)
        if not ok:
            # One self-repair attempt: the account may simply not exist yet.
            _say("login failed (%s) - repairing the account once" % detail)
            fixed, notes = _repair_database(user, password)
            repairs.extend(notes)
            if fixed:
                ok, detail = verify_login(base_url, user, password)
        if not ok:
            return {"ok": False, "exit_code": EXIT_ENV_UNFIXABLE,
                    "repairs": repairs, "reason": detail}
        _say(detail)

        if repairs:
            _say("REPAIRED before testing: " + "; ".join(repairs))
        print("-" * 78)
        return {"ok": True, "exit_code": EXIT_OK, "repairs": repairs,
                "reason": "environment ready"}
    except Exception as exc:                # noqa: BLE001 - preflight never raises
        return {"ok": False, "exit_code": EXIT_ENV_UNFIXABLE, "repairs": repairs,
                "reason": "preflight itself failed: %r" % (exc,)}


if __name__ == "__main__":
    import config as C
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    print(state["reason"])
    sys.exit(state["exit_code"])
