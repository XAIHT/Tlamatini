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
    # The ACP canvas' own private palette: the Log Viewer / Agent
    # Description near-black card (#1e1e1e), their #2d2d2d bars, and the
    # #555 borders + #4a5568 hover of the right-click menu.
    "agentic_control_panel.css": ["#1e1e1e", "#2d2d2d", "#4a5568", "#626978"],
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

    def test_focus_state_restates_the_input_background(self):
        """
        A dark field that turns WHITE the moment it is focused.

        Found live on 2026-08-12 by the visible ACP check - and it was
        the worst possible instance of the bug, because jQuery UI
        AUTOFOCUSES the first field, so the canvas Configure dialog
        opened with a white box already staring at the user.

        Bootstrap's `.form-control:focus` sets
        `background-color: var(--bs-body-bg)` at specificity (0,2,0);
        the resting `.tlm-dlg-input` rule is only (0,1,0), and being
        later in the cascade cannot rescue a weaker selector. The focus
        rule therefore has to re-state background AND colour itself.
        """
        block = _rule_body(self.css, ".tlm-dlg-input:focus,")
        self.assertIn(
            "--tlm-dlg-input-bg", block,
            "The focus rule no longer paints the field's background, so "
            "Bootstrap's `.form-control:focus` turns every focused field "
            "WHITE inside the dark dialog. Do not remove it because the "
            "resting rule 'already sets it' - it loses on specificity.")
        self.assertIn(
            "--tlm-dlg-title", block,
            "The focus rule must also re-state the text colour, or the "
            "caret and typed text follow Bootstrap back to dark-on-dark.")

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


# ══════════════════════════════════════════════════════════════════
#  THE ACP WORKFLOW DESIGNER  (agentic_control_panel.html)
# ══════════════════════════════════════════════════════════════════
#
# The 2026-08-12 pass above landed the theme and fixed the CHAT page.
# The canvas page then still shipped three MORE private skins, because
# it builds most of its dialogs in JavaScript:
#
#   5. the Log Viewer + Agent Description native modals - a #1e1e1e
#      card, #2d2d2d bars, #555 borders, 10px corners;
#   6. the FlowCreator "working..." modal - a #2a2a2a card outlined in
#      blue;
#   7. the Parametrizer mapping modal - a #1e1e1e card outlined 2px in
#      saturated purple, with grey buttons floating on it.
#
# Plus two LIGHT-IN-DARK leaks of exactly the `.exec-perm-value` kind:
# the canvas Configure dialog painted every input `#fff` on `#000`, and
# the runtime notification chip used #D1FAE5 / #FEE2E2 / #FEF3C7 with
# dark green/red/amber text.
#
# These tests pin the parts a screenshot cannot catch.


_DIALOG_SELECTOR_TOKENS = ("ui-dialog", "ui-widget-overlay", "context-menu",
                           "log-viewer", "agent-description", "tlm-native",
                           "tlm-dlg")


def _dialog_rules(css: str) -> str:
    """
    Every rule whose SELECTOR names a dialog surface, concatenated.

    Scoping matters here. `agentic_control_panel.css` styles the whole
    workflow designer, and the PAGE legitimately uses some of the same
    greys the dialogs had to give up - `#main-agents-container` is
    `#2d2d2d`, for instance. A whole-file search for a dead colour
    therefore fails on the sidebar, which has nothing to do with
    dialogs. This walks braces (recursing through `@media`) so the
    assertions below can look at the dialog rules ALONE.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules, depth, sel_start, body_start, selector = [], 0, 0, 0, ""
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                selector = css[sel_start:i]
                body_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = css[body_start:i]
                if selector.strip().startswith("@"):
                    rules.append(_dialog_rules(body))
                elif any(t in selector for t in _DIALOG_SELECTOR_TOKENS):
                    rules.append("%s{%s}" % (selector, body))
                sel_start = i + 1
    return "\n".join(rules)


def _all_rule_bodies(css: str, selector: str) -> list[str]:
    """Every declaration block for `selector`, comments stripped."""
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [chunk.split("}", 1)[0]
            for chunk in stripped.split(selector + " {")[1:]]


def _strip_js_comments(text: str) -> str:
    """
    Drop `/* … */` blocks and WHOLE-LINE `//` comments.

    Same reason `_rule_body` strips CSS comments: every fix below is
    documented by a comment that QUOTES the dead value it replaced
    ("`height: '4vh'` - a viewport-relative button height"), so a naive
    substring search finds the essay, not the code. Only full-line `//`
    is stripped - a blanket `//` strip would cut real code at `https://`
    and at the '/agent/…/' URLs these modules post to.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//")
    )


