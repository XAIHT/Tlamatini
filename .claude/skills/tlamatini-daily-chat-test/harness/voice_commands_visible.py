# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
r"""VISIBLE proof that the **VOICE COMMANDS** catalog section is GONE (v1.96.1).

History: on 2026-09-12 the Catalog of Prompts gained a VOICE COMMANDS section
(prompts #121 YOUR FIRST VOICE COMMAND and #122 SPEAK YOUR PROMPT). On
2026-11-21 Angela removed it, because the microphone button beside Send does
the same job directly. ``views.PROMPT_CATEGORY_ORDER`` no longer lists
``voice_commands``, and a migration (0226 in Tlamatini, 0228 in
Tlamatini-Spanish) hides the two cards without renumbering them. This runner
used to prove the section existed; it now proves the opposite.

HEADED Chrome on Angela's real desktop — never ``--headless``, per the standing
rule — and every photo is taken by Tlamatini's own **SHOTER** agent through
``take_shot``, never PIL.

WHAT IT PROVES, in the REAL Catalog-of-Prompts modal:

  1. ``/agent/list_prompts/`` serves no ``voice_commands`` section and neither
     prompt #121 nor #122, and its first section is Getting Started.
  2. The modal on screen has no VOICE COMMANDS header, its FIRST header is
     Getting Started, and cards #121 and #122 are not in the DOM.
  3. Searching "voice" in the catalog finds neither card.
  4. The microphone button that replaced the section sits beside Send.

⚠️ WHICH APP ANSWERS ON :8000 DECIDES WHAT THIS CAN SAY.
    * If the server still serves a ``voice_commands`` section, it is running
      code older than v1.96.1 (usually the FROZEN install before its update).
      The runner stops with exit code 3 and reports neither a pass nor a fail.
    * If the code is new but #121/#122 still appear (under "More"), the
      database has not been migrated. That is a real FAIL, and the message says
      to run ``python Tlamatini/manage.py migrate``.

RUN IT (from this directory, in a VISIBLE foreground window):
    set TLAMATINI_USER=angela
    set TLAMATINI_PASS=...          (or put both in .creds.env beside this file)
    python voice_commands_visible.py
"""
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from playwright.sync_api import sync_playwright          # noqa: E402
from shoter_shot import take_shot                        # noqa: E402

