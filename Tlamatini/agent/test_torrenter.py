# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .agents.torrenter.contract import FIELDS, TorrentError, route, validated
from .chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
from .chat_agent_runtime import get_chat_agent_run, list_chat_agent_runs
from .context_governor import bind_user, unbind_user
from .models import ChatAgentRun, TorrenterProfile
from .torrenter_bridge import canvas_config, protect_pool, stage_chat_magnets
from .torrenter_tool import build_tool

SPEC = next(s for s in WRAPPED_CHAT_AGENT_SPECS if s.key == "torrenter")
ID = "a" * 32


class ActionContractTests(SimpleTestCase):
    def test_closed_schema_and_service_authority(self):
        for action, args in [
            ("undelete", {}),
            ("stop", {"job_id": ID}),
            ("stop", {"job_id": "../x", "revision": 1}),
            ("delete_content", {"preview_id": ID, "revision": 1, "confirmed": True}),
            ("list", {"owner": "another"}),
            ("status", {"job_id": ID, "url": "https://example.org"}),
            ("inspect", {}),
            ("inspect", {"source_ref": ID, "info_hash": "a" * 40}),
            ("select", {"job_id": ID, "revision": True, "selected_file_ids": [0]}),
            ("list", {"search": "magnet:?private"}),
            ("set_web_seeds", {"job_id": ID, "revision": 1, "urls": []}),
        ]:
            with (
                self.subTest(action=action, args=args),
                self.assertRaises(TorrentError),
            ):
                validated(action, args)

    def test_explicit_selection_and_false_and_zero(self):
        args = dict(
            inspection_id=ID,
            metadata_revision=1,
            selected_file_ids=[0],
            priorities={"0": 4},
            destination_root_id="downloads",
            resume_on_boot=False,
            operation_key=ID,
        )
        parsed = validated("download", args)
        method, path, body = route("download", parsed)
        self.assertEqual((method, path), ("POST", "torrents"))
        self.assertNotIn("operation_key", body)
        self.assertIs(body["resume_on_boot"], False)
        self.assertEqual(body["selected_file_ids"], [0])
        cfg = canvas_config(
            {
                "action": "download",
                "arguments": json.dumps(args),
                "target_agents": ["ender_1"],
            }
        )
        self.assertEqual(json.loads(cfg["arguments"]), args)
        self.assertEqual(cfg["target_agents"], ["ender_1"])

    def test_writes_use_distinct_routes(self):
        for action, expected in (
            ("stop", ("POST", "torrents/" + ID + "/actions")),
            ("remove_job", ("DELETE", "torrents/" + ID)),
            ("delete_preview", ("POST", "content-deletion-previews")),
            ("delete_content", ("POST", "content-deletions")),
        ):
            args = {
                "preview_id" if action == "delete_content" else "job_id": ID,
                "revision": 2,
            }
            method, path, body = route(action, validated(action, args))
            self.assertEqual((method, path), expected)
            self.assertNotIn("revision", body or {})

    def test_typed_tool_refuses_unknown_input_before_launch(self):
        def unexpected(*a, **kw):
            self.fail("Refused input reached the launcher")

        wrapper = build_tool(SPEC, unexpected, json.dumps)
        for raw in (
            {"request": "stop everything"},
            {"action": "list", "permission": True},
            {"action": "list", "arguments": {"password": "secret"}},
        ):
            answer = json.loads(wrapper.invoke(raw))
            self.assertEqual(answer["status"], "refused")
            self.assertNotIn("secret", str(answer))

    def test_pool_binding_rejects_a_second_account(self):
        def account(pk):
            return SimpleNamespace(user=SimpleNamespace(pk=pk, is_authenticated=True))

        with tempfile.TemporaryDirectory() as d:
            protect_pool(account(5), d, claim=True)
            protect_pool(account(5), d)
            with self.assertRaises(PermissionDenied):
                protect_pool(account(6), d, claim=True)
            with self.assertRaises(PermissionDenied):
                protect_pool(account(6), d)

    def test_model_schema_lists_all_actions(self):
        from .torrenter_tool import TorrenterInput

        actions = TorrenterInput.model_json_schema()["properties"]["action"]["enum"]
        self.assertEqual(set(actions), set(FIELDS))

    def test_exec_report_and_gate(self):
        from .mcp_agent import _ASK_EXECS_REQUIRED_TOOLS, _resolve_exec_report_spec
        from .tools import tool_gate_table

        self.assertIn(SPEC.tool_name, _ASK_EXECS_REQUIRED_TOOLS)
        self.assertEqual(
            _resolve_exec_report_spec(SPEC.tool_name), ("torrenter", "Torrenter")
        )
        self.assertIn(
            ("chat-agent-torrenter", "Torrenter"),
            [(t, a) for t, a, _ in tool_gate_table()],
        )


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("torrenter-a")
        cls.bob = get_user_model().objects.create_user("torrenter-b")
        cls.profile = TorrenterProfile.objects.create(user=cls.alice)
        ChatAgentRun.objects.create(
            runId=ID,
            owner=cls.alice,
            templateAgentDir="torrenter",
            toolDescription=SPEC.tool_description,
            status="completed",
        )

    def test_cross_account_run_id_prefix_list_and_absent_identity(self):
        for identity in (self.bob.pk, None, self.alice.pk):
            token = bind_user(identity)
            try:
                visible = identity == self.alice.pk
                self.assertEqual(bool(get_chat_agent_run(ID)), visible)
                self.assertEqual(bool(get_chat_agent_run(ID[:8])), visible)
                self.assertEqual(
                    any(r.pk == ID for r in list_chat_agent_runs()), visible
                )
            finally:
                unbind_user(token)

    def test_login_selects_a_stable_private_queue(self):
        url = reverse("torrenter_workspace") + "session/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.bob)
        first = self.client.get(url).json()
        self.assertEqual(first["username"], self.bob.username)
        self.assertEqual(first["profile"], self.client.get(url).json()["profile"])
        self.assertNotEqual(first["profile"], str(self.profile.account))
        self.assertNotIn("access_token", first)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_workspace_rejects_cross_account_writes_and_minting_routes(self):
        url = reverse("torrenter_workspace") + "api/v1/"
        self.client.force_login(self.bob)
        stale = self.client.post(url + "torrents", {}, content_type="application/json",
                                 HTTP_X_TORRENTER_PROFILE=str(self.profile.account))
        self.assertEqual(stale.status_code, 403)
        self.assertEqual(stale.json()["code"], "account_changed")
        mine = self.client.get(reverse("torrenter_workspace") + "session/").json()["profile"]
        self.assertEqual(self.client.post(url + "sessions", {}, content_type="application/json",
                                          HTTP_X_TORRENTER_PROFILE=mine).status_code, 404)
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.bob)
        self.assertEqual(strict.post(url + "torrents", {}, content_type="application/json",
                                     HTTP_X_TORRENTER_PROFILE=mine).status_code, 403)

    def test_chat_replaces_private_magnet_before_history(self):
        magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&tr=private_token"
        with patch("agent.agents.torrenter.sources.stage", return_value=ID) as store:
            msg = stage_chat_magnets(self.alice.pk, "Inspect " + magnet)
        store.assert_called_once_with(str(self.profile.account), "magnet", magnet)
        self.assertIn(ID, msg)
        self.assertNotIn("private_token", msg)

    def test_search_handoff_preserves_the_complete_magnet_for_both_mcp_routes(self):
        from .torrenter_bridge import stage_search_magnet

        magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&tr=https%3A%2F%2Ftracker.example%2Fprivate_token"
        formatted = magnet + "\n\nstructuredContent:\n" + json.dumps(magnet)
        for supervisor in (False, True):
            raw = json.dumps({"ok": True, "result": formatted}) if supervisor else formatted
            with self.subTest(supervisor=supervisor), patch("agent.agents.torrenter.sources.stage", return_value=ID) as store:
                answer = stage_search_magnet(self.alice.pk, raw, supervisor=supervisor)
                store.assert_called_once_with(str(self.profile.account), "magnet", magnet)
                self.assertEqual(json.loads(answer)["torrenter_request"], {"action": "inspect", "arguments": {"source_ref": ID}})
                self.assertNotIn("private_token", answer)
        self.assertEqual(stage_search_magnet(None, "file.torrent"), "file.torrent")
        with self.assertRaises(TorrentError):
            stage_search_magnet(None, magnet)

    def test_source_forms_escape_names_and_keep_input_out_of_response(self):
        self.client.force_login(self.alice)
        with (
            patch("agent.torrenter_views.client.session", return_value="local-token"),
            patch(
                "agent.torrenter_views.client.request",
                return_value=(
                    201,
                    dict(
                        inspection_id=ID,
                        phase="ready",
                        metadata_revision=1,
                        name="<script>unsafe</script>",
                        files=[{"id": 0, "path": "example", "size": 8}],
                    ),
                ),
            ) as api,
        ):
            res = self.client.post(
                reverse("torrenter_sources"), {"magnet": "magnet:?private"}
            )
        api.assert_called_once()
        self.assertContains(res, ID)
        self.assertContains(res, "&lt;script&gt;")
        self.assertNotContains(res, "magnet:?private")
        self.assertNotContains(res, "local-token")


