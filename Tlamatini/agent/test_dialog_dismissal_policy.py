# Tlamatini Author Banner - do not remove (releases scrub the name automatically)
"""DIALOG DISMISSAL POLICY - COVERAGE AUDIT  (Angela, 2026-08-13)

    A dialog disappears ONLY by its titlebar X, its Cancel button, its
    Continue button, or the ESCAPE KEY. X behaves exactly like Cancel, and
    ESCAPE behaves exactly like X. Never an outside click. Every dialog, both
    pages, every corner.

ESCAPE FLIPPED ON 2026-08-16, ON ANGELA'S EXPLICIT INSTRUCTION. Until that day
the rule read "never Escape" and this file's job was to prove Escape was
DISARMED everywhere. It now proves the opposite - that Escape is ARMED
everywhere and that it dismisses the way Cancel does, i.e. WITHOUT taking any
action on the user's behalf. The outside-click half of the rule is UNCHANGED
and its assertions are untouched.

TWO INSTRUMENTS, AND THEY ARE NOT INTERCHANGEABLE - read this before adding
a test here:

  * THIS FILE IS A COVERAGE AUDIT, NOT A BEHAVIOUR TEST. Its job is to prove
    that NO UNMIGRATED DISMISSAL SITE EXISTS ANYWHERE in the tree - a question
    about the whole codebase, which only a whole-codebase scan can answer. It
    is the thing that makes "every single dialog" checkable instead of a claim.
  * THE BEHAVIOUR is proven by the HEADED Playwright run
    (.claude/skills/tlamatini-daily-chat-test/harness/dialog_policy_visible.py),
    which opens every dialog in a real Chrome on Angela's desktop, clicks
    outside (it must STAY), and presses Escape (it must GO).

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


def _read(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _strip_comments(js: str) -> str:
    """Drop /* block */ and // line comments.

    Same lesson as `test_dialog_theme._rule_body`: parse the code, not the
    essay. Every migrated call site keeps a comment SAYING what it replaced
    ("The dialog was modal:true, closeOnEscape:false and its titlebar X is
    hidden"), so a naive scan flags the sentence that documents the fix.
    """
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)//.*$", "", js)


def _js_files():
    for name in sorted(os.listdir(_JS)):
        if name.endswith(".js"):
            yield name, os.path.join(_JS, name)


# Dismissal patterns that must not exist anywhere. Each entry is
# (compiled regex, why it is forbidden).
_FORBIDDEN = (
    (re.compile(r"e\.target\s*===\s*(overlay|dlg)\b"),
     "outside/backdrop click closes the dialog"),
    (re.compile(r"<div[^>]*-overlay\"[^>]*onclick\s*=\s*\"Close"),
     "the overlay div itself closes on click"),
    # THE FLIPPED ONE. `closeOnEscape: true` used to be the offence; opting OUT
    # of Escape is the offence now. A module that sets it false is a dialog the
    # user cannot dismiss with the key every other dialog answers to.
    (re.compile(r"closeOnEscape\s*[:=]\s*false"),
     "this dialog opts OUT of Escape; Escape must dismiss every dialog"),
)


class NoDismissalEscapeHatchSurvivesTests(SimpleTestCase):
    """The whole-tree sweep. A new dialog cannot quietly reintroduce one."""

    def test_no_outside_click_or_escape_optout_anywhere(self):
        offenders = []
        for label, path in _js_files():
            text = _strip_comments(_read(path))
            for rx, why in _FORBIDDEN:
                for m in rx.finditer(text):
                    line = text[:m.start()].count("\n") + 1
                    offenders.append(f"{label}:~{line} - {why}: {m.group(0)!r}")
        for page in _PAGES:
            text = _read(os.path.join(_TPL, page))
            for rx, why in _FORBIDDEN:
                for m in rx.finditer(text):
                    line = text[:m.start()].count("\n") + 1
                    offenders.append(f"{page}:{line} - {why}: {m.group(0)!r}")
        self.assertEqual(
            offenders, [],
            "A dialog can still be dismissed by clicking outside, or refuses "
            "to be dismissed by Escape. Route it through the policy layer "
            "instead:\n  " + "\n  ".join(offenders))

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

    def test_the_policy_is_the_first_document_keydown_handler_on_each_page(self):
        """Ordering is not cosmetic here.

        The dispatcher calls stopImmediatePropagation() when it dismisses, and
        that only stops listeners registered on `document` AFTER it. Several
        dialogs (External MCPs, Contacts, About/Update) bind their own
        document-level Escape handler, so the policy has to be loaded before
        every one of them or a single Escape closes two stacked layers.
        """
        for page in _PAGES:
            text = _read(os.path.join(_TPL, page))
            policy_at = text.index("dialog_policy.js")
            for module in ("external_mcps_dialog.js", "contacts_dialog.js",
                           "agent_page_dialogs.js", "tools_dialog.js",
                           "chat_image_paste.js", "acp-canvas-core.js"):
                at = text.find(module)
                if at == -1:
                    continue        # not loaded on this page
                self.assertLess(
                    policy_at, at,
                    f"{page} loads {module} BEFORE dialog_policy.js, so that "
                    "module's own document keydown handler would run first and "
                    "stopImmediatePropagation() could not protect it.")


class PolicyLayerContractTests(SimpleTestCase):
    """The mechanisms the audit above depends on must actually be there."""

    def setUp(self):
        self.src = _read(os.path.join(_JS, "dialog_policy.js"))

    def test_escape_is_armed_for_all_three_dialog_technologies(self):
        self.assertIn("closeOnEscape = true", self.src,
                      "jQuery UI dialogs would not close on Escape.")
        self.assertIn("keyboard = true", self.src,
                      "Bootstrap modals would not close on Escape.")
        self.assertNotIn(
            "addEventListener('cancel'", self.src,
            "the native <dialog> `cancel` event is being intercepted again - "
            "`cancel` IS the platform's Escape/dismiss, so blocking it puts "
            "the old 'Escape never closes' rule back for native dialogs.")

    def test_the_outside_click_half_of_the_rule_is_untouched(self):
        """Angela flipped Escape, and ONLY Escape. A click on the backdrop
        must still do nothing - that is what protects a half-filled form."""
        self.assertIn("backdrop = 'static'", self.src,
                      "Bootstrap modals would close on a backdrop click.")

    def test_the_titlebar_close_restore_is_deferred(self):
        """jQuery UI fires `dialogopen` BEFORE the dialog's own `open:`
        callback, so a synchronous handler loses to a callback that hides the
        X (acp-control-buttons.js does exactly that). The restore must be
        deferred a tick or the X silently stays hidden."""
        block = self.src.split("dialogopen", 1)[1].split("});", 1)[0]
        self.assertIn("setTimeout", block)

    def test_escape_only_acts_while_a_dialog_is_actually_open(self):
        """Escape must keep working elsewhere - the ACP canvas hides its agent
        tooltip with it and the avatar stops speaking."""
        self.assertIn("topmostOpenDialog", self.src)
        block = self.src.split("addEventListener('keydown'", 1)[-1]
        self.assertIn("if (!target) return;", block,
                      "the dispatcher must bail when no dialog is open instead "
                      "of swallowing the key for the whole page.")

    def test_the_dispatcher_runs_in_the_bubble_phase(self):
        """Load-bearing: the Catalog's search box clears the query on Escape
        and stops the event there, so the FIRST Escape empties the search and
        only the SECOND closes the catalog. A capture-phase listener steals
        both."""
        block = self.src.split("function dismissTopDialog", 1)[1]
        listener = block.split("addEventListener('keydown'", 1)[1]
        # Bound the slice to THIS registration. The file also contains the
        # sealed-key guard, which is deliberately capture-phase, so scanning to
        # end-of-file would flag a listener that is correct.
        end_bubble = listener.find("});")
        end_capture = listener.find("}, true);")
        self.assertNotEqual(end_bubble, -1,
                            "the Escape dispatcher registration never closes.")
        self.assertTrue(
            end_capture == -1 or end_bubble < end_capture,
            "the Escape dispatcher is registered in the CAPTURE phase; it must "
            "bubble so an inner widget can consume Escape first.")

    def test_the_dispatcher_stops_immediate_propagation_when_it_dismisses(self):
        """Otherwise Escape on a tlmConfirm raised OVER the External-MCPs
        dialog dismisses the confirm here and then lets that module close the
        dialog underneath it - two layers for one keystroke."""
        self.assertIn("stopImmediatePropagation", self.src)

    def test_the_dispatcher_presses_the_dialogs_own_dismiss_control(self):
        """It must never just hide a node: hiding skips the exec-permission
        prompt's DENY, acpConfirm's `false`, the sealed updater's refusal and
        every `body.style.overflow` restore."""
        self.assertIn("dialog('close')", self.src,
                      "jQuery UI dialogs must be closed through the widget.")
        self.assertIn("control.click()", self.src,
                      "hand-rolled dialogs must be dismissed by a REAL click "
                      "on their own X/Cancel, so their handlers run.")
        self.assertIn("mayClose", self.src,
                      "the seal gate must still exist for the updater.")

    def test_escape_can_never_press_an_affirmative_button(self):
        """Escape is Cancel. If the label scan could match an affirmative word
        it would be able to SUBMIT a dialog the user tried to abandon."""
        words = self.src.split("DISMISS_WORDS = [", 1)[1].split("]", 1)[0].lower()
        for forbidden in ("ok", "continue", "yes", "accept", "save", "delete",
                          "update", "proceed", "start", "aceptar"):
            self.assertNotIn(
                f"'{forbidden}'", words,
                f"'{forbidden}' is an AFFIRMATIVE label; Escape must never be "
                "able to click it.")

    def test_the_backdrops_are_excluded_from_dismissal(self):
        """`.ui-widget-overlay` also wears `.starter-execution-overlay`, so the
        `-overlay` shape matches it. Dismissing a backdrop would leave its
        panel floating over an undimmed page."""
        self.assertIn("ui-widget-overlay", self.src)
        self.assertIn("NOT_A_DIALOG", self.src)


#: Modules that have been fully migrated onto the THEMED popups. A native
#: alert/confirm/prompt in one of these is a regression, not a style opinion.
#: ADD YOUR NEW DIALOG MODULE HERE once you have migrated it.
_THEMED_DIALOG_MODULES = ("contacts_dialog.js", "external_mcps_dialog.js")

#: A bare call, and the `window.`-qualified form, with comments already gone.
_NATIVE_POPUP_RES = (
    re.compile(r"(?<![.\w$])(alert|confirm|prompt)\s*\("),
    re.compile(r"window\s*\.\s*(alert|confirm|prompt)\s*\("),
)


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

    def test_escape_resolves_the_themed_popup_as_a_dismissal(self):
        """Escape on a tlmConfirm must resolve `dismissValue` - which is FALSE.
        Resolving TRUE would let a keystroke authorise a destructive action.
        """
        src = _read(os.path.join(_JS, "dialog_policy.js"))
        block = src.split("host.addEventListener('keydown'", 1)[1][:700]
        self.assertIn("_popupTeardown(host, onDone, opts.dismissValue)", block,
                      "Escape on the themed popup neither closes it nor "
                      "resolves its promise - the caller would hang.")
        confirm_block = src.split("function tlmConfirm", 1)[1][:900]
        self.assertIn("dismissValue: false", confirm_block,
                      "tlmConfirm must dismiss to FALSE.")

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


class ButtonlessDialogsDeclareTheirDismissalTests(SimpleTestCase):
    """A dialog with no X and no Cancel needs an explicit hook.

    The dispatcher's last resort is to hide the node, and for the Catalog of
    prompts that would be WRONG rather than merely ugly: closeModal() also
    restores `document.body.style.overflow`, so a blind hide leaves the whole
    chat page unscrollable with no dialog on screen to explain why.
    """

    def test_the_catalog_of_prompts_exposes_tlm_dismiss(self):
        src = _read(os.path.join(_JS, "tools_dialog.js"))
        self.assertIn(
            "modal.tlmDismiss = closeModal", src,
            "The Catalog has no X and no Cancel button, so Escape can only "
            "dismiss it through an explicit `el.tlmDismiss` hook.")

    def test_the_dispatcher_honours_the_hook(self):
        src = _read(os.path.join(_JS, "dialog_policy.js"))
        self.assertIn("el.tlmDismiss", src)


class SealedUpdateDialogTests(SimpleTestCase):
    """The updater must be uninterruptible while it is running - and NOT
    afterwards, or a failed update leaves an unclosable dialog.

    ESCAPE DOES NOT BREAK THE SEAL, and that is the correct reading of "Escape
    behaves exactly like X": on a sealed dialog the X itself refuses, so
    Escape refuses too. Interrupting a half-applied update leaves the install
    directory in a mixed state.
    """

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

    def test_the_modules_own_escape_handler_defers_to_the_dispatcher(self):
        """Both handlers live on `document`. Without the guard a sealed update
        would run CloseUpdateDialog twice and raise the 'please wait' notice
        twice for one keystroke."""
        block = self.src.split("const aboutOverlay", 1)[0][-600:]
        self.assertIn("event.defaultPrevented", block,
                      "the About/Update Escape handler must bail when "
                      "dialog_policy.js has already dismissed the top dialog.")


class SealedDialogIsInvulnerableToEscapeTests(SimpleTestCase):
    """THE ONE EXCEPTION TO "Escape closes every dialog"  (Angela, 2026-08-16).

        *"make the only dialog invulnerable to 'Esc' (MUST IGNORE EVERY ESCAPE
        AND CLOSE OF ANY TYPE) ... the Check for updates dialog, while there is
        a download in progress."*

    It is not a special case bolted onto the dispatcher: a dialog declares
    `el.tlmSealKey`, and while that key is sealed NOTHING dismisses it. The
    updater is simply the first dialog to use it.
    """

    def setUp(self):
        self.policy = _read(os.path.join(_JS, "dialog_policy.js"))
        self.dialogs = _read(os.path.join(_JS, "agent_page_dialogs.js"))

    def test_the_seal_is_tested_before_every_dismissal_path(self):
        """Order is the whole guarantee.

        The last resort in `dismissDialog` HIDES the node. If the seal were
        checked anywhere but first, a sealed dialog whose X was missing or
        hidden would be hidden by that fallback with the seal never consulted -
        the update interrupted by exactly the fallback meant to help.
        """
        body = self.policy.split("function dismissDialog", 1)[1]
        seal_at = body.index("isSealed(sealKey)")
        for later, what in (("dialog('close')", "the jQuery UI close"),
                            ("control.click()", "the X/Cancel click"),
                            ("style.display = 'none'", "the last-resort hide")):
            self.assertLess(
                seal_at, body.index(later),
                "dismissDialog tests the seal AFTER %s; it must be the very "
                "first thing the function does." % what)

    def test_escape_on_a_sealed_dialog_is_swallowed_not_passed_on(self):
        """A refusal must still consume the keystroke.

        Otherwise the event reaches agent_page_dialogs.js's own document-level
        Escape handler, which calls CloseUpdateDialog again -> a SECOND "please
        wait" notice for one press of one key.
        """
        block = self.policy.split("var dismissed = dismissDialog(target);", 1)[1]
        block = block.split("});", 1)[0]
        self.assertIn("ev.preventDefault();", block)
        self.assertIn("ev.stopImmediatePropagation();", block)
        prevent_at = block.index("ev.preventDefault();")
        nudge_at = block.index("nudgeSealed(target)")
        self.assertLess(
            prevent_at, nudge_at,
            "the key must be consumed BEFORE the nudge, so an exception in the "
            "nudge can never let the keystroke escape to another handler.")

    def test_the_sealed_nudge_is_not_a_modal(self):
        """A modal per keypress would stack, and each notice would become the
        new topmost dialog - so the NEXT Escape would dismiss the notice
        instead of reaching the sealed dialog. It must be a passive cue."""
        body = self.policy.split("function nudgeSealed", 1)[1].split("\n    }", 1)[0]
        for forbidden in ("tlmAlert", "tlmConfirm", "mayClose", "window.alert"):
            self.assertNotIn(
                forbidden, body,
                "nudgeSealed must not raise %s - Escape has to be IGNORED, not "
                "answered with a dialog." % forbidden)
        self.assertIn("classList", body, "the nudge should be a CSS cue.")

    def test_the_update_overlay_is_bound_to_the_seal_when_it_opens(self):
        """Sealed but UNBOUND is still dismissible: `dismissDialog` looks the
        seal up through `el.tlmSealKey`, so the binding is what makes the
        updater invulnerable rather than merely 'refusing in CloseUpdateDialog'."""
        block = self.dialogs.split("function OpenCheckUpdatesDialog", 1)[1][:1400]
        self.assertIn("bindSeal(overlay, 'update')", block,
                      "OpenCheckUpdatesDialog must bind #update-overlay to the "
                      "'update' seal key.")

    def test_binding_happens_before_the_dialog_is_shown(self):
        block = self.dialogs.split("function OpenCheckUpdatesDialog", 1)[1][:1400]
        self.assertLess(
            block.index("bindSeal(overlay, 'update')"),
            block.index("overlay.style.display = 'flex'"),
            "bind the seal key BEFORE the dialog becomes visible, so there is "
            "no frame in which it is on screen and unbound.")

    def test_a_failed_start_always_lifts_the_seal(self):
        """The bug this prevents is worse than the one the seal prevents.

        `StartTlamatiniUpdate` seals BEFORE POSTing /agent/start_update/. If the
        request is rejected or throws, nothing is downloading - and if the seal
        stayed the user would own a dialog that ignores Escape, ignores its X
        and never goes away. Both failure paths must unseal.
        """
        block = self.dialogs.split("async function StartTlamatiniUpdate", 1)[1]
        block = block.split("async function _pollUpdateStatus", 1)[0]
        self.assertEqual(
            block.count("unseal('update')"), 2,
            "expected exactly two unseal sites in StartTlamatiniUpdate: the "
            "`!data.ok` rejection and the catch. Found "
            + str(block.count("unseal('update')")))
        self.assertLess(
            block.index("seal('update'"), block.index("unseal('update')"),
            "the seal must be taken before the failure paths that lift it.")

    def test_the_key_guard_swallows_reload_and_close_keystrokes(self):
        """Angela, 2026-08-16: *"blind the downloading dialog from Ctrl+F4
        too"*. Escape is not the only key that can destroy the dialog - F5 and
        Ctrl+R reload the page out from under it, and that is the accident a
        user is far more likely to have."""
        body = self.policy.split("function isSealedCloseKey", 1)[1]
        body = body.split("\n    }", 1)[0]
        for combo in ("'F5'", "'r'", "'w'", "'F4'"):
            self.assertIn(combo, body,
                          "the sealed key guard does not classify %s" % combo)

    def test_the_key_guard_only_fires_while_something_is_sealed(self):
        """Blocking reload on an ordinary page would be hostile - the user must
        be able to press F5 whenever nothing is downloading."""
        block = self.policy.split("function isSealedCloseKey", 1)[1]
        block = block.split("addEventListener('keydown'", 1)[1].split("}, true)", 1)[0]
        self.assertIn("var key = anySealed();", block)
        self.assertIn("if (!key) return;", block,
                      "the guard must bail immediately when nothing is sealed.")
        self.assertLess(
            block.index("anySealed()"), block.index("preventDefault"),
            "the seal must be checked BEFORE anything is swallowed.")

    def test_the_key_guard_is_capture_phase(self):
        """Unlike the Escape dispatcher (which must bubble so an inner widget
        gets first refusal), this one must win outright - no application
        shortcut may act on a keystroke aimed at killing a live update."""
        listener = self.policy.split("function isSealedCloseKey", 1)[1]
        listener = listener.split("addEventListener('keydown'", 1)[1]
        end_capture = listener.find("}, true);")
        end_bubble = listener.find("});")
        self.assertNotEqual(end_capture, -1,
                            "the sealed key guard is not capture-phase.")
        self.assertTrue(
            end_bubble == -1 or end_capture < end_bubble,
            "the sealed key guard must be registered in the CAPTURE phase so "
            "no application shortcut can act on a keystroke aimed at killing a "
            "live update.")

    def test_the_unblockable_keys_still_have_beforeunload(self):
        """The honest half: Chrome RESERVES Ctrl+W / Ctrl+Shift+W / Alt+F4 and
        never delivers them to a page. `beforeunload` is the only defence the
        platform offers there, so it must never be removed."""
        self.assertIn("addEventListener('beforeunload'", self.policy)
        block = self.policy.split("addEventListener('beforeunload'", 1)[1][:420]
        self.assertIn("anySealed()", block,
                      "beforeunload must only prompt while something is sealed.")
        self.assertIn("returnValue", block,
                      "Chrome needs returnValue set for the prompt to appear.")

    def test_unsealing_releases_the_bound_element(self):
        """Or a dialog sealed once keeps a stale reference for the page's life."""
        block = self.policy.split("function unseal", 1)[1].split("\n    }", 1)[0]
        self.assertIn("delete sealedElements[key]", block)

    def test_the_nudge_shakes_the_panel_not_the_backdrop(self):
        """#update-overlay IS the full-screen dim layer. Translating it would
        show a bright sliver down one edge of the screen."""
        css = _read(os.path.join(_HERE, "static", "agent", "css",
                                 "dialog_theme.css"))
        self.assertIn("tlm-dlg-sealed-shake", css,
                      "dialog_theme.css must own the sealed-nudge animation.")
        self.assertIn(".tlm-dlg-sealed-nudge > .about-window", css,
                      "the shake must target the update dialog's PANEL.")
        block = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for rule in re.findall(r"([^{}]*)\{[^{}]*animation:\s*tlm-dlg-sealed-shake",
                               block):
            self.assertNotIn(
                ".tlm-dlg-sealed-nudge {", rule + "{",
                "the animation is applied to the backdrop itself.")