class CheckForUpdatesDialogTests(SimpleTestCase):
    """The EIGHTH skin — missed by the first pass, caught by Angela.

    "Check for updates" is a real dialog (title, body, release notes,
    progress, actions) that wore the About SPLASH's private palette: a
    ``#1a1a2e`` card with 12px corners and no border, a bare 24px "x"
    with no hit target, and a purple/pink gradient button. It also had
    NO header bar and NO kicker — so even once the panel colour matched,
    it still read as a window from another program.

    It is easy to miss precisely because it is NOT a `.ui-dialog`: the
    theme's jQuery-UI rules could never reach it.
    """

    def setUp(self):
        self.css = _read(os.path.join(_CSS, "agent_page.css"))
        self.html = _read(os.path.join(_TPL, "agent_page.html"))

    def test_card_is_built_from_the_tokens(self):
        block = _rule_body(self.css, ".about-window {")
        self.assertNotIn("#1a1a2e", block,
                         "the About/update card is back on its private "
                         "near-navy surface")
        for token in ("--tlm-dlg-surface", "--tlm-dlg-radius",
                      "--tlm-dlg-shadow", "--tlm-dlg-border"):
            self.assertIn(token, block)

    def test_it_has_a_header_bar_and_a_footer_bar(self):
        for selector in (".update-header {", ".update-actions {"):
            block = _rule_body(self.css, selector)
            self.assertIn(
                "--tlm-dlg-chrome", block,
                "%s must be a real chrome BAR — the strip at the top and "
                "the strip at the bottom are what make a dialog read as "
                "ours." % selector)
        self.assertIn("border-top", _rule_body(self.css, ".update-actions {"))
        self.assertIn("border-bottom", _rule_body(self.css, ".update-header {"))

    def test_markup_carries_the_header_and_the_kicker(self):
        self.assertIn('class="update-header"', self.html)
        self.assertIn('class="update-kicker"', self.html)
        head = self.html.split('class="update-header"', 1)[1][:400]
        self.assertLess(head.index("update-kicker"), head.index("update-title"),
                        "the kicker must sit ABOVE the title")

    def test_primary_button_is_the_shared_teal(self):
        block = _rule_body(self.css, ".update-btn {")
        self.assertNotIn(
            "linear-gradient", block,
            "the update button is back to its purple/pink gradient — the "
            "confirm button is teal everywhere else in the app")
        self.assertIn("--tlm-dlg-accent", block)

    def test_close_button_has_a_real_hit_target(self):
        block = _rule_body(self.css, ".about-close-btn {")
        self.assertIn("32px", block,
                      "the close X went back to a bare glyph with no 32px "
                      "hit-target / hover chip")
        self.assertIn("--tlm-dlg-radius-sm", block)


