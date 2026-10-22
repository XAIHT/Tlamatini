# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Native-save safety tests; run from a verified visible development console.

The dialog is mocked here. The headed acceptance harness verifies the real
native picker separately; these tests never claim to exercise its UI.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from agent import canvas_file_views as files
from agent import native_dialogs


class CanvasNativeSaveTests(SimpleTestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / "Temp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="canvas-save-test-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.path = self.folder / "source.rs"
        self.factory = RequestFactory()
        files._CAPABILITIES.clear()
        self.addCleanup(files._CAPABILITIES.clear)

    def request(self, data, *, user=7, session="canvas-test", remote="127.0.0.1"):
        request = self.factory.post("/agent/canvas/save/", data, REMOTE_ADDR=remote)
        request.user = SimpleNamespace(pk=user, is_authenticated=True)
        request.session = SimpleNamespace(session_key=session)
        return request

    def save(self, content=b"fn main() {}\r\n", *, token="", revision="", **kwargs):
        data = {"file": SimpleUploadedFile("source.rs", content), "token": token, "revision": revision}
        response = files.save(self.request(data, **kwargs))
        return response, json.loads(response.content)

    def first_save(self, content=b"fn main() {}\r\n"):
        with patch.object(files, "_pick", return_value=str(self.path)):
            response, result = self.save(content)
        self.assertEqual(response.status_code, 200, result)
        self.assertTrue(result["saved"])
        return result

    def test_save_as_preserves_exact_bytes_and_grants_capability(self):
        raw = b"\xff\xfe" + "Espa\u00f1a\r\n\U0001f40d\r\n".encode("utf-16-le")
        result = self.first_save(raw)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(result["revision"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["filename"], self.path.name)
        self.assertGreaterEqual(len(result["token"]), 40)

    def test_save_replaces_selected_file_without_another_picker(self):
        result = self.first_save()
        with patch.object(files, "_pick") as picker:
            response, saved = self.save(b"changed\n", token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 200, saved)
        picker.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b"changed\n")
        self.assertEqual(saved["token"], result["token"])

    def test_empty_document_is_saved(self):
        result = self.first_save(b"")
        self.assertEqual(self.path.read_bytes(), b"")
        self.assertEqual(result["bytes"], 0)

    def test_cancel_writes_nothing_and_grants_nothing(self):
        with patch.object(files, "_pick", return_value=""):
            response, result = self.save()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(result["canceled"])
        self.assertFalse(result["saved"])
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertEqual(len(files._CAPABILITIES), 0)

    def test_same_size_external_change_with_same_timestamp_conflicts(self):
        result = self.first_save(b"original")
        old_stat = self.path.stat()
        self.path.write_bytes(b"external")
        os.utime(self.path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        response, result = self.save(b"my edits", token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(result["code"], "conflict")
        self.assertEqual(self.path.read_bytes(), b"external")

    def test_missing_file_is_not_silently_recreated(self):
        result = self.first_save()
        self.path.unlink()
        response, result = self.save(token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.path.exists())

    def test_missing_revision_refuses_before_writing(self):
        result = self.first_save(b"original")
        response, result = self.save(b"changed", token=result["token"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_old_revision_cannot_overwrite_a_second_save(self):
        initial = self.first_save(b"first")
        response, _ = self.save(b"second", token=initial["token"], revision=initial["revision"])
        self.assertEqual(response.status_code, 200)
        response, _ = self.save(b"third", token=initial["token"], revision=initial["revision"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.path.read_bytes(), b"second")

    def test_failed_replace_preserves_original_and_removes_staging(self):
        result = self.first_save(b"original")
        with patch.object(files, "_replace_destination", side_effect=PermissionError("File is locked")):
            response, result = self.save(b"changed", token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(result["code"], "write_failed")
        self.assertEqual(self.path.read_bytes(), b"original")
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_change_during_staging_refuses_replacement(self):
        result = self.first_save(b"original")
        real_snapshot = files._snapshot
        reads = 0

        def changed_snapshot(path):
            nonlocal reads
            reads += 1
            if reads == 2:
                path.write_bytes(b"external during save")
            return real_snapshot(path)

        with patch.object(files, "_snapshot", side_effect=changed_snapshot):
            response, _ = self.save(b"my edits", token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.path.read_bytes(), b"external during save")
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_readonly_staging_is_cleaned_after_failed_replace(self):
        result = self.first_save(b"original")
        self.path.chmod(0o444)
        try:
            with patch.object(files, "_replace_destination", side_effect=PermissionError("Read-only target")):
                response, _ = self.save(b"changed", token=result["token"], revision=result["revision"])
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.path.read_bytes(), b"original")
            self.assertEqual(list(self.folder.iterdir()), [self.path])
        finally:
            self.path.chmod(0o600)

    @skipUnless(os.name == "nt", "Windows metadata preservation")
    def test_real_windows_save_preserves_named_stream_and_creation_time(self):
        result = self.first_save(b"original")
        stream = Path(str(self.path) + ":Zone.Identifier")
        metadata = b"[ZoneTransfer]\r\nZoneId=3\r\n"
        stream.write_bytes(metadata)
        original = self.path.stat()
        created = getattr(original, "st_birthtime_ns", original.st_ctime_ns)
        response, saved = self.save(b"changed", token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 200, saved)
        self.assertEqual(self.path.read_bytes(), b"changed")
        self.assertEqual(stream.read_bytes(), metadata)
        final = self.path.stat()
        self.assertEqual(getattr(final, "st_birthtime_ns", final.st_ctime_ns), created)
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_windows_replace_errors_leave_original_and_staging_intact(self):
        self.path.write_bytes(b"original")
        temporary = self.folder / "staging.tmp"
        temporary.write_bytes(b"changed")
        for code in (1175, 1176, 5):
            with self.subTest(code=code), patch.object(files, "_win_replace_file", side_effect=OSError(code, "Windows refused")):
                with self.assertRaises(OSError):
                    files._replace_existing_windows(self.path, temporary)
            self.assertEqual(self.path.read_bytes(), b"original")
            self.assertEqual(temporary.read_bytes(), b"changed")
            self.assertEqual(list(self.folder.glob(".tlamatini-backup-*")), [])

    def test_windows_partial_replace_restores_original_from_backup(self):
        self.path.write_bytes(b"original")
        temporary = self.folder / "staging.tmp"
        temporary.write_bytes(b"changed")

        def partial(path, _temporary, backup):
            os.rename(path, backup)
            raise OSError(1177, "Replacement could not be moved")

        with patch.object(files, "_win_replace_file", side_effect=partial):
            with self.assertRaises(OSError):
                files._replace_existing_windows(self.path, temporary)
        self.assertEqual(self.path.read_bytes(), b"original")
        self.assertEqual(temporary.read_bytes(), b"changed")
        self.assertEqual(list(self.folder.glob(".tlamatini-backup-*")), [])

    def test_windows_failed_recovery_keeps_backup_and_names_it(self):
        self.path.write_bytes(b"original")
        temporary = self.folder / "staging.tmp"
        temporary.write_bytes(b"changed")
        rename = os.rename

        def partial(path, _temporary, backup):
            rename(path, backup)
            raise OSError(1177, "Replacement could not be moved")

        with patch.object(files, "_win_replace_file", side_effect=partial), \
                patch.object(files.os, "rename", side_effect=PermissionError("Recovery locked")):
            with self.assertRaises(OSError) as caught:
                files._replace_existing_windows(self.path, temporary)
        backup, = self.folder.glob(".tlamatini-backup-*")
        self.assertEqual(backup.read_bytes(), b"original")
        self.assertIn(str(backup), str(caught.exception))
        self.assertFalse(self.path.exists())

    def test_windows_recovery_never_overwrites_file_created_by_other_writer(self):
        self.path.write_bytes(b"original")
        temporary = self.folder / "staging.tmp"
        temporary.write_bytes(b"changed")

        def partial(path, _temporary, backup):
            os.rename(path, backup)
            path.write_bytes(b"another writer")
            raise OSError(1177, "Replacement could not be moved")

        with patch.object(files, "_win_replace_file", side_effect=partial):
            with self.assertRaises(OSError) as caught:
                files._replace_existing_windows(self.path, temporary)
        backup, = self.folder.glob(".tlamatini-backup-*")
        self.assertEqual(backup.read_bytes(), b"original")
        self.assertIn(str(backup), str(caught.exception))
        self.assertEqual(self.path.read_bytes(), b"another writer")

    def test_tokens_belong_to_both_user_and_session(self):
        result = self.first_save(b"original")
        for owner in ({"user": 8}, {"session": "other-tab-login"}):
            with self.subTest(owner=owner), patch.object(files, "_pick") as picker:
                response, denied = self.save(b"changed", token=result["token"], revision=result["revision"], **owner)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(denied["code"], "expired")
                picker.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_expired_token_requires_save_as(self):
        result = self.first_save()
        files._CAPABILITIES[result["token"]].touched -= files.TOKEN_TTL + 1
        response, result = self.save(token=result["token"], revision=result["revision"])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(result["code"], "expired")

    def test_remote_request_never_opens_desktop_picker(self):
        with patch.object(files, "_pick") as picker:
            response, result = self.save(remote="192.0.2.1")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(result["code"], "local_only")
        picker.assert_not_called()

    def test_untrusted_browser_path_is_refused(self):
        request = self.request({"file": SimpleUploadedFile("source.rs", b"text"), "path": str(self.path)})
        with patch.object(files, "_pick") as picker:
            response = files.save(request)
        self.assertEqual(response.status_code, 400)
        picker.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_size_limit_is_checked_before_picker(self):
        with patch.object(files, "MAX_FILE_BYTES", 3), patch.object(files, "_pick") as picker:
            response, result = self.save(b"1234")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(result["code"], "too_large")
        picker.assert_not_called()

    def test_oversized_request_is_rejected_before_multipart_parsing(self):
        request = self.request({"file": SimpleUploadedFile("source.rs", b"text")})
        request.META["CONTENT_LENGTH"] = str(files.MAX_FILE_BYTES + 65537)
        with patch.object(files, "_pick") as picker:
            response = files.save(request)
        self.assertEqual(response.status_code, 413)
        self.assertFalse(hasattr(request, "_files"))
        picker.assert_not_called()

    def test_read_returns_bytes_and_revision_without_accepting_external_change(self):
        result = self.first_save(b"original")
        self.path.write_bytes(b"external")
        response = files.read(self.request({"token": result["token"]}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"external")
        self.assertEqual(response["X-Canvas-Revision"], hashlib.sha256(b"external").hexdigest())
        self.assertIn("source.rs", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        denied, _ = self.save(b"old edits", token=result["token"], revision=result["revision"])
        self.assertEqual(denied.status_code, 409)
        accepted, _ = self.save(b"new edits", token=result["token"], revision=response["X-Canvas-Revision"])
        self.assertEqual(accepted.status_code, 200)

    def test_read_denies_unknown_token_and_missing_file(self):
        response = files.read(self.request({"token": "<REDACTED>"}))
        self.assertEqual(response.status_code, 403)
        result = self.first_save()
        self.path.unlink()
        response = files.read(self.request({"token": result["token"]}))
        self.assertEqual(response.status_code, 404)

    def test_real_url_wrappers_enforce_csrf_authentication_and_post(self):
        for endpoint in ("save", "read"):
            handler = resolve(f"/agent/canvas/{endpoint}/").func
            request = self.request({})
            response = handler(request)
            self.assertEqual(response.status_code, 403)
            request = self.request({})
            request.user.is_authenticated = False
            self.assertEqual(handler(request).status_code, 302)
            request = self.factory.get(f"/agent/canvas/{endpoint}/")
            request.user = SimpleNamespace(is_authenticated=True)
            self.assertEqual(handler(request).status_code, 405)

    def test_unavailable_dialog_is_reported_distinctly(self):
        with patch.object(native_dialogs, "is_supported", return_value=False):
            response, result = self.save()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(result["code"], "non_windows")

    def test_dialog_runs_on_its_own_thread_and_cancel_propagates(self):
        import threading
        threads = []

        def picker(*_args):
            threads.append(threading.current_thread().name)
            return ""

        with patch.object(native_dialogs, "is_supported", return_value=True), \
                patch.object(native_dialogs, "pick_save_file", side_effect=picker):
            self.assertEqual(files._pick("source.rs"), "")
        self.assertEqual(threads, ["tlamatini-canvas-save-picker"])

    def test_second_native_dialog_is_refused_without_waiting(self):
        with patch.object(native_dialogs, "is_supported", return_value=True):
            files._PICKER_LOCK.acquire()
            try:
                with self.assertRaises(files.SaveError) as caught:
                    files._pick("source.rs")
            finally:
                files._PICKER_LOCK.release()
        self.assertEqual(caught.exception.code, "busy")
