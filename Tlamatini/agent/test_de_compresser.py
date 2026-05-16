"""Automated tests for the De-Compresser workflow agent.

Covers:
- Extension detection (compound .tar.gz / .gz.tar precedence over .gz)
- Password resolution via DE_COMPRESSER_PWD with passwordless on/off
- Output validation (existing dir / missing dir auto-created / no-write)
- Decompression for .gz / .zip / .7z(py7zr fallback) / .tar.gz
- Compression for .gz / .zip / .7z(py7zr fallback) / .tar.gz
- main() end-stage contract: target_agents are always started (success OR failure)
- main() emits exactly one INI_SECTION_DE_COMPRESSER block per run, even on failure
- Registry integration: ChatWrappedAgentSpec, Exec Report row, Agent contract
  discovery, JS/CSS wiring, URL route, and migration presence.

The agent ships as a standalone script under ``agent/agents/de_compresser/`` (it
runs as a separate Python subprocess in the pool — see the create_new_agent.md
skill). Loading it through ``importlib.util.spec_from_file_location`` mirrors
the pattern used by the existing Ender and Parametrizer test modules so the
agent's module-level ``os.chdir`` + ``open(LOG_FILE_PATH, 'w').close()`` side
effects land inside its own directory and don't pollute the test runner cwd.
"""

import gzip
import importlib.util
import io
import logging
import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from functools import lru_cache
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

try:
    import py7zr  # type: ignore
except ImportError:  # pragma: no cover — optional dependency
    py7zr = None


