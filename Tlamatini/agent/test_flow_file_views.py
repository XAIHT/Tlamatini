# Tlamatini Author Banner — Angela López Mendoza
"""Run via manage.py test in a verified visible foreground console."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from agent import flow_file_open as files


class FlowFileWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('flow-file-user', password='test-only-736')
        cls.other = get_user_model().objects.create_user('flow-file-other', password='test-only-937')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = patch.object(files, 'request_directory', return_value=Path(self.temp.name))
        self.queue.start()
        self.addCleanup(self.queue.stop)
        self.flow = {'nodes': [], 'connections': []}

    def file(self, name='sample.flw', data=None):
        return SimpleUploadedFile(name, json.dumps(self.flow if data is None else data).encode(), 'application/json')

    def test_authenticated_csrf_protected_upload(self):
        url = '/agent/flow_files/open/'
        response = self.client.post(url, {'file': self.file()})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        response = self.client.post(url, {'file': self.file()})
        self.assertEqual(response.status_code, 200)
        opened = response.json()['url']
        self.assertTrue(opened.startswith('/agent/agentic_control_panel/?open='))
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.user)
        self.assertEqual(guarded.post(url, {'file': self.file()}).status_code, 403)
        for endpoint in ('open', 'validate'):
            self.assertEqual(self.client.get('/agent/flow_files/' + endpoint + '/').status_code, 405)

    def test_payload_validation_and_no_token_for_validation_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/agent/flow_files/open/', {}).status_code, 400)
        self.assertEqual(self.client.post('/agent/flow_files/open/', {'file': self.file(data={})}).status_code, 400)
        response = self.client.post('/agent/flow_files/validate/', {'file': self.file()})
        self.assertEqual(response.json()['flow'], self.flow)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_login_retains_opening_destination(self):
        token = files.create_request(json.dumps(self.flow).encode(), 'sample.flw')
        destination = files.opening_path('sample.flw', token)
        response = self.client.get(destination)
        self.assertEqual(response.status_code, 302)
        login_page = self.client.get(response.url)
        self.assertContains(login_page, 'name="next"')
        self.assertContains(login_page, token)
        response = self.client.post('/agent/', {'username': 'flow-file-user', 'password': 'test-only-736', 'next': destination})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, destination)
        page = self.client.get(destination)
        self.assertContains(page, 'server-flw-data')
        self.assertContains(page, 'sample.flw')
        self.assertContains(self.client.get(destination), 'flow-open-error')

    def test_login_rejects_external_next(self):
        for destination in ('https://evil.invalid/path', '//evil.invalid', 'javascript:alert(1)'):
            self.client.logout()
            response = self.client.post('/agent/', {'username': 'flow-file-user', 'password': 'test-only-736', 'next': destination})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/agent/welcome/')

    def test_wrong_user_cannot_consume_upload(self):
        token = files.create_request(json.dumps(self.flow).encode(), 'sample.flw', user_id=self.user.pk)
        destination = files.opening_path('sample.flw', token)
        self.client.force_login(self.other)
        self.assertContains(self.client.get(destination), 'flow-open-error')
        self.client.force_login(self.user)
        self.assertContains(self.client.get(destination), 'server-flw-data')

    def test_status_identifies_only_this_loopback_instance(self):
        response = self.client.get('/agent/flow_files/status/', REMOTE_ADDR='127.0.0.1')
        self.assertEqual(response.json(), files.status_payload())
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/agent/flow_files/status/', REMOTE_ADDR='192.0.2.1').status_code, 403)
        self.assertEqual(self.client.post('/agent/flow_files/status/').status_code, 405)

    def test_prompt_flow_uses_its_own_editor(self):
        fixture = json.loads((Path(__file__).resolve().parents[2] / 'docs/examples/prompting-kickoff.fpmt').read_text(encoding='utf-8'))
        token = files.create_request(json.dumps(fixture).encode(), 'review.fpmt')
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/agent/agentic_control_panel/?open=' + token), 'flow-open-error')
        response = self.client.get(files.opening_path('review.fpmt', token))
        self.assertContains(response, 'server-fpmt-data')
        self.assertContains(response, 'review.fpmt')
