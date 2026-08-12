# Tlamatini Author Banner - do not remove
r"""
DIALOG STANDARDIZATION - VISIBLE REGRESSION
===========================================

Angela, 2026-08-12: "all the dialogs are almost similar but there are a few
that doesn't, like the voice configuration, and it makes the user feel somehow
weird, like a not professional software."

This test opens EVERY dialog in Tlamatini through the REAL navbar in a REAL,
HEADED Chrome on Angela's real desktop, and for each one it does two things:

  1. takes a FULL-DESKTOP photo with **Shoter** (Tlamatini's own agent - never
     PIL, per Angela's standing rule), so she can SEE each dialog; and
  2. reads the LIVE `getComputedStyle` of the dialog's panel / header / footer
     / primary button and compares it against the REFERENCE dialog
     (External > MCPs, the one in Angela's screenshot).

Point 2 is what makes this a test rather than a slideshow: a photo proves a
dialog rendered, only the computed style proves it rendered with the SAME
identity. The verdict is measured, not eyeballed, and a dialog that drifts
back to its own skin turns this red.

VISIBLE ONLY. There is no --headless flag and there never will be.
"""
from __future__ import annotations

import os
import sys
import time
import datetime

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shoter_shot import take_shot                     # noqa: E402

BASE = os.environ.get("TLM_BASE", "http://127.0.0.1:8010")
HARNESS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(r"C:\Development\Tlamatini\Temp", "dialog_theme_check")

# ── The identity, straight out of dialog_theme.css ────────────────────────────
CANON = {
    "panel_bg":  "rgb(74, 79, 92)",     # --tlm-dlg-surface  #4a4f5c
    "chrome_bg": "rgb(68, 72, 83)",     # --tlm-dlg-chrome   #444853
    "radius":    "8px",                 # --tlm-dlg-radius
    "primary":   "rgb(85, 187, 170)",   # --tlm-dlg-accent   #55bbaa
}