@lru_cache(maxsize=1)
def _load_de_compresser_module():
    module_path = os.path.join(
        os.path.dirname(__file__),
        'agents',
        'de_compresser',
        'de_compresser.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_de_compresser_module_for_tests',
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load De-Compresser module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
    return module


# ---------------------------------------------------------------------------
# Pure-function helpers (no I/O on the agent script's working dir)
# ---------------------------------------------------------------------------


class ExtensionDetectionTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()

    def test_tar_gz_precedence_over_plain_gz(self):
        """A `.tar.gz` file MUST resolve to `.tar.gz`, never `.gz`.

        The dispatcher branches on the returned extension, so misclassifying
        a tarball as plain gzip would extract the inner `.tar` file rather
        than its contents.
        """
        self.assertEqual(self.dec.detect_extension('archive.tar.gz'), '.tar.gz')
        self.assertEqual(self.dec.detect_extension('archive.gz.tar'), '.gz.tar')

    def test_single_format_extensions(self):
        self.assertEqual(self.dec.detect_extension('payload.gz'), '.gz')
        self.assertEqual(self.dec.detect_extension('payload.zip'), '.zip')
        self.assertEqual(self.dec.detect_extension('payload.7z'), '.7z')

    def test_unsupported_extension_returns_empty_string(self):
        self.assertEqual(self.dec.detect_extension('payload.rar'), '')
        self.assertEqual(self.dec.detect_extension('payload'), '')
        self.assertEqual(self.dec.detect_extension(''), '')

    def test_extension_detection_is_case_insensitive(self):
        self.assertEqual(self.dec.detect_extension('FILE.ZIP'), '.zip')
        self.assertEqual(self.dec.detect_extension('FILE.TAR.GZ'), '.tar.gz')


class PasswordResolutionTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()

    def test_passwordless_true_returns_none_password_and_no_error(self):
        password, err = self.dec.resolve_password(True)
        self.assertIsNone(password)
        self.assertIsNone(err)

    def test_passwordless_false_with_env_var_present(self):
        with patch.dict(os.environ, {'DE_COMPRESSER_PWD': 's3cret'}, clear=False):
            password, err = self.dec.resolve_password(False)
        self.assertEqual(password, 's3cret')
        self.assertIsNone(err)

    def test_passwordless_false_with_env_var_missing(self):
        env = os.environ.copy()
        env.pop('DE_COMPRESSER_PWD', None)
        with patch.dict(os.environ, env, clear=True):
            password, err = self.dec.resolve_password(False)
        self.assertIsNone(password)
        self.assertIsNotNone(err)
        self.assertIn('DE_COMPRESSER_PWD', err)


# ---------------------------------------------------------------------------
# Output-directory validation
# ---------------------------------------------------------------------------


class OutputValidationTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()

    def test_empty_path_fails(self):
        self.assertIsNotNone(self.dec.ensure_writable_directory(''))

    def test_existing_writable_directory_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.dec.ensure_writable_directory(tmp))

    def test_missing_directory_is_auto_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'fresh', 'nested')
            self.assertIsNone(self.dec.ensure_writable_directory(target))
            self.assertTrue(os.path.isdir(target))

    def test_path_that_exists_as_file_is_rejected(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            err = self.dec.ensure_writable_directory(tmp_path)
            self.assertIsNotNone(err)
            self.assertIn('not a directory', err)
        finally:
            os.remove(tmp_path)


class InputValidationTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()

    def test_empty_input_is_rejected(self):
        self.assertIsNotNone(self.dec.ensure_input_exists(''))

    def test_missing_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNotNone(
                self.dec.ensure_input_exists(os.path.join(tmp, 'nope.zip'))
            )

    def test_existing_file_passes(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self.assertIsNone(self.dec.ensure_input_exists(tmp_path))
        finally:
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# Round-trip compression / decompression — actual byte-level correctness
# ---------------------------------------------------------------------------


class GzRoundTripTests(SimpleTestCase):
    """Pure stdlib path (no 7z CLI required, no password).

    Tests use ``passwordless=true`` semantics so the agent uses the stdlib
    ``gzip`` module on both ends, which is deterministic regardless of host.
    """

    def setUp(self):
        self.dec = _load_de_compresser_module()
        self.tmp = tempfile.mkdtemp()
        self.payload = b'Hello De-Compresser! ' * 200

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gz_round_trip(self):
        src = os.path.join(self.tmp, 'payload.bin')
        with open(src, 'wb') as f:
            f.write(self.payload)
        archive = os.path.join(self.tmp, 'payload.bin.gz')
        extracted_dir = os.path.join(self.tmp, 'out')
        os.makedirs(extracted_dir)

        # Compress
        self.dec.compress_gz(src, archive, password=None)
        self.assertTrue(os.path.exists(archive))

        # Sanity-check: the resulting file is a real gzip stream
        with gzip.open(archive, 'rb') as gz:
            self.assertEqual(gz.read(), self.payload)

        # Decompress through the agent's own helper (drops .gz suffix)
        out_path = self.dec.decompress_gz(archive, extracted_dir, password=None)
        with open(out_path, 'rb') as f:
            self.assertEqual(f.read(), self.payload)

    def test_compress_gz_rejects_directory(self):
        with self.assertRaises(RuntimeError):
            self.dec.compress_gz(self.tmp, os.path.join(self.tmp, 'x.gz'), password=None)


class ZipRoundTripTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_zip_single_file_round_trip(self):
        src = os.path.join(self.tmp, 'doc.txt')
        with open(src, 'w', encoding='utf-8') as f:
            f.write('hola tlamatini')
        archive = os.path.join(self.tmp, 'doc.zip')
        out_dir = os.path.join(self.tmp, 'out')
        os.makedirs(out_dir)

        self.dec.compress_zip(src, archive, password=None)
        extracted = self.dec.decompress_zip(archive, out_dir, password=None)
        self.assertTrue(extracted)
        # The extracted file should be at out_dir/doc.txt
        round_tripped = os.path.join(out_dir, 'doc.txt')
        self.assertTrue(os.path.exists(round_tripped))
        with open(round_tripped, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'hola tlamatini')

    def test_zip_directory_round_trip(self):
        src_dir = os.path.join(self.tmp, 'tree')
        os.makedirs(os.path.join(src_dir, 'sub'))
        with open(os.path.join(src_dir, 'a.txt'), 'w', encoding='utf-8') as f:
            f.write('AAA')
        with open(os.path.join(src_dir, 'sub', 'b.txt'), 'w', encoding='utf-8') as f:
            f.write('BBB')

        archive = os.path.join(self.tmp, 'tree.zip')
        out_dir = os.path.join(self.tmp, 'out')
        os.makedirs(out_dir)

        self.dec.compress_zip(src_dir, archive, password=None)

        # Verify the archive structure independently
        with zipfile.ZipFile(archive, 'r') as zf:
            names = sorted(zf.namelist())
        self.assertIn('tree/a.txt', [n.replace('\\', '/') for n in names])
        self.assertIn('tree/sub/b.txt', [n.replace('\\', '/') for n in names])

        self.dec.decompress_zip(archive, out_dir, password=None)
        self.assertTrue(os.path.exists(os.path.join(out_dir, 'tree', 'a.txt')))
        self.assertTrue(os.path.exists(os.path.join(out_dir, 'tree', 'sub', 'b.txt')))


class TarGzRoundTripTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tar_gz_directory_round_trip(self):
        src_dir = os.path.join(self.tmp, 'bundle')
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, 'x.txt'), 'w', encoding='utf-8') as f:
            f.write('payload')

        archive = os.path.join(self.tmp, 'bundle.tar.gz')
        out_dir = os.path.join(self.tmp, 'out')
        os.makedirs(out_dir)

        self.dec.compress_tar_gz(src_dir, archive, password=None)

        # Verify archive is a real gzipped tar
        with tarfile.open(archive, 'r:gz') as tar:
            names = tar.getnames()
        self.assertTrue(any(n.endswith('bundle/x.txt') or n == 'bundle/x.txt' for n in names))

        # Decompress through the agent
        extracted = self.dec.decompress_tar_gz(archive, out_dir, password=None)
        self.assertTrue(extracted)
        self.assertTrue(os.path.exists(os.path.join(out_dir, 'bundle', 'x.txt')))


