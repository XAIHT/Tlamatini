# Tlamatini Author Banner - do not remove (Angela López Mendoza, creator of Tlamatini)
"""Two chat pages on two models must not ping-pong (Angela, 2026-10-08).

Compact mode keeps ONE shared note of "the current model".  Every re-measure
notes its own tab's model, and a changed note is announced to every tab.
Before the fix that announcement made every tab re-send all its Configure rows
and RE-MEASURE, which noted ITS model again - so two tabs on two different
models bounced forever.  Measured on the dev copy with both pages idle:
1,081 row re-sends, 1,255 notes and 209,006 log lines in 60 seconds; Angela's
installed log reached 61,779 lines in one evening.

A VERDICT (what a model can hold) now updates every tab's box and stops there;
a real change (the switch, a saved dialog, her Self-modify box) still re-sends
the rows and re-measures, exactly as before.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from django.test import TestCase

from agent import compact_mode as cm
from agent.consumers import AgentConsumer
from agent.global_state import global_state


class _Tab:
    """One chat page: the REAL group handler runs, its side effects are recorded."""

    def __init__(self, model):
        self.model = model
        self.frames = []
        self.rows_resent = 0
        self.remeasured = []

    async def send(self, text_data=None):
        self.frames.append(text_data)

    async def _send_toggle_rows(self):
        self.rows_resent += 1

    def _schedule_context_gauge_refresh(self, reason, after_answer=False):
        self.remeasured.append(reason)


def _deliver(tab, kind):
    asyncio.run(AgentConsumer.compact_mode_changed(tab, {"kind": kind, "state": {}}))


class VerdictKindsTests(TestCase):
    def setUp(self):
        self._saved = dict(global_state._state)
        self.addCleanup(self._restore)
        cm.reset_cache()

    def _restore(self):
        global_state._state.clear()
        global_state._state.update(self._saved)
        cm.reset_cache()

    def test_a_verdict_updates_the_box_but_nobody_re_measures(self):
        for kind in cm.VERDICT_KINDS:
            tab = _Tab("glm-5.3:cloud")
            _deliver(tab, kind)
            self.assertEqual(len(tab.frames), 1, kind)             # the box still updates
            self.assertIn('"compact-mode-state"', tab.frames[0])
            self.assertEqual(tab.rows_resent, 0, kind)
            self.assertEqual(tab.remeasured, [], kind)

    def test_a_real_change_still_re_sends_the_rows_and_re_measures(self):
        for kind in ("on", "off", "rows", "state"):
            tab = _Tab("glm-5.3:cloud")
            _deliver(tab, kind)
            self.assertEqual(tab.rows_resent, 1, kind)
            self.assertEqual(tab.remeasured, ["Configure rows changed"], kind)
        tab = _Tab("glm-5.3:cloud")
        _deliver(tab, "self_modify")                                 # her own box
        self.assertEqual(tab.rows_resent, 0)
        self.assertEqual(tab.remeasured, ["Self-modify changed"])

    def test_the_self_modify_verdict_is_announced_as_a_verdict(self):
        sent = []
        with patch.object(cm, "self_modify_available", return_value=True), \
                patch.object(cm, "notify", side_effect=lambda kind="state": sent.append(kind) or True):
            cm.note_self_modify(fits=False, tokens=28_000, need_tokens=36_000)
        self.assertEqual(sent, ["self_modify_fit"])
        self.assertIn("self_modify_fit", cm.VERDICT_KINDS)
        self.assertIn("capacity", cm.VERDICT_KINDS)
        self.assertNotIn("self_modify", cm.VERDICT_KINDS)          # her box is a REAL change

    def test_two_tabs_on_two_models_settle_instead_of_bouncing_forever(self):
        tabs = [_Tab("glm-5.3:cloud"), _Tab("glm-5.2:cloud")]
        queue = []

        def fake_notify(kind="state"):
            queue.extend((tab, kind) for tab in tabs)
            return True

        def measure(tab):            # what fit_request does on every re-measure
            cm.note_capacity(model=tab.model, strict=False, window_tokens=1_048_576,
                             everything_tokens=96_158, auto_enter=False)

        with patch.object(cm, "notify", side_effect=fake_notify):
            measure(tabs[0])
            measure(tabs[1])         # page B arrives on another model
            rounds = 0
            while queue and rounds < 200:
                tab, kind = queue.pop(0)
                rounds += 1
                before = len(tab.remeasured)
                _deliver(tab, kind)
                if len(tab.remeasured) > before:
                    measure(tab)
        self.assertLess(rounds, 10, "the two pages kept re-measuring each other")
        self.assertEqual(sum(tab.rows_resent for tab in tabs), 0)
        self.assertEqual(sum(len(tab.remeasured) for tab in tabs), 0)
