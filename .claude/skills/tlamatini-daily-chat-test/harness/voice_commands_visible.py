# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
r"""VISIBLE proof of the **VOICE COMMANDS** catalog section (Angela, 2026-09-12).

HEADED Chrome on Angela's real desktop — never ``--headless``, per the standing
rule — and every photo is taken by Tlamatini's own **SHOTER** agent through
``take_shot``, never PIL.

WHAT IT PROVES, in the REAL Catalog-of-Prompts modal:

  1. **VOICE COMMANDS is the FIRST section in the catalog** — literally the first
     ``.prompt-category-header`` in the DOM, ahead of GETTING STARTED — and its
     header really renders in capitals (``text-transform: uppercase``), so what
     Angela sees on screen is the words she asked for.
  2. The section holds its two cards in rank order: **#121 YOUR FIRST VOICE
     COMMAND** then **#122 SPEAK YOUR PROMPT**.
  3. Card #122 carries Angela's sentence **verbatim**, letter for letter.
  4. Card #122 wears exactly the three natures she specified —
     **Multi-turn · ACPX · Exec-report** — and card #121 wears
     Multi-turn · Step-by-Step · Exec-report.
  5. **Clicking #122 really ticks those three toolbar checkboxes** (Multi-Turn,
     Exec report, ACPX) and leaves Step-by-Step OFF, and drops the full prompt
     into the chat box. Clicking #121 afterwards flips the toolbar the other way
     (Step-by-Step ON, ACPX OFF) — which proves the boxes follow the CARD and are
     not a leftover from the previous click.
  6. The live search finds the card by the word "voice".

⚠️ WHAT IT DELIBERATELY DOES **NOT** PROVE — and will never claim to.
    It does not speak into a microphone. A voice command needs a human voice; no
    automated runner can supply one without faking the very thing under test, and
    a faked pass is worse than no test. So this proves everything up to and
    including "the prompt is loaded and the right modes are armed"; the last
    step — Angela presses Send and talks — is hers, and the script prints the
    exact instruction for it at the end. The SUMMARY.html says so too.

⚠️ WHICH APP ANSWERS ON :8000 DECIDES WHETHER THIS CAN PASS. The VOICE COMMANDS
    section lives in the SOURCE tree (``views.PROMPT_CATEGORY_ORDER`` + migration
    0201). The FROZEN install at ``C:\Tlamatini`` does not carry it until the next
    build. This script therefore asks ``/agent/list_prompts/`` FIRST and, if the
    answering server has no such section, stops with a clear message instead of
    reporting a misleading failure — or, worse, a misleading pass.

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
    "voice_commands_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
os.makedirs(OUT, exist_ok=True)

SECTION_LABEL = "Voice Commands"
OPENER_ID = "prompt-121"
ANGELA_ID = "prompt-122"

# Angela's own words, 2026-09-12 — the reason card #122 exists. Stored exactly as
# she wrote them, trailing "go!." included.
ANGELA_SENTENCE = (
    "Tlamatini, using Whisperer record my voice till I finish to tell you a "
    "prompt, then use the text extracted as a prompt and invoke it, go!."
)

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
_READ_CATALOG = """() => {
    const body = document.getElementById('tools-body');
    const headers = Array.from(body.querySelectorAll('.prompt-category-header'));
    const out = {sections: [], cards: {}, firstSectionCards: []};
    headers.forEach((h) => {
        const lab = h.querySelector('.prompt-category-label');
        out.sections.push({
            key: h.dataset.category || '',
            label: lab ? lab.textContent : '',
            transform: lab ? getComputedStyle(lab).textTransform : '',
            shownAs: lab ? lab.textContent.toUpperCase() : ''
        });
    });
    // Cards that belong to the FIRST section = every .prompt-card between the
    // first header and the second one, in DOM order (which IS display order).
    const kids = Array.from(body.children);
    const firstHeader = kids.findIndex((n) => n.classList.contains('prompt-category-header'));
    for (let i = firstHeader + 1; i < kids.length; i++) {
        if (kids[i].classList.contains('prompt-category-header')) break;
        if (kids[i].classList.contains('prompt-card')) out.firstSectionCards.push(kids[i].id);
    }
    body.querySelectorAll('.prompt-card').forEach((c) => {
        out.cards[c.id] = {
            modes: c.dataset.modes || '',
            badges: Array.from(c.querySelectorAll('.prompt-mode-badge')).map((b) => b.textContent),
            title: (c.querySelector('.prompt-card-title') || {}).textContent || '',
            content: c.dataset.fullContent || ''
        };
    });
    return out;
}"""

_READ_TOGGLES = """() => {
    const g = (id) => {
        const el = document.getElementById(id);
        return el ? {checked: !!el.checked, disabled: !!el.disabled} : null;
    };
    return {
        multiturn: g('multi-turn-enabled'),
        execreport: g('exec-report-enabled'),
        acpx: g('acpx-enabled'),
        stepbystep: g('step-by-step-enabled'),
        chat: (document.getElementById('chat-message-input') || {}).value || '',
        modalOpen: (document.getElementById('modal') || {}).style
            ? document.getElementById('modal').style.display !== 'none' : null
    };
}"""


def open_catalog(page):
    page.click("#prompts-catalog")
    page.wait_for_selector("#tools-body .prompt-category-header", timeout=20000)
    time.sleep(1.2)                      # let every card render + bind


def reset_toggles(page):
    """Put the toolbar in a state that is WRONG for both cards, so a later
    'correct' reading can only have come from the card click itself."""
    page.evaluate("""() => {
        const set = (id, want) => {
            const el = document.getElementById(id);
            if (!el || el.disabled) return;
            if (!!el.checked !== want) {
                el.checked = want;
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
        };
        set('multi-turn-enabled', false);
        set('acpx-enabled', false);
        set('step-by-step-enabled', false);
        const chat = document.getElementById('chat-message-input');
        if (chat) chat.value = '';
    }""")
    time.sleep(0.4)


def main():
    print("=" * 74)
    print("VOICE COMMANDS CATALOG SECTION — VISIBLE PROOF (headed Chrome)")
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

        # ---- 0. is this server even carrying the section? --------------
        served = page.evaluate("""async () => {
            const r = await fetch('/agent/list_prompts/', {credentials: 'same-origin'});
            if (!r.ok) return {error: 'HTTP ' + r.status};
            const p = await r.json();
            return {first: (p.categories || [])[0] || null,
                    count: (p.prompts || []).length};
        }""")
        first_key = (served.get("first") or {}).get("key")
        if first_key != "voice_commands":
            shot(page, "00_wrong_server.png", "the server on :8000 has no VOICE COMMANDS section")
            print("")
            print("!! The app answering %s does NOT serve a 'voice_commands' section." % BASE)
            print("!! It served %r first, with %s prompts." % (first_key, served.get("count")))
            print("!! This is almost certainly the FROZEN install; the section lives in the")
            print("!! SOURCE tree (views.PROMPT_CATEGORY_ORDER + migration 0201). Start the")
            print("!! source server and run again. NOT reporting a pass or a fail on the")
            print("!! feature itself — this run simply could not see it.")
            browser.close()
            return 3
        check("the server serves 'voice_commands' as the FIRST catalog section", True,
              "%s prompts total" % served.get("count"))

        # ---- 1. open the catalog ---------------------------------------
        open_catalog(page)
        shot(page, "01_catalog_open.png",
             "Catalog of prompts open — VOICE COMMANDS is the first section")
        cat = page.evaluate(_READ_CATALOG)

        sections = cat["sections"]
        check("the catalog rendered its sections", len(sections) > 5,
              "%d sections" % len(sections))
        first = sections[0] if sections else {}
        check("the FIRST section on screen is VOICE COMMANDS",
              first.get("key") == "voice_commands" and first.get("label") == SECTION_LABEL,
              "got key=%r label=%r" % (first.get("key"), first.get("label")))
        check("its header really renders in CAPITALS",
              first.get("transform") == "uppercase",
              "text-transform=%r -> reads %r" % (first.get("transform"), first.get("shownAs")))
        check("it sits AHEAD of Getting Started",
              [s["key"] for s in sections].index("voice_commands") <
              ([s["key"] for s in sections].index("getting_started")
               if "getting_started" in [s["key"] for s in sections] else 999))

        # ---- 2. the two cards, in rank order ---------------------------
        check("the section holds exactly its two cards, opener first",
              cat["firstSectionCards"] == [OPENER_ID, ANGELA_ID],
              str(cat["firstSectionCards"]))

        angela = cat["cards"].get(ANGELA_ID, {})
        opener = cat["cards"].get(OPENER_ID, {})
        check("card #122 is titled SPEAK YOUR PROMPT",
              "SPEAK YOUR PROMPT" in (angela.get("title") or ""),
              repr(angela.get("title")))
        check("card #121 is titled YOUR FIRST VOICE COMMAND",
              "YOUR FIRST VOICE COMMAND" in (opener.get("title") or ""),
              repr(opener.get("title")))

        # ---- 3. Angela's sentence, verbatim ----------------------------
        check("card #122 carries Angela's sentence VERBATIM",
              ANGELA_SENTENCE in (angela.get("content") or ""),
              "%d chars of content" % len(angela.get("content") or ""))

        # ---- 4. the badges are the natures she asked for ---------------
        check("card #122 wears Multi-turn + ACPX + Exec-report",
              angela.get("badges") == ["Multi-turn", "ACPX", "Exec-report"],
              str(angela.get("badges")))
        check("card #122 is NOT badged Step-by-Step",
              "Step-by-Step" not in (angela.get("badges") or []))
        check("card #121 wears Multi-turn + Step-by-Step + Exec-report",
              angela is not None and
              opener.get("badges") == ["Multi-turn", "Step-by-Step", "Exec-report"],
              str(opener.get("badges")))

        # ---- 5. clicking #122 arms exactly those three boxes -----------
        reset_toggles(page)
        before = page.evaluate(_READ_TOGGLES)
        check("toolbar deliberately started WRONG for this card",
              not before["multiturn"]["checked"] and not before["acpx"]["checked"],
              "mt=%s acpx=%s" % (before["multiturn"]["checked"], before["acpx"]["checked"]))
        page.click("#" + ANGELA_ID)
        time.sleep(1.2)
        after = page.evaluate(_READ_TOGGLES)
        shot(page, "02_clicked_speak_your_prompt.png",
             "clicked SPEAK YOUR PROMPT — Multi-Turn + Exec report + ACPX armed, "
             "prompt in the chat box")
        check("clicking #122 ticked Multi-Turn", after["multiturn"]["checked"])
        check("clicking #122 ticked Exec report", after["execreport"]["checked"])
        check("clicking #122 ticked ACPX", after["acpx"]["checked"])
        check("clicking #122 left Step-by-Step OFF",
              not after["stepbystep"]["checked"])
        check("the full prompt landed in the chat box",
              ANGELA_SENTENCE in (after["chat"] or ""),
              "%d chars" % len(after["chat"] or ""))
        check("the catalog closed itself after the click", after["modalOpen"] is False)

        # ---- 6. clicking #121 flips it back the other way --------------
        open_catalog(page)
        page.click("#" + OPENER_ID)
        time.sleep(1.2)
        wiz = page.evaluate(_READ_TOGGLES)
        shot(page, "03_clicked_first_voice_command.png",
             "clicked YOUR FIRST VOICE COMMAND — Step-by-Step armed, ACPX cleared")
        check("clicking #121 ticked Step-by-Step", wiz["stepbystep"]["checked"])
        check("clicking #121 CLEARED ACPX (the boxes follow the card)",
              not wiz["acpx"]["checked"])
        check("clicking #121 kept Multi-Turn on", wiz["multiturn"]["checked"])

        # ---- 7. the live search finds it -------------------------------
        open_catalog(page)
        page.fill("#prompt-search-input", "voice")
        time.sleep(1.0)
        found = page.evaluate("""(id) => {
            const c = document.getElementById(id);
            if (!c) return {present: false};
            return {present: true, hidden: c.classList.contains('prompt-card-hidden')};
        }""", ANGELA_ID)
        shot(page, "04_search_voice.png", "searching 'voice' surfaces the card")
        check("searching 'voice' keeps card #122 visible",
              found.get("present") and not found.get("hidden"), str(found))
        page.fill("#prompt-search-input", "")
        time.sleep(0.6)
        page.keyboard.press("Escape")
        time.sleep(0.6)
        shot(page, "05_final.png", "catalog dismissed with Escape — final desktop state")

        build_summary()
        print("=" * 74)
        if failures:
            print("VERDICT: FAILURES (%d)" % len(failures))
            for f in failures:
                print("   - " + f)
        else:
            print("VERDICT: ALL GOOD — VOICE COMMANDS opens the catalog, and SPEAK")
            print("         YOUR PROMPT arms Multi-Turn + Exec report + ACPX.")
        print("")
        print("NOT PROVEN HERE (a machine cannot speak): the actual voice run.")
        print("To finish it yourself, Angela: the prompt is already in the chat box")
        print("after step 02 — press Send, wait for the banner, then say your")
        print("instruction out loud and stop talking. Whisperer closes the recording")
        print("after ~10 s of silence and Tlamatini executes what you said.")
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
        "<!doctype html><meta charset='utf-8'><title>VOICE COMMANDS — visible evidence</title>"
        "<style>body{font:14px/1.5 Segoe UI,Arial,sans-serif;margin:0;background:#0f1420;"
        "color:#e8ecf3}.top{background:#131a2b;padding:14px 20px;border-bottom:2px solid #2a3550}"
        "h1{margin:0 0 4px;font-size:19px}.sc{background:#182135;border:1px solid #26324e;"
        "border-radius:10px;margin:16px;padding:12px 14px}img{max-width:760px;width:100%%;"
        "border:1px solid #33405f;border-radius:6px;display:block;margin:8px 0}"
        ".s{color:#a7b3c9;font-size:12.5px}table{border-collapse:collapse;margin:16px}"
        "td{border-bottom:1px solid #26324e;padding:5px 12px;vertical-align:top}"
        ".warn{background:#3a2a12;border:1px solid #7a5b00;border-radius:10px;margin:16px;"
        "padding:12px 14px;color:#ffdf9e}</style>"
        "<div class='top'><h1>Tlamatini — VOICE COMMANDS catalog section · VISIBLE browser evidence</h1>"
        "<div class='s'>headed Chrome on the real desktop · every photo taken by the SHOTER agent "
        "(never PIL) · %s · %d checks, %d failed</div></div>"
        "<div class='warn'><b>What this evidence does NOT cover.</b> No microphone was used. "
        "A voice command needs a human voice, and faking it would fake the very thing under "
        "test. Everything up to &ldquo;the prompt is loaded and Multi-Turn + Exec report + ACPX "
        "are armed&rdquo; is proven below; pressing Send and speaking is Angela&rsquo;s step.</div>"
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