class AcpLegacyChromeTests(SimpleTestCase):
    """
    `agentic_control_panel.css` carried a full SECOND COPY of the dialog
    chrome. Two stylesheets both claiming to own "what a dialog looks
    like" is exactly how the two pages drifted: fixing one never fixed
    both, and whichever was edited last silently won.
    """

    def setUp(self):
        self.css = _read(os.path.join(_CSS, "agentic_control_panel.css"))
        # Only the DIALOG rules - the designer page itself still uses some
        # of these greys, and legitimately so.
        self.dialog_css = _dialog_rules(self.css)

    def test_no_dead_skin_colours(self):
        for dead in DEAD_SKINS["agentic_control_panel.css"]:
            self.assertNotIn(
                dead, self.dialog_css,
                "agentic_control_panel.css reintroduced %s IN A DIALOG RULE. "
                "That private palette is what made the canvas dialogs look "
                "like a different program. Use the --tlm-dlg-* tokens." % dead)

    def test_ui_dialog_declares_no_chrome(self):
        """Geometry may stay here; colour, corners and shadow may not."""
        block = _rule_body(self.css, ".ui-dialog {")
        for banned in ("background-color", "border-radius", "box-shadow"):
            self.assertNotIn(
                banned, block,
                "`.ui-dialog` in agentic_control_panel.css re-declares %r. "
                "The card's look belongs to dialog_theme.css alone - this "
                "block is for the canvas' sizing envelope only." % banned)

    def test_button_footer_is_not_re_declared(self):
        """
        The old copy centred the buttons and painted them #626978, and gave
        the pane the dialog's OWN background so there was no footer bar at
        all. Pure GEOMETRY may stay (the mobile block still sets
        `flex-wrap`); the chrome may not.
        """
        chrome = {
            ".ui-dialog .ui-dialog-buttonpane":
                ("background", "border", "box-shadow"),
            ".ui-dialog .ui-dialog-buttonset":
                ("justify-content", "float"),
            ".ui-dialog .ui-button":
                ("background", "border", "color", "font-family"),
        }
        for selector, banned in chrome.items():
            for block in _all_rule_bodies(self.css, selector):
                for prop in banned:
                    self.assertNotIn(
                        prop + ":", block,
                        "`%s` in agentic_control_panel.css declares %r again. "
                        "The footer bar and its buttons belong to "
                        "dialog_theme.css; re-declaring them here recreates "
                        "the centred grey-button footer."
                        % (selector, prop))

    def test_native_modals_consume_the_tokens(self):
        for needed in ("#log-viewer-dialog", "#agent-description-dialog",
                       "#agent-context-menu"):
            self.assertIn(needed, self.css)
        for surface in ("#log-viewer-dialog {", "#agent-description-dialog {"):
            block = _rule_body(self.css, surface)
            self.assertIn(
                "var(--tlm-dlg-surface)", block,
                "%s must be built from the shared surface token." % surface)
            self.assertIn("var(--tlm-dlg-shadow)", block)


class AcpNativeModalMarkupTests(SimpleTestCase):
    """
    The reference dialog is recognisable by a teal eyebrow above its
    title and a footer bar under its body. The Log Viewer had a footer
    but no kicker; the Agent Description had NEITHER, which is why it
    read as a tooltip that had escaped rather than as a dialog.
    """

    def setUp(self):
        self.html = _read(os.path.join(_TPL, "agentic_control_panel.html"))

    def test_both_native_modals_have_a_kicker(self):
        head = self.html.split('id="log-viewer-header"')[1][:400]
        self.assertIn("tlm-dlg-kicker", head)
        head = self.html.split('id="agent-description-header"')[1][:400]
        self.assertIn("tlm-dlg-kicker", head)

    def test_description_dialog_has_a_footer_bar(self):
        self.assertIn('id="agent-description-footer"', self.html,
                      "The Agent Description dialog must have a real footer "
                      "bar - it is half of the shared identity.")
        self.assertIn('id="agent-description-close-action"', self.html)

    def test_footer_close_is_wired(self):
        """A footer button nobody listens to is worse than no button."""
        js = _read(os.path.join(_JS, "contextual_menus.js"))
        self.assertIn("agent-description-close-action", js,
                      "The footer Close button is rendered but never wired "
                      "up in contextual_menus.js.")

    def test_live_indicator_structure_survives(self):
        """
        `updateLiveIndicator()` finds the label with
        `.log-viewer-live-indicator span:last-child`, so the dot+label
        pair must stay the last two children of that div.
        """
        block = self.html.split("log-viewer-live-indicator")[1][:300]
        self.assertLess(block.index("log-viewer-live-dot"),
                        block.index("Live"),
                        "The live DOT must stay before the 'Live' label or "
                        "updateLiveIndicator() rewrites the wrong span.")