@unittest.skipIf(py7zr is None, "py7zr is not installed; skipping .7z round-trip test")
class SevenZipRoundTripTests(SimpleTestCase):
    """Exercises the py7zr fallback path (when the 7z CLI is unavailable).

    We patch ``_seven_zip_available`` to False so the test is deterministic
    regardless of whether the host has the CLI on PATH. The py7zr branch is
    the documented frozen-build fallback and is the only one we can hit on
    a clean CI image.
    """

    def setUp(self):
        self.dec = _load_de_compresser_module()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seven_zip_round_trip_via_py7zr(self):
        src = os.path.join(self.tmp, 'doc.txt')
        with open(src, 'w', encoding='utf-8') as f:
            f.write('seven zip body')
        archive = os.path.join(self.tmp, 'doc.7z')
        out_dir = os.path.join(self.tmp, 'out')
        os.makedirs(out_dir)

        with patch.object(self.dec, '_seven_zip_available', return_value=False):
            self.dec.compress_seven_zip(src, archive, password=None)
            self.dec.decompress_seven_zip(archive, out_dir, password=None)

        round_tripped = os.path.join(out_dir, 'doc.txt')
        self.assertTrue(os.path.exists(round_tripped))
        with open(round_tripped, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'seven zip body')


# ---------------------------------------------------------------------------
# Dispatcher returns the correct success/message envelope
# ---------------------------------------------------------------------------


class DispatcherTests(SimpleTestCase):
    def setUp(self):
        self.dec = _load_de_compresser_module()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_decompression_with_unsupported_extension_returns_false(self):
        src = os.path.join(self.tmp, 'file.gz')
        with gzip.open(src, 'wb') as f:
            f.write(b'x')
        ok, msg = self.dec.run_decompression(src, self.tmp, '.rar', None)
        self.assertFalse(ok)
        self.assertIn('Unsupported', msg)

    def test_run_compression_with_unsupported_extension_returns_false(self):
        src = os.path.join(self.tmp, 'src.txt')
        with open(src, 'w', encoding='utf-8') as f:
            f.write('x')
        ok, msg = self.dec.run_compression(src, os.path.join(self.tmp, 'out.rar'), '.rar', None)
        self.assertFalse(ok)
        self.assertIn('Unsupported', msg)

    def test_run_decompression_failure_is_caught_and_reported(self):
        # A truly-not-a-zip file passed to the .zip branch must NOT raise;
        # the dispatcher catches the exception and returns (False, msg) so
        # main() can still trigger target_agents in its end-stage.
        bogus = os.path.join(self.tmp, 'bogus.zip')
        with open(bogus, 'wb') as f:
            f.write(b'NOT-A-ZIP')
        ok, msg = self.dec.run_decompression(bogus, self.tmp, '.zip', None)
        self.assertFalse(ok)
        self.assertIn('Decompression failure', msg)


# ---------------------------------------------------------------------------
# End-stage contract: main() always starts target_agents — success OR failure
# ---------------------------------------------------------------------------


