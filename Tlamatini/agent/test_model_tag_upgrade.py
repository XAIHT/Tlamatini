# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Retired model choices migrate without changing unrelated user settings."""
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from django.apps import apps
from django.db import connection
from django.test import SimpleTestCase, TestCase
from agent.agents import model_settings as registry
from agent.models import Prompt

OLD_VISION = 'mistral-large-3:675b-cloud'
SPEECH_MODEL = 'legraphista/Orpheus:3b-ft-q8'


class ModelTagConfigurationTests(SimpleTestCase):
    def test_old_saved_choices_resolve_in_dialog_chat_and_agent_overrides(self):
        original = {'image_interpreter_model': OLD_VISION,
                    'talker_model': SPEECH_MODEL, 'talker_voice': 'tara',
                    'unified_agent_model': 'my-model:custom',
                    'unrelated': OLD_VISION}
        resolved = registry.normalize_model_config(original)
        self.assertEqual(resolved['image_interpreter_model'], 'mistral-large-4:cloud')
        self.assertEqual(resolved['talker_model'], SPEECH_MODEL)
        self.assertEqual(resolved['talker_voice'], 'tara')
        self.assertEqual(resolved['unrelated'], OLD_VISION)
        self.assertEqual(resolved['unified_agent_model'], 'my-model:custom')
        self.assertEqual(original['talker_model'], SPEECH_MODEL)
        self.assertEqual(registry.values_for_dialog(original)['talker_model'],
                         SPEECH_MODEL)
        yaml = registry.resolve_agent_models('talker', {'model': SPEECH_MODEL, 'voice': 'tara'}, {})
        self.assertEqual(yaml['model'], SPEECH_MODEL)
        self.assertEqual(yaml['voice'], 'tara')
        yaml = registry.resolve_agent_models('talker', {'model': 'custom:local'}, {})
        self.assertEqual(yaml['model'], 'custom:local')

    def test_initial_text_models_use_deepseek_without_changing_speech_or_embeddings(self):
        defaults = registry.values_for_dialog({})
        for key in ('chained-model', 'unified_agent_model', 'access_aimed_prompt_model',
                    'mcp_files_search_model', 'image_merging_model', 'video_merging_model',
                    'pdfer_model', 'flowcreator_model', 'summarizer_model'):
            self.assertEqual(defaults[key], 'deepseek-v4.1-flash:cloud', key)
        self.assertEqual(defaults['talker_model'], SPEECH_MODEL)
        self.assertEqual(defaults['embeding-model'], 'Nomic-Embed-Text:latest')
        self.assertEqual(registry.values_for_dialog({'unified_agent_model': 'glm-5.3:cloud'})
                         ['unified_agent_model'], 'glm-5.3:cloud')

    def test_saved_dialog_values_cannot_restore_the_retired_defaults(self):
        payload = registry.values_for_dialog({})
        payload['image_interpreter_model'] = OLD_VISION
        payload['talker_model'] = SPEECH_MODEL
        saved, errors = registry.validate_values(payload)
        self.assertFalse(errors)
        self.assertEqual(saved['image_interpreter_model'], 'mistral-large-4:cloud')
        self.assertEqual(saved['talker_model'], SPEECH_MODEL)


class ModelTagCatalogTests(TestCase):
    def test_upgrade_changes_only_tags_and_is_idempotent(self):
        filename = next((Path(__file__).parent / 'migrations').glob('*_replace_mistral_large3.py'))
        migration = import_module('agent.migrations.' + filename.stem)
        row = Prompt.objects.create(idPrompt=9002, promptName='Custom title',
                                    promptContent='Use ' + OLD_VISION + ' then ' + SPEECH_MODEL,
                                    category='custom', sort_rank=999, hidden=True)
        editor = SimpleNamespace(connection=connection)
        migration.replace_tag(apps, editor)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, 'Use mistral-large-4:cloud then ' + SPEECH_MODEL)
        self.assertEqual((row.promptName, row.category, row.sort_rank, row.hidden),
                         ('Custom title', 'custom', 999, True))
        before = list(Prompt.objects.order_by('pk').values())
        migration.replace_tag(apps, editor)
        self.assertEqual(before, list(Prompt.objects.order_by('pk').values()))

    def test_fresh_catalog_has_no_retired_model_choices(self):
        for tag in (OLD_VISION, 'glm-5.3:cloud'):
            self.assertFalse(Prompt.objects.filter(promptContent__contains=tag).exists())
