# Tlamatini — Created by Angela López Mendoza · @angelahack1
"""Twenty real-ORM/file tests per edition; run only via rc_main_checks.py.

The runner creates every table in a fresh, application-owned SQLite file first.
These cases never load product settings, start a model or touch a live account.
"""
from io import BytesIO
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
import zipfile

from django.contrib.auth.models import User
from django.core import signing
from django.db import connection, transaction
from django.test import RequestFactory

from . import path_guard
from . import remote_response_files as files
from .remote_controller_bridge import EDITION
from .models import AgentMessage, LLMProgram, LLMSnippet, RemoteControllerProfile


class ResponseFileTests(unittest.TestCase):
    def setUp(self):
        database = str(connection.settings_dict["NAME"]).replace("\\", "/")
        if "/artifacts/rc-implementation/main-schema-" not in database or not database.endswith("/accounts.sqlite3"):
            raise RuntimeError("Use the isolated visible rc_main_checks.py runner")
        self.responses = []
        self.atomic = transaction.atomic()
        self.atomic.__enter__()
        self.addCleanup(self.rollback)
        self.user = User.objects.create(username="response-" + uuid.uuid4().hex, is_active=True)
        self.other = User.objects.create(username="response-other-" + uuid.uuid4().hex, is_active=True)
        self.bot, _ = User.objects.get_or_create(username="Tlamatini")
        self.profile = RemoteControllerProfile.objects.create(user=self.user, enabled=True, binding_id=uuid.uuid4().hex)
        self.other_profile = RemoteControllerProfile.objects.create(user=self.other, enabled=True, binding_id=uuid.uuid4().hex)
        self.factory = RequestFactory()
        self.folder = Path(database).parent / ("response-files-" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.words = "Español: información, corazón y niño 🚀" if EDITION == "spanish" else "English: résumé, café and rocket 🚀"
        def resolve(value, **kwargs):
            candidate = Path(value).resolve()
            return str(candidate) if candidate.is_relative_to(self.folder) and candidate.is_file() else None
        patcher = patch.object(path_guard, "resolve_runtime_agent_path", side_effect=resolve)
        patcher.start()
        self.addCleanup(patcher.stop)

    def rollback(self):
        transaction.set_rollback(True)
        self.atomic.__exit__(None, None, None)
        # FileResponse.close emits request_finished, which closes the direct
        # fixture connection. Emit it only after our test transaction exits.
        for response in self.responses:
            response.close()

    def row(self, html, owner=None):
        return AgentMessage.objects.create(user=self.bot, conversation_user=owner or self.user, message=html)

    def program(self, name="answer.py", language="python", content=None, snippet=False):
        body = self.words if content is None else content
        if snippet:
            LLMSnippet.objects.create(snippetName=name, snippetLanguage=language, snippetContent=body)
            obj = LLMSnippet.objects.filter(snippetName=name).order_by("-idSnippet").first()
        else:
            LLMProgram.objects.create(programName=name, programLanguage=language, programContent=body)
            obj = LLMProgram.objects.filter(programName=name).order_by("-idProgram").first()
        row = self.row(f'''<p>{self.words}</p><a href="#" onclick='loadCanvas("{name}");'>---Load in canvas---</a>''')
        row.response_files = files.record_artifacts([{
            "kind": "snippet" if snippet else "program", "name": name, "content": body}])
        row.save(update_fields=["response_files"])
        reference = {"kind": "canvas", "value": name}
        ticket, filename = files._issue(self.profile, row, reference)
        return obj, row, ticket, filename

    def local_file(self, name, data):
        path = self.folder / name
        path.write_bytes(data)
        row = self.row('<a href="' + path.as_uri() + '">Download</a>')
        row.response_files = files.capture_tool_files("chat_agent_file_creator", {
            "status": "completed", "agent_status": "created", "output_path": str(path),
            "output_sha256": hashlib.sha256(data).hexdigest()})
        row.save(update_fields=["response_files"])
        reference = {"kind": "file", "value": str(path).replace("\\", "/")}
        ticket, filename = files._issue(self.profile, row, reference)
        return path, row, ticket, filename

    def request(self, ticket, binding=None, address="127.0.0.1"):
        return self.factory.get('/agent/remote-controller/response-file/', {"ticket": ticket},
                                REMOTE_ADDR=address, HTTP_X_TLACHIHUANI_BINDING=binding or self.profile.binding_id)

    def consume(self, response, data, name):
        self.assertEqual(response.status_code, 200, getattr(response, "content", b""))
        actual = b"".join(response.streaming_content)
        self.responses.append(response)
        response.file_to_stream.close()
        self.assertEqual(actual, data)
        self.assertEqual(response["Content-Length"], str(len(data)))
        self.assertEqual(response["X-Content-SHA256"], hashlib.sha256(data).hexdigest())
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        from urllib.parse import quote
        self.assertTrue(name in response["Content-Disposition"] or quote(name) in response["Content-Disposition"])
        return actual

    def test_01_program_download_preserves_original_utf8_and_line_endings(self):
        content = '# ' + self.words + '\r\nprint("hello")\r\n'
        _, _, ticket, name = self.program(content=content)
        # Historical name collisions cannot redirect this receipt to a newer row.
        LLMProgram.objects.create(programName="answer.py", programLanguage="python", programContent="another response")
        self.consume(files.download(self.request(ticket)), content.encode("utf-8"), name)

    def test_02_snippet_infers_its_real_language_extension(self):
        _, _, ticket, name = self.program(name="Without_Name", language="sql", snippet=True)
        self.assertEqual(name, "Without_Name.sql")
        self.consume(files.download(self.request(ticket)), self.words.encode("utf-8"), name)

    def test_03_unicode_json_csv_xml_and_markdown_are_not_reformatted(self):
        cases = {"informe-ñ.json": json.dumps({"title": self.words}, ensure_ascii=False),
                 "table.csv": 'title,value\r\n"' + self.words + '",3\r\n',
                 "document.xml": '<title>' + self.words + '</title>',
                 "notes.md": '# ' + self.words + '\n\n- one\n- two\n'}
        for name, content in cases.items():
            with self.subTest(name=name):
                _, _, ticket, filename = self.program(name=name, language="by-extension", content=content)
                self.consume(files.download(self.request(ticket)), content.encode("utf-8"), filename)

    def test_04_binary_pdf_png_zip_and_office_files_keep_exact_bytes(self):
        import base64
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aUnkAAAAASUVORK5CYII=")
        cases = {"report.pdf": b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF", "image.png": png,
                 "raw.bin": bytes(range(256)) * 1000, "LICENSE": self.words.encode("utf-8")}
        for ext in ("zip", "docx", "xlsx", "pptx"):
            output = BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
                archive.writestr("content.txt", self.words)
            cases["document." + ext] = output.getvalue()
        for name, data in cases.items():
            with self.subTest(name=name):
                _, _, ticket, filename = self.local_file(name, data)
                self.consume(files.download(self.request(ticket)), data, filename)

    def test_05_rich_styles_entities_and_tables_are_preserved(self):
        html = '<div style="background:linear-gradient(135deg,#0a0a23,#3a0ca3);color:white"><h3>' + self.words + '</h3><table><tr><td>&lt;code&gt; &amp; value</td></tr></table></div>'
        self.assertEqual(files.render_response(self.user.pk, None, html), html)
        row = self.row(html * 700)
        ticket = files.content_ticket(self.user.pk, row.pk, row.message)
        response = files.response_content(self.request(ticket))
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["html"], row.message)
        self.assertFalse(payload["truncated"])
        row.message += "changed"
        row.save(update_fields=["message"])
        self.assertEqual(files.response_content(self.request(ticket)).status_code, 409)

    def test_06_report_boundary_survives_download_link_rewriting(self):
        _, row, _, _ = self.program()
        row.message += '<!--TLAMATINI_EXEC_REPORT_BOUNDARY--><table><tr><td>Done</td></tr></table>'
        row.save(update_fields=["message"])
        rendered = files.render_response(self.user.pk, row.pk, row.message)
        self.assertIn('data-rc-file=', rendered)
        self.assertIn('<!--TLAMATINI_EXEC_REPORT_BOUNDARY-->', rendered)
        self.assertNotIn('onclick=', rendered)
        self.assertNotIn('Load in canvas', rendered)
        self.assertIn('Guardar archivo' if EDITION == 'spanish' else 'Save file', rendered)

    def test_07_another_binding_cannot_redeem_a_valid_ticket(self):
        _, _, ticket, _ = self.program()
        self.assertEqual(files.download(self.request(ticket, binding=self.other_profile.binding_id)).status_code, 403)
        grant = signing.loads(ticket, key=files._SIGNING_KEY, salt=files.SALT, fallback_keys=[])
        forged = signing.dumps(grant, salt=files.SALT)
        self.assertEqual(files.download(self.request(forged)).status_code, 403)

    def test_08_revoked_or_inactive_account_cannot_download(self):
        _, _, ticket, _ = self.program()
        self.profile.enabled = False
        self.profile.save(update_fields=["enabled"])
        self.assertEqual(files.download(self.request(ticket)).status_code, 403)
        self.profile.enabled = True
        self.profile.save(update_fields=["enabled"])
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(files.download(self.request(ticket)).status_code, 403)

    def test_09_expired_ticket_reports_expiry(self):
        _, _, ticket, _ = self.program()
        with patch.object(files, "MAX_TICKET_SECONDS", -1):
            self.assertEqual(files.download(self.request(ticket)).status_code, 410)
        with patch.object(files, "_SIGNING_KEY", "different-private-process-key"):
            self.assertEqual(files.download(self.request(ticket)).status_code, 403)

    def test_10_tampered_ticket_and_nonlocal_requests_are_refused(self):
        _, _, ticket, _ = self.program()
        changed = ticket[:-1] + ("A" if ticket[-1] != "A" else "B")
        self.assertEqual(files.download(self.request(changed)).status_code, 403)
        request = self.request(ticket, address="192.0.2.20")
        request.META["HTTP_X_FORWARDED_FOR"] = "127.0.0.1"
        self.assertEqual(files.download(request).status_code, 403)

    def test_11_deleted_message_invalidates_its_download(self):
        _, row, ticket, _ = self.program()
        row.delete()
        self.assertEqual(files.download(self.request(ticket)).status_code, 404)

    def test_12_changed_database_or_disk_bytes_are_never_substituted(self):
        obj, _, ticket, _ = self.program()
        obj.programContent = "different"
        obj.save(update_fields=["programContent"])
        self.assertEqual(files.download(self.request(ticket)).status_code, 409)
        path, _, ticket, _ = self.local_file("changed.bin", b"first")
        path.write_bytes(b"other")
        self.assertEqual(files.download(self.request(ticket)).status_code, 409)

    def test_13_deleted_file_reports_missing(self):
        path, _, ticket, _ = self.local_file("removed.txt", b"original")
        path.unlink()
        self.assertEqual(files.download(self.request(ticket)).status_code, 404)

    def test_14_size_limit_refuses_before_delivery(self):
        _, _, ticket, _ = self.local_file("bounded.bin", b"a" * 100)
        with patch.object(files, "MAX_FILE_BYTES", 50):
            self.assertEqual(files.download(self.request(ticket)).status_code, 413)

    def test_15_path_permissions_are_rechecked_at_download(self):
        _, _, ticket, _ = self.local_file("allowed.txt", b"original")
        with patch.object(path_guard, "resolve_runtime_agent_path", return_value=None):
            self.assertEqual(files.download(self.request(ticket)).status_code, 403)

    def test_16_reparse_points_are_refused(self):
        path, _, ticket, _ = self.local_file("plain.txt", b"original")
        original = Path.lstat
        def reparse(candidate, *args, **kwargs):
            info = original(candidate, *args, **kwargs)
            if candidate == path:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(Path, "lstat", reparse):
            self.assertEqual(files.download(self.request(ticket)).status_code, 403)

    def test_17_full_workspace_saves_owned_canvas_content(self):
        _, row, _, name = self.program()
        request = self.factory.get('/agent/mobile/response-file/', {"message_id": row.pk, "name": "answer.py"}, REMOTE_ADDR="127.0.0.1")
        request.user = self.user
        self.consume(files.mobile_download(request), self.words.encode("utf-8"), name)

    def test_18_full_workspace_refuses_other_accounts_and_unreferenced_files(self):
        _, row, _, _ = self.program()
        for owner, name in [(self.other, "answer.py"), (self.user, "secret.py")]:
            request = self.factory.get('/agent/mobile/response-file/', {"message_id": row.pk, "name": name}, REMOTE_ADDR="127.0.0.1")
            request.user = owner
            self.assertIn(files.mobile_download(request).status_code, (403, 404))

    def test_19_html_svg_and_script_files_are_attachments_never_inline(self):
        for name, content in {"page.html": '<script>alert(1)</script>', "drawing.svg": '<svg onload="alert(1)"></svg>', "run.ps1": 'Write-Output "' + self.words + '"'}.items():
            _, _, ticket, filename = self.program(name=name, content=content)
            self.consume(files.download(self.request(ticket)), content.encode("utf-8"), filename)

    def test_20_only_exact_canvas_actions_and_valid_filenames_are_authorized(self):
        for action in ['loadCanvas("x");evil()', 'other("x")', 'loadCanvas(variable)', 'loadCanvas("x", "y")']:
            self.assertIsNone(files._reference([("onclick", action)]))
        for name in ('../secret', 'bad\\name', 'bad:name', 'bad\nname', ''):
            with self.assertRaises(files.FileFault):
                files._filename(name)
        self.assertEqual(files._references('<code>loadCanvas("secret")</code>'), [])
        _, owned, _, _ = self.program(name="private.py", content="private content")
        forged = self.row(owned.message)  # A link alone grants nothing, even in this account.
        with self.assertRaises(files.FileFault):
            files._issue(self.profile, forged, {"kind": "canvas", "value": "private.py"})
        self.assertNotIn("data-rc-file", files.render_response(self.user.pk, forged.pk, forged.message))
        path, _, _, _ = self.local_file("private.bin", b"private")
        forged.message = '<a href="' + path.as_uri() + '">pretend output</a>'
        forged.save(update_fields=["message"])
        self.assertNotIn("data-rc-file", files.render_response(self.user.pk, forged.pk, forged.message))
        self.assertEqual(files.capture_tool_files("chat_agent_executer", {"status": "completed", "output_path": str(path)}), [])
        self.assertEqual(files.capture_tool_files("chat_agent_file_creator", {"status": "completed", "output_path": str(path)}), [])


