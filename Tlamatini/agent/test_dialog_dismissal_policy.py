# Tlamatini Author Banner - do not remove (releases scrub the name automatically)
"""DIALOG DISMISSAL POLICY - COVERAGE AUDIT  (Angela, 2026-08-13)

    A dialog disappears ONLY by its titlebar X, its Cancel button, or its
    Continue button. X behaves exactly like Cancel. Never an outside click,
    never Escape. Every dialog, both pages, every corner.

TWO INSTRUMENTS, AND THEY ARE NOT INTERCHANGEABLE - read this before adding
a test here:

  * THIS FILE IS A COVERAGE AUDIT, NOT A BEHAVIOUR TEST. Its job is to prove
    that NO UNMIGRATED DISMISSAL SITE EXISTS ANYWHERE in the tree - a question
    about the whole codebase, which only a whole-codebase scan can answer. It
    is the thing that makes "every single dialog" checkable instead of a claim.
  * THE BEHAVIOUR is proven by the HEADED Playwright run
    (.claude/skills/tlamatini-daily-chat-test/harness/dialog_policy_visible.py),
    which opens every dialog in a real Chrome on Angela's desktop, clicks
    outside, presses Escape, and asserts the dialog is STILL THERE.

Asserting on source text is NOT a substitute for exercising the UI - that
mistake is exactly what made `test_preserved_user_state.py` worthless. Here the
scan IS the subject: "does a forbidden pattern survive anywhere".
"""
from __future__ import annotations

import os
import re

from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
_JS = os.path.join(_HERE, "static", "agent", "js")
_TPL = os.path.join(_HERE, "templates", "agent")
_PAGES = ("agent_page.html", "agentic_control_panel.html")

# Dismissal patterns that must not exist anywhere. Each entry is
# (compiled regex, why it is forbidden).
_FORBIDDEN = (
    (re.compile(r"e\.target\s*===\s*(overlay|dlg)\b"),
     "outside/backdrop click closes the dialog"),
    (re.compile(r"<div[^>]*-overlay\"[^>]*onclick\s*=\s*\"Close"),
     "the overlay div itself closes on click"),
    (re.compile(r"closeOnEscape\s*:\s*true"),
     "Escape closes this dialog"),
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _js_files():
    for name in sorted(os.listdir(_JS)):
        if name.endswith(".js"):
            yield name, os.path.join(_JS, name)


class NoDismissalEscapeHatchSurvivesTests(SimpleTestCase):
    """The whole-tree sweep. A new dialog cannot quietly reintroduce one."""

    def test_no_outside_click_or_escape_dismissal_anywhere(self):
        offenders = []
        targets = list(_js_files())
        targets += [(p, os.path.join(_TPL, p)) for p in _PAGES]
        for label, path in targets:
            text = _read(path)
            for rx, why in _FORBIDDEN:
                for m in rx.finditer(text):
                    line = text[:m.start()].count("\n") + 1
                    offenders.append(f"{label}:{line} - {why}: {m.group(0)!r}")
        self.assertEqual(
            offenders, [],
            "A dialog can still be dismissed by clicking outside or pressing "
            "Escape. Route it through the policy layer instead:\n  "
            + "\n  ".join(offenders))

    def test_every_page_loads_the_policy_before_its_dialog_modules(self):
        for page in _PAGES:
            text = _read(os.path.join(_TPL, page))
            self.assertIn(
                "dialog_policy.js", text,
                f"{page} does not load the dialog policy at all.")
            policy_at = text.index("dialog_policy.js")
            jqui_at = text.index("jquery-ui")
            self.assertLess(
                jqui_at, policy_at,
                f"{page} loads dialog_policy.js BEFORE jQuery UI - the widget "
                "defaults patch would silently do nothing.")


class PolicyLayerContractTests(SimpleTestCase):
    """The mechanisms the audit above depends on must actually be there."""

    def setUp(self):
        self.src = _read(os.path.join(_JS, "dialog_policy.js"))

    def test_escape_is_disarmed_for_all_three_dialog_technologies(self):
        self.assertIn("closeOnEscape = false", self.src,
                      "jQuery UI dialogs would still close on Escape.")
        self.assertIn("'cancel'", self.src,
                      "native <dialog> Escape (the `cancel` event) is not "
                      "intercepted.")
        self.assertIn("keyboard = false", self.src,
                      "Bootstrap modals would still close on Escape.")
        self.assertIn("backdrop = 'static'", self.src,
                      "Bootstrap modals would still close on a backdrop click.")

    def test_the_titlebar_close_restore_is_deferred(self):
        """jQuery UI fires `dialogopen` BEFORE the dialog's own `open:`
        callback, so a synchronous handler loses to a callback that hides the
        X (acp-control-buttons.js does exactly that). The restore must be
        deferred a tick or the X silently stays hidden."""
        block = self.src.split("dialogopen", 1)[1].split("});", 1)[0]
        self.assertIn("setTimeout", block)

    def test_escape_is_only_swallowed_while_a_custom_overlay_is_open(self):
        """Escape must keep working elsewhere - the ACP canvas uses it to
        cancel an in-progress connection drag."""
        self.assertIn("aCustomOverlayIsVisible", self.src)


#: Modules that have been fully migrated onto the THEMED popups. A native
#: alert/confirm/prompt in one of these is a regression, not a style opinion.
#: ADD YOUR NEW DIALOG MODULE HERE once you have migrated it.
_THEMED_DIALOG_MODULES = ("contacts_dialog.js", "external_mcps_dialog.js")

#: A bare call, and the `window.`-qualified form, with comments already gone.
_NATIVE_POPUP_RES = (
    re.compile(r"(?<![.\w$])(alert|confirm|prompt)\s*\("),
    re.compile(r"window\s*\.\s*(alert|confirm|prompt)\s*\("),
)


def _strip_comments(js: str) -> str:
    """Drop /* block */ and // line comments.

    Same lesson as `test_dialog_theme._rule_body`: parse the code, not the
    essay. Every migrated call site keeps a comment SAYING which native popup
    it replaced ("the old synchronous confirm() was the last native popup this
    dialog raised"), so a naive scan flags the sentence that documents the fix.
    """
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)//.*$", "", js)


