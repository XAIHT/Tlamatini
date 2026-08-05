# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""BEHAVIOURAL proof of the SPACE-bar bulk checkbox toggle, in a REAL browser.

Angela, 2026-08-04. HEADED Chrome on the real desktop (never --headless);
every photo is taken by Tlamatini's own SHOTER agent — never PIL.

WHY THIS EXISTS SEPARATELY FROM bulk_toggle_visible.py
    bulk_toggle_visible.py drives the live app on :8000. That port is served by
    the FROZEN install (C:\\Tlamatini\\Tlamatini.exe), which does not carry a
    source-tree change until the next build — so it cannot prove a brand-new
    module. This script instead loads the REAL, SHIPPED
    static/agent/js/checkbox_bulk_toggle.js into a real Chrome page and drives
    it with REAL MOUSE DRAGS and REAL key presses over faithful replicas of the
    three DOM shapes the app actually renders:

      A. Configure Mcps / Agents  -> ul > li > div(flex) > input + label[for]
      B. Configure Skills         -> ul > li > input + label[for] > span + span
      C. External MCPs            -> .emx-row[data-key] > input.emx-cb (which is
                                     pointer-events:none and DECORATIVE) with a
                                     container click handler that mutates a model
                                     and RE-RENDERS every row on each toggle.

    Shape C is the one that can silently break: after the first toggle the
    original elements are detached, so a naive implementation would click a
    dead node and lose every remaining change.
