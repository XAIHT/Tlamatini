"""Tests for the create-superuser wizard catalog prompt (migration 0145).

The wizard is INSERTED at catalog slot #1 (prompt-1) by 0145, which shifts every
pre-existing prompt up by one. These tests pin the contract the frontend relies
on: the wizard is genuinely first, the catalog stays gap-free, and the prompt
carries the exact keywords the catalog classifier (static/agent/js/tools_dialog.js
::classifyPromptModes) keys on to badge it Multi-turn + Step-by-Step + Exec-report
(and NOT ACPX) and to run createsuperuser in both frozen and source modes.
"""
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
        self.assertIn('----<set name here>----', p.promptContent)
        self.assertIn('treat that reply as <USERNAME> and continue to Step 1', p.promptContent)

    def test_catalog_is_contiguous_and_wizard_first(self):
        ids = sorted(Prompt.objects.values_list('idPrompt', flat=True))
        self.assertEqual(ids[0], 1, 'the wizard must be the very first catalog prompt')
        gaps = [n for n in range(ids[0], ids[-1] + 1) if n not in ids]
        self.assertEqual(gaps, [], 'the catalog must stay gap-free for the dropdown')

    def test_classifier_keywords_present(self):
        # Mirrors tools_dialog.js::classifyPromptModes — these substrings are what
        # make the card badge Multi-turn + Step-by-Step + Exec-report and tick the
        # three toolbar checkboxes on click.
        c = self._wizard().promptContent
        self.assertIn('Multi-Turn', c)            # -> Multi-turn (+ Exec-report)
        self.assertIn('chat_agent_executer', c)   # -> Multi-turn (operator tool)
        # -> Step-by-Step (hyphenated form + intent word; the spaced "step by step"
        #    used elsewhere in the catalog must NOT trip the same detector).
        self.assertRegex(c, r'[Ss]tep-by-[Ss]tep\s+(?:setup|wizard|checkbox)')
        # Must NOT look like an ACPX prompt.
        self.assertNotIn('acp_spawn', c)
        self.assertNotIn('invoke_skill', c)

    def test_runs_in_both_frozen_and_source(self):
        c = self._wizard().promptContent
        self.assertIn('Tlamatini.exe" createsuperuser', c)      # frozen branch
        self.assertIn('python manage.py createsuperuser', c)    # source branch
        self.assertIn('execute_forked_window=true', c)          # visible console
        self.assertIn('non_blocking=true', c)                   # detached, returns
        self.assertIn('restart', c.lower())                     # restart guidance
