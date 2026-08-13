# Tlamatini Author Banner - do not remove
r"""
ACP RIGHT-CLICK DIALOGS - VISIBLE CHECK, DRIVEN BY PLAYWRIGHTER
===============================================================

The five dialogs a user reaches by RIGHT-CLICKING an agent on the canvas:
the context menu itself, Configure, Description, the Log Viewer, and the
Validate result. (`acp_dialog_full_sweep.py` covers the Parametrizer and the
runtime alert family.)

Browser driven by TLAMATINI'S OWN **Playwrighter** agent; every photo taken
by TLAMATINI'S OWN **Shoter** agent. This harness opens no browser itself.

The row that matters most is **Configure**: it used to paint every input
`#fff` on `#000` - a WHITE form inside the dark card, on the most-used dialog
of the whole workflow designer - so its field background is measured
explicitly and must be dark.

VISIBLE ONLY. There is no --headless flag and there never will be.
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwrighter_run import PlaywrighterError, failed_steps, run_steps  # noqa: E402

BASE = os.environ.get("TLM_BASE", "http://127.0.0.1:8010")
ACP = BASE + "/agent/agentic_control_panel/"
OUT = os.path.join(r"C:\Development\Tlamatini\Temp", "acp_dialog_theme_check")
STATE = os.path.join(r"C:\Development\Tlamatini\Temp", "acp_session_state.json")

CANON = {
    "panel":  "rgb(74, 79, 92)",
    "chrome": "rgb(68, 72, 83)",
    "radius": "8px",
    "teal":   "rgb(85, 187, 170)",
}

UID = ".ui-dialog:not([style*='display: none'])"

# Executer is deliberate: its config has a `script` TEXTAREA plus text
# inputs, so a returning white-form leak is impossible to miss.
AGENT = "Executer"

# label: bars (True | "header" | False), confirm, note
SHAPE = {
    "01_context_menu":       (False, False, "popover: surface + 6px corner only"),
    "02_configure":          (True,  True,  "fields must be DARK, not white"),
    "03_description":        (True,  False, "kicker + real footer bar"),
    "04_log_viewer":         (True,  False, "inset log pane inside the card"),
    "05_validation_result":  (True,  True,  "teal confirm on a real footer bar"),
}

TEAL_PROBE = """(sel) => {
    const p = document.querySelector(sel);
    if (!p) return '';
    for (const b of p.querySelectorAll('button, .ui-button')) {
        if (getComputedStyle(b).backgroundColor === 'rgb(85, 187, 170)') {
            return 'rgb(85, 187, 170)';
        }
    }
    return '';
}"""

CLEANUP = {"action": "evaluate", "name": "cleanup", "expression": """() => {
    document.querySelectorAll('.ui-dialog:not([style*="display: none"]) button')
        .forEach(b => { if (/cancel|dismiss/i.test(b.textContent || '')) b.click(); });
    try {
        $('.ui-dialog-content').each(function () {
            try { $(this).dialog('close'); } catch (e) { /* not a dialog */ }
        });
    } catch (e) { /* jQuery UI absent */ }
    for (const id of ['agent-description-dialog', 'agent-description-overlay',
                      'log-viewer-dialog', 'log-viewer-overlay',
                      'agent-context-menu']) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    }
    document.querySelectorAll('.ui-widget-overlay').forEach(e => e.remove());
    return 'clean';
}"""}


def measure(label, panel, header=None, footer=None, field=None):
    steps = [{"action": "computed_style", "selector": panel, "name": label + ".panel",
              "properties": ["backgroundColor", "borderTopLeftRadius"]}]
    for sel, suffix in ((header, ".header"), (footer, ".footer"), (field, ".field")):
        if sel:
            steps.append({"action": "computed_style", "selector": sel,
                          "name": label + suffix,
                          "properties": ["backgroundColor"]})
    steps.append({"action": "evaluate", "name": label + ".teal",
                  "expression": TEAL_PROBE, "arg": panel})
    steps.append({"action": "shoter", "dir": OUT, "filename": label + ".png",
                  "name": label})
    return steps


RIGHT_CLICK = [
    {"action": "right_click", "selector": ".canvas-item"},
    {"action": "wait_for", "selector": "#agent-context-menu", "state": "visible"},
    {"action": "wait", "ms": 600},
]


def build_steps():
    steps = [
        {"action": "goto", "url": ACP},
        {"action": "wait_for", "selector": "#agents-list .agent-tool-item",
         "state": "visible"},
        {"action": "wait", "ms": 2200},
        {"action": "drag_to", "selector": ".agent-tool-item[data-content='%s']" % AGENT,
         "target": "#canvas-content", "target_position": {"x": 300, "y": 150}},
        {"action": "wait_for", "selector": ".canvas-item", "state": "visible"},
        {"action": "wait", "ms": 900},
    ]

    # 01 - the context menu itself: the DOOR to the other four.
    steps += RIGHT_CLICK
    steps += measure("01_context_menu", "#agent-context-menu")

    # 02 - Configure (the white-form dialog).
    steps += [{"action": "click", "selector": "#ctx-menu-configure"},
              {"action": "wait", "ms": 2200}]
    steps += measure("02_configure", UID, UID + " .ui-dialog-titlebar",
                     UID + " .ui-dialog-buttonpane",
                     field="#canvas-item-list textarea")
    steps += [CLEANUP, {"action": "wait", "ms": 800}]

    # 03 - Description (native modal: had neither kicker nor footer).
    steps += RIGHT_CLICK
    steps += [{"action": "click", "selector": "#ctx-menu-description"},
              {"action": "wait", "ms": 1600}]
    steps += measure("03_description", "#agent-description-dialog",
                     "#agent-description-header", "#agent-description-footer")
    steps += [{"action": "click", "selector": "#agent-description-close-action"},
              {"action": "wait", "ms": 700}]

    # 04 - Log viewer (the other native modal).
    steps += RIGHT_CLICK
    steps += [{"action": "click", "selector": "#ctx-menu-view-log"},
              {"action": "wait", "ms": 1800}]
    steps += measure("04_log_viewer", "#log-viewer-dialog",
                     "#log-viewer-header", "#log-viewer-footer")
    steps += [{"action": "click", "selector": "#log-viewer-close"},
              {"action": "wait", "ms": 700}]

    # 05 - Validate result (toolbar).
    steps += [{"action": "click", "selector": "#btn-validate"},
              {"action": "wait", "ms": 2500}]
    steps += measure("05_validation_result", UID, UID + " .ui-dialog-titlebar",
                     UID + " .ui-dialog-buttonpane")
    steps += [CLEANUP]
    return steps


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=" * 78)
    print(" TLAMATINI - ACP RIGHT-CLICK DIALOGS  (driven by PLAYWRIGHTER)")
    print(" browser : Tlamatini's Playwrighter agent, headed real Chrome")
    print(" photos  : Tlamatini's Shoter agent (never PIL) -> %s" % OUT)
    print(" agent   : %s dragged onto the real canvas" % AGENT)
    print("=" * 78)

    if not os.path.isfile(STATE):
        print("!! No session at %s" % STATE)
        return 2

    steps = build_steps()
    print("-- handing %d steps to Playwrighter..." % len(steps))
    try:
        result = run_steps(steps, runtime_base=OUT, start_url=ACP,
                           storage_state_in=STATE, headless=False,
                           hold_open_seconds=2, timeout=900)
    except PlaywrighterError as exc:
        print("!! Playwrighter could not start: %s" % exc)
        return 2

    print("-- Playwrighter status=%s  steps ok=%d/%d"
          % (result["status"], result["steps_run"], result["steps_total"]))
    for bad in failed_steps(result)[:12]:
        print("   !! step %s (%s): %s"
              % (bad.get("index"), bad.get("action"), str(bad.get("error"))[:110]))

    values = result["extracted"]

    print("\n" + "=" * 78)
    print(" VERDICT (measured against the External-MCPs reference)")
    print("=" * 78)

    ok_all = True
    html = ["<!doctype html><meta charset='utf-8'><title>ACP right-click dialogs</title>",
            "<style>body{background:#2b2f3a;color:#eee;font-family:Nunito,sans-serif;padding:24px}",
            "table{border-collapse:collapse;width:100%;margin-bottom:26px}",
            "td,th{border:1px solid #555;padding:7px 9px;font-size:.86rem;text-align:left}",
            "th{background:#444853}.ok{color:#7fe6d2;font-weight:700}.bad{color:#ff9c9c;font-weight:700}",
            "img{max-width:100%;border:1px solid #555;border-radius:8px;margin:6px 0 22px}</style>",
            "<h1>Tlamatini - ACP right-click dialogs</h1>",
            "<p>Browser driven by <b>Playwrighter</b>; photos by <b>Shoter</b>. "
            "Measured against the External-MCPs reference.</p>",
            "<table><tr><th>Dialog</th><th>Panel</th><th>Radius</th><th>Header</th>"
            "<th>Footer</th><th>Teal</th><th>Field</th><th>Verdict</th></tr>"]

    for label in sorted(SHAPE):
        bars, confirm, note = SHAPE[label]
        panel = values.get(label + ".panel.backgroundColor", "")
        radius = values.get(label + ".panel.borderTopLeftRadius", "")
        header = values.get(label + ".header.backgroundColor", "")
        footer = values.get(label + ".footer.backgroundColor", "")
        teal = values.get(label + ".teal", "")
        field = values.get(label + ".field.backgroundColor", "")

        checks = {"opened": bool(panel),
                  "panel": panel == CANON["panel"]}
        # The popover keeps the small 6px radius; dialogs use 8px.
        checks["radius"] = radius == ("6px" if label.endswith("context_menu")
                                      else CANON["radius"])
        if bars in (True, "header"):
            checks["chrome"] = header == CANON["chrome"]
        if bars is True:
            checks["footer"] = footer == CANON["chrome"]
        if confirm:
            checks["teal"] = teal == CANON["teal"]
        if field:
            # A field brighter than mid-grey means the white form is back.
            nums = [int(n) for n in field.replace(",", " ")
                    .replace("(", " ").replace(")", " ").split()
                    if n.isdigit()]
            checks["dark_field"] = bool(nums) and (sum(nums[:3]) / 3.0) < 128

        good = all(checks.values())
        ok_all = ok_all and good
        print(" %-24s %s" % (label, "PASS" if good else "FAIL " +
              ",".join(k for k, v in checks.items() if not v)))
        html.append(
            "<tr><td>%s<br><small style='color:#9ca2ba'>%s</small></td><td>%s</td>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td class='%s'>%s</td></tr>"
            % (label, note, panel or "-", radius or "-", header or "-",
               footer or "-", teal or "-", field or "-",
               "ok" if good else "bad", "PASS" if good else "FAIL"))
    html.append("</table>")

    for label in sorted(SHAPE):
        shot = os.path.join(OUT, label + ".png")
        if os.path.isfile(shot):
            html.append("<h2>%s</h2><img src='%s'>" % (label, label + ".png"))
        else:
            html.append("<h2>%s</h2><p class='bad'>NO PHOTO</p>" % label)

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html.append("<p style='color:#9ca2ba'>Generated %s - browser by Playwrighter, "
                "photos by Shoter.</p>" % stamp)
    summary = os.path.join(OUT, "SUMMARY.html")
    with open(summary, "w", encoding="utf-8") as fh:
        fh.write("\n".join(html))
    print("\n summary: %s" % summary)
    print(" RESULT : %s" % ("ALL CANVAS DIALOGS STANDARDIZED" if ok_all
                            else "DRIFT REMAINS - see table"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
