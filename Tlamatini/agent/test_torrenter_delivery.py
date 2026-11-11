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
        clock = _Clock()
        with patch.object(torrenter, "session", return_value="test-only"), \
                patch.object(torrenter, "time", clock), \
                patch.object(torrenter, "request", side_effect=_answers(state, manifest)):
            with self.assertRaisesRegex(TorrentError, "Disk is full"):
                torrenter.wait_for_publication("test", {"job_id": "a" * 32}, MagicMock())
        # Jobs retries a failed save every 60 s, so the wait gives it that chance first.
        self.assertGreaterEqual(clock.now, torrenter.DELIVERY_GRACE_SECONDS)


class _Clock:
    """A fake time module: sleeping advances the clock instantly."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _answers(state, *manifests):
    """Jobs replies: the job state, then each manifest in turn (the last one repeats)."""
    queue = list(manifests)

    def reply(method, path, **_):
        if not path.endswith("/manifest"):
            return 200, state
        return 200, queue.pop(0) if len(queue) > 1 else queue[0]
    return reply


class WaitForPublicationTests(unittest.TestCase):
    JOB = "b" * 32

    def wait(self, reply, clock=None, renew=None):
        receipt = {"job_id": self.JOB, "response_body": {}}
        with patch.object(torrenter, "session", renew or MagicMock(return_value="test-only")), \
                patch.object(torrenter, "time", clock or _Clock()), \
                patch.object(torrenter, "request", side_effect=reply):
            torrenter.wait_for_publication("test", receipt, MagicMock())
        return receipt

    def test_a_paused_download_ends_the_wait_instead_of_waiting_forever(self):
        for state in ({"phase": "paused", "desired_state": "paused"},
                      {"phase": "pausing", "desired_state": "paused", "verified_bytes": 4}):
            with self.subTest(phase=state["phase"]):
                with self.assertRaisesRegex(TorrentError, "ended before verified publication. paused"):
                    self.wait(_answers(state, {}))

    def test_a_failed_save_that_jobs_repairs_in_time_completes(self):
        state = {"phase": "completed", "completed_at": 1, "verified_bytes": 9, "selected_bytes": 9}
        failed = {"verified": False, "delivery_state": "failed", "delivery_error": "File in use"}
        saved = {"verified": True, "delivery_state": "saved", "files": []}
        receipt = self.wait(_answers(state, failed, failed, saved))
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["status"], "completed")

    def test_a_short_jobs_outage_does_not_end_the_download(self):
        state = {"phase": "completed", "completed_at": 1, "verified_bytes": 9, "selected_bytes": 9}
        replies = iter([TorrentError("Cannot read the Jobs API."), TorrentError("Cannot read the Jobs API."),
                        (200, state), (200, {"verified": True, "files": []})])

        def reply(method, path, **_):
            item = next(replies)
            if isinstance(item, Exception):
                raise item
            return item
        self.assertTrue(self.wait(reply)["verified"])

    def test_an_expired_token_is_renewed(self):
        state = {"phase": "completed", "completed_at": 1, "verified_bytes": 9, "selected_bytes": 9}
        replies = iter([client.JobsHttpError(401, "Jobs HTTP 401."), (200, state),
                        (200, {"verified": True, "files": []})])

        def reply(method, path, **_):
            item = next(replies)
            if isinstance(item, Exception):
                raise item
            return item
        renew = MagicMock(return_value="test-only")
        self.assertTrue(self.wait(reply, renew=renew)["verified"])
        self.assertEqual(renew.call_count, 2)

    def test_a_long_outage_ends_the_wait_and_says_the_download_continues(self):
        clock = _Clock()

        def reply(method, path, **_):
            raise TorrentError("Cannot read the Jobs API.")
        with self.assertRaisesRegex(TorrentError, "continues in Jobs"):
            self.wait(reply, clock)
        self.assertGreaterEqual(clock.now, torrenter.API_OUTAGE_SECONDS)

    def test_a_refusal_is_not_treated_as_an_outage(self):
        calls = []

        def reply(method, path, **_):
            calls.append(path)
            raise client.JobsHttpError(404, "Jobs HTTP 404. Check the owned ID.")
        with self.assertRaisesRegex(TorrentError, "404"):
            self.wait(reply)
        self.assertEqual(len(calls), 1)

    def test_a_download_with_no_progress_stops_waiting_after_the_limit(self):
        clock = _Clock()
        state = {"phase": "waiting_for_peers", "desired_state": "running", "verified_bytes": 0,
                 "selected_bytes": 9, "download_rate_bps": 0}
        with self.assertRaisesRegex(TorrentError, "No download progress"):
            self.wait(_answers(state, {}), clock)
        self.assertGreaterEqual(clock.now, torrenter.STALL_SECONDS)


if __name__ == "__main__":
    unittest.main()
