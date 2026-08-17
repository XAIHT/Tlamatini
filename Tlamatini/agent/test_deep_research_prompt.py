# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the Deep Internet Research catalog prompt (migration 0194).

Pins the two contracts the frontend relies on:

  1. PLACEMENT — the prompt is APPENDED at id 118 (never renumbered) in
     ``getting_started`` with ``sort_rank = 100``, i.e. the LAST card of the
     Getting Started section (the section previously topped out at rank 90).
  2. CLASSIFIER MODES — the catalog classifier
     (static/agent/js/tools_dialog.js::classifyPromptModes) must badge the card
     Multi-turn + Exec-report, so clicking it ticks exactly the Multi-Turn and
     Exec report toolbar checkboxes (Angela's reference screenshot, 2026-08-17)
     — and must NOT badge ACPX or Step-by-Step. The checks below mirror the
     classifier's regexes exactly; the end-to-end proof is running the real JS
     function against the seeded content, which yields ["multiturn","execreport"].
"""
import re

from django.test import TestCase

from agent.models import Prompt

# Mirrors of the classifier regexes in tools_dialog.js::classifyPromptModes.
_ACPX_TOOLS_RE = re.compile(
    r'\b(?:acp_doctor|acp_spawn|acp_send|acp_send_and_wait|acp_relay|acp_kill'
    r'|acp_transcript|acp_session_status|acp_list_sessions|list_acp_agents'
    r'|invoke_skill|list_skills)\b',
    re.IGNORECASE,
)
_MULTITURN_RE = re.compile(r'\bmulti-?turn\b', re.IGNORECASE)
_STEPBYSTEP_RES = (
    re.compile(
        r'step-?by-?step\s+(?:wizard|checkbox|toggle|mode|nature|guidance|pacing|cadence|setup)',
        re.IGNORECASE,
    ),
    re.compile(r'(?:tick|check|enable|turn\s+on)[^.\n]{0,60}step-?by-?step', re.IGNORECASE),
)


class DeepResearchPromptTests(TestCase):
    def _prompt(self):
        return Prompt.objects.get(idPrompt=118)

    def test_appended_at_118_in_getting_started(self):
        p = self._prompt()
        self.assertEqual(p.promptName, 'prompt-118')
        self.assertEqual(p.category, 'getting_started')
        self.assertFalse(p.hidden)
        # Angela's verbatim lead text is preserved.
        self.assertIn('search thoroughly all over the entire Internet', p.promptContent)
        self.assertIn('[[ Place your topic here ... ]]', p.promptContent)

    def test_last_card_of_getting_started(self):
        section = list(
            Prompt.objects.filter(category='getting_started', hidden=False)
            .order_by('sort_rank', 'idPrompt')
            .values_list('idPrompt', 'sort_rank')
        )
        self.assertEqual(section[-1], (118, 100),
                         'the Deep Research prompt must render LAST in Getting Started')
        # Rank uniqueness inside the section (the display order must never
        # fall back to idPrompt for two tied cards).
        ranks = [r for _pid, r in section]
        self.assertEqual(len(ranks), len(set(ranks)))

    def test_classifier_badges_multiturn_and_execreport(self):
        c = self._prompt().promptContent
        # Multi-turn trigger present (Exec-report rides along automatically for
        # every non-One-Shot prompt in classifyPromptModes).
        self.assertRegex(c, _MULTITURN_RE)

    def test_classifier_does_not_badge_acpx_or_stepbystep(self):
        c = self._prompt().promptContent
        self.assertNotRegex(c, _ACPX_TOOLS_RE)
        self.assertNotIn('code-review', c)
        self.assertNotIn('security-audit', c)
        for rx in _STEPBYSTEP_RES:
            self.assertNotRegex(c, rx)