class AcpInlineStyleLeakTests(SimpleTestCase):
    """
    Inline styles beat every stylesheet, so these are the only places
    where correct CSS could not save the page.
    """

    def _js(self, name: str) -> str:
        return _strip_js_comments(_read(os.path.join(_JS, name)))

    def test_configure_dialog_paints_no_white_inputs(self):
        """
        The canvas Configure dialog is the most-used dialog of the whole
        designer, and it rendered a WHITE form inside the dark card.
        """
        js = self._js("canvas_item_dialog.js")
        for banned in ('backgroundColor = "#fff"', 'style.color = "#000"'):
            self.assertNotIn(
                banned, js,
                "canvas_item_dialog.js paints %s inline again - a white "
                "form inside the dark dialog, the same leak as the "
                "Ask-Execs white card. Use the `tlm-dlg-input` class." % banned)
        self.assertIn("tlm-dlg-input", js,
                      "The Configure dialog's fields must carry the shared "
                      "`tlm-dlg-input` class.")

    def test_no_module_blanks_the_footer_bar(self):
        """
        `buttonPane.css({background:'none', border:'none'})` ERASED the
        footer bar - the single most recognisable half of the reference
        dialog - on every dialog that ran it.
        """
        for name in ("canvas_item_dialog.js", "acp-validate.js",
                     "acp-control-buttons.js"):
            js = self._js(name)
            self.assertNotIn(
                "buttonPane.css(", js,
                "%s blanks the button pane again; that erases the footer "
                "bar dialog_theme.css paints." % name)

    def test_no_viewport_relative_button_height_on_the_canvas(self):
        js = self._js("canvas_item_dialog.js")
        self.assertNotIn(
            "'height': '4vh'", js,
            "A viewport-relative height made dialog buttons the one control "
            "that resized with the window (43px on 1080p, 26px on a laptop).")

    def test_runtime_notification_chip_is_not_light_themed(self):
        """
        The matched log text sat on a LIGHT chip with dark text inside the
        dark dialog. This file loads on BOTH pages, so it leaked twice.
        """
        js = self._js("shared-runtime-dialogs.js")
        for dead in ("#D1FAE5", "#FEE2E2", "#FEF3C7",
                     "#065F46", "#991B1B", "#92400E"):
            self.assertNotIn(
                dead, js,
                "shared-runtime-dialogs.js is painting the severity chip "
                "light (%s) inside a dark dialog again." % dead)

    def test_asker_dialog_draws_no_coloured_edge(self):
        """
        A 4px straight bar across an 8px-rounded card reads as a rendering
        fault, and it was the only coloured edge in the app.
        """
        js = self._js("shared-runtime-dialogs.js")
        self.assertNotIn("'border-top', '4px solid", js)

    def test_parametrizer_shell_uses_the_surface_token(self):
        """
        Only the SHELL is normalised: the two-column mapping widget keeps
        its cyan/orange/purple coding, which is real information.
        """
        js = self._js("acp-parametrizer-dialog.js")
        self.assertNotIn(
            "border: '2px solid #AA00FF'", js,
            "The Parametrizer card is outlined in saturated purple again.")
        self.assertIn("var(--tlm-dlg-surface)", js)
        self.assertIn("#00E5FF", js,
                      "The source/target colour coding is CONTENT and must "
                      "survive the shell normalisation.")


class NoNativePopupTests(SimpleTestCase):
    """No `window.alert` / `window.confirm` anywhere on the canvas.

    Angela, 2026-08-12, asking for the alert dialogs to be swept: the ACP
    page raised **28 native alert() boxes and 2 confirm()** - "Only one
    FlowCreator agent is allowed per flow", "Invalid Connection: ...",
    "This will permanently delete all deployed agents...".

    A native popup is OS chrome: a grey Windows/Chrome strip carrying the
    page's URL, dropped into the middle of a dark themed application. It is
    the loudest "different program" moment in the app - louder than any of
    the eight private skins, because it is not even the same renderer, and
    NO stylesheet can reach it.

    It is also BLOCKING, which is why the Clear button could not be
    photographed at all until it was replaced: a native dialog freezes the
    page and stalls the visible check.
    """

    CANVAS_MODULES = (
        "acp-canvas-core.js", "acp-control-buttons.js", "acp-validate.js",
        "acp-file-io.js", "acp-running-state.js", "acp-session.js",
        "acp-layout.js", "acp-canvas-undo.js", "acp-agent-connectors.js",
        "acp-flow-snapshot.js", "canvas_item_dialog.js", "contextual_menus.js",
        "shared-runtime-dialogs.js", "acp-parametrizer-dialog.js",
    )

    # `acpAlert(`, `window.alert(` and `myalert(` must NOT match.
    NATIVE = re.compile(r"(?<![\w.$])(alert|confirm)\(")

    def test_no_native_popups_on_the_canvas(self):
        offenders = []
        for name in self.CANVAS_MODULES:
            path = os.path.join(_JS, name)
            if not os.path.isfile(path):
                continue
            body = _strip_js_comments(_read(path))
            for match in self.NATIVE.finditer(body):
                line = body[:match.start()].count("\n") + 1
                offenders.append("%s:%d  %s(" % (name, line, match.group(1)))
        self.assertEqual(
            offenders, [],
            "native browser popups are back on the canvas: %s\nUse acpAlert / "
            "acpConfirm (acp-globals.js) - they render the same themed dialog "
            "as everything else, and unlike a native box they do not block "
            "the page." % ", ".join(offenders))

    def test_the_replacements_exist_and_fail_open(self):
        js = _read(os.path.join(_JS, "acp-globals.js"))
        self.assertIn("function acpAlert", js)
        self.assertIn("function acpConfirm", js)
        # If the markup is missing, a warning must still reach the user.
        self.assertIn("window.alert(message)", js,
                      "acpAlert must fall back to the native box when the "
                      "dialog markup is absent - a LOST warning is worse "
                      "than an ugly one.")
        self.assertIn("window.confirm(", js)

    def test_confirm_defaults_to_cancel(self):
        """Dismissing a destructive prompt must never mean 'yes'."""
        js = _read(os.path.join(_JS, "acp-globals.js"))
        block = js.split("function acpConfirm")[1].split("\n}")[0]
        self.assertIn("dialogclose", block)
        self.assertIn("finish(false)", block)


