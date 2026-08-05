# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Guards the SPACE-bar bulk check/uncheck of selected checkboxes.

Angela, 2026-08-04. The Configure Mcps / Tools / Agents / Skills dialogs list
dozens of checkboxes; clearing 20 of them cost 20 clicks. Now the user drags a
normal text selection across the labels and presses SPACE once.

``static/agent/js/checkbox_bulk_toggle.js`` is deliberately ONE self-contained
module with NO per-dialog wiring: it finds the checkboxes by asking which ones
the live selection overlaps, so every checkbox dialog — present AND future —
gets the behaviour for free. That design is exactly what makes it fragile to a
careless edit, hence this guard.

Three layers, because each breaks on its own:

1. SOURCE CONTRACT — the invariants a future edit could silently undo:
   the CAPTURE-phase listener (bubble phase would let a list's own Space
   handler toggle a row a second time and net it back to where it started),
   the text-entry bail (SPACE must keep typing a space in every search box),
   the "any checked -> uncheck all" rule, and toggling via ``.click()`` so
   the existing change/click handlers still run.
2. TEMPLATE WIRING — a module nobody loads does nothing. Both pages must
   include it: the chat page AND the ACP workflow designer.
3. COLLECTED STATIC — ``staticfiles/`` is what the browser downloads. Source
   can be perfect while the served copy is stale (this mirrors
   ``test_frontend_mutable_state.py``'s const-poison guard).
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent

JS_RELATIVE = Path("agent") / "js" / "checkbox_bulk_toggle.js"
JS_SOURCE = ROOT / "static" / JS_RELATIVE
COLLECTED_ROOT = PROJECT_ROOT / "staticfiles"

TEMPLATES = (
    ROOT / "templates" / "agent" / "agent_page.html",
    ROOT / "templates" / "agent" / "agentic_control_panel.html",
)

SCRIPT_TAG_FRAGMENT = "agent/js/checkbox_bulk_toggle.js"

# This edition is ENGLISH: the one user-visible string must stay English.
HINT_FRAGMENT = "select several labels with the mouse"
FOREIGN_HINT_FRAGMENT = "selecciona varias etiquetas"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class CheckboxBulkToggleSourceContractTests(unittest.TestCase):
    """The invariants that make the feature correct instead of merely present."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read(JS_SOURCE)

    def test_module_exists_and_is_wrapped_in_an_iife(self):
        # A top-level `const`/`let` here would be a cross-file global and could
        # trip the const-poison sweep in test_frontend_mutable_state.py.
        self.assertTrue(JS_SOURCE.exists(), f"missing {JS_SOURCE}")
        self.assertIn("(function () {", self.js)
        self.assertIn("'use strict';", self.js)
        for line in self.js.splitlines():
            self.assertFalse(
                line.startswith("const ") or line.startswith("let ") or line.startswith("var "),
                f"top-level binding leaks out of the IIFE: {line!r}",
            )

    def test_listener_is_registered_in_capture_phase(self):
        # BUBBLE phase would be a silent data-corrupting bug: the External-MCPs
        # row handler (external_mcps_dialog.js) already binds Space and only
        # calls preventDefault(), so it would toggle the focused row FIRST and
        # our pass would toggle it AGAIN — netting that one row back to its
        # original state while its neighbours flipped.
        self.assertIn("document.addEventListener('keydown', onKeyDown, true)", self.js)

    def test_space_is_the_only_key_claimed_and_modifiers_are_left_alone(self):
        self.assertIn("event.key !== ' '", self.js)
        self.assertIn("event.ctrlKey || event.metaKey || event.altKey", self.js)

    def test_it_never_steals_space_from_a_text_field(self):
        # Both event.target AND document.activeElement: after a mouse-drag the
        # target is usually <body>, not the field the user is typing in.
        self.assertIn("isTextEntry(event.target) || isTextEntry(document.activeElement)", self.js)
        for tag in ("'textarea'", "'select'", "isContentEditable"):
            self.assertIn(tag, self.js, f"text-entry guard lost {tag}")

    def test_it_only_acts_on_a_real_non_collapsed_selection(self):
        self.assertIn("selection.isCollapsed", self.js)
        self.assertIn("selection.rangeCount", self.js)
        # No targets -> return BEFORE preventDefault, so native SPACE (page
        # scroll, focused-checkbox toggle) is untouched.
        self.assertIn("if (!targets.length) return;", self.js)

    def test_overlap_test_is_strict(self):
        # A zero-length touch at a boundary must NOT count, or selecting label A
        # drags in the first character of label B.
        self.assertIn("const START_TO_END = 1;", self.js)
        self.assertIn("const END_TO_START = 3;", self.js)
        self.assertIn("compareBoundaryPoints(END_TO_START, nodeRange) < 0", self.js)
        self.assertIn("compareBoundaryPoints(START_TO_END, nodeRange) > 0", self.js)

    def test_a_row_must_own_exactly_one_checkbox(self):
        # Without this guard the whole list container could be taken for one
        # row, and ANY selection would toggle every checkbox in the dialog.
        self.assertIn(
            "node.querySelectorAll('input[type=\"checkbox\"]').length !== 1", self.js
        )

    def test_the_rule_is_any_checked_means_uncheck_all(self):
        self.assertIn("let desired = true;", self.js)
        self.assertIn("if (targets[i].checkbox.checked) { desired = false; break; }", self.js)
        self.assertIn("if (!!live.checked === desired) continue;", self.js)

    def test_it_toggles_with_a_real_click(self):
        # .click() runs every existing click/change handler (state persistence,
        # the External-MCPs 5-server cap). Setting .checked directly would
        # silently skip them and lose the user's change.
        self.assertIn("live.click();", self.js)

    def test_disabled_checkboxes_are_never_touched(self):
        self.assertIn("if (cb.disabled) continue;", self.js)

    def test_self_rerendering_lists_are_resolved_late(self):
        # The External-MCPs catalog rebuilds every row from its model on each
        # toggle, so a snapshotted element is detached by the time we reach it.
        self.assertIn("function makeResolver(", self.js)
        self.assertIn("data-key", self.js)
        self.assertIn("isConnected", self.js)

    def test_the_hint_is_in_this_edition_s_language(self):
        self.assertIn(HINT_FRAGMENT, self.js)
        self.assertNotIn(FOREIGN_HINT_FRAGMENT, self.js)


class CheckboxBulkToggleTemplateWiringTests(unittest.TestCase):
    """A module nobody loads does nothing — both pages must include it."""

    def test_both_pages_load_the_module(self):
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                self.assertIn(SCRIPT_TAG_FRAGMENT, _read(template))

    def test_the_script_tag_carries_a_cache_buster(self):
        # Same reason as the other state scripts: a stale cached copy would
        # leave the user without the feature and with no way to tell.
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                text = _read(template)
                line = next(ln for ln in text.splitlines() if SCRIPT_TAG_FRAGMENT in ln)
                self.assertIn("STATIC_VERSION", line)
                self.assertIn("_bulktoggle", line)


class CheckboxBulkToggleCollectedStaticTests(unittest.TestCase):
    """staticfiles/ is what the browser downloads — a stale copy ships nothing."""

    def test_collected_copy_matches_the_source(self):
        if not COLLECTED_ROOT.is_dir():
            self.skipTest("staticfiles/ not collected in this checkout")
        collected = COLLECTED_ROOT / JS_RELATIVE
        self.assertTrue(
            collected.exists(),
            "checkbox_bulk_toggle.js is missing from staticfiles/ — "
            "run `python Tlamatini/manage.py collectstatic --noinput`",
        )
        self.assertEqual(
            _read(collected),
            _read(JS_SOURCE),
            "the collected copy is STALE — "
            "run `python Tlamatini/manage.py collectstatic --noinput`",
        )


if __name__ == "__main__":
    unittest.main()
