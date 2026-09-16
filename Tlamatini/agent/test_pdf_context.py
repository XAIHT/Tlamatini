# Tlamatini Author Banner — Angela López Mendoza
"""PDF upload permissions, extraction, user isolation and real consumer handoff."""

import asyncio
import json
from pathlib import Path
import tempfile
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings

from . import pdf_context
from .pdf_context import PdfContextError, prepare_pdf_context, resolve_pdf_context


@override_settings(SECRET_KEY="pdf-context-tests")
class PdfContextTests(SimpleTestCase):
    def setUp(self):
        from .path_guard import get_app_temp_root
        self.temporary = tempfile.TemporaryDirectory(dir=get_app_temp_root())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        patcher = patch.object(pdf_context, 'get_runtime_agent_root', return_value=str(self.root))
        patcher.start()
        self.addCleanup(patcher.stop)
        from .pdf_image_analysis import create_pdf_image_analyzer
        self.real_analyzer = create_pdf_image_analyzer
        analyzer = patch('agent.pdf_image_analysis.create_pdf_image_analyzer',
                         return_value=lambda path: (f'Visual analysis of {path.name}: a green rectangle.', 'merged'))
        self.analyzer_mock = analyzer.start()
        self.addCleanup(analyzer.stop)

    def pdf_upload(self):
        import pymupdf
        with pymupdf.open() as document:
            for number in range(3):
                page = document.new_page()
                page.insert_text((50, 50), f"Context page {number + 1}")
                page.draw_rect(pymupdf.Rect(50, 70, 150, 170), fill=(0, 1, 0))
            return SimpleUploadedFile("report.pdf", document.tobytes(), content_type="application/pdf")

    def test_all_pages_and_artifacts_survive_preparation(self):
        progress = []
        result = prepare_pdf_context(self.pdf_upload(), 7, process_images=True, progress=progress.append)
        directory, filename = resolve_pdf_context(result['token'], 7)
        content = (directory / filename).read_text(encoding='utf-8')
        for number in range(1, 4):
            self.assertIn(f"Context page {number}", content)
            self.assertIn(str(directory / 'images' / f'page_{number:06d}.png'), content)
        self.assertIn(str(directory / 'source.pdf'), content)
        self.assertIn('Visual analysis of page_000003.png', content)
        self.assertEqual(len(list((directory / 'images').glob('page_*.png'))), 3)
        for stage in ('extract', 'analyze'):
            self.assertEqual([item['completed'] for item in progress if item['stage'] == stage], [0, 1, 2])
            self.assertTrue(all(item['total'] == 3 for item in progress if item['stage'] == stage))

    def test_signed_context_cannot_be_claimed_by_another_user_or_forged(self):
        result = prepare_pdf_context(self.pdf_upload(), 7)
        for token, user in [(result['token'], 8), (result['token'] + 'tampered', 7), ('../source.pdf', 7), (None, 7)]:
            with self.assertRaises(PdfContextError):
                resolve_pdf_context(token, user)

    def test_corrupt_upload_removes_only_its_incomplete_package(self):
        with self.assertRaises(Exception):
            prepare_pdf_context(SimpleUploadedFile('broken.pdf', b'invalid'), 7)
        self.assertEqual(list((self.root / 'context_files/pdf_canvas/7').iterdir()), [])

    def test_route_requires_login_post_and_csrf(self):
        from .urls import urlpatterns
        route = next(item.callback for item in urlpatterns if item.name == 'prepare_pdf_context')
        factory = RequestFactory()
        request = factory.post('/agent/prepare_pdf_context/')
        request.user = SimpleNamespace(is_authenticated=False)
        self.assertEqual(route(request).status_code, 302)
        request.user = SimpleNamespace(pk=7, is_authenticated=True)
        self.assertEqual(route(request).status_code, 403)
        request = factory.get('/agent/prepare_pdf_context/')
        request.user = SimpleNamespace(pk=7, is_authenticated=True)
        self.assertEqual(route(request).status_code, 405)

    def test_consumer_hands_prepared_document_to_normal_rag_chain(self):
        from .consumers import AgentConsumer
        result = prepare_pdf_context(self.pdf_upload(), 7)
        directory, filename = resolve_pdf_context(result['token'], 7)

        async def exercise(failure=False):
            consumer = AgentConsumer()
            user = SimpleNamespace(pk=7, id=7, username='pdf-test', is_authenticated=True)
            consumer.scope = {'user': user}
            consumer.send = AsyncMock()
            consumer.save_session_state = AsyncMock()
            consumer.setup_contextual_rag_chain = AsyncMock(
                return_value=True, side_effect=RuntimeError('Test setup failure') if failure else None)
            await consumer.receive(json.dumps({'type': 'set-pdf-canvas-as-context',
                                               'message': 'report.pdf', 'context_token': result['token']}))
            await asyncio.sleep(0)
            consumer.save_session_state.assert_awaited_once_with(user, str(directory), 'file', filename)
            consumer.setup_contextual_rag_chain.assert_awaited_once_with(str(directory), filename)
            reply = json.loads(consumer.send.call_args_list[0].kwargs['text_data'])
            self.assertEqual(reply['context_path'], str(directory / filename))
            self.assertEqual(reply['type'], 'context-path-set')
            finished = json.loads(consumer.send.call_args_list[-1].kwargs['text_data'])
            self.assertEqual(finished, {'type': 'pdf-canvas-context-finished',
                                       'context_token': result['token'], 'success': not failure})
        asyncio.run(exercise())
        asyncio.run(exercise(failure=True))

    def test_real_image_interpreter_analysis_is_included_in_pdf_context(self):
        import yaml
        from .test_image_interpreter_agent import _FakeOllama
        from . import pdf_image_analysis
        with _FakeOllama(delay_seconds=0.01) as server:
            config_dir = self.root / 'agents/image_interpreter'
            config_dir.mkdir(parents=True)
            (config_dir / 'config.yaml').write_text(yaml.safe_dump({
                'llm': {'host': server.host}, 'interpreter_model_1': 'pdf-vision-a',
                'interpreter_model_2': 'pdf-vision-b', 'merging_model': 'pdf-merge',
            }), encoding='utf-8')
            self.analyzer_mock.side_effect = self.real_analyzer
            with patch.object(pdf_image_analysis, 'get_runtime_agent_root', return_value=str(self.root)):
                result = prepare_pdf_context(self.pdf_upload(), 7, process_images=True)
            directory, filename = resolve_pdf_context(result['token'], 7)
            content = (directory / filename).read_text(encoding='utf-8')
            self.assertEqual(content.count('REPLY-FROM-pdf-merge'), 3)
            self.assertEqual(len(server.by_model('pdf-vision-a')), 3)
            self.assertEqual(len(server.by_model('pdf-vision-b')), 3)
            self.assertEqual(len(server.by_model('pdf-merge')), 3)
            self.assertEqual(result['analysis_warnings'], 0)
            self.assertIn('Transcribe visible document text', server.by_model('pdf-vision-a')[0]['user'])

    def test_cancelled_background_job_stops_before_next_image(self):
        from .pdf_context_jobs import start_job, job_status
        entered, release = threading.Event(), threading.Event()
        def delayed_analysis(path):
            entered.set()
            release.wait(5)
            return 'Cancelled analysis should not be indexed.', 'merged'
        self.analyzer_mock.return_value = delayed_analysis
        token = start_job(self.pdf_upload(), 7, process_images=True)
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(ValueError):
                job_status(token, 8, cancel=True)
            job_status(token, 7, cancel=True)
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and job_status(token, 7)['status'] == 'pending':
            time.sleep(0.01)
        self.assertEqual(job_status(token, 7)['status'], 'cancelled')
        self.assertEqual(list((self.root / 'context_files/pdf_canvas/7').iterdir()), [])

    def test_cancellation_before_upload_response_prevents_processing(self):
        from .pdf_context_jobs import cancel_request, start_job, job_status
        request_id = str(uuid.uuid4())
        cancel_request(request_id, 7)
        token = start_job(self.pdf_upload(), 7, request_id=request_id)
        self.assertEqual(job_status(token, 7)['status'], 'cancelled')
        self.analyzer_mock.assert_not_called()
        self.assertFalse((self.root / 'context_files').exists())

    def test_image_analysis_failures_are_reported_without_losing_pdf_text(self):
        self.analyzer_mock.return_value = lambda path: ('Error: vision models are unavailable.', 'error')
        result = prepare_pdf_context(self.pdf_upload(), 7, process_images=True)
        directory, filename = resolve_pdf_context(result['token'], 7)
        content = (directory / filename).read_text(encoding='utf-8')
        self.assertEqual(result['analysis_warnings'], 3)
        self.assertIn('Context page 3', content)
        self.assertIn('Status: error', content)

    def test_default_text_only_skips_all_image_work_and_model_configuration(self):
        import pymupdf
        progress = []
        with patch.object(pymupdf.Page, 'get_pixmap', side_effect=AssertionError('Unexpected page rendering')), \
                patch.object(pymupdf.Page, 'get_images', side_effect=AssertionError('Unexpected image extraction')):
            result = prepare_pdf_context(self.pdf_upload(), 7, progress=progress.append)
        directory, filename = resolve_pdf_context(result['token'], 7)
        content = (directory / filename).read_text(encoding='utf-8')
        self.assertIn('Context page 3', content)
        self.assertIn('Image processing is disabled', content)
        self.assertFalse((directory / 'images').exists())
        self.assertFalse(result['process_images'])
        self.assertEqual((result['images'], result['page_previews'], result['analyses']), (0, 0, 0))
        self.assertTrue(all(item['stage'] == 'extract' for item in progress))
        self.analyzer_mock.assert_not_called()

    def test_text_only_without_selectable_text_explains_how_to_retry(self):
        import pymupdf
        with pymupdf.open() as document:
            document.new_page().draw_rect(pymupdf.Rect(10, 10, 100, 100))
            upload = SimpleUploadedFile('image-only.pdf', document.tobytes(), content_type='application/pdf')
        with self.assertRaisesMessage(PdfContextError, 'Enable Process images'):
            prepare_pdf_context(upload, 7)
        self.analyzer_mock.assert_not_called()
        self.assertEqual(list((self.root / 'context_files/pdf_canvas/7').iterdir()), [])

    def test_upload_route_requires_explicit_true_for_image_processing(self):
        from .pdf_context_views import prepare_pdf_context_view
        for option, expected in [(None, False), ('false', False), ('true', True)]:
            data = {'pdf': self.pdf_upload()}
            if option is not None:
                data['process_images'] = option
            request = RequestFactory().post('/agent/prepare_pdf_context/', data)
            request.user = SimpleNamespace(pk=7)
            with patch('agent.pdf_context_views.start_job', return_value='job-token') as start:
                self.assertEqual(prepare_pdf_context_view(request).status_code, 202)
                self.assertIs(start.call_args.kwargs['process_images'], expected)
        request = RequestFactory().post('/agent/prepare_pdf_context/', {'pdf': self.pdf_upload(), 'process_images': 'yes'})
        request.user = SimpleNamespace(pk=7)
        with patch('agent.pdf_context_views.start_job') as start:
            self.assertEqual(prepare_pdf_context_view(request).status_code, 400)
            start.assert_not_called()

    def test_image_interpreter_import_has_no_process_side_effects(self):
        import importlib.util
        import logging
        import os
        import subprocess
        script = Path(__file__).parent / 'agents/image_interpreter/image_interpreter.py'
        cwd, handlers, popen = os.getcwd(), list(logging.getLogger().handlers), subprocess.Popen.__init__
        spec = importlib.util.spec_from_file_location('pdf_import_safety_test', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(os.getcwd(), cwd)
        self.assertEqual(logging.getLogger().handlers, handlers)
        self.assertIs(subprocess.Popen.__init__, popen)
