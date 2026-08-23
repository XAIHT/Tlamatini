# Tlamatini Author Banner - do not remove
r"""
ESCAPE CLOSES EVERY DIALOG - VISIBLE REGRESSION, DRIVEN BY PLAYWRIGHTER
======================================================================

Angela, 2026-08-16: *"Standarize in every ... every dialog and all of the
dialog without exception that if 'Esc' is pressed then the dialog must be
closed with the similar action to 'cancel'/'dismiss' (doing nothing) for every
agent in agentic_control_panel.html for every asset on agent_page.html."*

`agent/test_dialog_dismissal_policy.py` proves no source file OPTS OUT of the
rule. Only this run proves the rule is TRUE in a browser. It was cited by that
test's docstring for three days before anybody noticed the file did not exist -
which is exactly the kind of claim this project does not get to make.

For every dialog on BOTH pages it does four things:

  1. opens it the way a person does (navbar entry, canvas right-click, button);
  2. photographs the whole desktop with **Shoter** - Tlamatini's own agent,
     never PIL (Angela's standing rule);
  3. presses **a real Escape** (`page.keyboard.press`, not a synthesised
     KeyboardEvent), through Tlamatini's own **Playwrighter** agent; and
  4. re-probes the DOM and photographs it again.

PASS = the dialog was OPEN before the key and GONE after it. The probe is
written here, in the harness, from plain selectors - it deliberately does NOT
call `TlamatiniDialogPolicy.topmostOpenDialog()`, because a test that asks the
code under test whether it worked is not a test.

NOT COVERED HERE, ON PURPOSE:
  * the OUTSIDE-CLICK half of the policy (unchanged by this work, and already
    swept by acp_dialog_full_sweep.py / dialog_theme_visible.py);
  * the exec-permission prompt and the SEALED updater, which cannot be raised
    without a live tool call / a real update in flight. Both are pinned by
    `agent/test_dialog_dismissal_policy.py::SealedUpdateDialogTests` and by
    the `close:` handler that turns any dismissal into DENY.

VISIBLE ONLY. There is no --headless flag and there never will be.

    python dialog_policy_visible.py            # both pages
    python dialog_policy_visible.py --chat     # chat page only
    python dialog_policy_visible.py --canvas   # ACP designer only
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwrighter_run import PlaywrighterError, failed_steps, run_steps  # noqa: E402

BASE = os.environ.get("TLM_BASE", "http://127.0.0.1:8010")
CHAT = BASE + "/agent/agent/"
ACP = BASE + "/agent/agentic_control_panel/"
OUT = os.path.join(r"C:\Development\Tlamatini\Temp", "dialog_policy_escape")
CHAT_STATE = os.environ.get(
    "TLM_CHAT_STATE",
    os.path.join(r"C:\Development\Tlamatini\Temp", "chat_session_state.json"))
ACP_STATE = os.environ.get(
    "TLM_ACP_STATE",
    os.path.join(r"C:\Development\Tlamatini\Temp", "acp_session_state.json"))
USER = os.environ.get("TLAMATINI_USER", "")
PASS = os.environ.get("TLAMATINI_PASS", "")

# ---------------------------------------------------------------------------
# THE PROBE - independent of dialog_policy.js on purpose.
#
# Reports every dialog-shaped element that is actually laid out right now.
# `getClientRects().length` is the one check that catches display:none, the
# `hidden` attribute and a zero-size node in a single question.
# ---------------------------------------------------------------------------
PROBE = """() => {
    const SELECTORS = [
        '.ui-dialog', '.tlmpop-overlay', '#modal',
        '.emx-modal', '.ctb-modal',
        '#about-overlay', '#update-overlay', '#tlm-voice-overlay',
        '#log-viewer-dialog', '#agent-description-dialog',
        '#parametrizer-dialog-overlay', '#parametrizer-error-overlay',
        '#flowcreator-progress-overlay', '#chat-img-preview-overlay'
    ];
    const open = [];
    for (const sel of SELECTORS) {
        document.querySelectorAll(sel).forEach(el => {
            if (el.hidden) return;
            if (el.getClientRects().length === 0) return;
            open.push(String(el.id || el.className).trim().split(/\\s+/)[0]);
        });
    }
    return open.length ? open.join('|') : 'NONE';
}"""

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

# Between dialogs: close by the app's own routes, then remove what survives.
# A leftover .ui-widget-overlay swallows every later click, so the NEXT dialog
# would silently never open and the whole run would read as a policy failure.
# NEVER clicks a Continue/OK - a sweep must not confirm anything.
CLEANUP = {
    "action": "evaluate", "name": "cleanup",
    "expression": """() => {
        for (const id of ['external-mcps-close', 'tlm-voice-close',
                          'contacts-cancel', 'log-viewer-close',
                          'agent-description-close']) {
            const b = document.getElementById(id);
            if (b) b.click();
        }
        document.querySelectorAll('.update-window .about-close-btn')
            .forEach(b => b.click());
        document.querySelectorAll('.ui-dialog:not([style*="display: none"]) button')
            .forEach(b => { if (/cancel|dismiss/i.test(b.textContent || '')) b.click(); });
        try {
            $('.ui-dialog-content').each(function () {
                try { $(this).dialog('close'); } catch (e) { /* not a dialog */ }
            });
        } catch (e) { /* jQuery UI absent */ }
        document.querySelectorAll('.ui-widget-overlay').forEach(e => e.remove());
        for (const id of ['about-overlay', 'update-overlay', 'modal',
                          'tlm-voice-overlay']) {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        }
        document.querySelectorAll('.tlmpop-overlay').forEach(e => e.remove());
        return 'clean';
    }"""}


def _menu(item_id):
    """Open a chat-navbar dialog by its menu-item id."""
    return [
        {"action": "evaluate", "expression": OPEN_MENU, "arg": item_id},
        {"action": "wait", "ms": 450},
        {"action": "click", "selector": "#" + item_id},
    ]


# (label, opener steps, settle-ms). The chat page, every dialog reachable from
# the navbar plus the Catalog of prompts.
CHAT_DIALOGS = [
    ("chat_01_external_mcps", _menu("external-mcps"), 2200),
    ("chat_02_voice_settings", _menu("config-voice"), 1400),
    ("chat_03_contacts_book", _menu("config-contacts"), 1800),
    ("chat_04_config_models", _menu("config-models"), 1600),
    ("chat_05_config_urls", _menu("config-urls"), 1600),
    ("chat_06_configure_mcps_tools", _menu("enable-mcps"), 1800),
    ("chat_07_configure_agents", _menu("enable-agents"), 1800),
    ("chat_08_configure_skills", _menu("configure-skills"), 1800),
    ("chat_09_browse_skills", _menu("browse-skills"), 1800),
    ("chat_10_access_keys_wizard", _menu("access-keys-wizard"), 2000),
    ("chat_11_check_for_updates", _menu("check-updates-button"), 2600),
    # The Catalog is the one dialog with NO X and NO Cancel - it exists here
    # precisely because it is the case a blind "hide the node" dismissal gets
    # wrong (it would leave body.style.overflow clamped).
    ("chat_12_catalog_of_prompts",
     [{"action": "click", "selector": "#prompts-catalog"}], 2200),
    # The themed popup, raised ABOVE a native modal at z-index 20000. Escape
    # must dismiss THIS and leave the dialog underneath alone - the exact case
    # stopImmediatePropagation() exists for.
    ("chat_13_themed_confirm_over_dialog",
     _menu("config-contacts") + [
         {"action": "wait", "ms": 1200},
         {"action": "evaluate", "expression":
          "() => { tlmConfirm('Escape must dismiss THIS, not the dialog "
          "underneath it.', 'Harness probe', 'Please confirm'); return 'raised'; }"},
     ], 1200),
]

# The ACP designer. A canvas agent has to exist before its configuration
# dialog can be opened, so the first entry drags one on.
CANVAS_PRELUDE = [
    {"action": "goto", "url": ACP},
    {"action": "wait_for", "selector": "#agents-list .agent-tool-item",
     "state": "visible"},
    {"action": "wait", "ms": 2200},
    # `target_position` is the agent's own parameter name. Dropping dead-centre
    # stacks every node on the same coordinates, so the drop point is explicit.
    {"action": "drag_to", "selector": ".agent-tool-item[data-content='Parametrizer']",
     "target": "#canvas-content", "target_position": {"x": 240, "y": 130}},
    {"action": "wait", "ms": 700},
    {"action": "drag_to", "selector": ".agent-tool-item[data-content='Executer']",
     "target": "#canvas-content", "target_position": {"x": 470, "y": 130}},
    {"action": "wait_for", "selector": ".canvas-item", "state": "visible"},
    {"action": "wait", "ms": 900},
]

def _ctx(item, entry):
    """Right-click a canvas AGENT and pick one context-menu entry."""
    return [
        {"action": "right_click", "selector": ".canvas-item[id^='" + item + "']"},
        {"action": "wait_for", "selector": "#agent-context-menu", "state": "visible"},
        {"action": "wait", "ms": 450},
        {"action": "click", "selector": "#" + entry},
    ]


CANVAS_DIALOGS = [
    # "for every agent in agentic_control_panel.html" - the per-agent
    # configuration dialog is the one Angela named.
    ("acp_01_agent_configuration", _ctx("executer", "ctx-menu-configure"), 1800),
    ("acp_02_agent_description", _ctx("executer", "ctx-menu-description"), 1400),
    ("acp_03_log_viewer", _ctx("executer", "ctx-menu-view-log"), 1600),
    # An UNWIRED Parametrizer refuses to map and raises its validation error -
    # a dialog whose ONLY control is "OK". It is here precisely because it is
    # the case the label scan must NOT solve by matching an affirmative word:
    # a one-button dialog is an acknowledgement, and that button is its way out.
    ("acp_04_parametrizer_error", _ctx("parametrizer", "ctx-menu-configure"), 1800),
    ("acp_05_clear_confirmation", [
        {"action": "click", "selector": "#btn-clear"},
    ], 1600),
    ("acp_06_start_validation", [
        {"action": "click", "selector": "#btn-start"},
    ], 2200),
    # The canvas's own themed popup pair (acpAlert / acpConfirm).
    ("acp_07_acp_confirm", [
        {"action": "evaluate", "expression":
         "() => { acpConfirm('Escape must dismiss this and resolve FALSE.', "
         "'', 'Harness probe'); return 'raised'; }"},
    ], 1200),
]


def sweep(label, opener, settle):
    """Open it, photograph it, press a real Escape, photograph it again."""
    return (
        opener
        + [{"action": "wait", "ms": settle},
           {"action": "evaluate", "name": label + ".before", "expression": PROBE},
           {"action": "shoter", "dir": OUT, "filename": label + "_1_open.png",
            "name": label + ".shot_open"},
           # THE KEY. No selector -> page.keyboard.press(), so it lands on
           # whatever really has focus, exactly like a person pressing it.
           {"action": "press", "key": "Escape"},
           {"action": "wait", "ms": 900},
           {"action": "evaluate", "name": label + ".after", "expression": PROBE},
           {"action": "shoter", "dir": OUT, "filename": label + "_2_after_esc.png",
            "name": label + ".shot_after"},
           CLEANUP,
           {"action": "wait", "ms": 600}]
    )


# ---------------------------------------------------------------------------
# THE ONE DIALOG THAT MUST *SURVIVE* ESCAPE.
#
# Angela, 2026-08-16: the Check-for-updates dialog must ignore Escape - and
# every other close - WHILE A DOWNLOAD IS IN PROGRESS.
#
# ⚠️ THIS DOES NOT START A REAL UPDATE. That would download a release and swap
# Angela's installation; a test may not do that to her machine. `seal('update')`
# puts the policy in the EXACT state `StartTlamatiniUpdate` puts it in - same
# key, same module, same `dismissDialog` branch - and that state IS the subject.
# The seal is lifted again afterwards so the run leaves nothing sealed behind.
SEAL_UPDATE = """() => {
    const p = window.TlamatiniDialogPolicy;
    if (!p || !p.seal) return 'no-policy';
    p.seal('update', 'HARNESS: pretending a download is in progress.',
           document.getElementById('update-overlay'));
    return p.isSealed('update') ? 'sealed' : 'not-sealed';
}"""

UNSEAL_UPDATE = """() => {
    const p = window.TlamatiniDialogPolicy;
    if (p && p.unseal) p.unseal('update');
    return p && p.isSealed('update') ? 'STILL-SEALED' : 'unsealed';
}"""

# A RELOAD destroys the page and the dialog with it, so "the dialog is still
# there" is only meaningful if the page never reloaded. This canary is wiped by
# any reload, so reading it back proves the F5 was actually swallowed rather
# than the dialog happening to be re-opened.
CANARY_SET = """() => { window.__tlmSealCanary = 'alive'; return 'set'; }"""
CANARY_READ = """() => (window.__tlmSealCanary === 'alive'
    ? 'alive' : 'PAGE-WAS-RELOADED')"""

# ⚠️ WHAT THIS CAN AND CANNOT PROVE, so the green tick is not read as more than
# it is. Playwright dispatches keys through CDP, straight at the document - so
# Ctrl+W and Ctrl+F4 ARRIVE here even though Chrome RESERVES them and never
# delivers a real user's Ctrl+W to a page. Pressing them is still worth doing
# (it proves our handler classifies and swallows them, which is what matters in
# any browser that does deliver them), but F5 is the honest one: a human's F5
# really does reach the page, and really is blocked.
SEALED_CLOSE_KEYS = ["Escape", "Escape", "Escape", "Control+F4", "Control+w", "F5"]

#: Labels whose PASS condition is inverted: the dialog must still be there.
SEALED_LABELS = set()


def sweep_sealed(label, opener, settle):
    """Open it, SEAL it, hammer every close key, prove it is STILL THERE."""
    SEALED_LABELS.add(label)
    hammer = []
    for key in SEALED_CLOSE_KEYS:
        hammer += [{"action": "press", "key": key},
                   {"action": "wait", "ms": 350}]
    return (
        opener
        + [{"action": "wait", "ms": settle},
           {"action": "evaluate", "name": label + ".seal", "expression": SEAL_UPDATE},
           {"action": "evaluate", "name": label + ".canary_set",
            "expression": CANARY_SET},
           {"action": "evaluate", "name": label + ".before", "expression": PROBE},
           {"action": "shoter", "dir": OUT, "filename": label + "_1_open.png",
            "name": label + ".shot_open"}]
        # Three Escapes, not one: a single Escape that fails to close it could
        # be an accident of focus; three is a rule. Then the close/reload keys.
        + hammer
        + [{"action": "wait", "ms": 500},
           {"action": "evaluate", "name": label + ".canary", "expression": CANARY_READ},
           {"action": "evaluate", "name": label + ".after", "expression": PROBE},
           {"action": "shoter", "dir": OUT, "filename": label + "_2_after_esc.png",
            "name": label + ".shot_after"},
           {"action": "evaluate", "name": label + ".unseal",
            "expression": UNSEAL_UPDATE},
           CLEANUP,
           {"action": "wait", "ms": 600}]
    )


CHAT_SEALED = [
    ("chat_14_sealed_update_ignores_escape", _menu("check-updates-button"), 2600),
]


def build_steps(do_chat, do_canvas):
    steps = []
    dialogs = []
    if do_chat:
        steps += [
            {"action": "goto", "url": CHAT},
            {"action": "wait_for", "selector": "#mcps-menu-button", "state": "attached"},
            {"action": "wait", "ms": 2500},
        ]
        for label, opener, settle in CHAT_DIALOGS:
            steps += sweep(label, opener, settle)
            dialogs.append(label)
        # Last, so a sealed dialog can never leak into the dialogs before it.
        for label, opener, settle in CHAT_SEALED:
            steps += sweep_sealed(label, opener, settle)
            dialogs.append(label)
    if do_canvas:
        steps += CANVAS_PRELUDE
        for label, opener, settle in CANVAS_DIALOGS:
            steps += sweep(label, opener, settle)
            dialogs.append(label)
    return steps, dialogs


def main():
    args = [a.lower() for a in sys.argv[1:]]
    if "--headless" in args:
        print("!! HEADLESS IS FORBIDDEN. Angela must be able to WATCH the run.")
        return 2
    do_chat = "--canvas" not in args
    do_canvas = "--chat" not in args

    os.makedirs(OUT, exist_ok=True)
    print("=" * 78)
    print(" TLAMATINI - ESCAPE CLOSES EVERY DIALOG   (driven by PLAYWRIGHTER)")
    print(" rule    : Escape === titlebar X === Cancel (dismiss, doing nothing)")
    print(" browser : Tlamatini's Playwrighter agent, headed real Chrome")
    print(" photos  : Tlamatini's Shoter agent (never PIL) -> %s" % OUT)
    print(" base    : %s" % BASE)
    print("=" * 78)

    state = CHAT_STATE if do_chat else ACP_STATE
    if not os.path.isfile(state):
        if not (USER and PASS):
            print("!! No session at %s and no TLAMATINI_USER / TLAMATINI_PASS set."
                  % state)
            print("   Either create the session state once, or export the two")
            print("   env vars so the harness can log in itself.")
            return 2
        state = ""

    steps, dialogs = build_steps(do_chat, do_canvas)
    if not state:
        steps = [
            {"action": "goto", "url": BASE + "/"},
            {"action": "fill", "selector": "#id_username", "value": USER},
            {"action": "fill", "selector": "#id_password", "value": PASS},
            {"action": "click", "selector": "form button[type=submit]"},
            {"action": "wait", "ms": 2500},
        ] + steps

    print("-- handing %d steps to Playwrighter (%d dialogs)..."
          % (len(steps), len(dialogs)))
    try:
        result = run_steps(steps, runtime_base=OUT,
                           start_url=CHAT if do_chat else ACP,
                           storage_state_in=state, headless=False,
                           hold_open_seconds=2, timeout=3000)
    except PlaywrighterError as exc:
        print("!! Playwrighter could not start: %s" % exc)
        return 2

    print("-- Playwrighter status=%s  steps ok=%d/%d"
          % (result["status"], result["steps_run"], result["steps_total"]))
    for bad in failed_steps(result)[:14]:
        print("   !! step %s (%s): %s"
              % (bad.get("index"), bad.get("action"), str(bad.get("error"))[:110]))

    values = result["extracted"]

    print("\n" + "=" * 78)
    print(" VERDICT - did Escape dismiss it?")
    print("=" * 78)

    rows = []
    ok_all = True
    for label in dialogs:
        before = values.get(label + ".before", "")
        after = values.get(label + ".after", "")
        opened = bool(before) and before != "NONE"
        if label in SEALED_LABELS:
            # INVERTED: this one must SURVIVE every close key we can send.
            survived = "update-overlay" in after
            # A reload would destroy the page AND re-open nothing, so without
            # the canary "the dialog is gone" and "F5 worked" look identical.
            no_reload = values.get(label + ".canary", "") == "alive"
            good = opened and survived and no_reload
            if not opened:
                verdict = "FAIL - never opened"
            elif not no_reload:
                verdict = "FAIL - THE PAGE RELOADED (F5 was not blocked)"
            elif not survived:
                verdict = "FAIL - A CLOSE KEY KILLED A SEALED DIALOG"
            else:
                verdict = "PASS - ignored Esc x3 / Ctrl+F4 / Ctrl+W / F5"
        else:
            closed = after == "NONE"
            # A stacked case (the themed popup over a dialog) legitimately
            # leaves the dialog underneath OPEN - that is the point of that
            # test. So "closed" also holds when strictly FEWER layers remain.
            if not closed and opened:
                closed = len(after.split("|")) < len(before.split("|"))
            good = opened and closed
            verdict = "PASS" if good else ("FAIL - never opened" if not opened
                                           else "FAIL - Escape did not dismiss")
        ok_all = ok_all and good
        print(" %-38s %-6s  before=%-28s after=%s"
              % (label, "PASS" if good else "FAIL", before or "-", after or "-"))
        rows.append((label, before or "-", after or "-", good, verdict))

    html = ["<!doctype html><meta charset='utf-8'><title>Escape closes every dialog</title>",
            "<style>body{background:#2b2f3a;color:#eee;font-family:Nunito,sans-serif;padding:24px}",
            "table{border-collapse:collapse;width:100%;margin-bottom:26px}",
            "td,th{border:1px solid #555;padding:7px 9px;font-size:.86rem;text-align:left}",
            "th{background:#444853}.ok{color:#7fe6d2;font-weight:700}.bad{color:#ff9c9c;font-weight:700}",
            "img{max-width:48%;border:1px solid #555;border-radius:8px;margin:6px 4px 22px}</style>",
            "<h1>Tlamatini - Escape closes every dialog</h1>",
            "<p>Rule: <b>Escape === titlebar X === Cancel</b> (dismiss, doing nothing). "
            "Browser driven by <b>Playwrighter</b>; photos by <b>Shoter</b>. "
            "Left = dialog open, right = after a real Escape keypress.</p>",
            "<table><tr><th>Dialog</th><th>Open before Esc</th><th>After Esc</th>"
            "<th>Verdict</th></tr>"]
    for label, before, after, good, verdict in rows:
        html.append("<tr><td>%s</td><td>%s</td><td>%s</td><td class='%s'>%s</td></tr>"
                    % (label, before, after, "ok" if good else "bad", verdict))
    html.append("</table>")
    for label, _b, _a, _g, _v in rows:
        html.append("<h2>%s</h2>" % label)
        for suffix in ("_1_open.png", "_2_after_esc.png"):
            shot = os.path.join(OUT, label + suffix)
            if os.path.isfile(shot):
                html.append("<img src='%s'>" % (label + suffix))
            else:
                html.append("<p class='bad'>NO PHOTO: %s</p>" % (label + suffix))

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html.append("<p style='color:#9ca2ba'>Generated %s - browser by Playwrighter, "
                "photos by Shoter.</p>" % stamp)
    summary = os.path.join(OUT, "SUMMARY.html")
    with open(summary, "w", encoding="utf-8") as fh:
        fh.write("\n".join(html))
    print("\n summary  : %s" % summary)
    print(" agent log: %s" % result.get("runtime"))
    print(" RESULT   : %s" % ("ESCAPE DISMISSES EVERY DIALOG"
                              if ok_all else "SOME DIALOGS IGNORED ESCAPE - see table"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
