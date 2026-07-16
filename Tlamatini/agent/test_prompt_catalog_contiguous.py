# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ═══════════════════════════════════════════════════════════════════
"""Catalog-of-Prompts INVARIANTS after the re-group/re-sort/no-gaps renumber
(migration 0179, Angela 2026-07-15).

`manage.py test` builds a fresh test DB by running EVERY migration — 0002 seeds the
prompts, later migrations add the demos, 0178 adds the two step-by-step blink
walkthroughs, and 0179 renumbers the whole catalog. So these tests prove the
renumber applied cleanly on the REAL seeded prompt set and produced a contiguous,
category-grouped catalog (no live DB is touched)."""
from django.test import TestCase

from agent.models import Prompt
from agent.views import PROMPT_CATEGORY_ORDER

_RANK = {key: i for i, (key, _label) in enumerate(PROMPT_CATEGORY_ORDER)}
_OTHER = _RANK['other']


def _rank(category):
    return _RANK.get((category or '').strip(), _OTHER)


class PromptCatalogContiguityTests(TestCase):
    def _rows(self):
        return list(
            Prompt.objects.all()
            .values('idPrompt', 'promptName', 'category', 'promptContent')
            .order_by('idPrompt')
        )

    def test_ids_are_contiguous_1_to_n_no_gaps(self):
        ids = [r['idPrompt'] for r in self._rows()]
        self.assertTrue(ids, 'the catalog must not be empty')
        self.assertEqual(
            ids, list(range(1, len(ids) + 1)),
            'idPrompt must be a contiguous 1..N with NO gaps after migration 0179',
        )

    def test_promptname_matches_id(self):
        for r in self._rows():
            self.assertEqual(r['promptName'], f"prompt-{r['idPrompt']}")

    def test_grouped_by_category_rank(self):
        # As idPrompt increases the category rank must never DECREASE — i.e. every
        # category forms one contiguous block, in the UI's display order.
        prev = -1
        for r in self._rows():
            rank = _rank(r['category'])
            self.assertGreaterEqual(
                rank, prev,
                f"prompt {r['idPrompt']} (category {r['category']!r}) breaks the "
                f"category grouping order",
            )
            prev = rank

    def test_new_stm32_platformio_prompts_present_and_firmware(self):
        fw = Prompt.objects.filter(category='firmware_iot')
        # The Blue Pill (STM32F103) demos + the F407 Discovery walkthrough.
        self.assertTrue(fw.filter(promptContent__contains='bluepill_f103c8').exists())
        self.assertTrue(fw.filter(promptContent__contains='disco_f407vg').exists())
        # Both step-by-step camera-verified walkthroughs drive Camcorder.
        self.assertTrue(fw.filter(promptContent__contains='chat_agent_camcorder').exists())