class RecoveryTests(SimpleTestCase):
    def test_workspace_uses_this_editions_files_without_jobs_installation(self):
        from django.test import override_settings
        from . import torrenter_views
        with override_settings(DEBUG=False), patch.object(
            torrenter_views.client, "known_folder", side_effect=AssertionError("External install lookup")
        ):
            for name in torrenter_views._ASSETS:
                response = torrenter_views._asset(name)
                self.assertEqual(response.status_code, 200, name)
                self.assertGreater(len(response.content), 100)
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_log_survives_pool_removal_and_is_private_to_its_owner(self):
        from pathlib import Path
        import uuid
        from .agents.torrenter.activity import ActivityLog, latest_record
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root)
            pool = parent / "disposable-canvas"
            node = pool / "torrenter_1"
            node.mkdir(parents=True)
            owner, other = str(uuid.uuid4()), str(uuid.uuid4())
            with patch("agent.agents.torrenter.client.known_folder", return_value=parent):
                report = ActivityLog(node, "manifest", False, owner)
                report.write("fixture.pdf")
                node.rmdir()
                pool.rmdir()
                self.assertEqual(latest_record(owner, pool, node.name), report.path)
                self.assertIn("fixture.pdf", report.path.read_text(encoding="utf-8"))
                self.assertIsNone(latest_record(other, pool, node.name))

    def test_missing_activity_route_still_shows_file_hash_and_connected_seeds(self):
        from pathlib import Path
        from .agents.torrenter import torrenter as worker
        item = {"id":0, "size":9, "path":"a real book.pdf", "sha256":"8" * 64}
        manifest = {"output_root":"C:/books", "verified":True, "files":[item]}
        def legacy(method, path, *, bearer):
            if path.endswith("/activity"):
                raise TorrentError("Unknown detail resource.")
            if path.endswith("/files"):
                return 200, {"items":[dict(item, selected=True)]}
            if path.endswith(ID):
                return 200, {"name":"book", "seeds":7, "peers":12, "known_seeds":None}
            return 200, {"items":[]}
        with tempfile.TemporaryDirectory() as folder:
            audit = worker.ActivityLog(Path(folder), "manifest", False)
            with patch.object(worker, "session", return_value="local"), patch.object(worker, "request", side_effect=legacy):
                worker.describe_assets("profile", "torrents/" + ID, audit, manifest)
            report = audit.path.read_text(encoding="utf-8")
            for expected in ("a real book.pdf", item["sha256"], ": 7\n", ": 12\n"):
                self.assertIn(expected, report)

    def test_download_wait_finishes_only_at_verified_publication(self):
        from .agents.torrenter import torrenter as worker
        state = {"phase":"completed", "completed_at":1, "verified_bytes":32, "selected_bytes":32}
        manifest = {"verified":True, "output_root":"C:/downloads", "files":[]}
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path
            audit = worker.ActivityLog(Path(d), "download", True)
            receipt = {"job_id": ID, "response_body":{"operation_id": ID}}
            with (patch.object(worker, "session", return_value="local"),
                  patch.object(worker, "request", side_effect=[(200,state),(200,{"verified":False}),(200,state),(200,manifest)]),
                  patch.object(worker.time, "sleep") as delay):
                worker.wait_for_publication("profile", receipt, audit)
                self.assertTrue(receipt["verified"])
                self.assertEqual(receipt["status"], "completed")
                delay.assert_called_once()
            with (patch.object(worker, "session", return_value="local"),
                  patch.object(worker, "request", return_value=(200,{"phase":"cancelled"})), self.assertRaises(TorrentError)):
                worker.wait_for_publication("profile", receipt, audit)

    def test_wait_is_an_explicit_boolean_and_old_config_defaults_to_no(self):
        self.assertIs(canvas_config({"action":"list"})["wait_for_completion"], False)
        self.assertIs(canvas_config({"action":"list", "wait_for_completion":True})["wait_for_completion"], True)
        with self.assertRaises(TorrentError):
            canvas_config({"action":"list", "wait_for_completion":"no"})

    def test_boundary_piece_bytes_only_become_selected_bytes_after_publication(self):
        from .agents.torrenter.torrenter import report_selected_bytes

        for completed, expected in ((None, None), ("2026-10-31T00:00:00Z", 1514)):
            row = {
                "selected_bytes": 1514,
                "verified_bytes": 131072,
                "completed_at": completed,
            }
            report_selected_bytes(row)
            self.assertEqual(row["verified_bytes"], expected)
            self.assertEqual(row["engine_verified_bytes"], 131072)

    def test_reanimation_reattaches_instead_of_repeating_an_accepted_mutation(self):
        import os
        from pathlib import Path
        from .agents.torrenter import torrenter as worker

        fields = {"job_id": ID, "revision": 1}
        response = {"operation_id": "b" * 32, "job_id": ID, "phase": "accepted"}
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(worker, "HERE", Path(d)),
            patch.object(worker, "installation", return_value="test-installation"),
            patch.object(worker, "session", return_value="test-session"),
            patch.object(worker, "request") as api,
        ):
            api.return_value = (202, response)
            first = worker.execute("stop", fields, "test-profile")
            api.return_value = (200, dict(response, phase="succeeded"))
            with patch.dict(os.environ, {"AGENT_REANIMATED": "1"}):
                later = worker.execute("stop", fields, "test-profile")
                with self.assertRaises(TorrentError):
                    worker.execute("pause", fields, "test-profile")
            self.assertEqual(api.call_count, 2)
            self.assertEqual(
                api.call_args.args[:2],
                ("GET", "operations/" + response["operation_id"]),
            )
            self.assertEqual(later["operation_key"], first["operation_key"])
            self.assertEqual(later["phase"], "succeeded")
