"""Offline flow/catalog regressions. No LLM requests or desktop input are sent."""
import importlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, mock_open

import yaml


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UPDATER = load_file("catalog_updater_test", REPO / "scripts/update_flow_catalog.py")
KNOWLEDGE = load_file("knowledge_test", ROOT / "agents/flowcreator/flow_knowledge.py")
CONVERTER = load_file("converter_test", ROOT / "agents/flowcreator/result_to_flw.py")
CATALOG = KNOWLEDGE.load_catalog()
SPEC = importlib.import_module(UPDATER.package.__name__ + ".flow_spec")
COMPILER = importlib.import_module(UPDATER.package.__name__ + ".flow_compiler")


def load_agent(name):
    with (patch.dict(sys.modules, {'flow_knowledge': KNOWLEDGE}),
          patch.object(os, 'chdir'), patch('builtins.open', mock_open()),
          patch.object(logging, 'basicConfig'), patch.object(logging.getLogger(), 'addHandler'),
          patch.object(subprocess, '_conhost_guard_applied', True, create=True),
          patch.object(sys, 'stderr', sys.stderr)):
        return load_file(f'test_{name}_module', ROOT / f'agents/{name}/{name}.py')


def agent(name, **config):
    return {'agent_type': name, 'config': config}


class CatalogTests(unittest.TestCase):
    def test_skill_converter_matches_runtime_converter(self):
        self.assertEqual((ROOT / 'agents/flowcreator/result_to_flw.py').read_bytes(),
                         (ROOT / 'skills_pkg/flow_making/scripts/result_to_flw.py').read_bytes())

    def test_every_installed_agent_has_current_contract_and_schema(self):
        actual = {p.name for p in (ROOT / 'agents').iterdir()
                  if (p / (p.name + '.py')).is_file() and (p / 'config.yaml').is_file()}
        self.assertEqual(set(CATALOG), actual)
        self.assertEqual(KNOWLEDGE.load_catalog(), UPDATER.exporter.build_catalog()['agents'])
        for name, spec in CATALOG.items():
            cfg = yaml.safe_load((ROOT / f'agents/{name}/config.yaml').read_text(encoding='utf-8'))
            self.assertTrue(set(cfg).issubset(spec['config_schema']), name)
            self.assertTrue(spec['purpose'], name)

    def test_each_agent_has_detailed_guide_and_selection_entry(self):
        guide = (ROOT / 'agents/flowcreator/agentic_skill.md').read_text(encoding='utf-8')
        details = KNOWLEDGE.guide_sections(guide, CATALOG)
        roster = KNOWLEDGE.roster_prompt(CATALOG)
        self.assertEqual(set(details), set(CATALOG))
        for name in CATALOG:
            self.assertIn(name + ': ', roster)
            prompt = KNOWLEDGE.design_prompt(guide, CATALOG, [name])
            self.assertIn('"' + name + '":', prompt)
            self.assertIn(details[name], prompt)
            self.assertEqual(prompt.count('## Output Format'), 1)

    def test_selection_rejects_nonexistent_gui_manager(self):
        with self.assertRaises(ValueError):
            KNOWLEDGE.select_types('["GUI-Manager"]', CATALOG)
        self.assertIn('keyboarder', KNOWLEDGE.select_types('["Keyboarder"]', CATALOG))

    def test_export_contains_types_never_config_values(self):
        schema = UPDATER.exporter.config_schema({'token': 'TOP_SECRET', 'headers': {'Authorization': 'Bearer SECRET'}, 'port': 8877})
        self.assertNotIn('SECRET', json.dumps(schema))
        self.assertEqual(schema['port'], 'int')

    def test_runtime_refresh_contains_helper_and_current_catalog(self):
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            for name in ('flowcreator', 'flowhypervisor', 'parametrizer'):
                folder = Path(temp) / name
                UPDATER.exporter.write_runtime_knowledge(folder, name)
                self.assertTrue((folder / 'flow_knowledge.py').is_file())
                self.assertEqual(json.loads((folder / 'flow_catalog.json').read_text(encoding='utf-8'))['agents'], CATALOG)

    def test_non_agent_directory_is_not_registered(self):
        contracts = importlib.import_module(UPDATER.package.__name__ + '.agent_contracts')
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            (Path(temp) / 'debris').mkdir()
            with patch.object(contracts, 'get_agents_root', return_value=Path(temp)):
                self.assertEqual(contracts._discover_contracts_from_disk(), {})

    def test_existing_pool_refresh_installs_portable_helpers(self):
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            for name, helper in (('mouser', 'mouser_coordinates.py'), ('keyboarder', 'keyboarder_input.py'),
                                 ('video_analyzer', 'video_content.py')):
                node = SPEC.FlowNode(id=name + '-1', text=CATALOG[name]['display_name'])
                folder = Path(temp) / node.pool_name
                folder.mkdir()
                (folder / 'config.yaml').write_text('custom: preserved\n', encoding='utf-8')
                COMPILER._ensure_pool_agent(node, Path(temp))
                self.assertTrue((folder / helper).is_file())
                self.assertEqual((folder / 'config.yaml').read_text(encoding='utf-8'), 'custom: preserved\n')


