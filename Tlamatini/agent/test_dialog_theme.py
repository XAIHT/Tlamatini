"""
Tlamatini Author Banner - do not remove.

DIALOG STANDARDIZATION CONTRACT  (Angela, 2026-08-12)
=====================================================

Angela: "all of the dialogs ... they all are almost similar but there are a few
that doesn't, like the voice configuration, and it makes the user feel somehow
weird, like a not professional software."

Tlamatini used to ship FOUR unrelated dialog skins:

  1. the native modals  - External > MCPs (`emx-*`) and Contacts (`ctb-*`);
     this is the REFERENCE identity, the one in Angela's screenshot;
  2. the jQuery-UI family - Config / Tools / Skills / Access-Keys / canvas
     node dialogs: same two greys, but 12px corners, no border, a flat shadow,
     a grey title and centred grey buttons;
  3. the VOICE dialog (`.tlm-modal-*`) - #1b1e2b surface, gradient titlebar,
     no kicker, no footer bar, borderless 7px buttons;
  4. the Catalog of Prompts (`.modal-content`) - an 18px-radius card filled
     with a three-stop gradient.

`static/agent/css/dialog_theme.css` now defines the identity ONCE as custom
properties and makes every family wear it. These tests pin the parts that are
invisible to a screenshot and therefore easiest to break by accident:

  * the tokens still exist and still hold the reference values;
  * BOTH pages load the theme, and load it LAST (it wins on cascade ORDER, not
    specificity - move the <link> up and every dialog silently reverts);
  * the collected `staticfiles/` copy is in sync with the source (Angela's
    hot-swap rule: the served copy is the one that matters);
  * no stylesheet reintroduces one of the four dead skins;
  * the inline button style in JS still matches the CSS (inline wins, so a
    drift there re-breaks the footer no matter what the CSS says).

VISIBLE counterpart: `.claude/skills/tlamatini-daily-chat-test/harness/
dialog_theme_visible.py` opens every dialog in a headed Chrome, photographs it
with Shoter and compares the LIVE computed styles against the reference.
"""
from __future__ import annotations

import os
import re

from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSS = os.path.join(_HERE, "static", "agent", "css")
_JS = os.path.join(_HERE, "static", "agent", "js")
_TPL = os.path.join(_HERE, "templates", "agent")
_COLLECTED = os.path.join(os.path.dirname(_HERE), "staticfiles", "agent")

THEME = "dialog_theme.css"

# The identity, as it appears in Angela's screenshot.
CANON_TOKENS = {
    "--tlm-dlg-surface": "#4a4f5c",
    "--tlm-dlg-chrome": "#444853",
    "--tlm-dlg-radius": "8px",
    "--tlm-dlg-radius-sm": "6px",
    "--tlm-dlg-accent": "#55bbaa",
}

# Surfaces that MUST NOT come back. Each was one of the four skins.
DEAD_SKINS = {
    "avatar.css": ["#1b1e2b", "#3a3f57", "#12131c", "#2b2f45"],
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _rule_body(css: str, selector: str) -> str:
    """
    The declaration block of `selector`, with COMMENTS STRIPPED FIRST.

    Parse the code, not the essay. Every comment in dialog_theme.css
    deliberately QUOTES the dead value it replaced ("`.exec-perm-value` used to
    be a LIGHT card (#f1f5f3)..."), because that is what makes the file
    self-documenting. A naive text split therefore lands inside the PROSE and
    the assertion fails on the very sentence explaining the fix - which is what
    happened the first time these tests ran.
    """
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert selector in stripped, "%s is not a real rule in this stylesheet" % selector
    return stripped.split(selector, 1)[1].split("}", 1)[0]


class DialogThemeTokenTests(SimpleTestCase):
    """The single source of truth exists and still says what it must."""

    def setUp(self):
        self.css = _read(os.path.join(_CSS, THEME))

    def test_theme_stylesheet_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(_CSS, THEME)),
                        "dialog_theme.css is the single source of truth for "
                        "every dialog's look - it must exist.")

    def test_canonical_tokens_hold_the_reference_values(self):
        for token, value in CANON_TOKENS.items():
            self.assertRegex(
                self.css, re.escape(token) + r"\s*:\s*" + re.escape(value),
                "%s must stay %s - it is the External-MCPs dialog Angela "
                "pointed at. Changing it restyles EVERY dialog at once, which "
                "is the point; do it deliberately, not by accident."
                % (token, value))

    def test_ui_dialog_family_is_restyled(self):
        """The jQuery-UI dialogs must be pulled onto the native-modal look."""
        for needed in (".ui-dialog", ".ui-dialog .ui-dialog-titlebar",
                       ".ui-dialog .ui-dialog-buttonpane",
                       ".ui-dialog .ui-button"):
            self.assertIn(needed, self.css,
                          "%s must be restyled by the theme, otherwise the "
                          "jQuery-UI dialogs keep their own skin." % needed)

    def test_buttonpane_is_a_real_footer_bar(self):
        """Chrome background + top hairline is half the reference identity."""
        pane = _rule_body(self.css, ".ui-dialog .ui-dialog-buttonpane")
        self.assertIn("--tlm-dlg-chrome", pane,
                      "The button strip must be a real footer BAR, filled with "
                      "the chrome colour like `.emx-footer`.")
        self.assertIn("border-top", pane,
                      "The footer needs its top hairline - that separator is "
                      "what makes it read as a footer and not floating buttons.")

    def test_ask_execs_light_theme_leak_is_repaired(self):
        """
        `.exec-perm-value` used to be a WHITE card (#f1f5f3) with dark-green
        text inside a dark dialog - the single most jarring moment in the app,
        and it appeared exactly when the user was asked to authorise something.
        """
        block = _rule_body(self.css, ".exec-perm-value")
        self.assertNotIn("#f1f5f3", block,
                         "The white card is back inside the dark permission "
                         "dialog. It appears exactly when the user is asked to "
                         "authorise something - it must read as one program.")
        self.assertIn("--tlm-dlg-input-bg", block)


