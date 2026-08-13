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