class FlowTests(unittest.TestCase):
    def build(self, *agents):
        return KNOWLEDGE.build_flow(list(agents), CATALOG)

    def test_every_agent_type_can_be_represented_and_converted(self):
        for name, spec in CATALOG.items():
            if name == 'parametrizer':
                continue  # Mapping tested with its actual source and target below.
            with self.subTest(agent=name):
                result = CONVERTER.convert(self.build(agent(name)))
                normalized = SPEC.normalize_flow_payload(result)
                self.assertEqual(normalized.nodes[0].agent_type, name)
                self.assertEqual(result['nodes'][0]['text'], spec['display_name'])

    def test_counter_both_branches_reach_compiler_with_correct_slots(self):
        result = self.build(agent('starter', target_agents=['counter_1']),
                            agent('counter', target_agents_l=['sleeper_1'], target_agents_g=['ender_1']),
                            agent('sleeper'), agent('ender', target_agents=['starter_1']))
        self.assertIn({'sourceIndex': 1, 'targetIndex': 2, 'inputSlot': 0, 'outputSlot': 1}, result['connections'])
        self.assertIn({'sourceIndex': 1, 'targetIndex': 3, 'inputSlot': 0, 'outputSlot': 2}, result['connections'])
        compiled = COMPILER.compile_flow_spec(SPEC.normalize_flow_payload(CONVERTER.convert(result)), write=False)
        counter = next(a['config'] for a in compiled['agents'] if a['folder_name'] == 'counter_1')
        self.assertEqual(counter['target_agents_l'], ['sleeper_1'])
        self.assertEqual(counter['target_agents_g'], ['ender_1'])

    def test_ender_kill_list_does_not_become_outgoing_edges_or_auto_attach_leaves(self):
        result = self.build(agent('sleeper'), agent('ender', target_agents=['sleeper_1']))
        self.assertEqual(result['connections'], [])

    def test_dual_input_connections_are_deduplicated(self):
        result = self.build(agent('starter', target_agents=['and_1']), agent('sleeper', target_agents=['and_1']),
                            agent('and', source_agent_1='starter_1', source_agent_2='sleeper_1'))
        self.assertEqual(len(result['connections']), 2)
        self.assertEqual({c['inputSlot'] for c in result['connections']}, {1, 2})

    def test_branch_source_requires_explicit_output(self):
        with self.assertRaisesRegex(ValueError, 'Branch'):
            self.build(agent('forker'), agent('sleeper', source_agents=['forker_1']))

    def test_invalid_references_and_unknown_fields_fail(self):
        for cfg in ({'target_agents': ['absent_1']}, {'made_up': 42}, {'target_agents': 'sleeper_1'}):
            with self.subTest(config=cfg), self.assertRaises(ValueError):
                self.build(agent('starter', **cfg), agent('sleeper'))

    def test_singleton_and_no_input_rules(self):
        for agents in ([agent('flowhypervisor'), agent('flowhypervisor')],
                       [agent('starter', target_agents=['flowhypervisor']), agent('flowhypervisor')]):
            with self.assertRaises(ValueError):
                self.build(*agents)

    def test_fractional_mouse_and_dynamic_http_headers(self):
        self.build(agent('mouser', coordinate_space='normalized', end_posx=0.25, end_posy=0.5))
        self.build(agent('apirer', headers={'X-Custom': 'example'}))

    def mapping_flow(self, field='image_width', target='image_width'):
        return [agent('shoter', target_agents=['parametrizer_1']),
                agent('parametrizer', source_agent='shoter_1', target_agent='mouser_1',
                      _parametrizer_mappings=[{'source_field': field, 'target_param': target}]),
                agent('mouser', movement_type='inspect')]

    def test_parametrizer_geometry_mapping_survives_compilation(self):
        result = self.build(*self.mapping_flow())
        compiled = COMPILER.compile_flow_spec(SPEC.normalize_flow_payload(CONVERTER.convert(result)), write=False)
        self.assertEqual(len(result['connections']), 2)
        self.assertEqual(len(compiled['agents']), 3)

    def test_invalid_mapping_is_rejected(self):
        for field, target in (('fabricated', 'image_width'), ('image_width', 'fabricated')):
            with self.assertRaises(ValueError):
                self.build(*self.mapping_flow(field, target))


class ParametrizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_agent('parametrizer')

    def test_every_declared_producer_is_parseable(self):
        expected = {name for name, spec in CATALOG.items() if spec['output_fields']}
        self.assertEqual(set(self.module.SECTION_AGENT_TYPES), expected)
        for name in expected:
            fields = CATALOG[name]['output_fields']
            headers = '\r\n'.join(field + ': ' for field in fields if field != 'response_body')
            block = f'INI_SECTION_{name.upper()}<<<\r\n{headers}\r\n\r\nbody\r\n>>>END_SECTION_{name.upper()}'
            parsed = self.module.OUTPUT_PARSERS[name](block)[0]
            self.assertTrue(set(fields).issubset(parsed), name)
            self.assertEqual(parsed['response_body'], 'body')

    def test_empty_and_url_fields_preserved(self):
        parsed = self.module._parse_section_content('status: error\r\noutput_path: \r\nurl: https://example.test:443/a\r\n\r\nbody')
        self.assertEqual(parsed['output_path'], '')
        self.assertEqual(parsed['url'], 'https://example.test:443/a')

    def test_numeric_boolean_and_list_coercion(self):
        fn = self.module._coerce_value_for_target
        self.assertEqual(fn(0, '-1920'), -1920)
        self.assertIs(fn(True, 'false'), False)
        self.assertEqual(fn(0.5, '1.25'), 1.25)
        self.assertEqual(fn([], 'image.png'), ['image.png'])
        self.assertEqual(fn('', '001'), '001')
        for existing, value in ((0, '1.5'), (False, 'maybe'), (1.0, 'nan')):
            with self.assertRaises(ValueError):
                fn(existing, value)

    def test_partial_mapping_does_not_write_target(self):
        mappings = [{'source_field': 'a', 'target_param': 'image_width'}, {'source_field': 'b', 'target_param': 'image_height'}]
        with patch.object(self.module, 'write_target_config') as write:
            self.assertFalse(self.module.apply_mappings_to_config('mouser_1', mappings, {'a': '400'}, {'image_width': 0, 'image_height': 0}))
            write.assert_not_called()

    def test_interrupted_desktop_input_is_not_replayed(self):
        with (patch.object(self.module, 'get_target_backup_path', return_value='absent'),
              patch.object(self.module, 'save_progress_state') as save):
            with self.assertRaisesRegex(RuntimeError, 'automatic replay is blocked'):
                self.module.reconcile_reanimation_state('shoter_1', 'keyboarder_1', {'stage': self.module.STATE_STAGE_WAITING_TARGET})
            save.assert_not_called()

    def test_fresh_restart_cannot_bypass_desktop_replay_guard(self):
        m = self.module
        with (patch.object(m, 'load_config', return_value={'source_agent': 'shoter_1', 'target_agent': 'keyboarder_1'}),
              patch.object(m, 'load_interconnection_scheme', return_value=[{'source_field': 'response_body', 'target_param': 'text'}]),
              patch.object(m, 'load_progress_state', return_value={'stage': m.STATE_STAGE_WAITING_TARGET}),
              patch.object(m, 'get_target_backup_path', return_value='absent'),
              patch.object(m, 'write_pid_file'), patch.object(m, 'remove_pid_file'),
              patch.object(m.time, 'sleep'), patch.object(m, 'clear_progress_state') as clear,
              patch.object(m, '_IS_REANIMATED', False)):
            with self.assertRaisesRegex(RuntimeError, 'automatic replay is blocked'):
                m.main()
            clear.assert_not_called()


class HypervisorTests(unittest.TestCase):
    def test_execution_matrix_distinguishes_branches_kills_and_passive_links(self):
        names = ['counter_1', 'sleeper_1', 'ender_1', 'emailer_1', 'parametrizer_1']
        configs = {'counter_1': {'target_agents_l': ['sleeper_1'], 'target_agents_g': ['ender_1']},
                   'ender_1': {'target_agents': ['sleeper_1']}, 'emailer_1': {'target_agents': ['sleeper_1']},
                   'parametrizer_1': {'target_agent': 'sleeper_1'}}
        matrix = KNOWLEDGE.execution_matrix(names, configs, CATALOG)
        self.assertEqual(matrix[0][1:3], [1, 1])
        self.assertEqual(sum(matrix[2]), 0)
        self.assertEqual(sum(matrix[3]), 0)
        self.assertEqual(matrix[4][1], 1)

    def test_context_reports_duration_without_typed_content(self):
        context = KNOWLEDGE.monitoring_contract_context(['keyboarder_1', 'mouser_1'],
            {'keyboarder_1': {'text': 'PRIVATE_TEXT'}, 'mouser_1': {'total_time': 90}}, CATALOG)
        self.assertIn('total_time=90', context)
        self.assertNotIn('PRIVATE_TEXT', context)
        self.assertIn('input delivery only', context)

    def test_latest_receipt_persists_without_incremental_logs(self):
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            folder = Path(temp) / 'keyboarder_1'
            folder.mkdir()
            (folder / 'keyboarder_1.log').write_text('INI_SECTION_KEYBOARDER<<<\nstatus: error\ncharacters_sent: 3\n\nprivate body\n>>>END_SECTION_KEYBOARDER', encoding='utf-8')
            for _ in range(2):
                receipt = KNOWLEDGE.desktop_outcomes(temp, ['keyboarder_1'])
                self.assertIn('"status": "error"', receipt)
                self.assertNotIn('private body', receipt)

    def test_discovery_ignores_debris(self):
        module = load_agent('flowhypervisor')
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            (Path(temp) / 'garbage').mkdir()
            self.assertEqual(module.discover_agents(temp), [])