BASE = os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
OUT = os.path.join(
    HERE, "reports",
    "voice_commands_removed_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
os.makedirs(OUT, exist_ok=True)

SECTION_KEY = "voice_commands"
FIRST_KEY = "getting_started"
REMOVED_IDS = (121, 122)
REMOVED_CARDS = tuple("prompt-%d" % i for i in REMOVED_IDS)

# ── credentials: env first, then .creds.env beside this file. Never printed. ──
USER = os.environ.get("TLAMATINI_USER", "")
PASS = os.environ.get("TLAMATINI_PASS", "")
_creds = os.path.join(HERE, ".creds.env")
if (not USER or not PASS) and os.path.isfile(_creds):
    for line in open(_creds, encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            if key.strip() == "TLAMATINI_USER" and not USER:
                USER = value.strip()
            if key.strip() == "TLAMATINI_PASS" and not PASS:
                PASS = value.strip()
if not USER or not PASS:
    print("!! No credentials. Set TLAMATINI_USER / TLAMATINI_PASS, or put them "
          "in .creds.env beside this script. Refusing to guess.")
    sys.exit(2)

checks = []          # (label, ok, detail) — every one photographed in SUMMARY
failures = []
shots = []           # (caption, filename)


def check(label, ok, detail=""):
    print(("   OK   " if ok else "   FAIL ") + label + ("  " + detail if detail else ""))
    checks.append((label, bool(ok), detail))
    if not ok:
        failures.append(label + (" :: " + detail if detail else ""))


def shot(page, name, caption):
    try:
        page.bring_to_front()
    except Exception:
        pass
    time.sleep(0.35)
    path = take_shot(OUT, name)          # SHOTER takes every photo. Never PIL.
    shots.append((caption, name if path else ""))
    if not path:
        print("   !! Shoter left no photo for " + name)


# ── what the DOM says about the catalog, read in ONE pass ────────────────────
_READ_CATALOG = """(ids) => {
    const body = document.getElementById('tools-body');
    const headers = Array.from(body.querySelectorAll('.prompt-category-header'));
    const sections = headers.map((h) => {
        const lab = h.querySelector('.prompt-category-label');
        return {key: h.dataset.category || '', label: lab ? lab.textContent : ''};
    });
    const removedPresent = ids.filter((id) => !!document.getElementById(id));
    const voiceTitles = Array.from(body.querySelectorAll('.prompt-card-title'))
        .map((t) => t.textContent || '')
        .filter((t) => /VOICE COMMAND|SPEAK YOUR PROMPT/i.test(t));
    return {sections: sections, removedPresent: removedPresent, voiceTitles: voiceTitles,
            cards: body.querySelectorAll('.prompt-card').length};
}"""


def open_catalog(page):
    page.click("#prompts-catalog")
    page.wait_for_selector("#tools-body .prompt-category-header", timeout=20000)
    time.sleep(1.2)                      # let every card render + bind


def main():
    print("=" * 74)
    print("VOICE COMMANDS REMOVED FROM THE CATALOG — VISIBLE PROOF (headed Chrome)")
    print("target: " + BASE + "   ·   photos by SHOTER -> " + OUT)
    print("=" * 74)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, channel="chrome",
                                     args=["--start-maximized"])
        page = browser.new_context(no_viewport=True).new_page()

        # ---- log in ----------------------------------------------------
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("form button[type=submit]")
        page.wait_for_load_state("domcontentloaded")
        page.goto(BASE + "/agent/agent/", wait_until="domcontentloaded")
        page.wait_for_selector("#prompts-catalog", timeout=30000)
        time.sleep(2.0)

        # ---- 1. what the server serves ---------------------------------
        served = page.evaluate("""async () => {
            const r = await fetch('/agent/list_prompts/', {credentials: 'same-origin'});
            if (!r.ok) return {error: 'HTTP ' + r.status};
            const p = await r.json();
            return {keys: (p.categories || []).map((c) => c.key),
                    ids: (p.prompts || []).map((x) => x.index),
                    count: (p.prompts || []).length};
        }""")
        if served.get("error"):
            print("!! /agent/list_prompts/ answered " + served["error"] + ". Cannot judge.")
            browser.close()
            return 3
        keys = served.get("keys") or []
        if SECTION_KEY in keys:
            shot(page, "00_old_server.png",
                 "the server on :8000 still serves a VOICE COMMANDS section")
            print("")
            print("!! The app answering %s still serves 'voice_commands'." % BASE)
            print("!! It runs code older than v1.96.1 (usually the FROZEN install before")
            print("!! its update). Start the source server, or update the install, and")
            print("!! run again. NOT reporting a pass or a fail on the removal.")
            browser.close()
            return 3
        check("the server serves no 'voice_commands' section", True,
              "%d sections, %s prompts" % (len(keys), served.get("count")))
        leftovers = [i for i in REMOVED_IDS if i in (served.get("ids") or [])]
        check("the server serves neither prompt #121 nor #122", not leftovers,
              ("still served: %s -> run python Tlamatini/manage.py migrate" % leftovers)
              if leftovers else "")
        check("the first section served is Getting Started",
              bool(keys) and keys[0] == FIRST_KEY, "first=%r" % (keys[0] if keys else None))

        # ---- 2. the modal on screen ------------------------------------
        open_catalog(page)
        shot(page, "01_catalog_open.png",
             "Catalog of prompts open — it starts with Getting Started")
        cat = page.evaluate(_READ_CATALOG, list(REMOVED_CARDS))
        sections = cat["sections"]
        check("the catalog rendered its sections", len(sections) > 5,
              "%d sections, %d cards" % (len(sections), cat["cards"]))
        check("no VOICE COMMANDS header is on screen",
              SECTION_KEY not in [s["key"] for s in sections])
        check("the FIRST header on screen is Getting Started",
              bool(sections) and sections[0]["key"] == FIRST_KEY,
              "got key=%r label=%r" % ((sections[0]["key"], sections[0]["label"])
                                         if sections else (None, None)))
        check("cards #121 and #122 are not in the catalog",
              not cat["removedPresent"], str(cat["removedPresent"]))
        check("no card is titled VOICE COMMAND / SPEAK YOUR PROMPT",
              not cat["voiceTitles"], str(cat["voiceTitles"]))

        # ---- 3. the live search finds neither card ---------------------
        page.fill("#prompt-search-input", "voice")
        time.sleep(1.0)
        visible_removed = page.evaluate("""(ids) => ids.filter((id) => {
            const c = document.getElementById(id);
            return c && !c.classList.contains('prompt-card-hidden');
        })""", list(REMOVED_CARDS))
        shot(page, "02_search_voice.png", "searching 'voice' — neither removed card appears")
        check("searching 'voice' shows neither #121 nor #122",
              not visible_removed, str(visible_removed))
        page.fill("#prompt-search-input", "")
        time.sleep(0.6)
        page.keyboard.press("Escape")
        time.sleep(0.6)

        # ---- 4. the microphone button that replaced it -----------------
        mic = page.evaluate("""() => {
            const m = document.getElementById('chat-microphone');
            const s = document.getElementById('chat-message-submit');
            if (!m) return {present: false};
            const r = m.getBoundingClientRect();
            return {present: true, visible: r.width > 0 && r.height > 0,
                    beforeSend: !!(s && (m.compareDocumentPosition(s)
                                         & Node.DOCUMENT_POSITION_FOLLOWING))};
        }""")
        shot(page, "03_microphone_beside_send.png",
             "catalog closed — the microphone button beside Send replaces the section")
        check("the microphone button is on the page", mic.get("present"), str(mic))
        check("the microphone button is visible", mic.get("visible"))
        check("the microphone button sits right before Send", mic.get("beforeSend"))

        build_summary()
        print("=" * 74)
        if failures:
            print("VERDICT: FAILURES (%d)" % len(failures))
            for f in failures:
                print("   - " + f)
        else:
            print("VERDICT: ALL GOOD — VOICE COMMANDS is gone, the catalog opens with")
            print("         Getting Started, and the microphone sits beside Send.")
        print("photos + SUMMARY.html: " + OUT)
        print("=" * 74)
        time.sleep(3)
        browser.close()

    return 1 if failures else 0


def build_summary():
    import html as _h
    rows = []
    for label, ok, detail in checks:
        rows.append(
            "<tr><td style='color:%s;font-weight:700'>%s</td><td>%s</td>"
            "<td class='s'>%s</td></tr>"
            % ("#1e8e3e" if ok else "#c5221f", "OK" if ok else "FAIL",
               _h.escape(label), _h.escape(detail)))
    pics = []
    for caption, name in shots:
        if not name:
            pics.append("<div class='sc'><b>%s</b><div class='s'>SHOTER left no "
                        "photo for this step</div></div>" % _h.escape(caption))
            continue
        pics.append("<div class='sc'><b>%s</b><a href='%s' target='_blank'>"
                    "<img loading='lazy' src='%s'></a></div>"
                    % (_h.escape(caption), name, name))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    doc = (
        "<!doctype html><meta charset='utf-8'><title>VOICE COMMANDS removed — visible evidence</title>"
        "<style>body{font:14px/1.5 Segoe UI,Arial,sans-serif;margin:0;background:#0f1420;"
        "color:#e8ecf3}.top{background:#131a2b;padding:14px 20px;border-bottom:2px solid #2a3550}"
        "h1{margin:0 0 4px;font-size:19px}.sc{background:#182135;border:1px solid #26324e;"
        "border-radius:10px;margin:16px;padding:12px 14px}img{max-width:760px;width:100%%;"
        "border:1px solid #33405f;border-radius:6px;display:block;margin:8px 0}"
        ".s{color:#a7b3c9;font-size:12.5px}table{border-collapse:collapse;margin:16px}"
        "td{border-bottom:1px solid #26324e;padding:5px 12px;vertical-align:top}</style>"
        "<div class='top'><h1>Tlamatini — VOICE COMMANDS removed from the catalog · "
        "VISIBLE browser evidence</h1>"
        "<div class='s'>headed Chrome on the real desktop · every photo taken by the SHOTER agent "
        "(never PIL) · %s · %d checks, %d failed</div></div>"
        "<table>%s</table>%s"
        % (_h.escape(now), len(checks), len(failures), "".join(rows), "".join(pics))
    )
    with open(os.path.join(OUT, "SUMMARY.html"), "w", encoding="utf-8") as fh:
        fh.write(doc)
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
        json.dump({"checks": [{"label": a, "ok": b, "detail": c} for a, b, c in checks],
                   "failures": failures}, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
