# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
r"""
VISIBLE TEST — the "backend is down" banner in the ACP designer (ENGLISH)
========================================================================

WHAT IT ACTUALLY TESTS
    It kills the Tlamatini server FOR REAL, with the ACP designer open in a
    real Chrome, and demands that the red bar appear. Then it brings the server
    back and demands the bar turn green and hide itself.

    It does not inspect the file — it inspects the SCREEN. A test that merely
    grepped the .js would have passed even though the <script> was never
    included in the template (which is exactly the 2026-08-01 bug: the
    "already included?" check found the filename INSIDE the comment it had just
    inserted, and skipped the <script> tag).

ALWAYS VISIBLE (Angela's rule, non-negotiable)
    Real Chrome, headed. `--headless` is FORBIDDEN and this file refuses to run
    when it is passed. One FULL-SCREEN screenshot per step, taskbar clock in
    frame, so the timing can be checked afterwards.

IT NEVER LIES
    * It WAITS for the banner to really appear (with a timeout); it never assumes.
    * It checks the TEXT and the COLOUR (the -warning / -ok class), not just
      that the div exists.
    * It checks the language belongs to THIS tree and that the other language
      has not leaked in.
    * If the server cannot be started, it records FAILURE — it does not skip.

PASSWORD
    Read from .creds.env (gitignored) — never printed, never passed on a
    command line.

USAGE
    python acp_backend_banner_test.py
    python acp_backend_banner_test.py --port 8000
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import socket
import subprocess
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except Exception as exc:  # pragma: no cover
    print("!!! Playwright is required: %s" % exc)
    sys.exit(2)

# PIL.ImageGrab is FORBIDDEN (Angela, 2026-08-02): screenshots are
# taken by SHOTER, Tlamatini's own agent. See shoter_shot.py.
from shoter_shot import take_shot


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"C:\Development\Tlamatini"
DJANGO_DIR = os.path.join(ROOT, "Tlamatini")

# ── What THIS tree must say, and what it must never say ─────────────────────
LANGUAGE = "ENGLISH"
TEXT_DOWN = "Backend connection lost"
TEXT_BACK = "The backend is back"
TEXT_OTHER_LANGUAGE = "Se perdió la conexión con el backend"

SEL = {
    "user": "#id_username",
    "password": "<REDACTED>",
    "submit": "form button[type=submit]",
    "banner": "#connection-status",
    "canvas": "#agents-container",
}

BANNER_WAIT_S = 30        # the heartbeat is every 8 s; 30 is plenty of margin
RESULTS: list = []
SHOTS: list = []
OUT = ""
_PAGE = None


def log(m: str) -> None:
    print("[%s] %s" % (_dt.datetime.now().strftime("%H:%M:%S"), m), flush=True)


def shot(name: str) -> None:
    """FULL-DESKTOP screenshot — Chrome raised first, clock in frame."""
    global _PAGE
    if _PAGE is not None:
        try:
            _PAGE.bring_to_front()
            time.sleep(0.4)
        except Exception:
            pass
    path = os.path.join(OUT, "%02d_%s.png" % (len(SHOTS), name))
    take_shot(os.path.dirname(path), os.path.basename(path))
    SHOTS.append(os.path.basename(path))


def check(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"check": name, "pass": bool(ok), "detail": detail})
    log(("   PASS  " if ok else "   FAIL  ") + "%s — %s" % (name, detail))


def credentials() -> tuple:
    p = os.path.join(HERE, ".creds.env")
    u = c = ""
    if os.path.isfile(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            if k.strip() == "TLAMATINI_USER":
                u = v.strip()
            elif k.strip() == "TLAMATINI_PASS":
                c = v.strip()
    return u, c


# ── server control ──────────────────────────────────────────────────────────
def port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def start_server(port: int):
    """Start runserver in a VISIBLE console and return the Popen."""
    if port_open(port):
        log("server was already up")
        return None
    log("starting the server…")
    p = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "--noreload",
         "127.0.0.1:%d" % port],
        cwd=DJANGO_DIR,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    for _ in range(60):
        time.sleep(1)
        if port_open(port):
            log("server is up")
            return p
    log("!! the server did NOT come up")
    return p


def kill_server(port: int) -> bool:
    """Kill whoever holds the port. True when it is free."""
    log("KILLING the server (simulating the outage)…")
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=20).stdout
    except Exception:
        out = ""
    pids = set()
    for ln in out.splitlines():
        if ":%d " % port in ln and "LISTENING" in ln.upper():
            parts = ln.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                       capture_output=True)
    for _ in range(20):
        time.sleep(0.5)
        if not port_open(port):
            log("port free — the backend is down")
            return True
    log("!! could not kill the server")
    return False


# ── banner state, read off the SCREEN ───────────────────────────────────────
def banner_state(page) -> dict:
    try:
        return page.evaluate("""() => {
            const el = document.getElementById('connection-status');
            if (!el) { return {exists:false}; }
            const cl = el.className || '';
            const st = window.getComputedStyle(el);
            return {
                exists: true,
                text: (el.textContent || '').trim(),
                hidden: cl.indexOf('connection-status-hidden') >= 0,
                red:    cl.indexOf('connection-status-warning') >= 0,
                green:  cl.indexOf('connection-status-ok') >= 0,
                visible: st.display !== 'none'
            };
        }""")
    except Exception as exc:
        return {"exists": False, "error": str(exc)}


def wait_banner(page, want: str, limit=BANNER_WAIT_S) -> dict:
    """Really WAIT for the banner to reach the requested state."""
    t0 = time.time()
    last = {}
    while time.time() - t0 < limit:
        last = banner_state(page)
        if want == "red" and last.get("red") and last.get("visible"):
            return last
        if want == "green" and last.get("green") and last.get("visible"):
            return last
        if want == "hidden" and last.get("hidden"):
            return last
        time.sleep(0.5)
    return last


def main() -> int:
    global OUT, _PAGE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--headless", action="store_true",
                    help="FORBIDDEN — present only so the run can refuse")
    args = ap.parse_args()

    if args.headless:
        print("!!! HEADLESS IS FORBIDDEN IN THIS PROJECT. "
              "Tests are visible or they do not run.")
        return 2

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT = os.path.join(HERE, "reports", "acp_banner_en_%s" % stamp)
    os.makedirs(OUT, exist_ok=True)

    user, password = credentials()
    if not user or not password:
        log("!! TLAMATINI_USER / TLAMATINI_PASS not found in .creds.env")
        return 2

    print("=" * 74)
    print("  VISIBLE TEST — ACP backend-down banner  (%s)" % LANGUAGE)
    print("=" * 74)
    print("  tree    : %s" % ROOT)
    print("  port    : %d" % args.port)
    print("  user    : %s   (the password is NEVER printed)" % user)
    print("  report  : %s" % OUT)
    print("=" * 74)

    srv = start_server(args.port)
    if not port_open(args.port):
        check("server up before we start", False, "it did not come up")
        return 1

    base = "http://127.0.0.1:%d" % args.port
    with sync_playwright() as pw:
        # HEADED, real Chrome, on Angela's actual desktop.
        browser = pw.chromium.launch(headless=False, channel="chrome",
                                     args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        _PAGE = page
        try:
            # ── 1. log in and open the designer ─────────────────────────────
            page.goto(base + "/", wait_until="domcontentloaded")
            page.fill(SEL["user"], user)
            page.fill(SEL["password"], password)      # never printed
            page.click(SEL["submit"])
            page.wait_for_load_state("domcontentloaded")
            page.goto(base + "/agent/agentic_control_panel/",
                      wait_until="domcontentloaded")
            page.wait_for_selector(SEL["canvas"], timeout=20000)
            shot("01_acp_open")

            st = banner_state(page)
            check("banner exists in the DOM", bool(st.get("exists")),
                  "id=connection-status")
            check("starts HIDDEN", bool(st.get("hidden")),
                  "classes=%s" % ("hidden" if st.get("hidden") else st))

            # ── 2. kill the backend ─────────────────────────────────────────
            killed = kill_server(args.port)
            check("backend is down", killed, "port %d free" % args.port)

            st = wait_banner(page, "red")
            shot("02_backend_down")
            check("RED bar appears", bool(st.get("red") and st.get("visible")),
                  "text=%r" % (st.get("text", "")[:70]))
            check("text is correct (%s)" % LANGUAGE,
                  TEXT_DOWN in (st.get("text") or ""),
                  "expected %r" % TEXT_DOWN)
            check("does NOT carry the other language",
                  TEXT_OTHER_LANGUAGE not in (st.get("text") or ""),
                  "%r absent" % TEXT_OTHER_LANGUAGE)

            # ── 3. bring the backend back ───────────────────────────────────
            srv2 = start_server(args.port)
            check("backend is back", port_open(args.port),
                  "port %d listening" % args.port)

            st = wait_banner(page, "green")
            shot("03_backend_back")
            check("bar turns GREEN", bool(st.get("green")),
                  "text=%r" % (st.get("text", "")[:70]))
            check("announces recovery (%s)" % LANGUAGE,
                  TEXT_BACK in (st.get("text") or ""),
                  "expected %r" % TEXT_BACK)

            st = wait_banner(page, "hidden", limit=12)
            shot("04_bar_hidden")
            check("bar hides itself again", bool(st.get("hidden")),
                  "back to clean")

            for p in (srv, srv2):
                if p is not None:
                    try:
                        p.kill()
                    except Exception:
                        pass
        except Exception as exc:
            check("the test ran without blowing up", False, str(exc)[:200])
            shot("99_error")
        finally:
            try:
                time.sleep(2)
                ctx.close()
                browser.close()
            except Exception:
                pass

    failures = [r for r in RESULTS if not r["pass"]]
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
        json.dump({"language": LANGUAGE, "tree": ROOT, "checks": RESULTS,
                   "shots": SHOTS}, fh, ensure_ascii=False, indent=2)

    print("=" * 74)
    print("  %d of %d checks PASS" % (len(RESULTS) - len(failures), len(RESULTS)))
    for f in failures:
        print("   FAIL: %s — %s" % (f["check"], f["detail"]))
    print("  shots   : %d in %s" % (len(SHOTS), OUT))
    print("  VERDICT : %s" % ("ALL GOOD" if not failures else "FAILURES"))
    print("=" * 74)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