class FlowCreatorFailureTests(unittest.TestCase):
    def test_repaired_plan_writes_real_flw_and_canvas_result(self):
        module = load_agent('flowcreator')
        guide = (ROOT / 'agents/flowcreator/agentic_skill.md').read_text(encoding='utf-8')
        valid = [agent('starter', target_agents=['counter_1']),
                 agent('counter', target_agents_l=['sleeper_1'], target_agents_g=['ender_1']),
                 agent('sleeper'), agent('ender')]
        responses = ['["counter","sleeper"]', '[{"agent_type":"starter","config":{"target_agents":["missing_1"]}}]', json.dumps(valid)]
        with tempfile.TemporaryDirectory(dir=REPO / 'Temp') as temp:
            with (patch.dict(sys.modules, {'flow_knowledge': KNOWLEDGE, 'result_to_flw': CONVERTER}),
                  patch.object(module, '__file__', str(Path(temp) / 'flowcreator.py')),
                  patch.object(module, 'load_config', return_value={'prompt': 'a counter branch', 'flow_filename': 'verified.flw', 'output_dir': temp}),
                  patch.object(module, 'load_agentic_skill', return_value=guide),
                  patch.object(module, 'query_ollama', side_effect=responses) as query,
                  patch.object(module, 'write_pid_file'), patch.object(module, 'remove_pid_file'),
                  patch.object(module.time, 'sleep')):
                with self.assertRaises(SystemExit) as result:
                    module.main()
                self.assertEqual(result.exception.code, 0)
                self.assertEqual(query.call_count, 3)
            flw = json.loads((Path(temp) / 'verified.flw').read_text(encoding='utf-8'))
            canvas = json.loads((Path(temp) / 'flow_result.json').read_text(encoding='utf-8'))
            self.assertEqual(canvas['status'], 'success')
            self.assertEqual(flw['schemaVersion'], 2)
            self.assertEqual(len(flw['connections']), 3)

    def test_early_error_exits_nonzero_and_removes_pid(self):
        module = load_agent('flowcreator')
        with (patch.object(module, 'load_config', return_value={'prompt': ''}),
              patch.object(module, 'write_pid_file'), patch.object(module, 'remove_pid_file') as remove,
              patch.object(module.time, 'sleep'), patch('builtins.open', mock_open())):
            with self.assertRaises(SystemExit) as error:
                module.main()
            self.assertEqual(error.exception.code, 1)
            remove.assert_called_once()

    def test_flw_write_failure_never_publishes_success(self):
        module = load_agent('flowcreator')
        responses = ['["sleeper"]', '[{"agent_type":"starter","config":{"target_agents":["sleeper_1"]}},{"agent_type":"sleeper","config":{}}]']
        guide = (ROOT / 'agents/flowcreator/agentic_skill.md').read_text(encoding='utf-8')
        with (patch.dict(sys.modules, {'flow_knowledge': KNOWLEDGE}),
              patch.object(module, 'load_config', return_value={'prompt': 'wait'}),
              patch.object(module, 'load_agentic_skill', return_value=guide),
              patch.object(module, 'query_ollama', side_effect=responses),
              patch.object(module, 'write_pid_file'), patch.object(module, 'remove_pid_file'),
              patch.object(module, '_write_flw_file', return_value=''),
              patch.object(module.time, 'sleep'), patch('builtins.open', mock_open()),
              patch.object(module.logging, 'info') as info):
            with self.assertRaises(SystemExit) as error:
                module.main()
            self.assertEqual(error.exception.code, 1)
            self.assertFalse(any('status: success' in str(call) for call in info.call_args_list))


if __name__ == '__main__':
    unittest.main()
