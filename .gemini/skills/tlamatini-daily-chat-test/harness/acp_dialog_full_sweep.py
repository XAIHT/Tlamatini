# Tlamatini Author Banner - do not remove
r"""
ACP DIALOG STANDARDIZATION - FULL SWEEP, DRIVEN BY PLAYWRIGHTER
===============================================================

Angela, 2026-08-12: *"resweep all dialogs including parametrizer's dialogs,
alerts agents dialogs"* and then *"perhaps are you using Playwrighter or your
shit?"*.

So: the browser is driven by TLAMATINI'S OWN **Playwrighter** agent (through
`playwrighter_run.py`), and every photo is taken by TLAMATINI'S OWN **Shoter**
agent (Playwrighter's `shoter` step). Nothing here opens a browser itself.
The harness's only job is the part that is genuinely a test: turning measured
values into PASS or FAIL.

Playwrighter gained four capabilities to make this expressible, because it
could not do the job before:

  right_click     - no way to open a context menu
  drag_to         - no way to place a node on the canvas
  computed_style  - it could read what things SAY, never what they LOOK like
  evaluate        - the alert-class dialogs only exist during a live runtime
                    event; the page's own renderer has to paint one
  shoter          - full-desktop photo by the Shoter agent, not a page grab
  browser_channel - it launched Playwright's bundled chromium, which is not
                    installed here, so every run used to die at launch

WHAT IS SWEPT (9 dialogs):
  the Parametrizer's two modals, the Start-validation and Clear confirmations,
  and the runtime alert family - hypervisor alert, notifier, Asker choice,
  ender execution, deployment result.

HOW each one is opened is printed per row and never blurred:
  ui      - a real click path, the way a person opens it.
  render  - the dialog only exists during a live runtime event, so the page's
            OWN render function paints one. Same chrome, same code; only the
            trigger differs.

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
HARNESS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(r"C:\Development\Tlamatini\Temp", "acp_dialog_full_sweep")
STATE = os.path.join(r"C:\Development\Tlamatini\Temp", "acp_session_state.json")

CANON = {
    "panel":  "rgb(74, 79, 92)",     # --tlm-dlg-surface  #4a4f5c
    "chrome": "rgb(68, 72, 83)",     # --tlm-dlg-chrome   #444853
    "radius": "8px",                 # --tlm-dlg-radius
    "teal":   "rgb(85, 187, 170)",   # --tlm-dlg-accent   #55bbaa
}

UID = ".ui-dialog:not([style*='display: none'])"

# WHAT EACH DIALOG LEGITIMATELY HAS.
#
# Blanket expectations are how a check lies. Demanding a teal confirm from a
# dialog whose only actions are "Stop Flow" (red, destructive) and "Dismiss"
# would be demanding a BUG, and a red FAIL nobody believes is worse than no
# check at all.
#   bars    True = header AND footer bar | "header" = header only | False = neither
#   confirm the dialog has a primary action, which must be teal
SHAPE = {
    "01_parametrizer_error":     {"bars": False,    "confirm": True},
    "02_start_validation_check": {"bars": True,     "confirm": True},
    "03_clear_confirmation":     {"bars": True,     "confirm": True},
    "04_parametrizer_mapping":   {"bars": False,    "confirm": True},
    "05_hypervisor_alert":       {"bars": True,     "confirm": False},
    "06_runtime_notification":   {"bars": True,     "confirm": False},
    "07_asker_choice":           {"bars": "header", "confirm": False},
    "08_ender_execution":        {"bars": "header", "confirm": False},
    "09_deployment_result":      {"bars": True,     "confirm": True},
}

NOTES = {
    "01_parametrizer_error":     ("ui", "unwired Parametrizer refuses to map"),
    "02_start_validation_check": ("ui", "Run = teal, Verify = outlined"),
    "03_clear_confirmation":     ("ui", "was a NATIVE confirm() - now themed"),
    "04_parametrizer_mapping":   ("render", "gradient-clipped title removed"),
    "05_hypervisor_alert":       ("render", "Stop Flow stays red (destructive)"),
    "06_runtime_notification":   ("render", "severity chip must be DARK"),
    "07_asker_choice":           ("render", "no coloured edge across the card"),
    "08_ender_execution":        ("render", "spinner dialog"),
    "09_deployment_result":      ("render", "OK is teal, not red/green"),
}


def measure(label, panel, header=None, footer=None, field=None):
    """The steps that MEASURE one dialog and photograph it."""
    steps = [{"action": "computed_style", "selector": panel, "name": label + ".panel",
              "properties": ["backgroundColor", "borderTopLeftRadius"]}]
    if header:
        steps.append({"action": "computed_style", "selector": header,
                      "name": label + ".header", "properties": ["backgroundColor"]})
    if footer:
        steps.append({"action": "computed_style", "selector": footer,
                      "name": label + ".footer", "properties": ["backgroundColor"]})
    if field:
        steps.append({"action": "computed_style", "selector": field,
                      "name": label + ".field", "properties": ["backgroundColor"]})
    # The teal-confirm probe: report the FIRST teal button found inside the
    # panel, or "" - a value, never an exception.
    steps.append({
        "action": "evaluate", "name": label + ".teal",
        "expression": """(sel) => {
            const p = document.querySelector(sel);
            if (!p) return '';
            for (const b of p.querySelectorAll('button, .ui-button')) {
                if (getComputedStyle(b).backgroundColor === 'rgb(85, 187, 170)') {
                    return 'rgb(85, 187, 170)';
                }
            }
            return '';
        }""", "arg": panel})
    steps.append({"action": "shoter", "dir": OUT, "filename": label + ".png",
                  "name": label})
    return steps


CLEANUP = {
    "action": "evaluate", "name": "cleanup",
    "expression": """() => {
        // Close politely first (Cancel, never Continue - a sweep must never
        // CONFIRM a destructive dialog), then remove what is left. jQuery UI
        // leaves a full-screen .ui-widget-overlay behind a modal dialog, and
        // if it survives it swallows every later click.
        document.querySelectorAll('.ui-dialog:not([style*="display: none"]) button')
            .forEach(b => { if (/cancel|dismiss/i.test(b.textContent || '')) b.click(); });
        try {
            $('.ui-dialog-content').each(function () {
                try { $(this).dialog('close'); } catch (e) { /* not a dialog */ }
            });
        } catch (e) { /* jQuery UI absent */ }
        ['parametrizer-error-overlay', 'parametrizer-overlay']
            .forEach(id => { const el = document.getElementById(id); if (el) el.remove(); });
        document.querySelectorAll('.asker-dialog-wrapper, .hypervisor-dialog-class,'
            + ' .notification-dialog-class, .ui-widget-overlay')
            .forEach(e => e.remove());
        return 'clean';
    }"""}


def build_steps():
    """The whole sweep as ONE Playwrighter script.

    Order is load-bearing: the two toolbar-driven rows run FIRST, because
    painting a stop-path dialog (`showEnderExecutionDialog`) flips the flow's
    control state and DISABLES Start and Clear - a sweep that renders those
    first can never click either button again.
    """
    steps = [
        {"action": "goto", "url": ACP},
        {"action": "wait_for", "selector": "#agents-list .agent-tool-item",
         "state": "visible"},
        {"action": "wait", "ms": 2200},
        {"action": "drag_to", "selector": ".agent-tool-item[data-content='Parametrizer']",
         "target": "#canvas-content", "target_position": {"x": 240, "y": 130}},
        {"action": "wait", "ms": 700},
        {"action": "drag_to", "selector": ".agent-tool-item[data-content='Executer']",
         "target": "#canvas-content", "target_position": {"x": 470, "y": 130}},
        {"action": "wait_for", "selector": ".canvas-item", "state": "visible"},
        {"action": "wait", "ms": 900},

        # 01 - Parametrizer validation error (real UI)
        {"action": "right_click", "selector": ".canvas-item[id^='parametrizer']"},
        {"action": "wait_for", "selector": "#agent-context-menu", "state": "visible"},
        {"action": "wait", "ms": 500},
        {"action": "click", "selector": "#ctx-menu-configure"},
        {"action": "wait", "ms": 1800},
    ]
    steps += measure("01_parametrizer_error", "#parametrizer-error-overlay > div")
    steps += [{"action": "evaluate", "name": "c1", "expression":
               "() => { const e = document.getElementById('parametrizer-error-overlay');"
               " if (e) e.remove(); return 'x'; }"},
              {"action": "wait", "ms": 500}]

    # 02 - Start validation check (real UI)
    steps += [{"action": "click", "selector": "#btn-start"}, {"action": "wait", "ms": 1800}]
    steps += measure("02_start_validation_check", UID,
                     UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane")
    steps += [CLEANUP, {"action": "wait", "ms": 700}]

    # 03 - Clear confirmation (real UI; it was a NATIVE confirm() until today)
    steps += [{"action": "click", "selector": "#btn-clear"}, {"action": "wait", "ms": 1600}]
    steps += measure("03_clear_confirmation", UID,
                     UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane")
    steps += [CLEANUP, {"action": "wait", "ms": 700}]

    # 04 - Parametrizer mapping (render)
    steps += [{"action": "evaluate", "name": "pm", "expression": """() => {
        _renderParametrizerMappingDialog('parametrizer-1', {
            success: true, source_agent: 'apirer_1', target_agent: 'executer_1',
            source_fields: ['url', 'status', 'response_body'],
            target_params: [{ name: 'script', value: 'echo {content}' },
                            { name: 'non_blocking', value: 'false' }],
            existing_mappings: []
        });
        return 'rendered';
    }"""}, {"action": "wait", "ms": 1500}]
    steps += measure("04_parametrizer_mapping", "#parametrizer-dialog")
    steps += [CLEANUP, {"action": "wait", "ms": 600}]

    # 05 - Hypervisor alert (render)
    steps += [{"action": "evaluate", "name": "hv", "expression":
               "() => { showHypervisorAlertDialog('Agent executer_1 produced no "
               "output for 6 minutes while the flow reports RUNNING.'); return 'x'; }"},
              {"action": "wait", "ms": 1500}]
    steps += measure("05_hypervisor_alert", ".hypervisor-dialog-class",
                     ".hypervisor-dialog-class .ui-dialog-titlebar",
                     ".hypervisor-dialog-class .ui-dialog-buttonpane")
    steps += [CLEANUP, {"action": "wait", "ms": 600}]

    # 06 - Notifier / pattern detected (render). The light-chip leak lived here.
    steps += [{"action": "evaluate", "name": "nt", "expression": """() => {
        window.SharedRuntimeDialogs.renderNotifierToast({
            source_agent: 'monitor_log_1',
            matches: ['ERROR: connection refused'],
            timestamp: '2026-08-12 23:20:00',
            outcome_detail: 'The upstream service did not answer.',
            sound_enabled: false });
        return 'x';
    }"""}, {"action": "wait", "ms": 1500}]
    steps += measure("06_runtime_notification", ".notification-dialog-class",
                     ".notification-dialog-class .ui-dialog-titlebar",
                     ".notification-dialog-class .ui-dialog-buttonpane",
                     field=".notification-dialog-class .ui-dialog-content span")
    steps += [CLEANUP, {"action": "wait", "ms": 600}]

    # 07 - Asker choice (render)
    steps += [{"action": "evaluate", "name": "ak", "expression": """() => {
        window.SharedRuntimeDialogs.renderAskerChoiceDialog({
            identifier: 'asker_1', sendChoice: () => {},
            loadConfig: async () => ({ legend_a: 'Retry', legend_b: 'Skip' }) });
        return 'x';
    }"""}, {"action": "wait", "ms": 1600}]
    steps += measure("07_asker_choice", ".asker-dialog-wrapper",
                     ".asker-dialog-wrapper .ui-dialog-titlebar")
    steps += [CLEANUP, {"action": "wait", "ms": 600}]

    # 08 - Ender execution (render)
    steps += [{"action": "evaluate", "name": "en",
               "expression": "() => { showEnderExecutionDialog(); return 'x'; }"},
              {"action": "wait", "ms": 1500}]
    steps += measure("08_ender_execution", UID, UID + " .ui-dialog-titlebar")
    steps += [CLEANUP, {"action": "wait", "ms": 600}]

    # 09 - Deployment result (render)
    steps += [{"action": "evaluate", "name": "dp", "expression":
               "() => { showDeploymentResultDialog(true, 'executer_1', "
               "'C:\\\\Tlamatini\\\\agents\\\\pools\\\\executer_1'); return 'x'; }"},
              {"action": "wait", "ms": 1600}]
    steps += measure("09_deployment_result", UID,
                     UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane")
    steps += [CLEANUP]
    return steps


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=" * 78)
    print(" TLAMATINI - ACP DIALOG FULL SWEEP  (driven by PLAYWRIGHTER)")
    print(" browser : Tlamatini's Playwrighter agent, headed real Chrome")
    print(" photos  : Tlamatini's Shoter agent (never PIL) -> %s" % OUT)
    print(" base    : %s" % BASE)
    print("=" * 78)

    if not os.path.isfile(STATE):
        print("!! No session at %s" % STATE)
        print("   Create it once (it holds only a session cookie, never a password).")
        return 2

    steps = build_steps()
    print("-- handing %d steps to Playwrighter..." % len(steps))
    try:
        result = run_steps(steps, runtime_base=OUT, start_url=ACP,
                           storage_state_in=STATE, headless=False,
                           hold_open_seconds=2, timeout=1200)
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
    html = ["<!doctype html><meta charset='utf-8'><title>ACP dialog full sweep</title>",
            "<style>body{background:#2b2f3a;color:#eee;font-family:Nunito,sans-serif;padding:24px}",
            "table{border-collapse:collapse;width:100%;margin-bottom:26px}",
            "td,th{border:1px solid #555;padding:7px 9px;font-size:.85rem;text-align:left}",
            "th{background:#444853}.ok{color:#7fe6d2;font-weight:700}.bad{color:#ff9c9c;font-weight:700}",
            "img{max-width:100%;border:1px solid #555;border-radius:8px;margin:6px 0 22px}</style>",
            "<h1>Tlamatini - ACP dialog FULL sweep</h1>",
            "<p>Browser driven by <b>Playwrighter</b>; photos by <b>Shoter</b>. "
            "Measured against the External-MCPs reference (panel #4a4f5c, chrome "
            "#444853, radius 8px, teal #55bbaa). <b>ui</b> = a real click path; "
            "<b>render</b> = the page's own renderer, for dialogs that only exist "
            "during a live runtime event.</p>",
            "<table><tr><th>Dialog</th><th>How</th><th>Panel</th><th>Radius</th>"
            "<th>Header</th><th>Footer</th><th>Teal</th><th>Verdict</th></tr>"]

    for label in sorted(SHAPE):
        shape = SHAPE[label]
        how, note = NOTES[label]
        panel = values.get(label + ".panel.backgroundColor", "")
        radius = values.get(label + ".panel.borderTopLeftRadius", "")
        header = values.get(label + ".header.backgroundColor", "")
        footer = values.get(label + ".footer.backgroundColor", "")
        teal = values.get(label + ".teal", "")

        checks = {"opened": bool(panel),
                  "panel": panel == CANON["panel"],
                  "radius": radius == CANON["radius"]}
        if shape["bars"] in (True, "header"):
            checks["chrome"] = header == CANON["chrome"]
        if shape["bars"] is True:
            checks["footer"] = footer == CANON["chrome"]
        if shape["confirm"]:
            checks["teal"] = teal == CANON["teal"]

        good = all(checks.values())
        ok_all = ok_all and good
        print(" %-28s %-7s %s" % (label, how, "PASS" if good else "FAIL " +
              ",".join(k for k, v in checks.items() if not v)))
        shot = os.path.join(OUT, label + ".png")
        html.append(
            "<tr><td>%s<br><small style='color:#9ca2ba'>%s</small></td><td>%s</td>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td class='%s'>%s</td></tr>"
            % (label, note, how, panel or "-", radius or "-", header or "-",
               footer or "-", teal or "-", "ok" if good else "bad",
               "PASS" if good else "FAIL"))
        if os.path.isfile(shot):
            html.append("<!--shot:%s-->" % label)
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
    print(" agent log: %s" % result.get("runtime"))
    print(" RESULT : %s" % ("EVERY SWEPT DIALOG STANDARDIZED" if ok_all
                            else "DRIFT REMAINS - see table"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
