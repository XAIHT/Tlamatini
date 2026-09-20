"""Model selection across UI, standalone agents and isolated runtimes.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from django.test import RequestFactory, SimpleTestCase

from .agents import model_settings as registry
from .management.commands.check_agent_runtimes import check_model_loader


ROOT = Path(__file__).resolve().parent


def nested(config, path):
    for part in path.split('.'):
        config = config[part]
    return config


class ModelSettingsTests(SimpleTestCase):
    def test_monitor_and_mail_yaml_readers_explicitly_decode_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / 'config.yaml'
            config.write_text(yaml.safe_dump({'unicode_probe': 'Información 日本語'},
                                            allow_unicode=True), encoding='utf-8-sig')
            for name in ('monitor_log', 'monitor_netstat', 'recmailer'):
                with self.subTest(agent=name):
                    script = ROOT / 'agents' / name / f'{name}.py'
                    actual_open = open
                    def cp1252_default(path, mode='r', *args, **kwargs):
                        if 'b' not in mode and 'encoding' not in kwargs:
                            kwargs['encoding'] = 'cp1252'
                        return actual_open(path, mode, *args, **kwargs)
                    with patch('builtins.open', side_effect=cp1252_default):
                        actual = check_model_loader(script, config)
                    self.assertEqual(actual['unicode_probe'], 'Información 日本語')

    def test_actual_copied_yaml_loaders_follow_saved_values_then_local_overrides(self):
        from .services.flow_knowledge import write_runtime_knowledge
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = registry.values_for_dialog({})
            for field in registry.FIELDS:
                if field['agent'] and field['kind'] != 'choice':
                    values[field['key']] = '' if field['optional'] else 'saved/' + field['key']
            settings_path = root / 'config.json'
            settings_path.write_text(json.dumps(values), encoding='utf-8')
            with patch.dict(os.environ, {'CONFIG_PATH': str(settings_path)}):
                for agent in sorted(registry.AGENTS):
                    with self.subTest(agent=agent):
                        folder = root / agent
                        write_runtime_knowledge(folder, agent)
                        script = folder / f'{agent}.py'
                        script.write_bytes((ROOT / 'agents' / agent / script.name).read_bytes())
                        path = folder / 'config.yaml'
                        path.write_bytes((ROOT / 'agents' / agent / path.name).read_bytes())
                        actual = check_model_loader(script, path)
                        for field in registry.FIELDS:
                            if field['agent'] == agent:
                                self.assertEqual(nested(actual, field['path']), values[field['key']])
                        # Literal per-agent choices, including optional blanks,
                        # must survive subsequent global edits and reloading.
                        path.write_text(yaml.safe_dump(actual), encoding='utf-8')
                        with patch.dict(os.environ, {'CONFIG_PATH': str(root / 'absent.json')}):
                            self.assertEqual(check_model_loader(script, path), actual)

    def test_standalone_mcp_uses_saved_models_outside_agents_tree(self):
        source = ROOT.parents[1] / 'tlamatini_mcp_server.py'
        spec = importlib.util.spec_from_file_location('model_settings_mcp_test', source)
        mcp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mcp)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = root / 'config.json'
            settings.write_text(json.dumps({'talker_model': 'saved:speech', 'talker_voice': 'tara'}))
            template = ROOT / 'agents/talker'
            info = {'dir': str(template), 'config': {}}
            with (patch.object(mcp, 'RUNS_ROOT', str(root / 'runs')),
                  patch.object(mcp, 'TEMP_ROOT', str(root)),
                  patch.dict(os.environ, {'CONFIG_PATH': str(settings)}),
                  patch.object(mcp.subprocess, 'Popen') as popen):
                result = mcp.run_agent_blocking('talker', info, {'voice': 'jess'}, False, 5)
                folder = Path(result['run_dir'])
                actual = check_model_loader(folder / 'talker.py', folder / 'config.yaml')
                self.assertEqual(actual['model'], 'saved:speech')
                self.assertEqual(actual['voice'], 'jess')
                self.assertTrue((folder / 'model_settings.py').is_file())
                self.assertEqual(popen.call_args.kwargs['env']['CONFIG_PATH'], str(settings))

    def test_every_model_agent_loads_saved_values_and_preserves_explicit_overrides(self):
        # Run the actual loader functions without executing agent startup code.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'config.json'
            values = registry.values_for_dialog({})
            for field in registry.FIELDS:
                if field['agent'] and field['kind'] != 'choice':
                    values[field['key']] = 'custom/' + field['key']
            path.write_text(json.dumps(values), encoding='utf-8')
            with patch.dict(os.environ, {'CONFIG_PATH': str(path)}):
                for agent in sorted(registry.AGENTS):
                    with self.subTest(agent=agent):
                        source = ROOT / 'agents' / agent / f'{agent}.py'
                        template = yaml.safe_load(source.with_name('config.yaml').read_text(encoding='utf-8'))
                        tree = ast.parse(source.read_text(encoding='utf-8'))
                        loader = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'load_config')
                        namespace = {'__file__': str(source), '_load_config_file': lambda: template}
                        exec(compile(ast.Module(body=[loader], type_ignores=[]), str(source), 'exec'), namespace)
                        actual = namespace['load_config']()
                        for field in registry.FIELDS:
                            if field['agent'] == agent:
                                self.assertEqual(nested(actual, field['path']), values[field['key']])
                                self.assertEqual(nested(template, field['path']), '@config')
            explicit = {'model': 'custom-voice-model', 'voice': 'jess', 'private': 'untouched'}
            self.assertEqual(registry.resolve_agent_models('talker', explicit, values), explicit)

    def test_optional_blanks_and_engine_validation(self):
        values = registry.values_for_dialog({'whisperer_cloud_model': '', 'latexer_model': ''})
        self.assertEqual(values['latexer_model'], '')
        updates, errors = registry.validate_values(values)
        self.assertEqual(errors, {})
        self.assertEqual(updates['whisperer_cloud_model'], '')
        values.update(whisperer_engine='invalid', talker_voice='invalid', video_interpreter_model='@config')
        _, errors = registry.validate_values(values)
        self.assertEqual(set(errors), {'whisperer_engine', 'talker_voice', 'video_interpreter_model'})

    def test_source_frozen_and_pool_config_resolution(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'CONFIG_PATH': ''}):
            base = Path(temp)
            for folder in (base / 'source/agent', base / 'installed'):
                folder.mkdir(parents=True)
                (folder / 'config.json').write_text(json.dumps({'video_interpreter_model': 'saved:vision'}))
                for relative in ('agents/video_analyzer/video_analyzer.py', 'agents/pools/video_1/video_1.py'):
                    actual = registry.resolve_agent_models('video_analyzer', {}, agent_file=folder / relative)
                    self.assertEqual(actual['interpreter_model_1'], 'saved:vision')
            (folder / 'config.json').write_text('{broken')
            self.assertEqual(registry.read_app_config(folder / relative), {})

    def test_isolated_helper_refresh(self):
        from .services.flow_knowledge import write_runtime_knowledge
        with tempfile.TemporaryDirectory() as temp:
            for agent in registry.AGENTS:
                target = Path(temp) / agent
                write_runtime_knowledge(target, agent)
                self.assertEqual((target / 'model_settings.py').read_bytes(),
                                 (ROOT / 'agents/model_settings.py').read_bytes())

    def test_runtime_copy_with_frozen_module_paths(self):
        from . import chat_agent_runtime
        from .services import flow_knowledge
        # Frozen modules have synthetic __file__ paths, not loose .py files.
        # The old code failed here before even a non-model agent could start.
        with tempfile.TemporaryDirectory() as temp:
            internal = Path(temp) / '_internal/agent/services/flow_knowledge.py'
            with (patch.object(sys, 'frozen', True, create=True),
                  patch.object(sys, 'executable', str(Path(temp) / 'Tlamatini.exe')),
                  patch.object(flow_knowledge, '__file__', str(internal)),
                  patch.object(flow_knowledge, 'get_agents_root', return_value=ROOT / 'agents')):
                for name in ('file_creator', 'talker', 'whisperer', 'video_analyzer',
                             'flowcreator', 'flowhypervisor', 'parametrizer'):
                    with self.subTest(agent=name):
                        _, folder, _ = chat_agent_runtime.create_isolated_runtime_copy(
                            str(ROOT / 'agents' / name), name, runtime_root=temp)
                        folder = Path(folder)
                        self.assertTrue((folder / f'{name}.py').is_file())
                        if name in registry.AGENTS:
                            self.assertEqual((folder / 'model_settings.py').read_bytes(),
                                             (ROOT / 'agents/model_settings.py').read_bytes())
                        flow_knowledge.write_runtime_knowledge(folder, name)

    def test_non_model_agent_does_not_require_a_loose_registry(self):
        from .services import flow_knowledge
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(flow_knowledge, 'get_agents_root', return_value=Path(temp)):
                flow_knowledge.write_runtime_knowledge(Path(temp) / 'file_creator', 'file_creator')
            self.assertFalse((Path(temp) / 'model_settings.py').exists())

    def test_wrapped_chat_defaults_then_per_call_override(self):
        from .tools import _seed_global_agent_defaults
        values = registry.values_for_dialog({'video_interpreter_model': 'saved:vision', 'talker_model': 'saved:speech'})
        with patch('agent.tools.get_config_value', side_effect=lambda key, *args, **kwargs: values.get(key)):
            for agent in ('video_analyzer', 'talker', 'whisperer', 'flowcreator'):
                result = _seed_global_agent_defaults(agent, {})
                for field in registry.FIELDS:
                    if field['agent'] == agent:
                        self.assertEqual(nested(result, field['path']), values[field['key']])

    def test_models_get_save_and_rejected_input_are_atomic(self):
        from .views import load_config_section_view, save_config_models_view
        factory = RequestFactory()
        request = factory.get('/agent/load_config_section/models/')
        request.user = SimpleNamespace(is_authenticated=True)
        with patch('agent.views.load_config', return_value={'talker_voice': 'jess'}):
            response = json.loads(load_config_section_view(request, 'models').content)
        self.assertEqual(len(response['fields']), len(registry.FIELDS))
        self.assertEqual(response['values']['talker_voice'], 'jess')
        values = response['values']
        values['whisperer_model'] = 'small'
        for invalid in (False, True):
            if invalid:
                values['talker_voice'] = 'invalid'
            request = factory.post('/agent/save_config_models/', json.dumps(values), content_type='application/json')
            request.user = SimpleNamespace(is_authenticated=True)
            with patch('agent.views.save_config_updates', return_value='config.json') as save:
                response = save_config_models_view(request)
                self.assertEqual(response.status_code, 400 if invalid else 200)
                if invalid:
                    save.assert_not_called()
                else:
                    self.assertEqual(save.call_args.args[0]['whisperer_model'], 'small')