# label, menu-item id, panel sel, header sel, footer sel, close sel
DIALOGS = [
    ("01_external_mcps_REFERENCE", "external-mcps",
     ".emx-panel", ".emx-header", ".emx-footer", "#external-mcps-close"),
    ("02_voice_settings", "config-voice",
     ".tlm-modal", ".tlm-modal-head", ".tlm-modal-foot", "#tlm-voice-close"),
    ("03_contacts_book", "config-contacts",
     ".ctb-panel", ".ctb-header", ".ctb-footer", "#contacts-cancel"),
    ("04_config_models", "config-models",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("05_config_urls", "config-urls",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("06_configure_mcps_tools", "enable-mcps",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("07_configure_agents", "enable-agents",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("08_configure_skills", "configure-skills",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("09_browse_skills", "browse-skills",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("10_access_keys_wizard", "access-keys-wizard",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
    ("11_about", "about-button",
     ".ui-dialog:visible", ".ui-dialog:visible .ui-dialog-titlebar",
     ".ui-dialog:visible .ui-dialog-buttonpane",
     ".ui-dialog:visible .ui-dialog-titlebar-close"),
]

PROBE = """
(sels) => {
  const pick = (s) => {
    if (!s) return null;
    // ':visible' is a jQuery-ism - resolve it ourselves.
    if (s.includes(':visible')) {
      const base = s.replace(':visible', '');
      const parts = base.split(' ');
      const roots = Array.from(document.querySelectorAll(parts[0]))
        .filter(e => e.offsetParent !== null || e.getClientRects().length);
      if (!roots.length) return null;
      const root = roots[roots.length - 1];
      const rest = parts.slice(1).join(' ').trim();
      return rest ? root.querySelector(rest) : root;
    }
    return document.querySelector(s);
  };
  const cs = (el, p) => el ? getComputedStyle(el)[p] : null;
  const panel  = pick(sels.panel);
  const header = pick(sels.header);
  const footer = pick(sels.footer);
  // The primary button: teal is the identity, so look for it anywhere inside.
  let primary = null;
  if (panel) {
    const btns = Array.from(panel.querySelectorAll('button, .ui-button'));
    primary = btns.map(b => getComputedStyle(b).backgroundColor)
                  .find(c => c === 'rgb(85, 187, 170)') || null;
  }
  return {
    found:      !!panel,
    panel_bg:   cs(panel,  'backgroundColor'),
    radius:     cs(panel,  'borderTopLeftRadius'),
    border:     cs(panel,  'borderTopWidth'),
    chrome_bg:  cs(header, 'backgroundColor'),
    footer_bg:  cs(footer, 'backgroundColor'),
    font:       cs(panel,  'fontFamily'),
    primary:    primary,
  };
}
"""


def creds():
    u = p = ""
    fp = os.path.join(HARNESS, ".creds.env")
    if os.path.isfile(fp):
        for line in open(fp, encoding="utf-8"):
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "TLAMATINI_USER":
                u = v.strip()
            elif k.strip() == "TLAMATINI_PASS":
                p = v.strip()
    return (os.environ.get("TLAMATINI_USER") or u,
            os.environ.get("TLAMATINI_PASS") or p)


def open_menu_item(page, item_id):
    """Really click the dropdown toggle, then really click the entry."""
    page.evaluate(
        """(id) => {
             const el = document.getElementById(id);
             if (!el) return false;
             const d = el.closest('li.nav-item, .dropdown');
             const t = d && d.querySelector('.dropdown-toggle');
             if (t) t.setAttribute('data-tlm-open', '1');
             return !!t;
           }""", item_id)
    try:
        page.click("[data-tlm-open='1']", timeout=4000)
    except Exception:
        pass
    page.evaluate("""() => document.querySelectorAll('[data-tlm-open]')
                        .forEach(e => e.removeAttribute('data-tlm-open'))""")
    page.click("#" + item_id, timeout=6000)


def main():
    os.makedirs(OUT, exist_ok=True)
    user, password = creds()
    if not user or not password:
        print("!! TLAMATINI_USER / TLAMATINI_PASS not found in .creds.env")
        return 2

    print("=" * 74)
    print(" TLAMATINI - DIALOG STANDARDIZATION, VISIBLE CHECK")
    print(" base   : %s" % BASE)
    print(" user   : %s   (the password is NEVER printed)" % user)
    print(" photos : %s   (taken by SHOTER, never PIL)" % OUT)
    print("=" * 74)

    rows = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=False, channel="chrome",
                                args=["--start-maximized"])
        ctx = br.new_context(no_viewport=True)
        page = ctx.new_page()

        # Log in on "/" FIRST, then navigate to the chat — the same order the
        # working harnesses use. Going straight to /agent/agent/ bounces to the
        # login form and the post-login redirect does not land back on chat.
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.fill("#id_username", user)
        page.fill("#id_password", password)              # never printed
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("domcontentloaded")

        page.goto(BASE + "/agent/agent/", wait_until="domcontentloaded")
        page.wait_for_selector("#mcps-menu-button", timeout=30000)
        time.sleep(2.5)
        print("-- logged in, chat page ready")

        for label, item_id, panel, header, footer, closer in DIALOGS:
            print("\n-- %s" % label)
            try:
                open_menu_item(page, item_id)
            except Exception as exc:
                print("   !! could not open: %s" % str(exc)[:110])
                rows.append((label, {"found": False}, None))
                continue

            time.sleep(1.8)                       # let it render + settle
            try:
                got = page.evaluate(PROBE, {"panel": panel, "header": header,
                                            "footer": footer})
            except Exception as exc:
                print("   !! probe failed: %s" % str(exc)[:110])
                got = {"found": False}

            shot = take_shot(OUT, "%s.png" % label, runtime_base=OUT)
            print("   panel=%s radius=%s chrome=%s primary=%s"
                  % (got.get("panel_bg"), got.get("radius"),
                     got.get("chrome_bg"), got.get("primary")))
            print("   photo: %s" % (shot or "!! NO PHOTO"))
            rows.append((label, got, shot))

            # close it, really
            for sel in (closer, ".ui-dialog:visible .ui-dialog-titlebar-close"):
                try:
                    page.click(sel, timeout=2500)
                    break
                except Exception:
                    continue
            page.keyboard.press("Escape")
            time.sleep(0.8)

        time.sleep(1.5)
        ctx.close()
        br.close()

    # ── verdict ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print(" VERDICT (measured against the External-MCPs reference)")
    print("=" * 74)
    ok_all = True
    html = ["<!doctype html><meta charset='utf-8'><title>Dialog standardization</title>",
            "<style>body{background:#2b2f3a;color:#eee;font-family:Nunito,sans-serif;padding:24px}",
            "table{border-collapse:collapse;width:100%;margin-bottom:26px}",
            "td,th{border:1px solid #555;padding:7px 9px;font-size:.86rem;text-align:left}",
            "th{background:#444853}.ok{color:#7fe6d2;font-weight:700}.bad{color:#ff9c9c;font-weight:700}",
            "img{max-width:100%;border:1px solid #555;border-radius:8px;margin:6px 0 22px}</style>",
            "<h1>Tlamatini - dialog standardization</h1>",
            "<p>Every dialog measured against the External-MCPs reference "
            "(panel #4a4f5c, chrome #444853, radius 8px, teal #55bbaa).</p>",
            "<table><tr><th>Dialog</th><th>Panel</th><th>Radius</th>"
            "<th>Header</th><th>Footer</th><th>Teal button</th><th>Verdict</th></tr>"]

    for label, got, _shot in rows:
        checks = {
            "panel":  got.get("panel_bg") == CANON["panel_bg"],
            "radius": got.get("radius") == CANON["radius"],
            "chrome": got.get("chrome_bg") == CANON["chrome_bg"],
            "footer": got.get("footer_bg") == CANON["chrome_bg"],
            "teal":   got.get("primary") == CANON["primary"],
        }
        good = got.get("found") and all(checks.values())
        ok_all = ok_all and good
        print(" %-30s %s" % (label, "PASS" if good else
                             "FAIL " + ",".join(k for k, v in checks.items() if not v)))
        cls = "ok" if good else "bad"
        html.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td class='%s'>%s</td></tr>"
            % (label, got.get("panel_bg"), got.get("radius"), got.get("chrome_bg"),
               got.get("footer_bg"), got.get("primary"), cls,
               "PASS" if good else "FAIL"))
    html.append("</table>")

    for label, _got, shot in rows:
        if shot:
            html.append("<h2>%s</h2><img src='%s'>" % (label, os.path.basename(shot)))

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html.append("<p style='color:#9ca2ba'>Generated %s - photos by Shoter.</p>" % stamp)
    summary = os.path.join(OUT, "SUMMARY.html")
    open(summary, "w", encoding="utf-8").write("\n".join(html))
    print("\n summary: %s" % summary)
    print(" RESULT : %s" % ("ALL DIALOGS STANDARDIZED" if ok_all
                            else "DRIFT REMAINS - see table"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