class NoNativePopupSurvivesInThemedDialogsTests(SimpleTestCase):
    """The last nine native popups (Angela's review, 2026-08-16).

    contacts_dialog.js (2) and external_mcps_dialog.js (7) still raised
    `alert()` / `confirm()` long after every other dialog wore the theme - the
    two NEWEST dialogs were the last two showing a grey Windows/Chrome strip
    with the page URL in it, in the middle of a dark themed application. No CSS
    can reach those; they are not even the same rendering engine. They also
    BLOCK the page, which is why they cannot be photographed by the headed
    Playwright runs that prove everything else.
    """

    def test_no_native_popup_in_a_themed_dialog_module(self):
        offenders = []
        for name in _THEMED_DIALOG_MODULES:
            code = _strip_comments(_read(os.path.join(_JS, name)))
            for rx in _NATIVE_POPUP_RES:
                for m in rx.finditer(code):
                    line = code[:m.start()].count("\n") + 1
                    offenders.append(f"{name}:~{line} - {m.group(0)!r}")
        self.assertEqual(
            offenders, [],
            "A native browser popup came back in a themed dialog. Use "
            "tlmAlert(...) / tlmConfirm(...) from dialog_policy.js instead - "
            "they render the app's own modal ABOVE the native dialogs "
            "(z-index 100001) and obey the dismissal policy:\n  "
            + "\n  ".join(offenders))

    def test_the_themed_popup_helpers_exist_and_are_exported(self):
        src = _read(os.path.join(_JS, "dialog_policy.js"))
        for needed in ("function tlmAlert", "function tlmConfirm",
                       "window.tlmAlert", "window.tlmConfirm"):
            self.assertIn(needed, src,
                          f"dialog_policy.js must define/export {needed} - the "
                          "themed dialogs call it bare.")

    def test_the_themed_popup_fails_open_to_the_native_one(self):
        """A lost warning is worse than an ugly one.

        If the host cannot be built (no document.body yet, a DOM exception),
        the native popup MUST still fire. acp-globals.js made the same call for
        the canvas; both surfaces keep it.
        """
        src = _read(os.path.join(_JS, "dialog_policy.js"))
        self.assertIn("window.alert(text)", src,
                      "tlmAlert must fall back to the native alert.")
        self.assertIn("window.confirm(joined)", src,
                      "tlmConfirm must fall back to the native confirm.")

    def test_the_popup_host_is_escape_swallowed_like_every_other_overlay(self):
        src = _read(os.path.join(_JS, "dialog_policy.js"))
        overlays = src.split("CUSTOM_OVERLAYS", 1)[1].split("]", 1)[0]
        self.assertIn("#tlm-popup-host", overlays,
                      "The themed popup host must be listed in CUSTOM_OVERLAYS "
                      "or Escape would dismiss it while every other overlay "
                      "ignores Escape.")

    def test_the_popup_outranks_the_native_modals_it_is_raised_over(self):
        """z-index is load-bearing here, not decoration.

        These popups are raised BY native modals at z-index 20000. A confirm
        rendered underneath the dialog that asked for it is an invisible modal,
        i.e. a hang - which is also why they are not jQuery-UI dialogs
        (`.ui-front` is ~100).
        """
        css = _read(os.path.join(_HERE, "static", "agent", "css",
                                 "dialog_theme.css"))
        block = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertIn(".tlmpop-overlay", block,
                      "dialog_theme.css must own the themed popup's look.")
        body = block.split(".tlmpop-overlay", 1)[1].split("}", 1)[0]
        found = re.search(r"z-index\s*:\s*(\d+)", body)
        self.assertIsNotNone(found, "The popup overlay must set a z-index.")
        self.assertGreater(
            int(found.group(1)), 20000,
            "The themed popup must sit ABOVE the native modals (.emx-dialog / "
            ".ctb-dialog are at 20000) that raise it.")


class SealedUpdateDialogTests(SimpleTestCase):
    """The updater must be uninterruptible while it is running - and NOT
    afterwards, or a failed update leaves an unclosable dialog."""

    def setUp(self):
        self.src = _read(os.path.join(_JS, "agent_page_dialogs.js"))

    def test_close_is_gated_by_the_policy(self):
        block = self.src.split("function CloseUpdateDialog", 1)[1][:800]
        self.assertIn("mayClose('update')", block,
                      "the update dialog can be closed mid-update.")

    def test_the_seal_is_taken_when_the_update_starts(self):
        block = self.src.split("async function StartTlamatiniUpdate", 1)[1][:2000]
        self.assertIn("seal('update'", block)

    def test_the_seal_is_lifted_on_error_and_on_done_but_not_on_handoff(self):
        block = self.src.split("async function _pollUpdateStatus", 1)[1][:2500]
        self.assertEqual(
            block.count("unseal('update')"), 2,
            "expected exactly two unseal sites: phase 'error' and phase "
            "'done'. 'handoff' must stay sealed - the swapper is live and "
            "Tlamatini is closing.")
