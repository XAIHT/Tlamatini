# Tlamatini Author Banner - do not remove
r"""
DIALOG STANDARDIZATION - VISIBLE REGRESSION, DRIVEN BY PLAYWRIGHTER
===================================================================

Angela, 2026-08-12: *"all of the dialogs ... they all are almost similar but
there are a few that doesn't, like the voice configuration, and it makes the
user feel somehow weird, like a not professional software."*

This opens EVERY dialog of the CHAT page through the REAL navbar and, for
each one, does two things:

  1. photographs the whole desktop with **Shoter** - Tlamatini's own agent,
     never PIL (Angela's standing rule); and
  2. reads the LIVE `getComputedStyle` of the panel / header / footer /
     primary button and compares it to the REFERENCE dialog (External >
     MCPs, the one in Angela's screenshot).

Point 2 is what makes this a test rather than a slideshow: a photo proves a
dialog rendered, only the computed style proves it rendered with the SAME
identity.

The browser is driven by TLAMATINI'S OWN **Playwrighter** agent (via
`playwrighter_run.py`) - this harness opens no browser itself.

VISIBLE ONLY. There is no --headless flag and there never will be.
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwrighter_run import PlaywrighterError, failed_steps, run_steps  # noqa: E402

BASE = os.environ.get("TLM_BASE", "http://127.0.0.1:8010")
CHAT = BASE + "/agent/agent/"
HARNESS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(r"C:\Development\Tlamatini\Temp", "dialog_theme_check")
STATE = os.path.join(r"C:\Development\Tlamatini\Temp", "chat_session_state.json")

CANON = {
    "panel":  "rgb(74, 79, 92)",     # --tlm-dlg-surface  #4a4f5c
    "chrome": "rgb(68, 72, 83)",     # --tlm-dlg-chrome   #444853
    "radius": "8px",                 # --tlm-dlg-radius
    "teal":   "rgb(85, 187, 170)",   # --tlm-dlg-accent   #55bbaa
}

UID = ".ui-dialog:not([style*='display: none'])"

# label, navbar item id, panel, header, footer, has-teal-confirm
#
# "About" is deliberately ABSENT: `OpenAboutDialog` shows a full-screen VIDEO
# SPLASH with no titlebar, footer or buttons - it is not a dialog, and
# probing it for one printed a red FAIL on every run, which trains the reader
# to ignore the table.
DIALOGS = [
    ("01_external_mcps_REFERENCE", "external-mcps",
     ".emx-panel", ".emx-header", ".emx-footer", True),
    ("02_voice_settings", "config-voice",
     ".tlm-modal", ".tlm-modal-head", ".tlm-modal-foot", False),
    ("03_contacts_book", "config-contacts",
     ".ctb-panel", ".ctb-header", ".ctb-footer", True),
    ("04_config_models", "config-models",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    ("05_config_urls", "config-urls",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    ("06_configure_mcps_tools", "enable-mcps",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    ("07_configure_agents", "enable-agents",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    ("08_configure_skills", "configure-skills",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    ("09_browse_skills", "browse-skills",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    ("10_access_keys_wizard", "access-keys-wizard",
     UID, UID + " .ui-dialog-titlebar", UID + " .ui-dialog-buttonpane", True),
    # Check-for-updates IS a real dialog and was missed by the first pass: it
    # wore the About splash's private #1a1a2e skin with a purple/pink
    # gradient button, and had no header bar and no kicker.
    ("11_check_for_updates", "check-updates-button",
     ".update-window", ".update-header", ".update-actions", True),
]

# Opening a navbar entry: the dropdown must be opened first, exactly as a
# person does it. Bootstrap toggles it, so the toggle is really clicked.
OPEN_MENU = """(id) => {
    const el = document.getElementById(id);
    if (!el) return 'missing';
    const holder = el.closest('li.nav-item, .dropdown');
    const toggle = holder && holder.querySelector('.dropdown-toggle');
    if (toggle) toggle.click();
    return 'opened';
}"""

CLOSE_ALL = """() => {
    // Close by the app's own routes first, then remove what survives. A
    // leftover .ui-widget-overlay swallows every later click, so the NEXT
    // dialog would silently never open.
    for (const id of ['external-mcps-close', 'tlm-voice-close', 'contacts-cancel']) {
        const b = document.getElementById(id);
        if (b) b.click();
    }
    document.querySelectorAll('.update-window .about-close-btn').forEach(b => b.click());
    try {
        $('.ui-dialog-content').each(function () {
            try { $(this).dialog('close'); } catch (e) { /* not a dialog */ }
        });
    } catch (e) { /* jQuery UI absent */ }
    document.querySelectorAll('.ui-widget-overlay').forEach(e => e.remove());
    const upd = document.getElementById('update-overlay');
    if (upd) upd.style.display = 'none';
    return 'closed';
}"""

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


def build_steps():
    steps = [
        {"action": "goto", "url": CHAT},
        {"action": "wait_for", "selector": "#mcps-menu-button", "state": "attached"},
        {"action": "wait", "ms": 2500},
    ]
    for label, item_id, panel, header, footer, has_teal in DIALOGS:
        steps += [
            {"action": "evaluate", "name": label + ".menu",
             "expression": OPEN_MENU, "arg": item_id},
            {"action": "wait", "ms": 500},
            {"action": "click", "selector": "#" + item_id},
            {"action": "wait", "ms": 2000},
            {"action": "computed_style", "selector": panel, "name": label + ".panel",
             "properties": ["backgroundColor", "borderTopLeftRadius"]},
            {"action": "computed_style", "selector": header, "name": label + ".header",
             "properties": ["backgroundColor"]},
            {"action": "computed_style", "selector": footer, "name": label + ".footer",
             "properties": ["backgroundColor"]},
            {"action": "evaluate", "name": label + ".teal",
             "expression": TEAL_PROBE, "arg": panel},
            {"action": "shoter", "dir": OUT, "filename": label + ".png", "name": label},
            {"action": "evaluate", "name": label + ".close", "expression": CLOSE_ALL},
            {"action": "wait", "ms": 800},
        ]
    return steps


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=" * 78)
    print(" TLAMATINI - CHAT DIALOG STANDARDIZATION  (driven by PLAYWRIGHTER)")
    print(" browser : Tlamatini's Playwrighter agent, headed real Chrome")
    print(" photos  : Tlamatini's Shoter agent (never PIL) -> %s" % OUT)
    print(" base    : %s" % BASE)
    print("=" * 78)

    if not os.path.isfile(STATE):
        print("!! No chat session at %s" % STATE)
        print("   Create it once - it holds only a session cookie, never a password.")
        return 2

    steps = build_steps()
    print("-- handing %d steps to Playwrighter (%d dialogs)..."
          % (len(steps), len(DIALOGS)))
    try:
        result = run_steps(steps, runtime_base=OUT, start_url=CHAT,
                           storage_state_in=STATE, headless=False,
                           hold_open_seconds=2, timeout=1500)
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
    html = ["<!doctype html><meta charset='utf-8'><title>Dialog standardization</title>",
            "<style>body{background:#2b2f3a;color:#eee;font-family:Nunito,sans-serif;padding:24px}",
            "table{border-collapse:collapse;width:100%;margin-bottom:26px}",
            "td,th{border:1px solid #555;padding:7px 9px;font-size:.86rem;text-align:left}",
            "th{background:#444853}.ok{color:#7fe6d2;font-weight:700}.bad{color:#ff9c9c;font-weight:700}",
            "img{max-width:100%;border:1px solid #555;border-radius:8px;margin:6px 0 22px}</style>",
            "<h1>Tlamatini - chat dialog standardization</h1>",
            "<p>Browser driven by <b>Playwrighter</b>; photos by <b>Shoter</b>. Every "
            "dialog measured against the External-MCPs reference (panel #4a4f5c, "
            "chrome #444853, radius 8px, teal #55bbaa).</p>",
            "<table><tr><th>Dialog</th><th>Panel</th><th>Radius</th><th>Header</th>"
            "<th>Footer</th><th>Teal</th><th>Verdict</th></tr>"]

    for label, _item, _p, _h, _f, has_teal in DIALOGS:
        panel = values.get(label + ".panel.backgroundColor", "")
        radius = values.get(label + ".panel.borderTopLeftRadius", "")
        header = values.get(label + ".header.backgroundColor", "")
        footer = values.get(label + ".footer.backgroundColor", "")
        teal = values.get(label + ".teal", "")

        checks = {"opened": bool(panel),
                  "panel": panel == CANON["panel"],
                  "radius": radius == CANON["radius"],
                  "chrome": header == CANON["chrome"],
                  "footer": footer == CANON["chrome"]}
        if has_teal:
            checks["teal"] = teal == CANON["teal"]

        good = all(checks.values())
        ok_all = ok_all and good
        print(" %-30s %s" % (label, "PASS" if good else "FAIL " +
              ",".join(k for k, v in checks.items() if not v)))
        html.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td class='%s'>%s</td></tr>"
            % (label, panel or "-", radius or "-", header or "-", footer or "-",
               teal or "-", "ok" if good else "bad", "PASS" if good else "FAIL"))
    html.append("</table>")

    for label, _i, _p, _h, _f, _t in DIALOGS:
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
    print(" RESULT : %s" % ("ALL DIALOGS STANDARDIZED" if ok_all
                            else "DRIFT REMAINS - see table"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
