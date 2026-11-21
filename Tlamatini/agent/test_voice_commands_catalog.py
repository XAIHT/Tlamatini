# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
# ══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ══════════════════════════════════════════════════════════════════════════
"""VOICE COMMANDS was REMOVED from the Catalog of Prompts (2026-11-21).

Angela: the microphone button beside Send makes the section unnecessary.
Migration 0201 seeded its two cards (prompt-121, prompt-122); migration 0226
hides them, so the rows keep their ids but the catalog never serves them, and
``views.PROMPT_CATEGORY_ORDER`` no longer lists the section.
"""
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from agent.models import Prompt
from agent.views import PROMPT_CATEGORY_ORDER

SECTION_KEY = 'voice_commands'
VOICE_COMMAND_IDS = (121, 122)


class VoiceCommandsSectionRemovedTests(SimpleTestCase):

    def test_section_is_not_in_the_catalog_order(self):
        self.assertNotIn(SECTION_KEY, [key for key, _label in PROMPT_CATEGORY_ORDER])


class VoiceCommandsCardsHiddenTests(TestCase):

    def test_both_cards_are_hidden(self):
        rows = Prompt.objects.filter(idPrompt__in=VOICE_COMMAND_IDS)
        self.assertEqual(rows.count(), len(VOICE_COMMAND_IDS))
        self.assertFalse(rows.filter(hidden=False).exists())

    def test_catalog_serves_neither_the_section_nor_its_cards(self):
        User.objects.create_user(username='voice-tester', password='x')  # noqa: S106
        self.client.login(username='voice-tester', password='x')  # noqa: S106
        response = self.client.get('/agent/list_prompts/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn(SECTION_KEY, [c['key'] for c in payload['categories']])
        served_ids = {p['index'] for p in payload['prompts']}
        self.assertEqual(served_ids & set(VOICE_COMMAND_IDS), set())