class ResponseParserDownloadTests(unittest.TestCase):
    """Actual parser -> SQLite manifest -> rich response -> exact downloaded bytes."""
    def setUp(self):
        database = str(connection.settings_dict["NAME"]).replace("\\", "/")
        if "/artifacts/rc-implementation/main-schema-" not in database or not database.endswith("/accounts.sqlite3"):
            raise RuntimeError("Use the isolated visible rc_main_checks.py runner")
        self.user = User.objects.create(username="parser-response-" + uuid.uuid4().hex, is_active=True)
        self.profile = RemoteControllerProfile.objects.create(user=self.user, enabled=True, binding_id=uuid.uuid4().hex)
        self.folder = Path(database).parent / ("parser-files-" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.factory = RequestFactory()
        self.program_ids, self.snippet_ids = [], []
        def resolve(value, **kwargs):
            path = Path(value).resolve()
            return str(path) if path.is_relative_to(self.folder) and path.is_file() else None
        patcher = patch.object(path_guard, "resolve_runtime_agent_path", side_effect=resolve)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        LLMProgram.objects.filter(pk__in=self.program_ids).delete()
        LLMSnippet.objects.filter(pk__in=self.snippet_ids).delete()
        self.user.delete()

    def process(self, source, **kwargs):
        from asgiref.sync import async_to_sync
        from .services import response_parser
        with patch.object(response_parser, "get_time_stamp", return_value="rc-parser-" + uuid.uuid4().hex):
            rendered = async_to_sync(response_parser.process_llm_response)(
                source, None, None, None, conversation_user=self.user, **kwargs)
        row = AgentMessage.objects.filter(conversation_user=self.user, user__username="Tlamatini").latest("pk")
        self.assertEqual(row.message, rendered)
        for item in row.response_files:
            key = item["artifact"]["key"]
            if key.startswith("program:"):
                self.program_ids.append(int(key.split(":")[1]))
            elif key.startswith("snippet:"):
                self.snippet_ids.append(int(key.split(":")[1]))
        return row

    def saved_bytes(self, row, item):
        ticket, name = files._issue(self.profile, row, item["reference"])
        request = self.factory.get('/agent/remote-controller/response-file/', {"ticket": ticket},
                                   REMOTE_ADDR="127.0.0.1", HTTP_X_TLACHIHUANI_BINDING=self.profile.binding_id)
        response = files.download(request)
        self.assertEqual(response.status_code, 200)
        data = b"".join(response.streaming_content)
        response.close()
        self.assertEqual(hashlib.sha256(data).hexdigest(), item["artifact"]["sha256"])
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        return data

    def test_parser_all_generated_program_and_snippet_branches_are_downloadable(self):
        cases = [
            ('BEGIN-CODE<<<named.py>>>' + '```python\nprint("one")\n```' + '\nEND-CODE', 'print("one")'),
            ('BEGIN-CODE<<<named.txt>>>plain named\nEND-CODE', 'plain named'),
            ('BEGIN-CODE\n' + '```javascript\nconsole.log("two")\n```' + '\nEND-CODE', 'console.log("two")'),
            ('BEGIN-CODE\nplain unnamed\nEND-CODE', 'plain unnamed'),
            ('```python\nprint("snippet")\n```', 'print("snippet")'),
        ]
        for source, expected in cases:
            with self.subTest(source=source[:30]):
                row = self.process(source + '\nEND-RESPONSE')
                self.assertGreater(len(row.response_files), 0)
                rendered = files.render_response(self.user.pk, row.pk, row.message)
                self.assertIn('data-rc-file=', rendered)
                downloaded = [self.saved_bytes(row, item).decode("utf-8").strip() for item in row.response_files]
                self.assertIn(expected, downloaded)

    def test_real_parser_preserves_trusted_tool_output_and_refuses_model_forgery(self):
        output = self.folder / 'generated-report.pdf'
        data = b'%PDF-1.4\n% immutable test payload\n%%EOF'
        output.write_bytes(data)
        receipts = files.capture_tool_files('chat_agent_pdfer', {"status": "completed", "output_path": str(output)})
        self.assertEqual(len(receipts), 1)
        row = self.process('Report ready.\nEND-RESPONSE', tool_calls_log=[{
            "tool_name": "chat_agent_pdfer", "success": True, "response_files": receipts}])
        self.assertEqual(row.response_files, receipts)
        self.assertNotIn('file:', row.message)
        self.assertIn('data-rc-file=', files.render_response(self.user.pk, row.pk, row.message))
        self.assertEqual(self.saved_bytes(row, row.response_files[0]), data)
        forged = self.process('<a href="' + output.as_uri() + '">Pretend generated file</a>\nEND-RESPONSE', persist_artifacts=False)
        self.assertEqual(forged.response_files, [])
        self.assertNotIn('data-rc-file=', files.render_response(self.user.pk, forged.pk, forged.message))