class DialogThemeWiringTests(SimpleTestCase):
    """Load order is load-bearing; both pages must carry the theme LAST."""

    PAGES = ("agent_page.html", "agentic_control_panel.html")

    def test_both_pages_load_the_theme(self):
        for page in self.PAGES:
            html = _read(os.path.join(_TPL, page))
            self.assertIn("css/%s" % THEME, html,
                          "%s must load dialog_theme.css or its dialogs keep "
                          "the legacy chrome." % page)

    def test_theme_is_the_last_stylesheet(self):
        """
        The theme deliberately uses the SAME specificity as the legacy
        `.ui-dialog` rules it supersedes, so it wins on ORDER alone. If another
        stylesheet is appended after it, every dialog silently reverts to 12px
        corners and grey buttons - and nothing errors.
        """
        for page in self.PAGES:
            html = _read(os.path.join(_TPL, page))
            sheets = re.findall(r"agent/css/([A-Za-z0-9_]+\.css)", html)
            self.assertTrue(sheets, "no stylesheets found in %s" % page)
            self.assertEqual(
                sheets[-1], THEME,
                "In %s, dialog_theme.css must be the LAST stylesheet (found "
                "%r after it). It wins by cascade order, not specificity."
                % (page, sheets[-1]))


class DialogThemeCollectedCopyTests(SimpleTestCase):
    """
    Angela's rule: the SERVED copy is the one that matters. A source edit that
    never reaches `staticfiles/` looks fixed in the repo and broken in the app.
    """

    def test_collected_theme_matches_source(self):
        collected = os.path.join(_COLLECTED, "css", THEME)
        if not os.path.isdir(_COLLECTED):
            self.skipTest("staticfiles/ not collected in this checkout")
        self.assertTrue(
            os.path.isfile(collected),
            "dialog_theme.css was never collected - run "
            "`python Tlamatini/manage.py collectstatic --noinput`.")
        self.assertEqual(
            _read(os.path.join(_CSS, THEME)), _read(collected),
            "The collected dialog_theme.css differs from the source. Run "
            "collectstatic, then RESTART the app (never hot-swap static into "
            "a running frozen build).")


class DeadSkinTests(SimpleTestCase):
    """None of the four retired dialog skins may creep back."""

    def test_voice_dialog_has_no_private_palette(self):
        css = _read(os.path.join(_CSS, "avatar.css"))
        # Only the modal half matters; the avatar dock keeps its own colours.
        modal = css[css.index(".tlm-modal-overlay"):]
        for dead in DEAD_SKINS["avatar.css"]:
            self.assertNotIn(
                dead, modal,
                "avatar.css reintroduced %s in the voice dialog. That private "
                "palette is exactly what made the Voice dialog look like a "
                "different program. Use the --tlm-dlg-* tokens." % dead)

    def test_voice_dialog_consumes_the_tokens(self):
        css = _read(os.path.join(_CSS, "avatar.css"))
        for token in ("--tlm-dlg-surface", "--tlm-dlg-chrome",
                      "--tlm-dlg-accent"):
            self.assertIn(token, css,
                          "The voice dialog must be built from %s." % token)

    def test_voice_dialog_has_kicker_and_footer(self):
        """
        The reference dialog is recognisable by its teal eyebrow above the
        title and its footer bar. The voice dialog had neither.
        """
        html = _read(os.path.join(_TPL, "agent_page.html"))
        self.assertIn("tlm-modal-kicker", html)
        self.assertIn("tlm-modal-foot", html)
        css = _read(os.path.join(_CSS, "avatar.css"))
        self.assertIn(".tlm-modal-kicker", css)
        self.assertIn(".tlm-modal-foot", css)


class DialogButtonInlineStyleTests(SimpleTestCase):
    """
    `DIALOG_BUTTON_CSS` is applied with jQuery `.css()`, i.e. INLINE - it beats
    every stylesheet. If it drifts from the theme, the footer looks wrong no
    matter how correct the CSS is.
    """

    def setUp(self):
        self.js = _read(os.path.join(_JS, "agent_page_dialogs.js"))

    def test_no_viewport_relative_button_height(self):
        block = self.js.split("const DIALOG_BUTTON_CSS")[1].split("};")[0]
        self.assertNotIn(
            "4vh", block,
            "A viewport-relative height made dialog buttons the one control "
            "that resized with the window (43px on 1080p, 26px on a laptop). "
            "Height comes from the shared padding in dialog_theme.css.")

    def test_primary_button_matches_the_token(self):
        block = self.js.split("const DIALOG_BUTTON_CSS")[1].split("};")[0]
        self.assertIn("#55BBAA", block.upper().replace("#55BBAA", "#55BBAA"))
        self.assertIn("'6px'", block,
                      "The primary button radius must match "
                      "--tlm-dlg-radius-sm (6px).")

    def test_secondary_button_is_left_to_css(self):
        """
        Cancel must NOT be painted teal inline. In the reference dialog the
        pair is teal-Continue + outlined-Cancel; painting both teal made them
        both read as 'confirm'.
        """
        fn = self.js.split("function styleDialogButtons")[1].split("}")[0]
        self.assertNotIn(
            'contains("Cancel")', fn,
            "Cancel must inherit the outlined secondary style from "
            "dialog_theme.css, not be painted teal inline.")
