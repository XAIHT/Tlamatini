# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the create-superuser wizard catalog prompt (migration 0145).

The wizard is INSERTED at catalog slot #1 (prompt-1) by 0145, which shifts every
pre-existing prompt up by one. These tests pin the contract the frontend relies
on: the wizard is genuinely first, surviving prompt IDs stay stable, and the prompt
carries the exact keywords the catalog classifier (static/agent/js/tools_dialog.js
::classifyPromptModes) keys on to badge it Multi-turn + Step-by-Step + Exec-report
(and NOT ACPX) and to run createsuperuser in both frozen and source modes.
"""
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from agent.models import Prompt


class CreateSuperuserWizardPromptTests(TestCase):
    def _wizard(self):
        return Prompt.objects.get(idPrompt=1)

    def test_wizard_is_catalog_slot_one(self):
        p = self._wizard()
        self.assertEqual(p.promptName, 'prompt-1')
        self.assertIn('createsuperuser', p.promptContent)
        # Angela's opening phrasing + the placeholder the user edits before sending.
        # The catalog moved to the standardized parameter grammar (migrations
        # 0182-0185): `[[ ... ]]` marks a value the USER types. The old
        # `----<set name here>----` marker no longer exists anywhere.
        self.assertIn('[[ TYPE THE USERNAME HERE', p.promptContent)
        # The integrated handler accepts the next username only for this
        # wizard's pending exchange; it never asks a model to reconstruct it.
        self.assertIn('Treat my next bare username as the answer',
                      p.promptContent)

    def test_catalog_preserves_ids_and_wizard_first(self):
        ids = sorted(Prompt.objects.values_list('idPrompt', flat=True))
        self.assertEqual(ids[0], 1, 'the wizard must be the very first catalog prompt')
        gaps = [n for n in range(ids[0], ids[-1] + 1) if n not in ids]
        self.assertEqual(
            gaps, [90, 91, 92, 93],
            'Only the retired catalog slots may be absent; surviving IDs stay stable',
        )

    def test_classifier_keywords_present(self):
        # Mirrors tools_dialog.js::classifyPromptModes — these substrings are what
        # make the card badge Multi-turn + Step-by-Step + Exec-report and tick the
        # three toolbar checkboxes on click.
        c = self._wizard().promptContent
        self.assertIn('Multi-Turn', c)            # -> Multi-turn (+ Exec-report)
        self.assertIn('Exec Report', c)
        # -> Step-by-Step (hyphenated form + intent word; the spaced "step by step"
        #    used elsewhere in the catalog must NOT trip the same detector).
        self.assertRegex(c, r'[Ss]tep-by-[Ss]tep\s+(?:setup|wizard|checkbox)')
        # Must NOT look like an ACPX prompt.
        self.assertNotIn('acp_spawn', c)
        self.assertNotIn('invoke_skill', c)

    def test_runs_in_both_frozen_and_source(self):
        c = self._wizard().promptContent
        self.assertIn('source run, use the exact running Python and absolute manage.py path', c)
        self.assertIn("installed run, use this instance's executable", c)
        self.assertIn('createuserconsole', c)
        self.assertIn('Open one visible interactive console and return control', c)
        self.assertIn('without restarting', c)

    def test_integrated_handoff_is_private_and_does_not_poll_agents(self):
        text = self._wizard().promptContent
        self.assertIn('without asking a model to build a command', text)
        self.assertIn('never in chat', text)
        self.assertIn('Do not capture the credentials console', text)
        self.assertIn('poll agents', text)
        self.assertIn('A requested launch alone does not confirm', text)
        self.assertIn('DONE', text)
        self.assertIn('ERROR', text)
        self.assertIn('NOWINDOW', text)

    def test_repair_is_reversible_idempotent_and_preserves_metadata(self):
        migration = import_module('agent.migrations.0223_create_superuser_console_handoff')
        editor = SimpleNamespace(connection=connection)
        row = self._wizard()
        metadata = (row.promptName, row.category, row.sort_rank, row.hidden)
        self.assertEqual(row.promptContent, migration.WIZARD_PROMPT)
        migration.reverse(apps, editor)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, migration.OLD_WIZARD_PROMPT)
        migration.repair(apps, editor)
        migration.repair(apps, editor)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, migration.WIZARD_PROMPT)
        self.assertEqual((row.promptName, row.category, row.sort_rank, row.hidden), metadata)

    def test_repair_preserves_customized_card_and_metadata(self):
        migration = import_module('agent.migrations.0223_create_superuser_console_handoff')
        editor = SimpleNamespace(connection=connection)
        row = self._wizard()
        custom = migration.OLD_WIZARD_PROMPT + '\nMy own instruction.'
        row.promptContent = custom
        row.hidden = True
        row.sort_rank = 999
        row.save()
        migration.repair(apps, editor)
        migration.reverse(apps, editor)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, custom)
        self.assertTrue(row.hidden)
        self.assertEqual(row.sort_rank, 999)
