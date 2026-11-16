# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Native dispatch and consent lifecycle checks with isolated OS/runtime fakes.

Run visibly with the repository's isolated Django test settings. These checks
never invoke a service helper, start Tlamatini, or acquire a real Windows mutex.
"""

import asyncio
from datetime import datetime, timezone
import json
import sys
import threading
import uuid
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from . import remote_controller_bridge as bridge


def profile(*, key=1, enabled=True, active=True, account="2", adapter="3", binding="4"):
    return SimpleNamespace(
        pk=key, user_id=key, enabled=enabled, account=uuid.UUID(hex=account * 32),
        adapter=uuid.UUID(hex=adapter * 32), binding_id=binding * 32,
        user=SimpleNamespace(pk=key, is_active=active, get_username=lambda: "Account one"),
    )


def operation(kind="conversation.submit", **payload):
    return {"id": "5" * 32, "binding_id": "4" * 32,
            "kind": kind, "payload": payload or {"text": "A harmless question"}}


class RetryDelayTests(TestCase):
    def test_backoff_saturates_during_extended_outages(self):
        for failures, expected in [(0, 2), (1, 2), (2, 4), (3, 8), (4, 15),
                                   (1023, 15), (1024, 15), (1000000, 15)]:
            with self.subTest(failures=failures):
                self.assertEqual(bridge._retry_delay(failures), expected)


class ExtendedOutagePollingTests(IsolatedAsyncioTestCase):
    async def test_failed_poll_after_long_outage_keeps_cancellation_and_backoff(self):
        worker = SimpleNamespace(retiring=False, cancel=threading.Event(),
                                 poll_failures=1023, next_poll_at=0,
                                 tick=AsyncMock(side_effect=RuntimeError("offline")))
        with patch.object(bridge, "_now", return_value=100):
            await bridge._poll(worker, asyncio.Semaphore(1))
        self.assertTrue(worker.cancel.is_set())
        self.assertEqual(worker.poll_failures, 1024)
        self.assertEqual(worker.next_poll_at, 115)


class NativeBoundaryTests(TestCase):
    def setUp(self):
        self.binary = MagicMock()
        self.binary.is_file.return_value = True
        self.binary.resolve.return_value = self.binary
        self.binary.__str__.return_value = "C:\\Program Files\\XAIHT\\Tlachihuani\\RCServer\\Tlachihuani.RC.Server.exe"
        root = MagicMock()
        root.__truediv__.return_value = self.binary
        shell_module = SimpleNamespace(shell=SimpleNamespace(SHGetFolderPath=Mock(return_value="C:\\Program Files")))
        self.completed = SimpleNamespace(stdout='{"health":"ready"}', returncode=0)
        self.patches = [
            patch.object(bridge.os, "name", "nt"),
            patch.object(bridge, "Path", return_value=root),
            patch.dict(sys.modules, {"win32com.shell": shell_module}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.run_patch = patch.object(bridge.subprocess, "run", return_value=self.completed)
        self.run = self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

    def test_request_fields_never_change_fixed_executable_or_arguments(self):
        requested = {"op": "status", "executable": "untrusted.exe", "arguments": "--arbitrary"}
        bridge.native(requested)
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], [str(self.binary), "--control"])
        self.assertEqual(json.loads(kwargs["input"]), requested)
        self.assertNotIn("shell", kwargs)
        self.assertGreater(kwargs["timeout"], 0)

    def test_non_windows_refuses_before_helper_invocation(self):
        with patch.object(bridge.os, "name", "posix"):
            with self.assertRaises(bridge.RcBridgeError) as error:
                bridge.native({"op": "status"})
        self.assertEqual(error.exception.code, "windows_required")
        self.run.assert_not_called()

    def test_missing_installed_helper_does_not_fall_back_to_path(self):
        self.binary.is_file.return_value = False
        with self.assertRaises(bridge.RcBridgeError):
            bridge.native({"op": "status"})
        self.run.assert_not_called()

    def test_redirected_installed_helper_is_refused(self):
        self.binary.resolve.return_value = object()
        with self.assertRaises(bridge.RcBridgeError):
            bridge.native({"op": "status"})
        self.run.assert_not_called()

    def test_oversized_request_is_refused_before_spawn(self):
        with self.assertRaises(bridge.RcBridgeError) as error:
            bridge.native({"op": "status", "extra": "x" * 65536})
        self.assertEqual(error.exception.code, "request_too_large")
        self.run.assert_not_called()

    def test_oversized_response_is_not_accepted(self):
        self.completed.stdout = json.dumps({"extra": "x" * 65536})
        with self.assertRaises(bridge.RcBridgeError):
            bridge.native({"op": "status"})

    def test_invalid_json_becomes_service_error(self):
        self.completed.stdout = "not json"
        with self.assertRaises(bridge.RcBridgeError) as error:
            bridge.native({"op": "status"})
        self.assertEqual(error.exception.code, "service_unavailable")

    def test_response_array_is_refused(self):
        self.completed.stdout = "[]"
        with self.assertRaises(bridge.RcBridgeError):
            bridge.native({"op": "status"})

    def test_error_string_is_a_malformed_response_not_an_attribute_error(self):
        self.completed.stdout = '{"error":"untrusted error"}'
        with self.assertRaises(bridge.RcBridgeError) as error:
            bridge.native({"op": "status"})
        self.assertEqual(error.exception.code, "service_unavailable")

    def test_incomplete_error_object_is_refused(self):
        self.completed.stdout = '{"error":{"code":"forbidden"}}'
        with self.assertRaises(bridge.RcBridgeError) as error:
            bridge.native({"op": "status"})
        self.assertEqual(error.exception.code, "service_unavailable")

    def test_native_authorization_error_preserves_typed_code(self):
        self.completed.stdout = '{"error":{"code":"forbidden","message":"No authority"}}'
        with self.assertRaises(bridge.RcBridgeError) as error:
            bridge.native({"op": "status"})
        self.assertEqual(error.exception.code, "forbidden")

    def test_nonzero_helper_exit_never_claims_success(self):
        self.completed.returncode = 1
        with self.assertRaises(bridge.RcBridgeError):
            bridge.native({"op": "status"})

    def test_helper_timeout_has_bounded_failure(self):
        self.run.side_effect = bridge.subprocess.TimeoutExpired("fixed helper", 12)
        with self.assertRaises(bridge.RcBridgeError) as error:
            bridge.native({"op": "status"})
        self.assertEqual(error.exception.code, "service_unavailable")

    def test_native_os_failure_does_not_try_alternate_executable(self):
        self.run.side_effect = OSError("isolated fixture")
        with self.assertRaises(bridge.RcBridgeError):
            bridge.native({"op": "status"})
        self.run.assert_called_once()


class BindingBoundaryTests(TestCase):
    def test_binding_comes_from_authenticated_profile_identities(self):
        account = profile()
        with patch.object(bridge, "native", return_value={"id": "4" * 32}) as native:
            bridge.bind_profile(account)
        request = native.call_args.args[0]
        self.assertEqual(request["edition"], bridge.EDITION)
        self.assertEqual(request["account_id"], account.account.hex)
        self.assertEqual(request["adapter_id"], account.adapter.hex)
        self.assertEqual(request["display_name"], "Account one")
        self.assertEqual(request["op"], "bind-account")

    def test_unbind_names_only_own_binding_and_adapter(self):
        account = profile()
        with patch.object(bridge, "native", return_value={}) as native:
            bridge.unbind_profile(account)
        self.assertEqual(native.call_args.args[0], {
            "op": "unbind-account", "binding_id": account.binding_id,
            "adapter_id": account.adapter.hex,
        })

    def test_absent_binding_disable_is_idempotent_without_native_call(self):
        account = profile(binding="")
        with patch.object(bridge, "native") as native:
            self.assertEqual(bridge.unbind_profile(account), {"disabled": True})
        native.assert_not_called()

    def test_status_does_not_start_service(self):
        with patch.object(bridge, "native", return_value={"health": "ready"}) as native:
            self.assertEqual(bridge.service_status(), {"health": "ready"})
        native.assert_called_once_with({"op": "status"})

    def test_queued_revocation_cannot_override_fresh_enable(self):
        current = profile(enabled=True)
        with patch.object(bridge, "_revocation_profile", return_value=current), \
                patch.object(bridge, "unbind_profile") as unbind:
            bridge._retry_revocation(profile(enabled=False))
        unbind.assert_not_called()

    def test_replaced_profile_revokes_only_its_known_old_binding(self):
        old = profile(enabled=False)
        with patch.object(bridge, "_revocation_profile", return_value=None), \
                patch.object(bridge, "unbind_profile") as unbind:
            bridge._retry_revocation(old)
        unbind.assert_called_once_with(old)

    def test_disabled_consent_retries_revocation_and_clears_only_its_binding(self):
        current = profile(enabled=False)
        with patch.object(bridge, "_revocation_profile", return_value=current), \
                patch.object(bridge, "unbind_profile") as unbind, \
                patch.object(bridge, "_clear_binding") as clear:
            bridge._retry_revocation(current)
        unbind.assert_called_once_with(current)
        clear.assert_called_once_with(current)

    def test_inactive_account_revocation_clears_its_binding(self):
        current = profile(enabled=True, active=False)
        with patch.object(bridge, "_revocation_profile", return_value=current), \
                patch.object(bridge, "unbind_profile") as unbind, \
                patch.object(bridge, "_clear_binding") as clear:
            bridge._retry_revocation(current)
        unbind.assert_called_once_with(current)
        clear.assert_called_once_with(current)

    def test_binding_the_service_already_dropped_is_cleared(self):
        current = profile(enabled=False)
        gone = bridge.RcBridgeError("not_found", "fixture")
        with patch.object(bridge, "_revocation_profile", return_value=current), \
                patch.object(bridge, "unbind_profile", side_effect=gone), \
                patch.object(bridge, "_clear_binding") as clear:
            bridge._retry_revocation(current)
        clear.assert_called_once_with(current)

    def test_unreachable_service_keeps_the_binding_for_a_later_retry(self):
        current = profile(enabled=False)
        down = bridge.RcBridgeError("service_unavailable", "fixture")
        with patch.object(bridge, "_revocation_profile", return_value=current), \
                patch.object(bridge, "unbind_profile", side_effect=down), \
                patch.object(bridge, "_clear_binding") as clear:
            with self.assertRaises(bridge.RcBridgeError):
                bridge._retry_revocation(current)
        clear.assert_not_called()

    def test_clear_binding_touches_only_an_unconsented_exact_binding(self):
        from django.db.models import Q
        from . import models
        manager = Mock()
        account = profile(enabled=False)
        with patch.object(models.RemoteControllerProfile, "objects", manager):
            bridge._clear_binding(account)
        manager.filter.assert_called_once_with(
            Q(enabled=False) | Q(user__is_active=False),
            pk=account.pk, binding_id=account.binding_id,
        )
        manager.filter.return_value.update.assert_called_once_with(binding_id="", enabled=False)

    def test_ready_once_the_application_has_loaded(self):
        from django.apps import apps
        account = profile()
        with patch("agent.global_state.global_state.get_state", return_value=None):
            self.assertTrue(bridge._ready(account))
            with patch.object(apps, "ready", False):
                self.assertFalse(bridge._ready(account))
        with patch("agent.global_state.global_state.get_state", return_value=object()), \
                patch.object(apps, "ready", False):
            self.assertTrue(bridge._ready(account))


class AdapterLeaseTests(TestCase):
    def setUp(self):
        self.api = SimpleNamespace(CloseHandle=Mock())
        self.event = SimpleNamespace(CreateMutex=Mock(side_effect=lambda *_: object()),
                                     WaitForSingleObject=Mock(return_value=0), ReleaseMutex=Mock())
        self.patches = [patch.object(bridge.os, "name", "nt"),
                        patch.dict(sys.modules, {"win32api": self.api, "win32event": self.event}),
                        patch.object(bridge, "_leases", set())]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_same_adapter_cannot_dispatch_twice_on_same_loop_thread(self):
        first, second = bridge._AdapterLease("3" * 32), bridge._AdapterLease("3" * 32)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.close()
        self.assertTrue(second.acquire())
        second.close()

    def test_different_accounts_have_independent_leases(self):
        first, second = bridge._AdapterLease("3" * 32), bridge._AdapterLease("6" * 32)
        self.assertTrue(first.acquire())
        self.assertTrue(second.acquire())
        first.close()
        second.close()

    def test_another_process_ownership_refuses_without_waiting(self):
        self.event.WaitForSingleObject.return_value = 258  # WAIT_TIMEOUT
        lease = bridge._AdapterLease("3" * 32)
        self.assertFalse(lease.acquire())
        self.assertEqual(self.event.WaitForSingleObject.call_args.args[1], 0)
        self.assertIsNone(lease.handle)
        self.api.CloseHandle.assert_called_once()

    def test_terminated_owner_can_be_recovered_without_stealing_live_ownership(self):
        self.event.WaitForSingleObject.return_value = 128  # WAIT_ABANDONED
        lease = bridge._AdapterLease("3" * 32)
        self.assertTrue(lease.acquire())
        lease.close()

    def test_access_denied_never_grants_lease(self):
        self.event.CreateMutex.side_effect = OSError("access denied")
        lease = bridge._AdapterLease("3" * 32)
        with self.assertRaises(bridge.RcBridgeError):
            lease.acquire()
        self.assertIsNone(lease.handle)
        self.assertNotIn(lease.name, bridge._leases)

    def test_double_close_is_safe(self):
        lease = bridge._AdapterLease("3" * 32)
        lease.acquire()
        lease.close()
        lease.close()
        self.event.ReleaseMutex.assert_called_once()

    def test_wrong_thread_cannot_release_ownership(self):
        lease = bridge._AdapterLease("3" * 32)
        lease.acquire()
        with patch.object(bridge.threading, "get_ident", return_value=-1):
            with self.assertRaises(RuntimeError):
                lease.close()
        self.event.ReleaseMutex.assert_not_called()
        lease.close()


class AccountDispatchTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.worker = bridge.AccountWorker(profile())
        self.worker.lease = Mock()
        self.worker.call = AsyncMock()
        self.ready_patch = patch.object(bridge, "_ready", return_value=True)
        self.ready = self.ready_patch.start()
        self.addCleanup(self.ready_patch.stop)
        self.session = SimpleNamespace(run=AsyncMock(return_value={"text": "Real fixture answer"}),
                                       respond_permission=AsyncMock(return_value=True), request_cancel=Mock())
        self.factory = Mock(return_value=self.session)
        self.runtime_patch = patch.dict(sys.modules, {
            "agent.remote_controller_runtime": SimpleNamespace(RuntimeSession=self.factory, execution_capabilities=lambda: {}),
        })
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def reply(self, item=None, *, authorized=True):
        self.worker.call.side_effect = [
            {"active_authorized": authorized}, {"operation": item},
        ]

    async def test_cross_account_operation_never_reaches_chat(self):
        item = operation()
        item["binding_id"] = "6" * 32
        self.reply(item)
        with self.assertRaises(bridge.RcBridgeError) as error:
            await self.worker.tick()
        self.assertEqual(error.exception.code, "binding_mismatch")
        self.factory.assert_not_called()
        self.assertTrue(self.worker.cancel.is_set())

    async def test_operation_without_binding_is_refused(self):
        item = operation()
        del item["binding_id"]
        self.reply(item)
        with self.assertRaises(bridge.RcBridgeError):
            await self.worker.tick()
        self.factory.assert_not_called()

    async def test_invalid_operation_identity_never_reaches_chat(self):
        item = operation()
        item["id"] = "invalid"
        self.reply(item)
        with self.assertRaises(bridge.RcBridgeError) as error:
            await self.worker.tick()
        self.assertEqual(error.exception.code, "invalid_operation")
        self.factory.assert_not_called()

    async def test_chat_uses_only_current_profile_user_and_approved_text(self):
        self.reply(operation(text="My request"))
        await self.worker.tick()
        await self.worker.task
        self.factory.assert_called_once_with(self.worker.profile.user, self.worker.progress)
        self.session.run.assert_awaited_once_with("My request", self.worker.cancel)
        self.assertEqual(self.worker.outbox[0]["result"], {"text": "Real fixture answer"})
        self.assertIsNone(self.worker.active)

    async def test_duplicate_submit_cannot_replace_running_conversation(self):
        self.worker.active = operation()
        existing = self.worker.active
        item = operation(text="Second request")
        item["id"] = "6" * 32
        self.reply(item)
        await self.worker.tick()
        self.assertIs(self.worker.active, existing)
        self.assertEqual(self.worker.outbox[0]["error"], "account_busy")
        self.factory.assert_not_called()

    async def test_loading_status_does_not_claim_ready(self):
        self.ready.return_value = False
        self.reply(operation("application.status"))
        await self.worker.tick()
        self.assertEqual(self.worker.outbox[0]["result"], {
            "state": "loading", "ready": False, "edition": bridge.EDITION,
        })

    async def test_application_start_is_never_executed_by_account_adapter(self):
        self.reply(operation("application.start"))
        await self.worker.tick()
        self.assertEqual(self.worker.outbox[0]["error"], "unsupported_operation")
        self.factory.assert_not_called()

    async def test_history_reads_only_current_profile(self):
        self.reply(operation("conversation.history"))
        with patch.object(bridge, "_history", return_value={"messages": [], "truncated": False}) as history:
            await self.worker.tick()
        history.assert_called_once_with(self.worker.profile)
        self.assertEqual(self.worker.outbox[0]["result"], {"messages": [], "truncated": False})

    async def test_history_from_another_binding_never_reaches_database(self):
        item = operation("conversation.history")
        item["binding_id"] = "6" * 32
        self.reply(item)
        with patch.object(bridge, "_history") as history:
            with self.assertRaises(bridge.RcBridgeError):
                await self.worker.tick()
        history.assert_not_called()

    async def test_revoked_history_is_a_failed_receipt(self):
        self.reply(operation("conversation.history"))
        with patch.object(bridge, "_history", side_effect=bridge.RcBridgeError("account_unavailable", "fixture")):
            await self.worker.tick()
        self.assertEqual(self.worker.outbox[0]["error"], "account_unavailable")

    async def test_history_storage_failure_is_reported_as_failed_receipt(self):
        self.reply(operation("conversation.history"))
        with patch.object(bridge, "_history", side_effect=RuntimeError("fixture database failure")):
            await self.worker.tick()
        self.assertEqual(self.worker.outbox[0]["error"], "history_unavailable")
        self.assertIsNone(self.worker.outbox[0]["result"])

    async def test_lost_consent_refuses_new_poll(self):
        self.worker.consent_observed = False
        await self.worker.tick()
        self.worker.call.assert_not_awaited()

    async def test_pending_dispatch_cannot_reset_cancellation_after_consent_lookup_fails(self):
        entered = asyncio.Event()
        released = asyncio.Event()
        async def native_call(op, **_fields):
            if op == "adapter-heartbeat":
                return {"active_authorized": True}
            if op == "adapter-next":
                entered.set()
                await released.wait()
                return {"operation": operation()}
            return {}
        self.worker.call.side_effect = native_call
        polling = asyncio.create_task(self.worker.tick())
        await entered.wait()
        self.worker.consent_observed = False
        self.worker.cancel.set()
        released.set()
        await polling
        self.factory.assert_not_called()
        self.assertTrue(self.worker.cancel.is_set())
        self.assertIsNone(self.worker.active)
        self.assertEqual(self.worker.outbox[0]["error"], "account_unavailable")

    async def test_owned_cancel_requests_normal_runtime_cancellation(self):
        self.worker.active = operation()
        self.reply(operation("conversation.cancel", operation_id=self.worker.active["id"]))
        await self.worker.tick()
        self.assertTrue(self.worker.cancel.is_set())
        self.assertEqual(self.worker.outbox[0]["result"], {"cancellation_requested": True})

    async def test_cancel_cannot_name_another_operation(self):
        self.worker.active = operation()
        self.reply(operation("conversation.cancel", operation_id="6" * 32))
        await self.worker.tick()
        self.assertFalse(self.worker.cancel.is_set())
        self.assertEqual(self.worker.outbox[0]["error"], "operation_not_active")

    async def test_permission_targets_only_current_runtime_session(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.reply(operation("conversation.permission", operation_id=self.worker.active["id"],
                             request_id="7" * 32, decision="proceed"))
        await self.worker.tick()
        self.session.respond_permission.assert_awaited_once_with("7" * 32, "proceed")
        self.assertEqual(self.worker.outbox[0]["result"], {"resolved": True})

    async def test_permission_for_another_operation_cannot_resolve_broker(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.reply(operation("conversation.permission", operation_id="6" * 32,
                             request_id="7" * 32, decision="proceed"))
        await self.worker.tick()
        self.session.respond_permission.assert_not_awaited()
        self.assertEqual(self.worker.outbox[0]["error"], "operation_not_active")

    async def test_expired_permission_is_not_reported_as_approved(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.session.respond_permission.return_value = False
        self.reply(operation("conversation.permission", operation_id=self.worker.active["id"],
                             request_id="7" * 32, decision="proceed"))
        await self.worker.tick()
        self.assertEqual(self.worker.outbox[0]["error"], "permission_expired")
        self.assertIsNone(self.worker.outbox[0]["result"])

    async def test_revoked_conversation_cannot_approve_an_execution(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.reply(operation("conversation.permission", operation_id=self.worker.active["id"],
                             request_id="7" * 32, decision="proceed"), authorized=False)
        await self.worker.tick()
        self.session.respond_permission.assert_not_awaited()
        self.assertEqual(self.worker.outbox[0]["error"], "authorization_changed")

    async def test_permission_before_runtime_exists_is_expired(self):
        self.worker.active = operation()
        self.reply(operation("conversation.permission", operation_id=self.worker.active["id"],
                             request_id="7" * 32, decision="proceed"))
        await self.worker.tick()
        self.assertEqual(self.worker.outbox[0]["error"], "permission_expired")

    async def test_heartbeat_revocation_requests_cancellation(self):
        self.worker.active = operation()
        self.reply(authorized=False)
        await self.worker.tick()
        self.assertTrue(self.worker.cancel.is_set())

    async def test_progress_transport_loss_ends_execution_consent(self):
        self.worker.active = operation()
        self.worker.call.side_effect = bridge.RcBridgeError("service_unavailable", "fixture")
        with self.assertRaises(bridge.RcBridgeError):
            await self.worker.progress({"type": "message", "text": "working"})
        self.assertTrue(self.worker.cancel.is_set())

    async def test_cancelled_progress_closes_owned_runtime_without_native_emission(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.worker.cancel.set()
        await self.worker.progress({"type": "permission", "request_id": "7" * 32})
        self.session.request_cancel.assert_called_once_with()
        self.worker.call.assert_not_awaited()

    async def test_cancelled_progress_before_runtime_exists_is_suppressed(self):
        self.worker.active = operation()
        self.worker.cancel.set()
        await self.worker.progress({"type": "status", "status": "ready"})
        self.worker.call.assert_not_awaited()

    async def test_retirement_is_not_hidden_by_expected_cancellation(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.worker.cancel.set()
        self.worker.retiring = True
        with self.assertRaises(bridge.RcBridgeError) as error:
            await self.worker.progress({"type": "message", "text": "late"})
        self.assertEqual(error.exception.code, "authorization_changed")
        self.worker.call.assert_not_awaited()

    async def test_consent_loss_is_not_hidden_by_expected_cancellation(self):
        self.worker.active = operation()
        self.worker.session = self.session
        self.worker.cancel.set()
        self.worker.consent_observed = False
        with self.assertRaises(bridge.RcBridgeError) as error:
            await self.worker.progress({"type": "message", "text": "late"})
        self.assertEqual(error.exception.code, "authorization_changed")
        self.worker.call.assert_not_awaited()

    async def test_orphan_progress_is_not_sent_as_another_conversation(self):
        await self.worker.progress({"type": "message", "text": "late"})
        self.worker.call.assert_not_awaited()

    async def test_completion_is_retained_across_service_outage(self):
        await self.worker.finish(operation(), result={"text": "answer"})
        self.worker.call.side_effect = bridge.RcBridgeError("service_unavailable", "fixture")
        with self.assertRaises(bridge.RcBridgeError):
            await self.worker.tick()
        self.assertEqual(len(self.worker.outbox), 1)

    async def test_already_finalized_completion_is_not_replayed_forever(self):
        await self.worker.finish(operation(), result={"text": "answer"})
        self.worker.call.side_effect = [bridge.RcBridgeError("operation_conflict", "fixture"),
                                       {"active_authorized": True}, {"operation": None}]
        await self.worker.tick()
        self.assertEqual(self.worker.outbox, [])

    async def test_runtime_failure_is_a_failed_receipt_not_fabricated_answer(self):
        self.session.run.side_effect = RuntimeError("fixture failure")
        self.reply(operation())
        await self.worker.tick()
        await self.worker.task
        self.assertEqual(self.worker.outbox[0]["error"], "conversation_failed")
        self.assertIsNone(self.worker.outbox[0]["result"])

    async def test_retirement_holds_lease_until_chat_actually_finishes(self):
        done = asyncio.Event()
        self.worker.task = asyncio.create_task(done.wait())
        closing = asyncio.create_task(self.worker.close())
        await asyncio.sleep(0)
        self.assertTrue(self.worker.cancel.is_set())
        self.worker.lease.close.assert_not_called()
        done.set()
        await closing
        self.worker.lease.close.assert_called_once()

    async def test_cancelled_cleanup_still_holds_lease_until_chat_finishes(self):
        done = asyncio.Event()
        self.worker.task = asyncio.create_task(done.wait())
        closing = asyncio.create_task(self.worker.close())
        await asyncio.sleep(0)
        closing.cancel()
        await asyncio.gather(closing, return_exceptions=True)
        self.worker.lease.close.assert_not_called()
        done.set()
        await self.worker.task
        await asyncio.sleep(0)
        self.worker.lease.close.assert_called_once()


class WorkerLifecycleTests(IsolatedAsyncioTestCase):
    async def run_loop(self, snapshots, *, lease_available=True, on_tick=None, close_gate=None,
                       tombstones=(), revocation_failures=0, clock_step=1000.0):
        workers = []
        stop = threading.Event()
        observed = iter(snapshots)
        current_profiles = []
        durable = {bridge._identity(item): item for item in tombstones}
        real_sleep = asyncio.sleep
        turns = 0
        # A fake clock. By default each supervisor turn is longer than any poll
        # interval or retry delay, so a test sees one attempt per turn.
        clock = [0.0]

        def profiles():
            nonlocal current_profiles
            value = next(observed)
            if isinstance(value, Exception):
                raise value
            current_profiles = value
            return value

        def make_worker(value):
            worker = SimpleNamespace(profile=value, cancel=asyncio.Event(),
                                     lease=SimpleNamespace(acquire=Mock(return_value=lease_available)),
                                     poll_task=None, retiring=False, start_watchdog=Mock(),
                                     consent_observed=True)
            async def tick():
                if on_tick:
                    await on_tick(worker, workers)
            async def close():
                worker.retiring = True
                worker.cancel.set()
                if close_gate is not None and worker is workers[0]:
                    await close_gate.wait()
            worker.tick = AsyncMock(side_effect=tick)
            worker.close = AsyncMock(side_effect=close)
            workers.append(worker)
            return worker

        async def sleep(_seconds):
            nonlocal turns
            # Let the supervisor's task, bounded transport and completion
            # callbacks settle without spending a real second in each test.
            for _ in range(6):
                await real_sleep(0)
            turns += 1
            clock[0] += clock_step
            if turns >= len(snapshots):
                if close_gate is not None:
                    close_gate.set()
                stop.set()

        def revoke(value):
            current = next((item for item in current_profiles if item.pk == value.pk
                            and bridge._identity(item) == bridge._identity(value)), None)
            if current is None:
                bridge.unbind_profile(value)
            elif not current.enabled or not current.user.is_active:
                bridge.unbind_profile(current)
                bridge._clear_binding(current)

        async def to_thread(function, *args):
            return function(*args)

        failures = [bridge.RcBridgeError("service_unavailable", "fixture")
                    for _ in range(revocation_failures)]
        def unbind_result(_value):
            if failures:
                raise failures.pop(0)
            return {}

        with patch.object(bridge, "_stop", stop), patch.object(bridge, "_profiles", side_effect=profiles), \
                patch.object(bridge, "AccountWorker", side_effect=make_worker), \
                patch.object(bridge, "unbind_profile", side_effect=unbind_result) as unbind, \
                patch.object(bridge, "_clear_binding") as clear, \
                patch.object(bridge, "_retry_revocation", side_effect=revoke), \
                patch.object(bridge, "_pending_revocations", side_effect=lambda: list(durable.values())), \
                patch.object(bridge, "_remember_revocation", side_effect=lambda value: durable.__setitem__(bridge._identity(value), value)), \
                patch.object(bridge, "_forget_revocation", side_effect=lambda value: durable.pop(bridge._identity(value), None)), \
                patch.object(bridge.asyncio, "sleep", side_effect=sleep), \
                patch.object(bridge.asyncio, "to_thread", side_effect=to_thread), \
                patch.object(bridge, "_now", side_effect=lambda: clock[0]):
            await bridge._run()
        return workers, unbind, clear

    async def test_account_query_failure_cancels_existing_conversation(self):
        observed = []
        async def tick(worker, _workers):
            observed.append(worker.cancel.is_set())
        workers, _, _ = await self.run_loop(
            [[profile()], RuntimeError("database unavailable"), [profile()]], on_tick=tick,
        )
        self.assertEqual(observed, [False, True])
        self.assertTrue(workers[0].cancel.is_set())

    async def test_native_service_loss_cancels_before_polling_again(self):
        observed = []
        async def tick(worker, _workers):
            observed.append(worker.cancel.is_set())
            if len(observed) == 1:
                raise bridge.RcBridgeError("service_unavailable", "fixture")
        await self.run_loop([[profile()], [profile()]], on_tick=tick)
        self.assertEqual(observed, [False, True])

    async def test_changed_account_identity_retires_old_worker(self):
        old = profile()
        workers, unbind, _ = await self.run_loop([[old], [profile(account="6")]])
        self.assertEqual(len(workers), 2)
        self.assertTrue(workers[0].cancel.is_set())
        workers[0].close.assert_awaited_once()
        self.assertNotEqual(workers[0].profile.account, workers[1].profile.account)
        unbind.assert_called_once_with(old)

    async def test_deleted_account_retires_and_revokes_its_old_binding(self):
        old = profile()
        workers, unbind, clear = await self.run_loop([[old], []])
        self.assertTrue(workers[0].cancel.is_set())
        unbind.assert_called_once_with(old)
        clear.assert_not_called()

    async def test_deleted_account_revocation_survives_service_outage(self):
        old = profile()
        _, unbind, _ = await self.run_loop([[old], [], [], [], []], revocation_failures=1)
        self.assertEqual(unbind.call_count, 2)
        self.assertTrue(all(call.args == (old,) for call in unbind.call_args_list))

    async def test_restart_replays_durable_revocation_without_a_user_profile(self):
        old = profile()
        workers, unbind, _ = await self.run_loop([[], []], tombstones=[old])
        self.assertEqual(workers, [])
        unbind.assert_called_once_with(old)

    async def test_changed_binding_identity_retires_old_worker(self):
        workers, _, _ = await self.run_loop([[profile()], [profile(binding="6")]])
        self.assertEqual(len(workers), 2)
        self.assertTrue(workers[0].cancel.is_set())

    async def test_unchanged_identity_reuses_one_worker(self):
        workers, _, _ = await self.run_loop([[profile()], [profile()]])
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0].tick.await_count, 2)

    async def test_disabled_account_retires_and_retries_native_revocation(self):
        disabled = profile(enabled=False)
        workers, unbind, clear = await self.run_loop([[profile()], [disabled]])
        self.assertTrue(workers[0].cancel.is_set())
        unbind.assert_called_once_with(disabled)
        clear.assert_called_once_with(disabled)

    async def test_inactive_user_is_revoked_and_cleared_without_reenrollment(self):
        inactive = profile(active=False)
        workers, unbind, clear = await self.run_loop([[profile()], [inactive]])
        self.assertTrue(workers[0].cancel.is_set())
        unbind.assert_called_once_with(inactive)
        # Clearing the revoked binding stops the supervisor from revoking it
        # again every second for as long as the account stays inactive.
        clear.assert_called_once_with(inactive)
        self.assertEqual(len(workers), 1)

    async def test_duplicate_process_lease_prevents_any_dispatch(self):
        workers, _, _ = await self.run_loop([[profile()]], lease_available=False)
        workers[0].tick.assert_not_awaited()

    async def test_slow_retirement_does_not_block_another_account(self):
        gate = asyncio.Event()
        other = profile(key=2, account="6", adapter="7", binding="8")
        observed = []
        async def tick(worker, _workers):
            if worker.profile.pk == 2:
                observed.append(gate.is_set())
        workers, _, _ = await self.run_loop([[profile()], [other]], on_tick=tick, close_gate=gate)
        self.assertEqual(observed, [False])
        self.assertEqual(len(workers), 2)

    async def test_stalled_account_poll_does_not_block_another_account(self):
        gate = asyncio.Event()
        other = profile(key=2, account="6", adapter="7", binding="8")
        observed = []
        async def tick(worker, _workers):
            if worker.profile.pk == 1:
                await gate.wait()
            else:
                observed.append(gate.is_set())
        workers, _, _ = await self.run_loop([[profile(), other]], on_tick=tick, close_gate=gate)
        await asyncio.gather(*(worker.poll_task for worker in workers if worker.poll_task))
        self.assertEqual(observed, [False])

    async def test_idle_account_is_polled_every_few_seconds(self):
        workers, _, _ = await self.run_loop([[profile()]] * 7, clock_step=1.0)
        # One native round every IDLE_POLL_SECONDS: at 0, 3 and 6 seconds.
        self.assertEqual(workers[0].tick.await_count, 3)

    async def test_active_conversation_is_polled_every_second(self):
        async def tick(worker, _workers):
            worker.active = operation()
        workers, _, _ = await self.run_loop([[profile()]] * 4, on_tick=tick, clock_step=1.0)
        self.assertEqual(workers[0].tick.await_count, 4)

    async def test_failing_service_is_retried_with_growing_delays(self):
        async def tick(_worker, _workers):
            raise bridge.RcBridgeError("service_unavailable", "fixture")
        workers, _, _ = await self.run_loop([[profile()]] * 10, on_tick=tick, clock_step=1.0)
        # Attempts at 0, 2 and 6 seconds; the next one waits until 14 seconds.
        self.assertEqual(workers[0].tick.await_count, 3)

    async def test_revocation_retries_back_off_while_the_service_is_down(self):
        old = profile()
        _, unbind, _ = await self.run_loop([[old]] + [[]] * 11, revocation_failures=99,
                                           clock_step=1.0)
        # Attempts at 1, 4 and 9 seconds; the fourth waits until 18 seconds.
        self.assertEqual(unbind.call_count, 3)


class HeartbeatWatchdogTests(IsolatedAsyncioTestCase):
    def setUp(self):
        capability_patch = patch("agent.remote_controller_runtime.execution_capabilities", return_value={})
        capability_patch.start()
        self.addCleanup(capability_patch.stop)
        self.worker = bridge.AccountWorker(profile())
        self.worker.lease = Mock()
        self.worker.call = AsyncMock(return_value={})
        self.worker.active = operation()
        self.worker.authority_at = 10.0

    async def one_watchdog_pass(self, now):
        async def sleep(_seconds):
            self.worker.retiring = True
        with patch.object(bridge.time, "monotonic", return_value=now), \
                patch.object(bridge.asyncio, "sleep", side_effect=sleep):
            await self.worker.watchdog()

    async def test_missing_authority_heartbeat_cancels_after_twenty_seconds(self):
        await self.one_watchdog_pass(30.0)
        self.assertTrue(self.worker.cancel.is_set())

    async def test_current_authority_is_not_cancelled_early(self):
        await self.one_watchdog_pass(29.0)
        self.assertFalse(self.worker.cancel.is_set())

    async def test_unverified_active_operation_is_cancelled(self):
        self.worker.authority_at = None
        await self.one_watchdog_pass(10.0)
        self.assertTrue(self.worker.cancel.is_set())

    async def test_successful_progress_does_not_extend_authority(self):
        await self.worker.progress({"type": "message", "text": "Still working"})
        self.assertEqual(self.worker.authority_at, 10.0)
        await self.one_watchdog_pass(31.0)
        self.assertTrue(self.worker.cancel.is_set())

    async def test_successful_operation_heartbeat_extends_authority(self):
        self.worker.call.side_effect = [{"active_authorized": True}, {"operation": None}]
        with patch.object(bridge.time, "monotonic", return_value=25.0), \
                patch.object(bridge, "_ready", return_value=True):
            await self.worker.tick()
        self.assertEqual(self.worker.authority_at, 25.0)
        self.assertFalse(self.worker.cancel.is_set())

    async def test_denied_heartbeat_cannot_extend_authority(self):
        self.worker.call.side_effect = [{"active_authorized": False}, {"operation": None}]
        with patch.object(bridge.time, "monotonic", return_value=25.0), \
                patch.object(bridge, "_ready", return_value=True):
            await self.worker.tick()
        self.assertEqual(self.worker.authority_at, 10.0)
        self.assertTrue(self.worker.cancel.is_set())

    async def test_truthy_nonboolean_heartbeat_cannot_extend_authority(self):
        self.worker.call.side_effect = [{"active_authorized": "true"}, {"operation": None}]
        with patch.object(bridge, "_ready", return_value=True):
            await self.worker.tick()
        self.assertEqual(self.worker.authority_at, 10.0)
        self.assertTrue(self.worker.cancel.is_set())

    async def test_stalled_native_poll_does_not_stop_authority_watchdog(self):
        gate = asyncio.Event()
        async def call(op, **_fields):
            if op == "adapter-heartbeat":
                await gate.wait()
                return {"active_authorized": True}
            return {"operation": None}
        self.worker.call.side_effect = call
        with patch.object(bridge, "_ready", return_value=True):
            polling = asyncio.create_task(self.worker.tick())
            await asyncio.sleep(0)
            self.assertFalse(polling.done())
            await self.one_watchdog_pass(31.0)
            self.assertTrue(self.worker.cancel.is_set())
            self.assertFalse(polling.done())
            gate.set()
            await polling

    async def test_retirement_stops_watchdog_cleanly(self):
        self.worker.active = None
        self.worker.start_watchdog()
        watchdog = self.worker.watchdog_task
        await asyncio.sleep(0)
        await self.worker.close()
        self.assertTrue(watchdog.done())
        self.worker.lease.close.assert_called_once()


class BoundedNativeConcurrencyTests(IsolatedAsyncioTestCase):
    async def exercise(self, *, cancel_first=False):
        gate = asyncio.Event()
        running = 0
        peak = 0
        started = 0
        async def helper(_function, *_args):
            nonlocal running, peak, started
            running += 1
            started += 1
            peak = max(peak, running)
            try:
                await gate.wait()
                return {"ok": True}
            finally:
                running -= 1
        transport = bridge._NativeTransport()
        with patch.object(bridge.asyncio, "to_thread", side_effect=helper):
            tasks = [asyncio.create_task(transport.call({"op": "fixture"})) for _ in range(9)]
            for _ in range(4):
                await asyncio.sleep(0)
            self.assertEqual(started, 4)
            self.assertEqual(running, 4)
            if cancel_first:
                tasks[0].cancel()
                for _ in range(3):
                    await asyncio.sleep(0)
                self.assertEqual(started, 4)
                self.assertEqual(running, 4)
            gate.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
        self.assertLessEqual(peak, 4)
        self.assertEqual(running, 0)
        return results

    async def test_native_calls_never_exceed_four_helpers(self):
        results = await self.exercise()
        self.assertEqual(results, [{"ok": True}] * 9)

    async def test_cancelled_waiter_keeps_its_slot_until_helper_returns(self):
        results = await self.exercise(cancel_first=True)
        self.assertIsInstance(results[0], asyncio.CancelledError)
        self.assertTrue(all(value == {"ok": True} for value in results[1:]))


class ConversationHistoryTests(TestCase):
    def setUp(self):
        from .models import AgentMessage
        self.owner = profile()
        self.rows = []
        self.query = MagicMock()
        self.query.select_related.return_value = self.query
        self.query.order_by.return_value = self.query
        self.query.__getitem__.side_effect = lambda _slice: self.rows
        self.older = Mock()
        self.older.exists.return_value = False
        self.manager = Mock()
        self.manager.filter.side_effect = lambda **fields: self.older if "pk__lt" in fields else self.query
        self.patches = [patch.object(AgentMessage, "objects", self.manager),
                        patch.object(bridge, "_revocation_profile", return_value=self.owner),
                        patch("django.db.close_old_connections")]
        self.current_patch = self.patches[1]
        for item in self.patches:
            result = item.start()
            if item is self.current_patch:
                self.current = result
            self.addCleanup(item.stop)

    @staticmethod
    def row(key, text, username="Account one"):
        return SimpleNamespace(pk=key, message=text, user=SimpleNamespace(username=username),
                               conversation_user_id=1, response_files=[], timestamp=datetime(2026, 11, 13, tzinfo=timezone.utc))

    def test_history_queries_only_own_conversation(self):
        self.rows = [self.row(2, "Reply", "Tlamatini"), self.row(1, "Question")]
        result = bridge._history(self.owner)
        self.assertEqual([item["id"] for item in result["messages"]], [1, 2])
        self.assertEqual([item["role"] for item in result["messages"]], ["user", "assistant"])
        self.assertFalse(result["truncated"])
        for call in self.manager.filter.call_args_list:
            self.assertEqual(call.kwargs["conversation_user_id"], self.owner.user_id)

    def test_assistant_history_converts_rendered_html_to_safe_text(self):
        self.rows = [self.row(1, '<p>Use &lt;tag&gt;.</p><pre><code>x &amp; y</code></pre><style>hidden</style>', "Tlamatini")]
        result = bridge._history(self.owner)
        self.assertEqual(result["messages"][0]["text"], 'Use <tag>.\nx & y')
        self.assertEqual(result["messages"][0]["role"], "assistant")

    def test_user_history_preserves_literal_markup_and_entities(self):
        literal = '<script>My literal example</script> &lt;tag&gt; <p>Keep this</p>'
        self.rows = [self.row(1, literal)]
        result = bridge._history(self.owner)
        self.assertEqual(result["messages"][0]["text"], literal)
        self.assertEqual(result["messages"][0]["role"], "user")

    def test_history_fetch_is_bounded_to_forty_rows(self):
        bridge._history(self.owner)
        self.query.__getitem__.assert_called_once_with(slice(None, 40, None))

    def test_absent_consent_never_reads_messages(self):
        self.current.return_value = None
        with self.assertRaises(bridge.RcBridgeError):
            bridge._history(self.owner)
        self.manager.filter.assert_not_called()

    def test_disabled_consent_never_reads_messages(self):
        self.owner.enabled = False
        with self.assertRaises(bridge.RcBridgeError):
            bridge._history(self.owner)
        self.manager.filter.assert_not_called()

    def test_inactive_user_never_reads_messages(self):
        self.owner.user.is_active = False
        with self.assertRaises(bridge.RcBridgeError):
            bridge._history(self.owner)
        self.manager.filter.assert_not_called()

    def test_reassigned_local_user_cannot_read_stale_workers_history(self):
        self.current.return_value = profile(key=2)
        with self.assertRaises(bridge.RcBridgeError):
            bridge._history(self.owner)
        self.manager.filter.assert_not_called()

    def test_older_rows_are_reported_as_truncated(self):
        self.rows = [self.row(40, "Recent")]
        self.older.exists.return_value = True
        self.assertTrue(bridge._history(self.owner)["truncated"])

    def test_long_message_is_bounded_and_marked(self):
        from .remote_controller_runtime import _wire_size
        self.rows = [self.row(1, "x" * 8000)]
        result = bridge._history(self.owner)
        self.assertTrue(result["truncated"])
        self.assertLessEqual(_wire_size(result["messages"][0]["text"]), 4000)

    def test_unicode_history_fits_native_encoder_budget(self):
        from .remote_controller_runtime import _wire_size
        self.rows = [self.row(key, "😀<&'" * 2000, "Tlamatini") for key in range(40, 0, -1)]
        result = bridge._history(self.owner)
        self.assertLessEqual(_wire_size(result), 24000)
        self.assertTrue(result["truncated"])
        self.assertGreater(len(result["messages"]), 0)
        self.assertEqual(result["messages"][-1]["id"], 40)

    def test_empty_history_is_honestly_empty(self):
        self.assertEqual(bridge._history(self.owner), {"messages": [], "truncated": False})


class DurableRevocationTests(TestCase):
    def setUp(self):
        from .models import RemoteControllerRevocation
        self.model = RemoteControllerRevocation
        self.manager = MagicMock()
        self.manager.using.return_value = self.manager
        self.patches = [patch.object(self.model, "objects", self.manager),
                        patch("django.db.close_old_connections")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_profile_delete_signal_records_intent_without_external_ipc(self):
        from django.db.models.signals import post_delete
        from .models import RemoteControllerProfile
        deleted = profile()
        with patch.object(bridge, "native") as native:
            post_delete.send(sender=RemoteControllerProfile, instance=deleted, using="default")
        self.manager.using.assert_called_once_with("default")
        self.manager.get_or_create.assert_called_once_with(
            binding_id=deleted.binding_id,
            defaults={"account": deleted.account, "adapter": deleted.adapter},
        )
        native.assert_not_called()

    def test_unbound_profile_delete_does_not_create_revocation(self):
        from django.db.models.signals import post_delete
        from .models import RemoteControllerProfile
        post_delete.send(sender=RemoteControllerProfile, instance=profile(binding=""), using="default")
        self.manager.get_or_create.assert_not_called()

    def test_revocation_model_has_no_user_cascade_dependency(self):
        self.assertFalse(any(field.is_relation for field in self.model._meta.fields))

    def test_retiring_worker_persists_immutable_binding_intent(self):
        old = profile()
        bridge._remember_revocation(old)
        self.manager.get_or_create.assert_called_once_with(
            binding_id=old.binding_id,
            defaults={"account": old.account, "adapter": old.adapter},
        )

    def test_acknowledgement_cannot_remove_another_adapter_tombstone(self):
        old = profile()
        bridge._forget_revocation(old)
        self.manager.filter.assert_called_once_with(
            binding_id=old.binding_id, account=old.account, adapter=old.adapter,
        )
        self.manager.filter.return_value.delete.assert_called_once()

    def test_restart_recovery_load_is_bounded(self):
        bridge._pending_revocations()
        self.manager.order_by.assert_called_once_with("created_at")
        self.manager.order_by.return_value.__getitem__.assert_called_once_with(slice(None, 128, None))


class DurableAcknowledgementTests(IsolatedAsyncioTestCase):
    async def test_successful_service_revocation_removes_durable_intent(self):
        old = profile()
        transport = SimpleNamespace(run=AsyncMock(return_value=None))
        with patch.object(bridge, "_forget_revocation") as forget:
            self.assertTrue(await bridge._revoke(old, transport))
        forget.assert_called_once_with(old)

    async def test_service_outage_keeps_durable_intent(self):
        transport = SimpleNamespace(run=AsyncMock(side_effect=bridge.RcBridgeError("service_unavailable", "fixture")))
        with patch.object(bridge, "_forget_revocation") as forget:
            self.assertFalse(await bridge._revoke(profile(), transport))
        forget.assert_not_called()

    async def test_already_absent_service_binding_acknowledges_revocation(self):
        old = profile()
        transport = SimpleNamespace(run=AsyncMock(side_effect=bridge.RcBridgeError("not_found", "fixture")))
        with patch.object(bridge, "_forget_revocation") as forget:
            self.assertTrue(await bridge._revoke(old, transport))
        forget.assert_called_once_with(old)

    async def test_failed_local_acknowledgement_keeps_retry_required(self):
        transport = SimpleNamespace(run=AsyncMock(return_value=None))
        with patch.object(bridge, "_forget_revocation", side_effect=OSError("fixture storage unavailable")):
            self.assertFalse(await bridge._revoke(profile(), transport))
