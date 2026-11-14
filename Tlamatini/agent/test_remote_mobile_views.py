# Tlamatini — Created by Angela López Mendoza · XAIHT
"""Mobile boundaries with real filesystem/canvas behavior and isolated accounts."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings
from . import remote_mobile_views as mobile
from . import remote_controller_views as identity

@override_settings(ALLOWED_HOSTS=['testserver'], LOGIN_URL='/login/')
class MobileWorkspaceTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[3] / 'artifacts' / 'mobile-checks' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk=7, is_authenticated=True, is_active=True)
        self.profile = SimpleNamespace(enabled=True, binding_id='1'*32, account=uuid.uuid4())
        for target in (mobile, identity):
            patcher = patch.object(target, '_profile_for', return_value=self.profile)
            patcher.start(); self.addCleanup(patcher.stop)
        def resolve(value, **kwargs):
            path = Path(value).resolve()
            if not path.is_relative_to(self.root) or not path.exists(): return None
            if kwargs.get('expect_dir') and not path.is_dir(): return None
            return str(path)
        for name, kwargs in [('_get_application_root', {'return_value':str(self.root)}),
                             ('get_allowed_dirs_display', {'return_value':[]}),
                             ('resolve_runtime_agent_path', {'side_effect':resolve})]:
            patcher=patch.object(mobile.path_guard,name,**kwargs);patcher.start();self.addCleanup(patcher.stop)
    def request(self, method='get', data=None, address='127.0.0.1', owner=7):
        request=getattr(self.factory,method)('/agent/mobile/files/',data or {},REMOTE_ADDR=address)
        request.user=SimpleNamespace(pk=owner,is_authenticated=self.user.is_authenticated,is_active=self.user.is_active)
        request.session=SimpleNamespace(session_key='session-'+str(owner))
        return request
    def body(self,response): return json.loads(response.content)
    def select(self,name='note.txt'):
        response=mobile.canvas_selection(self.request('post',{'directory':str(self.root),'name':name}))
        self.assertEqual(response.status_code,200,response.content)
        return self.body(response)
    def save(self,selection,*,owner=7):
        return mobile.canvas_save(self.request('post',{'token':selection['token'],'revision':selection['revision'],
            'file':SimpleUploadedFile('note.txt',b'fresh content')},owner=owner))
    def test_anonymous_cannot_list_files(self):
        self.user.is_authenticated=False
        self.assertEqual(mobile.files(self.request()).status_code,302)
    def test_network_address_cannot_use_loopback_endpoint(self):
        request=self.request(address='192.0.2.1');request.META['HTTP_X_FORWARDED_FOR']='127.0.0.1'
        self.assertEqual(mobile.files(request).status_code,403)
    def test_disabled_profile_cannot_browse(self):
        self.profile.enabled=False;self.assertEqual(mobile.files(self.request()).status_code,403)
    def test_inactive_user_cannot_browse(self):
        self.user.is_active=False;self.assertEqual(mobile.files(self.request()).status_code,403)
    def test_unbound_profile_cannot_browse(self):
        self.profile.binding_id='';self.assertEqual(mobile.files(self.request()).status_code,403)
    def test_allowed_folder_lists_files_without_reading_content(self):
        (self.root/'one.txt').write_text('private body');(self.root/'folder').mkdir()
        response=mobile.files(self.request());self.assertEqual(response.status_code,200)
        body=self.body(response);self.assertEqual([x['name'] for x in body['entries']],['folder','one.txt'])
        self.assertNotIn('private body',response.content.decode());self.assertIsNone(body['parent'])
    def test_parent_escape_is_refused(self):
        self.assertEqual(mobile.files(self.request(data={'path':str(self.root.parent)})).status_code,403)
    def test_pagination_is_bounded(self):
        for index in range(202):(self.root/str(index)).touch()
        first=self.body(mobile.files(self.request()));self.assertEqual(len(first['entries']),200)
        second=self.body(mobile.files(self.request(data={'offset':first['next_offset']})))
        self.assertEqual(len(second['entries']),2);self.assertFalse(set(x['name'] for x in first['entries'])&set(x['name'] for x in second['entries']))
    def test_negative_offset_is_refused(self):
        self.assertEqual(mobile.files(self.request(data={'offset':'-1'})).status_code,400)
    def test_canvas_selection_does_not_write_a_file(self):
        selected=self.select();self.assertEqual(selected['revision'],'missing');self.assertFalse((self.root/'note.txt').exists())
    def test_canvas_saves_real_bytes_and_returns_revision(self):
        response=self.save(self.select());self.assertEqual(response.status_code,200,response.content)
        self.assertEqual((self.root/'note.txt').read_bytes(),b'fresh content');self.assertEqual(len(self.body(response)['revision']),64)
    def test_another_account_cannot_use_canvas_selection(self):
        response=self.save(self.select(),owner=8);self.assertEqual(response.status_code,403);self.assertFalse((self.root/'note.txt').exists())
    def test_external_edit_is_not_overwritten(self):
        (self.root/'note.txt').write_text('first');selected=self.select();(self.root/'note.txt').write_text('changed elsewhere')
        self.assertEqual(self.save(selected).status_code,409);self.assertEqual((self.root/'note.txt').read_text(),'changed elsewhere')
    def test_new_selection_cannot_overwrite_file_created_after_confirmation(self):
        selected=self.select();(self.root/'note.txt').write_text('new owner');self.assertEqual(self.save(selected).status_code,409)
    def test_disabled_profile_cannot_commit_selected_destination(self):
        selected=self.select();self.profile.enabled=False;self.assertEqual(self.save(selected).status_code,403)
    def test_canvas_traversal_name_is_refused(self):
        self.assertEqual(mobile.canvas_selection(self.request('post',{'directory':str(self.root),'name':'../outside.txt'})).status_code,400)
    def test_identity_uses_immutable_account_and_binding(self):
        body=self.body(identity.session_identity(self.request()));self.assertEqual(body['account_id'],self.profile.account.hex);self.assertEqual(body['binding_id'],self.profile.binding_id)
    def test_identity_requires_normal_login(self):
        self.user.is_authenticated=False;self.assertEqual(identity.session_identity(self.request()).status_code,401)
    def test_identity_does_not_accept_forwarded_loopback(self):
        request=self.request(address='192.0.2.1');request.META['HTTP_X_FORWARDED_FOR']='127.0.0.1';self.assertEqual(identity.session_identity(request).status_code,403)
    def test_identity_is_not_cached(self):
        self.assertIn('no-store',identity.session_identity(self.request())['Cache-Control'])