class MainEndStageTests(SimpleTestCase):
    """The agent's end-stage MUST trigger every target_agents entry even when
    the operation failed. This is the load-bearing contract that lets a Raiser
    on a downstream Parametrizer branch on the ``success=true|false`` field of
    the emitted INI_SECTION_DE_COMPRESSER block.
    """

    def setUp(self):
        self.dec = _load_de_compresser_module()
        self.tmp = tempfile.mkdtemp()
        self.cwd_before = os.getcwd()
        # main() reads config.yaml from the cwd and writes PID + log there.
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_config(self, cfg_dict):
        import yaml
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)

    def _capture_main(self, cfg_dict):
        """Run ``main()`` and return (sys_exit_code, list_of_started_agents,
        list_of_log_records). All real subprocess starts and waits are stubbed
        so the test does not spawn processes.
        """
        self._write_config(cfg_dict)

        started = []
        records = []

        class _ListHandler(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _ListHandler()
        logging.getLogger().addHandler(handler)

        with patch.object(self.dec, 'start_agent', side_effect=lambda name: (started.append(name) or True)), \
             patch.object(self.dec, 'wait_for_agents_to_stop'), \
             patch.object(self.dec, 'time') as time_mock:
            # Prevent the 0.4 s LED sleep at the bottom of main().
            time_mock.sleep = lambda _s: None
            try:
                self.dec.main()
            except SystemExit:
                pass

        logging.getLogger().removeHandler(handler)
        return started, records

    def test_target_agents_are_started_on_successful_decompression(self):
        # Build a real .zip to decompress.
        src = os.path.join(self.tmp, 'bundle.zip')
        with zipfile.ZipFile(src, 'w') as zf:
            zf.writestr('a.txt', 'hello')
        out_dir = os.path.join(self.tmp, 'out')
        os.makedirs(out_dir)

        started, records = self._capture_main({
            'input': src,
            'output': out_dir,
            'passwordless': True,
            'target_agents': ['downstream_1', 'downstream_2'],
        })

        self.assertEqual(started, ['downstream_1', 'downstream_2'])
        self.assertTrue(any('INI_SECTION_DE_COMPRESSER' in r for r in records))
        self.assertTrue(any('success: true' in r for r in records))

    def test_target_agents_are_started_even_on_failure(self):
        # Operation classification failure (unknown extension on both sides).
        started, records = self._capture_main({
            'input': __file__,  # exists but extension isn't an archive
            'output': self.tmp,  # extension isn't an archive either
            'passwordless': True,
            'target_agents': ['downstream_failure_path'],
        })

        self.assertEqual(started, ['downstream_failure_path'])
        # The block is always emitted, with success=false on failure paths.
        ini_blocks = [r for r in records if 'INI_SECTION_DE_COMPRESSER' in r]
        self.assertEqual(len(ini_blocks), 1)
        self.assertIn('success: false', ini_blocks[0])

    def test_missing_password_env_var_still_runs_end_stage(self):
        src = os.path.join(self.tmp, 'bundle.zip')
        with zipfile.ZipFile(src, 'w') as zf:
            zf.writestr('a.txt', 'hello')

        env = os.environ.copy()
        env.pop('DE_COMPRESSER_PWD', None)
        with patch.dict(os.environ, env, clear=True):
            started, records = self._capture_main({
                'input': src,
                'output': os.path.join(self.tmp, 'out'),
                'passwordless': False,
                'target_agents': ['always_runs'],
            })

        # The missing env var aborts the password stage with an error log
        # AND still falls through to the end-stage so the downstream chain
        # is never stranded.
        self.assertEqual(started, ['always_runs'])
        self.assertTrue(any('DE_COMPRESSER_PWD' in r for r in records))

    def test_emits_exactly_one_ini_section_per_run(self):
        # Atomic-emission contract: even on success path, only ONE block
        # appears. A future regression that splits the emission across
        # multiple ``logging.info`` calls would corrupt Parametrizer parsing
        # because concurrent log writes can interleave between them.
        src = os.path.join(self.tmp, 'bundle.zip')
        with zipfile.ZipFile(src, 'w') as zf:
            zf.writestr('a.txt', 'hello')
        out_dir = os.path.join(self.tmp, 'out')
        os.makedirs(out_dir)

        _, records = self._capture_main({
            'input': src,
            'output': out_dir,
            'passwordless': True,
            'target_agents': [],
        })
        ini_blocks = [r for r in records if 'INI_SECTION_DE_COMPRESSER' in r]
        self.assertEqual(len(ini_blocks), 1)
        # The block opens AND closes inside that single log message.
        self.assertIn('>>>END_SECTION_DE_COMPRESSER', ini_blocks[0])


# ---------------------------------------------------------------------------
# Registry integration — ensures every wiring step in the skill survives
# refactors. These are SimpleTestCase / no DB so they run fast.
# ---------------------------------------------------------------------------


class RegistryIntegrationTests(SimpleTestCase):
    def test_chat_wrapped_agent_spec_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME

        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_de_compresser')
        self.assertIsNotNone(spec, "chat_agent_de_compresser must be registered")
        self.assertEqual(spec.key, 'de_compresser')
        self.assertEqual(spec.template_dir, 'de_compresser')
        self.assertEqual(spec.tool_description, 'Chat-Agent-De-Compresser')
        self.assertEqual(spec.display_name, 'De-Compresser')

    def test_exec_report_tool_row_is_registered(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS

        entry = _EXEC_REPORT_TOOLS.get('chat_agent_de_compresser')
        self.assertEqual(entry, ('decompresser', 'De-Compresser'))

    def test_agent_contract_disk_discovery_picks_up_de_compresser(self):
        # The disk-discovery pass in agent_contracts.py walks
        # ``agent/agents/`` so a freshly-added template directory must show
        # up automatically — no _BUILTIN_CONTRACTS entry is required for a
        # plain action agent with the standard target_agents wiring.
        from agent.services.agent_contracts import get_agent_contract

        contract = get_agent_contract('de_compresser')
        self.assertEqual(contract.agent_type, 'de_compresser')
        # Output should land on target_agents (not output_agents).
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')
        # De-Compresser DOES start its targets at end-stage.
        self.assertFalse(contract.never_starts_targets)

    def test_url_route_exists(self):
        from django.urls import reverse

        url = reverse(
            'update_de_compresser_connection',
            kwargs={'agent_name': 'de-compresser-1'},
        )
        self.assertIn('update_de_compresser_connection', url)

    def test_canvas_classmap_contains_de_compresser(self):
        # The JS classMap MUST resolve "de-compresser" -> "decompresser-agent"
        # so the canvas item picks up the gradient class. Read the JS source
        # directly so the test pins the contract independent of any browser.
        js_path = os.path.join(
            os.path.dirname(__file__),
            'static', 'agent', 'js', 'acp-canvas-core.js',
        )
        with open(js_path, 'r', encoding='utf-8') as f:
            js_source = f.read()
        self.assertIn("'de-compresser': 'decompresser-agent'", js_source)

    def test_css_gradient_is_unique(self):
        # The 4-color "Vault Unsealed" gradient must appear exactly once in
        # the canvas CSS, and the four hex stops must NOT collide with the
        # other 4-color gradients in the file (gatewayer / gateway-relayer /
        # node-manager / whatstlamatini / acpx / acpxer / keyboarder / mouser /
        # teletlamatini).
        css_path = os.path.join(
            os.path.dirname(__file__),
            'static', 'agent', 'css', 'agentic_control_panel.css',
        )
        with open(css_path, 'r', encoding='utf-8') as f:
            css_source = f.read()
        gradient = '#1F2A56 0%, #B07A2B 33%, #D7263D 66%, #7CF6B5 100%'
        self.assertEqual(
            css_source.count(gradient), 1,
            "The De-Compresser canvas gradient must be unique to its rule",
        )


class MigrationPresenceTests(TestCase):
    """The 0083 Agent-row and 0084 Tool-row migrations are how the agent
    appears in the sidebar and the Tools dialog respectively. If they
    silently get reverted, the sidebar loses the icon and the Tools dialog
    stops being able to toggle the wrapper. These two tests pin the
    contract at the DB level (which is why they extend TestCase, not
    SimpleTestCase — they need the in-memory test database).
    """

    def test_agent_row_seeded_by_migration_0083(self):
        from agent.models import Agent
        self.assertTrue(
            Agent.objects.filter(agentDescription='De-Compresser').exists(),
            "Migration 0083 must seed an Agent row with agentDescription='De-Compresser'",
        )

    def test_tool_row_seeded_by_migration_0084(self):
        from agent.models import Tool
        self.assertTrue(
            Tool.objects.filter(toolDescription='Chat-Agent-De-Compresser').exists(),
            "Migration 0084 must seed a Tool row with toolDescription='Chat-Agent-De-Compresser'",
        )


# Silence the noisy "agent module emits log records during import" lines so
# the test runner output stays readable when this module is part of a wider
# suite. Without this, every load_de_compresser_module() call leaks the
# "📦 DE-COMPRESSER AGENT STARTED" line into stderr.
logging.getLogger().handlers = [
    h for h in logging.getLogger().handlers
    if not isinstance(h, logging.StreamHandler) or h.stream is not io.StringIO()
]