class AcpDialogButtonHelperTests(SimpleTestCase):
    """
    The ACP mirror of `DIALOG_BUTTON_CSS`. Both pages must paint the
    confirm button identically, or the two footers drift again.
    """

    def setUp(self):
        self.acp = _read(os.path.join(_JS, "acp-globals.js"))
        self.chat = _read(os.path.join(_JS, "agent_page_dialogs.js"))

    def _button_css(self, js: str, const_name: str) -> str:
        return js.split("const %s" % const_name)[1].split("};")[0]

    def test_helper_exists(self):
        self.assertIn("function styleAcpDialogButtons", self.acp)

    def test_primary_matches_the_chat_page(self):
        acp = self._button_css(self.acp, "ACP_DIALOG_BUTTON_CSS")
        chat = self._button_css(self.chat, "DIALOG_BUTTON_CSS")
        for prop in ("'background-color': '#55BBAA'", "'border-radius': '6px'"):
            self.assertIn(prop, acp)
            self.assertIn(prop, chat,
                          "The two pages' confirm buttons have drifted.")

    def test_secondary_is_left_to_css(self):
        """Cancel / Dismiss / Verify inherit the outlined style."""
        fn = self.acp.split("function styleAcpDialogButtons")[1].split("\n}")[0]
        for secondary in ("Cancel", "Dismiss", "Verify"):
            self.assertNotIn(
                'contains("%s")' % secondary, fn,
                "%s must inherit the outlined secondary style from "
                "dialog_theme.css, not be painted." % secondary)

    def test_no_viewport_relative_height(self):
        acp = self._button_css(self.acp, "ACP_DIALOG_BUTTON_CSS")
        self.assertNotIn("vh", acp)


class AcpCollectedCopyTests(SimpleTestCase):
    """The SERVED copy is the one that matters (Angela's hot-swap rule)."""

    FILES = (
        ("css", "agentic_control_panel.css"),
        ("js", "canvas_item_dialog.js"),
        ("js", "acp-globals.js"),
        ("js", "shared-runtime-dialogs.js"),
        ("js", "contextual_menus.js"),
    )

    def test_collected_copies_match_source(self):
        if not os.path.isdir(_COLLECTED):
            self.skipTest("staticfiles/ not collected in this checkout")
        source_root = {"css": _CSS, "js": _JS}
        for kind, name in self.FILES:
            collected = os.path.join(_COLLECTED, kind, name)
            if not os.path.isfile(collected):
                self.fail("%s was never collected - run collectstatic." % name)
            self.assertEqual(
                _read(os.path.join(source_root[kind], name)), _read(collected),
                "The collected %s differs from the source. Run collectstatic, "
                "then RESTART the app (never hot-swap static into a running "
                "frozen build)." % name)
