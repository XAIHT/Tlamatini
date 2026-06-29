# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Unrealer workflow agent and its surrounding infrastructure.

Unrealer drives a live Unreal Engine 5 editor through the Unreal MCP plugin's TCP
socket protocol (one ``{"type": <command>, "params": {...}}`` JSON command per run on
``127.0.0.1:55557``). It is a standalone pool agent under ``agent/agents/unrealer/``
that runs as a separate Python subprocess, so — exactly like the Kalier / Windower /
De-Compresser test modules — it is loaded through ``importlib.util.spec_from_file_location``
with a cwd save/restore so its module-level ``os.chdir`` + ``open(LOG_FILE_PATH)`` side
effects land in its own directory.

The agent is a *generic command forwarder*: it does not validate the command surface,
it sends whatever ``command`` + ``params`` config.yaml carries. These tests therefore
exercise the three defensive pre-send fixups that DO live in the agent —

- ``_normalize_content_path`` / ``_normalize_params_for_unreal``: /Content/ → /Game/
  normalization on the known content-path keys (including the P2 Asset + Material keys),
  while DISK-path keys (``source_file``, ``filepath``) are deliberately left alone.
- ``_remap_console_command``: ``params.console_command`` → the wire's ``params.command``
  for ``execute_console_command`` (so the console line does not collide with the agent's
  top-level ``command:`` selector).
- ``_prune_unset_params``: empty placeholder params ('', [], {}, None) are dropped, while
  meaningful ``0`` / ``False`` survive.

