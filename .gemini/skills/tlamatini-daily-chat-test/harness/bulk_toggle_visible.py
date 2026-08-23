# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""VISIBLE proof of the SPACE-bar bulk checkbox toggle.

Angela, 2026-08-04. HEADED Chrome on the real desktop (never --headless), and
every photo is taken by Tlamatini's own SHOTER agent through ``toma_foto`` —
never PIL.

What it proves, in the REAL Configure-Mcps dialog:

  1. A REAL MOUSE DRAG across several checkbox labels (mouse.down / move / up —
     not a synthetic JS selection) followed by ONE press of SPACE unchecks
     EVERY checkbox the drag covered.
  2. The checkboxes the drag did NOT cover are left exactly as they were.
  3. Pressing SPACE again turns the SAME block back on (the rule is
     "any checked -> uncheck all; all unchecked -> check all").
  4. SPACE still types a space in a text field — the feature never steals it.

The password is read from .creds.env by this script; it is never printed.

⚠️ WHICH APP ANSWERS ON :8000 DECIDES WHETHER THIS CAN PASS. On 2026-08-04 that
port was served by the FROZEN install (C:\\Tlamatini\\Tlamatini.exe), which by
design does NOT carry a source-tree change until the next build — so this script
correctly reported "checkbox_bulk_toggle.js is loaded by the page: FAIL". Run it
against a server started FROM SOURCE (or after a rebuild). For a server-free
proof of the module itself, run bulk_toggle_behaviour.py instead.
"""
import datetime
import os
import sys
import time

sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright          # noqa: E402
from shoter_shot import take_shot                        # noqa: E402

BASE = "http://127.0.0.1:8000"
OUT = os.path.abspath(os.path.join(
    "reports", "bulk_toggle_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
os.makedirs(OUT, exist_ok=True)

USER = PASS = ""
for line in open(".creds.env", encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        key, value = line.split("=", 1)
        if key.strip() == "TLAMATINI_USER":
            USER = value.strip()
        if key.strip() == "TLAMATINI_PASS":
            PASS = value.strip()

failures = []


def check(label, ok, detail=""):
    print(("   OK   " if ok else "   FAIL ") + label + ("  " + detail if detail else ""))
    if not ok:
        failures.append(label + (" :: " + detail if detail else ""))


READ_STATE = """() => {
    const out = {};
    document.querySelectorAll('#tool-mcps-list input[type=checkbox]')
        .forEach(cb => { out[cb.id] = cb.checked; });
    return out;
}"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, channel="chrome",
                                 args=["--start-maximized"])
    page = browser.new_context(no_viewport=True).new_page()

    print("=" * 70)
    print("SPACE-BAR BULK TOGGLE — VISIBLE PROOF")
    print("=" * 70)

    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.fill("#id_username", USER)
    page.fill("#id_password", PASS)
    page.click("form button[type=submit]")
    page.wait_for_load_state("domcontentloaded")
    page.goto(BASE + "/agent/agent/", wait_until="domcontentloaded")
    page.wait_for_selector("#mcps-menu-button", timeout=30000)
    time.sleep(2.0)

    # The module must actually be on the page.
    loaded = page.evaluate(
        "() => !!Array.from(document.scripts)"
        ".find(s => (s.src || '').includes('checkbox_bulk_toggle.js'))")
    check("checkbox_bulk_toggle.js is loaded by the page", loaded)

    # ---- open Configure Mcps -------------------------------------------
    page.click("#mcps-menu-button")
    time.sleep(0.6)
    page.click("#enable-mcps")
    page.wait_for_selector("#tool-mcps-list input[type=checkbox]", timeout=20000)
    time.sleep(2.5)          # let loadTools() settle the real checked states
    page.bring_to_front()
    time.sleep(0.5)
    take_shot(OUT, "01_dialog_open.png")

    before = page.evaluate(READ_STATE)
    ids = list(before.keys())
    check("the dialog rendered its tool checkboxes", len(ids) > 6,
          "%d checkboxes" % len(ids))

    # ---- drag a REAL text selection across 5 labels ---------------------
    picked = ids[1:6]                      # skip the very first row
    untouched = [i for i in ids if i not in picked]

    boxes = page.evaluate("""(ids) => ids.map(id => {
        const lb = document.querySelector('label[for="' + id + '"]');
        const r = lb.getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom};
    })""", picked)
    first, last = boxes[0], boxes[-1]

    page.mouse.move(first["left"] + 2, (first["top"] + first["bottom"]) / 2)
    page.mouse.down()
    for step in range(1, 13):              # a human-speed sweep, not a teleport
        page.mouse.move(
            first["left"] + (last["right"] - first["left"]) * step / 12.0,
            (first["top"] + first["bottom"]) / 2
            + ((last["top"] + last["bottom"]) / 2 - (first["top"] + first["bottom"]) / 2)
            * step / 12.0)
        time.sleep(0.04)
    page.mouse.move(last["right"] - 2, (last["top"] + last["bottom"]) / 2)
    page.mouse.up()
    time.sleep(0.6)

    selected_text = page.evaluate("() => (window.getSelection() || '').toString().trim()")
    check("a real mouse drag produced a text selection", len(selected_text) > 0,
          repr(selected_text[:60]))
    take_shot(OUT, "02_labels_selected.png")

    # ---- ONE press of SPACE ---------------------------------------------
    page.keyboard.press(" ")
    time.sleep(0.9)
    after = page.evaluate(READ_STATE)
    take_shot(OUT, "03_after_space.png")

    was_any_checked = any(before[i] for i in picked)
    check("the selected block started out with checked boxes", was_any_checked)
    check("SPACE unchecked EVERY selected checkbox",
          all(after[i] is False for i in picked),
          str({i: after[i] for i in picked}))
    check("checkboxes OUTSIDE the selection were left alone",
          all(after[i] == before[i] for i in untouched))

    # ---- SPACE again turns the same block back on -----------------------
    page.keyboard.press(" ")
    time.sleep(0.9)
    again = page.evaluate(READ_STATE)
    take_shot(OUT, "04_after_second_space.png")
    check("a second SPACE re-checked the same block",
          all(again[i] is True for i in picked),
          str({i: again[i] for i in picked}))
    check("the untouched ones are STILL untouched",
          all(again[i] == before[i] for i in untouched))

    # ---- SPACE must still type a space in a text field ------------------
    page.keyboard.press("Escape")
    time.sleep(0.4)
    page.evaluate("""() => {
        const d = document.getElementById('mcps-dialog-message');
        if (d && window.jQuery && jQuery(d).hasClass('ui-dialog-content')) {
            jQuery(d).dialog('close');
        }
    }""")
    time.sleep(0.6)
    page.click("#chat-message-input")
    page.keyboard.type("hola")
    page.keyboard.press(" ")
    page.keyboard.type("mundo")
    time.sleep(0.4)
    typed = page.evaluate("() => document.getElementById('chat-message-input').value")
    check("SPACE still types a space in the chat box", typed.endswith("hola mundo"),
          repr(typed[-20:]))
    take_shot(OUT, "05_space_still_types.png")

    print("=" * 70)
    if failures:
        print("VERDICT: FAILURES (%d)" % len(failures))
        for f in failures:
            print("   - " + f)
    else:
        print("VERDICT: ALL GOOD — the space bar bulk-toggles the selected checkboxes.")
    print("photos: " + OUT)
    print("=" * 70)
    time.sleep(3)
    browser.close()

sys.exit(1 if failures else 0)
