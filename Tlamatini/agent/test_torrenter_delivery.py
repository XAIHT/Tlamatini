# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Regression checks for internal IPC and honest delivered-file reporting."""
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from .agents.torrenter import client, torrenter
from .agents.torrenter.contract import TorrentError
from .agents.torrenter.activity import ActivityLog


def _scratch():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "Temp" / "torrenter-tests"
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


class DeliveryTests(unittest.TestCase):
    def test_issue_uses_the_edition_output_root_and_not_a_windows_profile(self):
        from .rag.config import default_application_path
        profile = "tlm-11111111-1111-1111-1111-111111111111"
        with patch.object(client, "native", return_value={}) as call:
            client.issue(profile, scope="read")
        root = Path(call.call_args.args[0]["application_content_root"])
        self.assertEqual(root, Path(default_application_path()) / "content_generated")
        self.assertFalse(root.is_relative_to(Path.home()))

    def test_verified_fallback_log_names_the_real_destination_and_reason(self):
        with _scratch() as folder:
            log = ActivityLog(Path(folder), "manifest", False)
            target = str(Path(folder) / "content_generated")
            log.assets({"publication":{"delivery_state":"saved","delivery_location":"content_generated",
                                       "saved_to":target,"downloads_error":"Access denied"}})
            text = log.path.read_text(encoding="utf8")
            self.assertIn(target, text)
            self.assertIn("Access denied", text)
            self.assertNotIn("Windows Downloads destination: " + target, text)

    def test_legacy_private_store_is_not_reported_as_delivered(self):
        source = {"verified": True, "output_root": "C:/ProgramData/private", "files": []}
        result = client.publication_status({"publication": source})["publication"]
        self.assertFalse(result["verified"])
        self.assertTrue(result["download_verified"])
        self.assertEqual(result["delivery_state"], "unavailable")
        self.assertTrue(source["verified"])  # Do not mutate the received evidence.

    def test_pending_delivery_never_logs_a_file_as_saved(self):
        with _scratch() as folder:
            log = ActivityLog(Path(folder), "manifest", False)
            log.assets({"files": [{"id":0,"path":"book.txt","size":10}], "publication": {
                "verified":False,"output_root":"C:/Downloads","delivery_state":"pending",
                "files":[{"id":0,"path":"book.txt","size":10,"sha256":"a"*64}]}})
            text = log.path.read_text(encoding="utf8")
            self.assertNotIn(str(Path("C:/Downloads") / "book.txt"), text)
            self.assertIn("pending", text)

    def test_internal_control_helper_cannot_allocate_a_console(self):
        with patch.object(client, "known_folder", return_value=Path("C:/Program Files")), \
                patch.object(client.subprocess, "run", return_value=SimpleNamespace(stdout='{"body":{}}')) as run:
            client.native({"op": "status"})
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 12)

    def test_completed_download_with_failed_delivery_is_not_reported_as_saved(self):
        state = {"phase": "completed", "completed_at": 123, "verified_bytes": 10, "selected_bytes": 10}
        manifest = {"verified": False, "delivery_state": "failed", "delivery_error": "Disk is full"}
        with patch.object(torrenter, "session", return_value="test-only"), \
                patch.object(torrenter, "request", side_effect=[(200, state), (200, manifest)]):
            with self.assertRaisesRegex(TorrentError, "Disk is full"):
                torrenter.wait_for_publication("test", {"job_id": "a" * 32}, MagicMock())


if __name__ == "__main__":
    unittest.main()