— plus the registry / contract / config.yaml integration that lets the expanded
53-command, nine-category surface actually be reached from chat and the canvas.
"""

import importlib.util
import logging
import os
import unittest
from functools import lru_cache

import yaml
from django.test import SimpleTestCase


@lru_cache(maxsize=1)
def _load_unrealer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'unrealer', 'unrealer.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_unrealer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Unrealer module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


def _config_path():
    return os.path.join(
        os.path.dirname(__file__), 'agents', 'unrealer', 'config.yaml',
    )


@lru_cache(maxsize=1)
def _load_unrealer_config():
    with open(_config_path(), encoding='utf-8') as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# _normalize_content_path — UE virtual content root
# ---------------------------------------------------------------------------


class NormalizeContentPathTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_content_prefix_becomes_game(self):
        self.assertEqual(self.u._normalize_content_path('/Content/UI'), '/Game/UI')

    def test_bare_content_root_becomes_game(self):
        self.assertEqual(self.u._normalize_content_path('/Content'), '/Game')

    def test_game_path_is_untouched(self):
        self.assertEqual(self.u._normalize_content_path('/Game/Maps/L1'), '/Game/Maps/L1')

    def test_backslashes_normalized_and_trailing_slash_stripped(self):
        self.assertEqual(self.u._normalize_content_path('\\Content\\UI\\'), '/Game/UI')

    def test_non_string_passthrough(self):
        self.assertEqual(self.u._normalize_content_path(123), 123)

    def test_empty_string_passthrough(self):
        self.assertEqual(self.u._normalize_content_path(''), '')


# ---------------------------------------------------------------------------
# _normalize_params_for_unreal — which keys get normalized
# ---------------------------------------------------------------------------


class NormalizeParamsTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_legacy_content_keys_normalized(self):
        params = {'path': '/Content/UI', 'asset_path': '/Content/Meshes'}
        out = self.u._normalize_params_for_unreal(params)
        self.assertEqual(out['path'], '/Game/UI')
        self.assertEqual(out['asset_path'], '/Game/Meshes')

    def test_new_asset_and_material_content_keys_normalized(self):
        params = {
            'destination_path': '/Content/Imported',
            'source': '/Content/A',
            'destination': '/Content/B',
            'parent_material': '/Content/Materials/M_Base',
            'material': '/Content/Materials/MI_Base',
        }
        out = self.u._normalize_params_for_unreal(params)
        self.assertEqual(out['destination_path'], '/Game/Imported')
        self.assertEqual(out['source'], '/Game/A')
        self.assertEqual(out['destination'], '/Game/B')
        self.assertEqual(out['parent_material'], '/Game/Materials/M_Base')
        self.assertEqual(out['material'], '/Game/Materials/MI_Base')

    def test_disk_path_keys_are_never_normalized(self):
        # source_file (import_asset) and filepath (take_screenshot) are real disk
        # paths and must survive verbatim even if they happen to start with /Content.
        params = {
            'source_file': r'C:\Content\models\hero.fbx',
            'filepath': r'C:\Content\shots\frame.png',
        }
        out = self.u._normalize_params_for_unreal(params)
        self.assertEqual(out['source_file'], r'C:\Content\models\hero.fbx')
        self.assertEqual(out['filepath'], r'C:\Content\shots\frame.png')

    def test_disk_keys_excluded_from_content_key_list(self):
        for key in self.u._DISK_PATH_PARAM_KEYS:
            self.assertNotIn(key, self.u._CONTENT_PATH_PARAM_KEYS)


# ---------------------------------------------------------------------------
# _remap_console_command — console line collides with top-level command:
# ---------------------------------------------------------------------------


class RemapConsoleCommandTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_console_command_remapped_to_command(self):
        params = {'console_command': 'stat fps'}
        out = self.u._remap_console_command('execute_console_command', dict(params))
        self.assertEqual(out['command'], 'stat fps')
        self.assertNotIn('console_command', out)

    def test_placeholder_dropped_when_unset(self):
        out = self.u._remap_console_command('execute_console_command', {'console_command': ''})
        self.assertNotIn('console_command', out)
        self.assertNotIn('command', out)

    def test_existing_command_not_overwritten(self):
        out = self.u._remap_console_command(
            'execute_console_command', {'console_command': 'stat fps', 'command': 'r.x 1'})
        self.assertEqual(out['command'], 'r.x 1')

    def test_other_commands_drop_placeholder_only(self):
        out = self.u._remap_console_command('spawn_actor', {'console_command': '', 'name': 'X'})
        self.assertNotIn('console_command', out)
        self.assertEqual(out['name'], 'X')
        self.assertNotIn('command', out)


# ---------------------------------------------------------------------------
# _prune_unset_params — empty placeholders dropped, meaningful 0/False kept
# ---------------------------------------------------------------------------


class PruneUnsetParamsTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_empty_sentinels_pruned(self):
        params = {'a': '', 'b': [], 'c': {}, 'd': None}
        self.assertEqual(self.u._prune_unset_params(params), {})

    def test_meaningful_falsey_values_kept(self):
        params = {'slot': 0, 'flag': False, 'name': 'Cube', 'loc': [0, 0, 100]}
        out = self.u._prune_unset_params(params)
        self.assertEqual(out, params)

    def test_mixed(self):
        params = {'name': 'Cube', 'type': '', 'location': [], 'slot': 0, 'recursive': True}
        out = self.u._prune_unset_params(params)
        self.assertEqual(out, {'name': 'Cube', 'slot': 0, 'recursive': True})


# ---------------------------------------------------------------------------
# _prepare_params_for_unreal — full pre-send pipeline, no input mutation
# ---------------------------------------------------------------------------


class PrepareParamsPipelineTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_pipeline_console_then_prune_then_normalize(self):
        original = {
            'console_command': 'stat unit',
            'name': '',           # pruned
            'path': '/Content/UI',  # normalized
            'recursive': True,    # kept
        }
        out = self.u._prepare_params_for_unreal('execute_console_command', dict(original))
        self.assertEqual(out['command'], 'stat unit')
        self.assertNotIn('console_command', out)
        self.assertNotIn('name', out)
        self.assertEqual(out['path'], '/Game/UI')
        self.assertEqual(out['recursive'], True)

    def test_input_not_mutated(self):
        original = {'name': '', 'path': '/Content/UI'}
        snapshot = dict(original)
        self.u._prepare_params_for_unreal('spawn_actor', original)
        self.assertEqual(original, snapshot)

    def test_non_dict_passthrough(self):
        self.assertEqual(self.u._prepare_params_for_unreal('spawn_actor', None), None)

    def test_material_value_list_survives(self):
        out = self.u._prepare_params_for_unreal(
            'set_material_parameter',
            {'material': '/Content/Materials/MI', 'parameter': 'BaseColor', 'value': [1, 0, 0]},
        )
        self.assertEqual(out['material'], '/Game/Materials/MI')
        self.assertEqual(out['value'], [1, 0, 0])


# ---------------------------------------------------------------------------
# _diagnose_no_response — actionable recv-timeout message
# ---------------------------------------------------------------------------


class DiagnoseNoResponseTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_generic_timeout_names_command_and_timeout(self):
        msg = self.u._diagnose_no_response(
            'spawn_actor', 'Timeout receiving Unreal response', 10)
        self.assertIn('spawn_actor', msg)
        self.assertIn('10s', msg)
        self.assertIn('read_timeout', msg)  # tells the operator the knob to turn
        self.assertNotIn('\n', msg)         # stays a single INI-header line

    def test_generic_timeout_has_no_save_remedy(self):
        msg = self.u._diagnose_no_response(
            'spawn_actor', 'Timeout receiving Unreal response', 10)
        self.assertNotIn('Save dialog', msg)

    def test_save_command_appends_modal_dialog_remedy(self):
        msg = self.u._diagnose_no_response(
            'save_current_level', 'Timeout receiving Unreal response', 10)
        self.assertIn('modal Save dialog', msg)
        self.assertIn('new_level', msg)   # names the silent-save escape hatch
        self.assertNotIn('\n', msg)

    def test_modal_prone_membership(self):
        self.assertIn('save_current_level', self.u._MODAL_PRONE_COMMANDS)
        self.assertIn('save_all', self.u._MODAL_PRONE_COMMANDS)
        self.assertIn('open_level', self.u._MODAL_PRONE_COMMANDS)
        self.assertNotIn('spawn_actor', self.u._MODAL_PRONE_COMMANDS)

    def test_compile_slow_command_appends_compile_remedy(self):
        # The root cause this fix targets: create_material timed out at the flat
        # 10 s while UE compiled the new material's shaders, cascading into
        # "parent material not found" downstream. Its diagnostic must name the
        # synchronous shader compile (NOT the modal Save dialog) as the cause.
        msg = self.u._diagnose_no_response(
            'create_material', 'Timeout receiving Unreal response', 60)
        self.assertIn('60s', msg)
        self.assertIn('shader', msg.lower())
        self.assertNotIn('modal Save dialog', msg)  # this is not the save case
        self.assertNotIn('\n', msg)

    def test_spawn_actor_gets_neither_remedy(self):
        msg = self.u._diagnose_no_response(
            'spawn_actor', 'Timeout receiving Unreal response', 10)
        self.assertNotIn('shader', msg.lower())
        self.assertNotIn('modal Save dialog', msg)

    def test_open_level_is_both_compile_slow_and_modal_prone(self):
        # open_level can be legitimately slow (map deserialize) AND modal-prone
        # (prompt to save the dirty current level), so its diagnostic carries the
        # modal remedy. It is floored (slow) but not in the compile-shader set.
        self.assertIn('open_level', self.u._MODAL_PRONE_COMMANDS)
        self.assertIn('open_level', self.u._SLOW_COMMAND_TIMEOUT_FLOORS)
        self.assertNotIn('open_level', self.u._COMPILE_SLOW_COMMANDS)
        msg = self.u._diagnose_no_response(
            'open_level', 'Timeout receiving Unreal response', 60)
        self.assertIn('modal Save dialog', msg)


# ---------------------------------------------------------------------------
# _effective_read_timeout — per-command recv-timeout floors
# ---------------------------------------------------------------------------


class EffectiveReadTimeoutTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def test_create_material_floor_raises_default(self):
        # The exact regression: the default 10 s is raised to the 60 s floor so
        # the first (shader-compiling) material in a session is not aborted.
        self.assertEqual(self.u._effective_read_timeout('create_material', 10), 60.0)

    def test_material_family_floors(self):
        self.assertEqual(self.u._effective_read_timeout('create_material_instance', 10), 45.0)
        self.assertEqual(self.u._effective_read_timeout('set_material_parameter', 10), 45.0)
        self.assertEqual(self.u._effective_read_timeout('import_asset', 10), 90.0)

    def test_unknown_command_keeps_configured_timeout(self):
        # A read/query command (no floor) must keep the operator's value verbatim.
        self.assertEqual(self.u._effective_read_timeout('get_actors_in_level', 10), 10.0)
        self.assertEqual(self.u._effective_read_timeout('spawn_actor', 12), 12.0)

    def test_configured_value_above_floor_is_honored(self):
        # An operator who set read_timeout: 120 must NOT have it lowered to 60.
        self.assertEqual(self.u._effective_read_timeout('create_material', 120), 120.0)

    def test_non_numeric_configured_falls_back(self):
        self.assertEqual(self.u._effective_read_timeout('create_material', None), 60.0)
        self.assertEqual(self.u._effective_read_timeout('spawn_actor', 'oops'), 10.0)

    def test_every_floor_command_is_categorized(self):
        # Every floored command must be modal-prone and/or compile-slow so the
        # timeout diagnostic always has a tailored remedy (no silent floor).
        for command in self.u._SLOW_COMMAND_TIMEOUT_FLOORS:
            self.assertTrue(
                command in self.u._MODAL_PRONE_COMMANDS
                or command in self.u._COMPILE_SLOW_COMMANDS,
                f'{command} is floored but has no diagnostic category',
            )


# ---------------------------------------------------------------------------
# send_command — read-timeout is diagnosed (no retry); connect-race retried
# ---------------------------------------------------------------------------


class SendCommandRetryTests(SimpleTestCase):
    def setUp(self):
        self.u = _load_unrealer_module()

    def _conn(self, read_timeout=10):
        return self.u.UnrealConnection(read_timeout=read_timeout)

    def _stub(self, conn, responder):
        """Replace the socket round-trip with a pure responder; record attempts."""
        calls = []

        def fake_once(command, params, attempt):
            calls.append(attempt)
            return responder(attempt)

        conn._send_command_once = fake_once
        return calls

    def test_read_timeout_is_not_retried_and_is_diagnosed(self):
        conn = self._conn(read_timeout=7)
        calls = self._stub(
            conn, lambda a: {'status': 'error', 'error': 'Timeout receiving Unreal response'})
        out = conn.send_command('save_current_level', {})
        self.assertEqual(calls, [1], 'a read-timeout must NOT trigger the connect-race retry')
        self.assertEqual(out['status'], 'error')
        self.assertIn('7s', out['error'])
        self.assertIn('modal Save dialog', out['error'])

    def test_connection_closed_is_retried_once(self):
        conn = self._conn()
        calls = self._stub(
            conn, lambda a: {'status': 'error', 'error': 'Connection closed before receiving data'})
        out = conn.send_command('spawn_actor', {})
        self.assertEqual(calls, [1, 2], 'the fast connect-race signature must still be retried')
        self.assertEqual(out['status'], 'error')

    def test_retry_recovers_on_second_attempt(self):
        conn = self._conn()
        calls = self._stub(
            conn,
            lambda a: {'status': 'error', 'error': 'Connection reset by peer'} if a == 1
            else {'status': 'success', 'result': {'ok': True}})
        out = conn.send_command('spawn_actor', {})
        self.assertEqual(calls, [1, 2])
        self.assertEqual(out['status'], 'success')

    def test_success_returns_on_first_attempt(self):
        conn = self._conn()
        calls = self._stub(conn, lambda a: {'status': 'success', 'result': {}})
        out = conn.send_command('get_current_level', {})
        self.assertEqual(calls, [1])
        self.assertEqual(out['status'], 'success')


# ---------------------------------------------------------------------------
# config.yaml — the placeholder catalog the Flow Compiler resolves against
# ---------------------------------------------------------------------------


class ConfigPlaceholderTests(SimpleTestCase):
    def setUp(self):
        self.cfg = _load_unrealer_config()
        self.params = self.cfg['params']

    def test_round_trips(self):
        self.assertEqual(self.cfg['command'], 'get_actors_in_level')
        self.assertEqual(self.cfg['port'], 55557)
        self.assertIsInstance(self.params, dict)

    def test_new_command_params_present(self):
        expected = [
            # editor extras
            'filepath', 'distance', 'orientation',
            # blueprint extras
            'auto_possess_player', 'can_be_damaged',
            'use_controller_rotation_yaw',
            # node extras
            'node_type', 'event_type',
            # system
            'code', 'console_command', 'class_name', 'recursive',
            # asset
            'source_file', 'destination_path', 'source', 'destination',
            # material
            'parent_material', 'material', 'parameter', 'value', 'actor', 'slot',
        ]
        for key in expected:
            self.assertIn(key, self.params, f'missing placeholder param: {key}')

    def test_always_sent_defaults_are_sensible(self):
        # recursive must default True (matches the upstream list_assets default) and
        # slot must default 0 (assign_material) — both survive pruning by design.
        self.assertIs(self.params['recursive'], True)
        self.assertEqual(self.params['slot'], 0)

    def test_pawn_and_focus_placeholders_are_prunable(self):
        # These must be '' / [] so a call that names only ONE of them does not force
        # the others to false/0 on the wire.
        self.assertEqual(self.params['distance'], '')
        self.assertEqual(self.params['can_be_damaged'], '')
        self.assertEqual(self.params['use_controller_rotation_yaw'], '')


# ---------------------------------------------------------------------------
# Registry / contract / exec-report integration (imports the Django app)
# ---------------------------------------------------------------------------


class RegistryIntegrationTests(SimpleTestCase):
    def test_chat_agent_spec_describes_new_surface(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_unrealer']
        purpose = spec.purpose
        self.assertIn('53 commands', purpose)
        for verb in ('execute_python', 'open_level', 'import_asset', 'create_material',
                     'take_screenshot', 'set_pawn_properties', 'find_blueprint_nodes'):
            self.assertIn(verb, purpose)
        # the headless-tools caveat must be present so the LLM doesn't try build/cook
        self.assertIn('UnrealEditor-Cmd', purpose)

    def test_security_hints_cover_new_categories(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_unrealer']
        hints = ' | '.join(spec.security_hints)
        for token in ('material', 'import asset', 'open level', 'execute python', 'console command'):
            self.assertIn(token, hints)

    def test_exec_report_row_present(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS['chat_agent_unrealer'], ('unrealer', 'Unrealer'))

    def test_parametrizer_source_fields_unchanged(self):
        from agent.services.agent_contracts import get_parametrizer_source_fields
        fields = get_parametrizer_source_fields()['unrealer']
        self.assertEqual(
            tuple(fields),
            ('host', 'port', 'command', 'status', 'error', 'response_body'),
        )


if __name__ == '__main__':
    unittest.main()
