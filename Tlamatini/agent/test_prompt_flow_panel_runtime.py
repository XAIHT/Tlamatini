# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Run in a verified visible foreground console with -NoExit:
python Tlamatini/manage.py test agent.test_prompt_flow_panel_runtime --noinput
Adapter boundary tests use fake model providers; no live provider or database.
"""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.prompt_flow_panel_runtime import PromptFlowPanelRuntime  # noqa: E402
from agent.services.prompt_flow_panel import FlowError, FlowStopped  # noqa: E402
from agent.cancellation import begin_llm_run, is_run_cancelled, reset_for_tests  # noqa: E402
from agent import path_guard as real_path_guard  # noqa: E402


class Chain:
    def __init__(self):
        self.client = Mock()

    def getHttpxClientInstance(self):
        return self.client


class PromptOnlyFallback(Chain):
    pass


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp_root = Path(__file__).resolve().parents[2] / 'Temp'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='prompt-flow-panel-adapter-test-', dir=temp_root)
        self.rag = types.ModuleType('agent.rag')
        self.rag.BasicPromptOnlyChain = PromptOnlyFallback
        self.rag.setup_llm = Mock(side_effect=lambda *args, **kwargs: Chain())
        self.rag.setup_llm_with_context = Mock(side_effect=lambda *args, **kwargs: Chain())
        self.rag.ask_rag = Mock(return_value='A real adapter result')
        self.guard = types.ModuleType('agent.path_guard')
        self.guard.get_app_temp_root = lambda: self.temp.name
        self.status = types.ModuleType('agent.self_healing')
        self.status.register_status_broadcaster = Mock()
        self.status.unregister_status_broadcaster = Mock()
        self.modules = patch.dict(sys.modules, {'agent.rag': self.rag, 'agent.path_guard': self.guard,
                                               'agent.self_healing': self.status})
        self.modules.start()
        self.runtime = PromptFlowPanelRuntime(types.SimpleNamespace(pk=17), AsyncMock())
        self.runtime._catalog = AsyncMock(return_value=([], [], [], ''))

    async def asyncTearDown(self):
        await self.runtime.close()
        reset_for_tests(self.runtime.key)
        reset_for_tests('unrelated-chat')
        self.modules.stop()
        self.temp.cleanup()

    async def test_prompt_passes_history_modes_and_isolated_identity(self):
        await self.runtime.comment('Previous commentary')
        result = await self.runtime.prompt('Explain a graph', {'multi_turn': True, 'acpx': True})
        self.assertEqual(result, 'A real adapter result')
        self.assertFalse(self.rag.setup_llm.call_args.kwargs['include_application_context'])
        args, kwargs = self.rag.ask_rag.call_args
        self.assertEqual(args[1]['conversation_user_id'], self.runtime.key)
        self.assertTrue(args[1]['multi_turn_enabled'])
        self.assertTrue(args[1]['acpx_enabled'])
        self.assertGreater(args[1]['cancel_run_epoch'], 0)
        self.assertEqual(kwargs['chat_history'][0].content, 'Previous commentary')
        self.assertEqual([m.content for m in self.runtime.history],
                         ['Previous commentary', 'Explain a graph', 'A real adapter result'])
        self.status.unregister_status_broadcaster.assert_called_once()

    async def test_embeddings_rebuild_with_fresh_filename_and_keep_history(self):
        await self.runtime.comment('Keep me')
        await self.runtime.feed('First context')
        previous = self.runtime.chain
        first_file = self.rag.setup_llm_with_context.call_args.kwargs['filename']
        await self.runtime.feed('Second context')
        second_file = self.rag.setup_llm_with_context.call_args.kwargs['filename']
        self.assertNotEqual(first_file, second_file)
        self.assertEqual((self.runtime.directory / second_file).read_text(encoding='utf-8'),
                         'First context\n\nSecond context')
        previous.client.close.assert_called_once()
        self.assertEqual(self.runtime.history[0].content, 'Keep me')

    async def test_failed_embedding_fallback_preserves_existing_context(self):
        await self.runtime.feed('Working context')
        previous = self.runtime.chain
        fallback = PromptOnlyFallback()
        self.rag.setup_llm_with_context.side_effect = None
        self.rag.setup_llm_with_context.return_value = fallback
        with self.assertRaisesRegex(FlowError, 'Embedding setup failed'):
            await self.runtime.feed('Failed addition')
        self.assertIs(self.runtime.chain, previous)
        self.assertEqual(self.runtime.context, ['Working context'])
        fallback.client.close.assert_called_once()
        previous.client.close.assert_not_called()

    async def test_flush_and_clean_are_independent(self):
        await self.runtime.comment('Keep my history')
        await self.runtime.feed('Context')
        await self.runtime.flush()
        self.assertFalse(self.rag.setup_llm.call_args.kwargs['include_application_context'])
        self.assertEqual(self.runtime.context, [])
        self.assertEqual(len(self.runtime.history), 1)
        await self.runtime.feed('Retain these embeddings')
        chain = self.runtime.chain
        await self.runtime.clean_history()
        self.assertEqual(self.runtime.history, [])
        self.assertIs(self.runtime.chain, chain)
        self.assertEqual(self.runtime.context, ['Retain these embeddings'])

    async def test_stop_latches_only_its_run_and_prevents_next_prompt(self):
        other_epoch = begin_llm_run('unrelated-chat')
        self.runtime.active_epoch = begin_llm_run(self.runtime.key)
        own_epoch = self.runtime.active_epoch
        self.runtime.cancel()
        self.assertTrue(is_run_cancelled(self.runtime.key, own_epoch))
        self.assertFalse(is_run_cancelled('unrelated-chat', other_epoch))
        with self.assertRaises(FlowStopped):
            await self.runtime.prompt('Explain the next step', {'multi_turn': False, 'acpx': False})
        self.rag.ask_rag.assert_not_called()

    async def test_provider_failure_does_not_append_fictitious_answer(self):
        self.rag.ask_rag.side_effect = RuntimeError('Provider unavailable')
        with self.assertRaisesRegex(RuntimeError, 'Provider unavailable'):
            await self.runtime.prompt('Explain a graph', {'multi_turn': False, 'acpx': False})
        self.assertEqual(self.runtime.history, [])
        self.status.unregister_status_broadcaster.assert_called_once()
        self.assertIsNone(self.runtime.active_epoch)

    async def test_close_removes_only_its_context_directory(self):
        unrelated = Path(self.temp.name) / 'unrelated.txt'
        unrelated.write_text('Retain', encoding='utf-8')
        await self.runtime.feed('Temporary context')
        directory = self.runtime.directory
        await self.runtime.close()
        self.assertFalse(directory.exists())
        self.assertEqual(unrelated.read_text(encoding='utf-8'), 'Retain')

    async def test_context_uses_real_path_resolver_in_source_and_frozen_layouts(self):
        for frozen in (False, True):
            with self.subTest(frozen=frozen):
                app = Path(self.temp.name) / ('Installed ñ app' if frozen else 'Source ñ app')
                app.mkdir()
                internal = app / '_internal'
                runtime = PromptFlowPanelRuntime(types.SimpleNamespace(pk=17), AsyncMock())
                runtime._catalog = AsyncMock(return_value=([], [], [], ''))
                source_file = app / 'Tlamatini/agent/path_guard.py'
                try:
                    with patch.dict(sys.modules, {'agent.path_guard': real_path_guard}), \
                            patch.object(sys, 'frozen', frozen, create=True), \
                            patch.object(sys, 'executable', str(app / 'Tlamatini.exe')), \
                            patch.object(sys, '_MEIPASS', str(internal), create=True), \
                            patch.object(real_path_guard, '__file__', str(source_file)):
                        await runtime.feed('Context with Unicode: ñ ✓')
                        self.assertEqual(runtime.directory.parent, app / 'Temp')
                        name = self.rag.setup_llm_with_context.call_args.kwargs['filename']
                        self.assertEqual((runtime.directory / name).read_text(encoding='utf-8'),
                                         'Context with Unicode: ñ ✓')
                        self.assertFalse(internal.exists(), 'Never write context into frozen bundle data')
                        await runtime.flush()
                        self.assertFalse(self.rag.setup_llm.call_args.kwargs['include_application_context'])
                finally:
                    await runtime.close()
                self.assertFalse(runtime.directory.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