"""
import datetime
import os
import sys
import time

sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright          # noqa: E402
from shoter_shot import take_shot                        # noqa: E402

MODULE = (r"C:\Development\Tlamatini\Tlamatini\agent\static\agent\js"
          r"\checkbox_bulk_toggle.js")

OUT = os.path.abspath(os.path.join(
    "reports", "bulk_behaviour_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
os.makedirs(OUT, exist_ok=True)

failures = []


def check(label, ok, detail=""):
    print(("   OK   " if ok else "   FAIL ") + label + ("   " + detail if detail else ""))
    if not ok:
        failures.append(label + (" :: " + detail if detail else ""))


PAGE = """
<!doctype html><html><head><meta charset="utf-8"><style>
 body{font-family:sans-serif;background:#2b2b2b;color:#eee;margin:18px}
 h3{margin:18px 0 6px}
 ul{list-style:none;padding:0;margin:0}
 li{margin:2px 0}
 .emx-row{padding:4px;border:1px solid #444;margin:2px 0}
 .emx-cb{pointer-events:none}
 .toolbar-toggle{user-select:none}
</style></head><body>

<h3>A - Mcps / Agents shape</h3>
<ul id="tool-mcps-list"></ul>

<h3>B - Skills shape</h3>
<ul id="skills-configure-list"></ul>

<h3>C - External MCPs shape (model-driven, re-renders on every toggle)</h3>
<div id="external-mcps-list"></div>

<h3>D - a dialog that also has a text box</h3>
<input id="search-box" type="text" value="">

<h3>E - toolbar toggle (user-select:none, must be unreachable)</h3>
<span class="toolbar-toggle"><input id="multi-turn-enabled" type="checkbox" checked>
<label for="multi-turn-enabled">Multi-Turn</label></span>

<script>
 // --- A: the Configure-Mcps DOM, built exactly like agent_page_dialogs.js ---
 const listA = document.getElementById('tool-mcps-list');
 for (let i = 1; i <= 10; i++) {
   const li = document.createElement('li');
   const wrap = document.createElement('div');
   wrap.style.display = 'flex';
   const cb = document.createElement('input');
   cb.type = 'checkbox'; cb.id = 'tool-' + i; cb.checked = true;
   const lb = document.createElement('label');
   lb.htmlFor = cb.id; lb.id = 'label-' + cb.id; lb.innerText = 'Chat-Agent-Number-' + i;
   wrap.appendChild(cb); wrap.appendChild(lb); li.appendChild(wrap); listA.appendChild(li);
 }
 // one deliberately UNCHECKED box inside the block we will drag over,
 // so we prove the "any checked -> uncheck ALL" rule on a MIXED block.
 document.getElementById('tool-4').checked = false;

 // --- B: the Configure-Skills DOM, built like skills_dialog.js -------------
 const listB = document.getElementById('skills-configure-list');
 ['acp-router', 'security-audit', 'flow-making', 'summarize'].forEach(n => {
   const li = document.createElement('li');
   const cb = document.createElement('input');
   cb.type = 'checkbox'; cb.id = 'skill-checkbox-' + n; cb.checked = true;
   const lb = document.createElement('label');
   lb.setAttribute('for', cb.id);
   const a = document.createElement('span'); a.textContent = n;
   const b = document.createElement('span'); b.textContent = ' - a skill description';
   lb.appendChild(a); lb.appendChild(b);
   li.appendChild(cb); li.appendChild(lb); listB.appendChild(li);
 });

 // --- C: the External-MCPs DOM: model is the truth, rows are rebuilt ------
 window.servers = [
   {key: 'alpha',   display: 'Alpha Server',   active: true},
   {key: 'bravo',   display: 'Bravo Server',   active: true},
   {key: 'charlie', display: 'Charlie Server', active: true},
   {key: 'delta',   display: 'Delta Server',   active: true}
 ];
 const listC = document.getElementById('external-mcps-list');
 window.renderC = function () {
   listC.innerHTML = '';
   for (const s of window.servers) {
     const row = document.createElement('div');
     row.className = 'emx-row';
     row.dataset.key = s.key;
     row.setAttribute('role', 'checkbox');
     row.innerHTML = '<input type="checkbox" class="emx-cb"' +
       (s.active ? ' checked' : '') + '><span>' + s.display + '</span>';
     listC.appendChild(row);
   }
 };
 window.renderC();
 listC.onclick = (e) => {
   const row = e.target.closest('.emx-row');
   if (!row) return;
   const s = window.servers.find(x => x.key === row.dataset.key);
   if (!s) return;
   s.active = !s.active;
   window.renderC();          // <-- every element the caller held is now detached
 };
</script></body></html>
"""


def drag_over(page, selectors):
    """A REAL mouse drag from the first selector's text to the last one's."""
    boxes = page.evaluate("""(sels) => sels.map(s => {
        const r = document.querySelector(s).getBoundingClientRect();
        return {l: r.left, r: r.right, t: r.top, b: r.bottom};
    })""", selectors)
    a, z = boxes[0], boxes[-1]
    y0, y1 = (a["t"] + a["b"]) / 2, (z["t"] + z["b"]) / 2
    page.mouse.move(a["l"] + 2, y0)
    page.mouse.down()
    for step in range(1, 11):
        page.mouse.move(a["l"] + (z["r"] - 2 - a["l"]) * step / 10.0,
                        y0 + (y1 - y0) * step / 10.0)
        time.sleep(0.03)
    page.mouse.move(z["r"] - 2, y1)
    page.mouse.up()
    time.sleep(0.35)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, channel="chrome",
                                 args=["--start-maximized"])
    page = browser.new_context(no_viewport=True).new_page()
    page.set_content(PAGE)
    page.add_script_tag(path=MODULE)     # THE REAL, SHIPPED MODULE
    time.sleep(1.0)
    page.bring_to_front()
    time.sleep(0.5)

    print("=" * 74)
    print("SPACE-BAR BULK TOGGLE - BEHAVIOURAL PROOF (real module, real browser)")
    print("=" * 74)
    take_shot(OUT, "01_page_ready.png")

    # ---------- A: mixed block, one SPACE clears it ----------------------
    picked = ['#label-tool-2', '#label-tool-3', '#label-tool-4',
              '#label-tool-5', '#label-tool-6']
    drag_over(page, picked)
    sel = page.evaluate("() => window.getSelection().toString().trim()")
    check("A: a real mouse drag selected the labels", len(sel) > 0, repr(sel[:48]))
    take_shot(OUT, "02_A_selected.png")

    page.keyboard.press(" ")
    time.sleep(0.6)
    stateA = page.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('#tool-mcps-list input')).map(c => [c.id, c.checked]))")
    take_shot(OUT, "03_A_after_space.png")
    check("A: SPACE unchecked the whole MIXED block (any checked -> clear all)",
          all(stateA['tool-%d' % i] is False for i in (2, 3, 4, 5, 6)),
          str({k: v for k, v in stateA.items() if k in
               ('tool-2', 'tool-3', 'tool-4', 'tool-5', 'tool-6')}))
    check("A: rows outside the drag were untouched",
          all(stateA['tool-%d' % i] is True for i in (1, 7, 8, 9, 10)))

    page.keyboard.press(" ")
    time.sleep(0.6)
    stateA2 = page.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('#tool-mcps-list input')).map(c => [c.id, c.checked]))")
    check("A: a second SPACE turned the same block back ON",
          all(stateA2['tool-%d' % i] is True for i in (2, 3, 4, 5, 6)))

    # ---------- B: the Skills shape --------------------------------------
    drag_over(page, ['label[for="skill-checkbox-acp-router"]',
                     'label[for="skill-checkbox-flow-making"]'])
    page.keyboard.press(" ")
    time.sleep(0.6)
    stateB = page.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('#skills-configure-list input')).map(c => [c.id, c.checked]))")
    take_shot(OUT, "04_B_skills.png")
    check("B: hyphenated skill ids toggled (acp-router .. flow-making)",
          stateB['skill-checkbox-acp-router'] is False and
          stateB['skill-checkbox-flow-making'] is False, str(stateB))
    check("B: the skill below the drag was untouched",
          stateB['skill-checkbox-summarize'] is True)

    # ---------- C: the self-re-rendering, model-driven list ---------------
    drag_over(page, ['[data-key="alpha"] span', '[data-key="charlie"] span'])
    # Diagnose FIRST: a failure here must say whether the drag even made a
    # selection (a test/timing flake) or whether the toggle itself failed
    # (a real bug). Without this the two are indistinguishable.
    sel_c = page.evaluate("() => window.getSelection().toString().trim()")
    check("C: the drag produced a selection over the rows", len(sel_c) > 0,
          repr(sel_c[:48]))
    page.keyboard.press(" ")
    time.sleep(0.8)
    model = page.evaluate("() => window.servers.map(s => [s.key, s.active])")
    take_shot(OUT, "05_C_external_mcps.png")
    active = dict(model)
    check("C: the MODEL was updated for every dragged row, despite the re-render",
          active['alpha'] is False and active['bravo'] is False and
          active['charlie'] is False, str(model))
    check("C: the row below the drag stayed active", active['delta'] is True)

    # ---------- D: SPACE must still type in a text box --------------------
    drag_over(page, picked)               # a live selection is present...
    page.click("#search-box")             # ...but focus is in a text field
    page.keyboard.type("ab")
    page.keyboard.press(" ")
    page.keyboard.type("cd")
    time.sleep(0.3)
    typed = page.evaluate("() => document.getElementById('search-box').value")
    stateD = page.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('#tool-mcps-list input')).map(c => [c.id, c.checked]))")
    take_shot(OUT, "06_D_text_box.png")
    check("D: SPACE typed a space instead of toggling", typed == "ab cd", repr(typed))
    check("D: no checkbox moved while typing in the text box",
          stateD == stateA2, "checkboxes changed while typing")

    # ---------- E: no selection -> native SPACE only ---------------------
    page.evaluate("() => window.getSelection().removeAllRanges()")
    page.focus("#tool-1")
    page.keyboard.press(" ")
    time.sleep(0.4)
    stateE = page.evaluate(
        "() => Object.fromEntries(Array.from("
        "document.querySelectorAll('#tool-mcps-list input')).map(c => [c.id, c.checked]))")
    take_shot(OUT, "07_E_no_selection.png")
    check("E: with NO selection, SPACE only toggled the focused checkbox",
          stateE['tool-1'] is False and
          all(stateE['tool-%d' % i] == stateA2['tool-%d' % i] for i in range(2, 11)),
          str(stateE))

    print("=" * 74)
    if failures:
        print("VERDICT: FAILURES (%d)" % len(failures))
        for f in failures:
            print("   - " + f)
    else:
        print("VERDICT: ALL GOOD - space bulk-toggles exactly the selected checkboxes,")
        print("         survives a self-re-rendering list, and never steals a space")
        print("         from a text box.")
    print("photos: " + OUT)
    print("=" * 74)
    time.sleep(3)
    browser.close()

sys.exit(1 if failures else 0)
