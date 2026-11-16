# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Account adapter for the independent Remote-Controller Windows service.

Only the installed fixed native helper is invoked. Browser input never supplies
an executable, account, adapter, service, PID, port, or command line.
"""
import asyncio
import atexit
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

EDITION = "english"
_log = logging.getLogger(__name__)
_gate = threading.Lock()
_started = False
_stop = threading.Event()
_leases_lock = threading.Lock()
_leases = set()
enrollment_lock = threading.RLock()
AUTHORITY_SECONDS = 20.0
# Each native call starts a helper process. Poll an idle account every few
# seconds, an active conversation every second, and back off while the
# service keeps failing, so a stopped service costs almost nothing.
ACTIVE_POLL_SECONDS = 1.0
IDLE_POLL_SECONDS = 3.0
MAX_RETRY_SECONDS = 15.0


def _now():
    return time.monotonic()


def _retry_delay(failures):
    """2, 4, 8, then at most 15 seconds between attempts that keep failing."""
    # Saturate before exponentiation: a long outage must never overflow and
    # bypass the retry schedule or interrupt the revocation supervisor.
    if failures >= 4:
        return MAX_RETRY_SECONDS
    return min(MAX_RETRY_SECONDS, 2.0 ** max(1, failures))


class RcBridgeError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def native(request):
    if os.name != "nt":
        raise RcBridgeError("windows_required", "Remote-Controller requires Windows.")
    from win32com.shell import shell
    binary = Path(shell.SHGetFolderPath(0, 38, 0, 0)) / "XAIHT/Tlachihuani/RCServer/Tlachihuani.RC.Server.exe"
    if not binary.is_file() or binary.resolve() != binary:
        raise RcBridgeError("service_unavailable", "Install Tlachihuani and start Remote-Controller in XT.")
    raw = json.dumps(request, ensure_ascii=True, separators=(",", ":"))
    if len(raw.encode()) > 65536:
        raise RcBridgeError("request_too_large", "The RC request exceeds the limit.")
    try:
        completed = subprocess.run([str(binary), "--control"], input=raw + "\n",
                                   capture_output=True, text=True, encoding="utf-8",
                                   timeout=12, creationflags=subprocess.CREATE_NO_WINDOW,
                                   check=False)
        if not isinstance(completed.stdout, str) or len(completed.stdout.encode()) > 65536:
            raise ValueError("oversized native response")
        reply = json.loads(completed.stdout)
        if not isinstance(reply, dict):
            raise ValueError("invalid native response")
        error = reply.get("error")
        if error is not None:
            if (not isinstance(error, dict) or not isinstance(error.get("code"), str)
                    or not isinstance(error.get("message"), str)):
                raise ValueError("invalid native error response")
            raise RcBridgeError(error["code"], error["message"])
        if completed.returncode:
            raise ValueError("native control failed")
        return reply
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RcBridgeError("service_unavailable", "Cannot reach Remote-Controller. Check Services in XT.") from exc


def service_status():
    return native({"op": "status"})


def bind_profile(profile):
    return native({"op": "bind-account", "edition": EDITION,
                   "account_id": profile.account.hex, "adapter_id": profile.adapter.hex,
                   "display_name": profile.user.get_username()[:80]})


def unbind_profile(profile):
    if not profile.binding_id:
        return {"disabled": True}
    return native({"op": "unbind-account", "binding_id": profile.binding_id,
                   "adapter_id": profile.adapter.hex})


def _profiles():
    from django.db import close_old_connections
    from .models import RemoteControllerProfile
    close_old_connections()
    return list(RemoteControllerProfile.objects.select_related("user").exclude(binding_id="")[:128])


def _clear_binding(profile):
    from django.db.models import Q
    from .models import RemoteControllerProfile
    # Clear only this exact revoked binding, and only while consent is absent:
    # remote access disabled here, or the Django account deactivated. After a
    # reactivation the account must enable remote access again.
    RemoteControllerProfile.objects.filter(
        Q(enabled=False) | Q(user__is_active=False),
        pk=profile.pk, binding_id=profile.binding_id,
    ).update(binding_id="", enabled=False)


def _pending_revocations():
    from django.db import close_old_connections
    from .models import RemoteControllerRevocation
    close_old_connections()
    return list(RemoteControllerRevocation.objects.order_by("created_at")[:128])


def _remember_revocation(profile):
    from django.db import close_old_connections
    from .models import RemoteControllerRevocation
    close_old_connections()
    RemoteControllerRevocation.objects.get_or_create(
        binding_id=profile.binding_id,
        defaults={"account": profile.account, "adapter": profile.adapter},
    )


def _forget_revocation(profile):
    from django.db import close_old_connections
    from .models import RemoteControllerRevocation
    close_old_connections()
    RemoteControllerRevocation.objects.filter(
        binding_id=profile.binding_id, account=profile.account, adapter=profile.adapter,
    ).delete()


def _ready(profile):
    # A remote conversation builds this account's chain on demand, so the
    # application can serve it once Django has loaded. An existing desktop
    # chain only means that it is already warm.
    from django.apps import apps
    from .global_state import global_state
    return bool(global_state.get_state(f"rag_chain_{profile.user_id}")) or apps.ready


class _NativeTransport:
    """At most four native helper calls, including progress and revocations."""
    def __init__(self):
        self.slots = asyncio.Semaphore(4)

    async def run(self, function, *args):
        async with self.slots:
            task = asyncio.create_task(asyncio.to_thread(function, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Cancelling to_thread does not terminate the native helper.
                # Retain its slot until the bounded helper actually returns.
                await asyncio.shield(task)
                raise

    async def call(self, request):
        return await self.run(native, request)


def _revocation_profile(profile):
    from django.db import close_old_connections
    from .models import RemoteControllerProfile
    close_old_connections()
    return RemoteControllerProfile.objects.select_related("user").filter(
        account=profile.account, adapter=profile.adapter,
        binding_id=profile.binding_id,
    ).first()


def _retry_revocation(profile):
    # A queued retry must not revoke a newer explicit enable from the account
    # page. Check fresh consent under the same lock that page uses to enroll.
    with enrollment_lock:
        current = _revocation_profile(profile)
        if current is None:
            # The supervisor retained this trusted old identity before its
            # account was deleted or replaced. Revoke that exact old binding;
            # a replacement profile has different immutable identifiers.
            unbind_profile(profile)
            return
        if current.enabled and current.user.is_active:
            return
        try:
            unbind_profile(current)
        except RcBridgeError as exc:
            # The service no longer knows this binding: it is already revoked.
            if exc.code != "not_found":
                raise
        # Consent is gone here or the account is inactive. Clearing the revoked
        # binding ends the retries instead of repeating them every second.
        _clear_binding(current)


def _history(profile):
    from django.db import close_old_connections
    from .models import AgentMessage
    from .remote_controller_runtime import _assistant_text, _bounded_text, _wire_size
    close_old_connections()
    try:
        current = _revocation_profile(profile)
        if (current is None or not current.enabled or not current.user.is_active
                or current.user_id != profile.user_id):
            raise RcBridgeError("account_unavailable", "Remote access for this account is disabled.")
        rows = list(AgentMessage.objects.filter(
            conversation_user_id=profile.user_id,
        ).select_related("user").order_by("-pk")[:40])
        truncated = bool(rows and AgentMessage.objects.filter(
            conversation_user_id=profile.user_id, pk__lt=rows[-1].pk,
        ).exists())
        messages = []
        for row in rows:
            assistant = row.user.username == "Tlamatini"
            text, cut = _bounded_text(_assistant_text(row.message) if assistant else row.message, 4000)
            item = {"id": row.pk, "text": text,
                    "role": "assistant" if assistant else "user",
                    "created_at": row.timestamp.isoformat()}
            if assistant:
                from .remote_response_files import content_ticket, render_response
                rendered = render_response(profile.user_id, row.pk, row.message,
                                           row=row, profile=current)
                rich = {**item, "format": "html", "html": rendered}
                if _wire_size(rich) <= 18000:
                    item = rich
                    cut = False
                else:
                    cut = True
                    item["content_ticket"] = content_ticket(profile.user_id, row.pk, row.message, profile=current)
            item["truncated"] = cut
            if _wire_size({"messages": messages + [item], "truncated": True}) > 24000:
                truncated = True
                break
            messages.append(item)
            truncated = truncated or (cut and "content_ticket" not in item)
        messages.reverse()
        return {"messages": messages, "truncated": truncated}
    finally:
        close_old_connections()


class _AdapterLease:
    """A native mutex owns dispatch across processes and Windows sessions.

    The default Windows ACL restricts the object to its creator's account and
    administrators. A pre-existing inaccessible object refuses dispatch. The
    owning loop thread keeps the handle until all of its chat work has ended.
    """
    def __init__(self, adapter_id):
        self.name = "Global\\XAIHT.Tlamatini.RC.Adapter.v1." + uuid.UUID(hex=adapter_id).hex
        self.handle = None
        self.owner_thread = None

    def acquire(self):
        if self.handle is not None:
            return self.owner_thread == threading.get_ident()
        if os.name != "nt":
            raise RcBridgeError("windows_required", "Remote-Controller requires Windows.")
        import win32api
        import win32event
        # Windows mutex ownership is recursive on the same thread. A retiring
        # worker on this loop must therefore reserve the name here as well.
        with _leases_lock:
            if self.name in _leases:
                return False
            _leases.add(self.name)
        handle = None
        try:
            handle = win32event.CreateMutex(None, False, self.name)
            outcome = win32event.WaitForSingleObject(handle, 0)
            if outcome not in (0, 128):  # WAIT_OBJECT_0 / WAIT_ABANDONED
                win32api.CloseHandle(handle)
                with _leases_lock:
                    _leases.discard(self.name)
                return False
            self.handle = handle
            self.owner_thread = threading.get_ident()
            return True
        except Exception as exc:
            try:
                if handle is not None:
                    win32api.CloseHandle(handle)
            finally:
                with _leases_lock:
                    _leases.discard(self.name)
            raise RcBridgeError("adapter_lease_unavailable", "Another application owns this RC account adapter.") from exc

    def close(self):
        if self.handle is None:
            return
        if self.owner_thread != threading.get_ident():
            raise RuntimeError("The RC adapter lease must be released by its owning thread")
        import win32api
        import win32event
        handle, self.handle = self.handle, None
        try:
            win32event.ReleaseMutex(handle)
        finally:
            try:
                win32api.CloseHandle(handle)
            finally:
                with _leases_lock:
                    _leases.discard(self.name)


def _identity(profile):
    return (profile.account.hex, profile.adapter.hex, profile.binding_id)


class AccountWorker:
    """One active conversation per account; controls continue while it is running."""
    def __init__(self, profile):
        self.profile = profile
        self.active = None
        self.task = None
        self.session = None
        self.cancel = asyncio.Event()
        self.outbox = []
        self.lease = _AdapterLease(profile.adapter.hex)
        self.transport = None
        self.poll_task = None
        self.watchdog_task = None
        self.authority_at = None
        self.retiring = False
        self.consent_observed = True
        self._close_started = False
        self.next_poll_at = 0.0
        self.poll_failures = 0

    async def call(self, op, **fields):
        request = {"op": op, "adapter_id": self.profile.adapter.hex, **fields}
        if self.transport is not None:
            return await self.transport.call(request)
        return await asyncio.to_thread(native, request)

    def start_watchdog(self):
        if self.watchdog_task is None and not self.retiring:
            self.watchdog_task = asyncio.create_task(self.watchdog())

    async def watchdog(self):
        while not self.retiring:
            if self.active and (not self.consent_observed or self.authority_at is None
                                or time.monotonic() - self.authority_at >= AUTHORITY_SECONDS):
                self.cancel.set()
            await asyncio.sleep(1)

    async def progress(self, update):
        if self.active:
            if self.retiring or not self.consent_observed:
                raise RcBridgeError("authorization_changed", "The conversation is no longer authorized.")
            if self.cancel.is_set():
                # The event watcher may not have resumed yet. Latch the owned
                # runtime cancellation now and discard trailing output; this
                # is expected cancellation, not a broken approval channel.
                if self.session is not None:
                    self.session.request_cancel()
                return
            try:
                await self.call("adapter-progress", operation_id=self.active["id"], progress=update)
            except RcBridgeError:
                self.cancel.set()
                raise

    async def finish(self, operation, result=None, error=None):
        self.outbox.append({"operation_id": operation["id"], "result": result, "error": error})

    async def chat(self, operation):
        try:
            from .remote_controller_runtime import RuntimeSession
            self.session = RuntimeSession(self.profile.user, self.progress,
                                          **({"options": operation["payload"]["options"]}
                                             if "options" in operation["payload"] else {}))
            result = await self.session.run(operation["payload"]["text"], self.cancel)
            await self.finish(operation, result=result)
        except asyncio.CancelledError:
            self.cancel.set()
            raise
        except Exception as exc:
            code = getattr(exc, "code", "conversation_failed")
            if not isinstance(code, str) or not code.replace("_", "").isascii() or not code.replace("_", "").isalnum() or len(code) > 64:
                code = "conversation_failed"
            _log.warning("RC conversation ended: %s", code)
            await self.finish(operation, error=code)
        finally:
            self.active = None
            self.session = None

    async def flush_outbox(self):
        while self.outbox:
            try:
                await self.call("adapter-complete", **self.outbox[0])
            except RcBridgeError as exc:
                if exc.code not in {"not_found", "operation_conflict", "forbidden"}:
                    raise
            self.outbox.pop(0)

    async def tick(self):
        if self.retiring or not self.consent_observed:
            return
        await self.flush_outbox()
        if self.retiring or not self.consent_observed:
            return
        active_id = self.active["id"] if self.active else None
        from .remote_controller_runtime import execution_capabilities
        capabilities = await asyncio.to_thread(execution_capabilities)
        pulse = await self.call("adapter-heartbeat", ready=_ready(self.profile),
                                operation_id=active_id, capabilities=capabilities)
        if self.retiring or not self.consent_observed:
            return
        if self.active and self.active["id"] == active_id:
            if pulse.get("active_authorized") is True:
                self.authority_at = time.monotonic()
            else:
                self.cancel.set()
        reply = await self.call("adapter-next", controls_only=self.active is not None)
        operation = reply.get("operation")
        if not operation:
            return
        if not isinstance(operation, dict) or operation.get("binding_id") != self.profile.binding_id:
            self.cancel.set()
            raise RcBridgeError("binding_mismatch", "The operation does not belong to this account.")
        try:
            operation_id = operation["id"]
            if (not isinstance(operation_id, str) or len(operation_id) != 32
                    or uuid.UUID(hex=operation_id).int == 0
                    or not isinstance(operation.get("payload"), dict)
                    or not isinstance(operation.get("kind"), str)):
                raise ValueError("invalid operation")
        except (KeyError, ValueError, TypeError) as exc:
            self.cancel.set()
            raise RcBridgeError("invalid_operation", "The native operation response was invalid.") from exc
        if self.retiring or not self.consent_observed:
            await self.finish(operation, error="account_unavailable")
            return
        kind, payload = operation["kind"], operation["payload"]
        if kind == "conversation.submit":
            if self.active is not None:
                await self.finish(operation, error="account_busy")
                return
            self.active = operation
            self.cancel = asyncio.Event()
            # TakeNext has just revalidated the originating device. Only a
            # successful heartbeat for this operation may extend this grant.
            self.authority_at = time.monotonic()
            self.task = asyncio.create_task(self.chat(operation))
        elif kind == "application.status":
            await self.finish(operation, result={"state": "ready" if _ready(self.profile) else "loading",
                                                 "ready": _ready(self.profile), "edition": EDITION})
        elif kind == "conversation.history":
            try:
                await self.finish(operation, result=await asyncio.to_thread(_history, self.profile))
            except RcBridgeError as exc:
                await self.finish(operation, error=exc.code)
            except Exception as exc:
                _log.info("Remote-Controller history unavailable: %s", type(exc).__name__)
                await self.finish(operation, error="history_unavailable")
        elif kind in {"conversation.cancel", "conversation.permission"}:
            if not self.active or payload.get("operation_id") != self.active["id"]:
                await self.finish(operation, error="operation_not_active")
            elif kind == "conversation.cancel":
                self.cancel.set()
                await self.finish(operation, result={"cancellation_requested": True})
            elif self.cancel.is_set():
                await self.finish(operation, error="authorization_changed")
            elif self.session is None:
                await self.finish(operation, error="permission_expired")
            else:
                resolved = await self.session.respond_permission(payload["request_id"], payload["decision"])
                await self.finish(operation, result={"resolved": True} if resolved else None,
                                  error=None if resolved else "permission_expired")
        else:
            await self.finish(operation, error="unsupported_operation")

    async def close(self):
        if self._close_started:
            return
        self._close_started = True
        self.retiring = True
        self.cancel.set()
        try:
            if self.watchdog_task:
                self.watchdog_task.cancel()
                await asyncio.gather(self.watchdog_task, return_exceptions=True)
            if self.poll_task and self.poll_task is not asyncio.current_task():
                await asyncio.shield(self.poll_task)
            if self.task and not self.task.done():
                # Runtime cancellation uses the application's owned run epoch
                # and permission broker. The lease remains held until the
                # runtime confirms completion, even if cancellation is slow.
                try:
                    await asyncio.wait_for(asyncio.shield(self.task), 10)
                except asyncio.TimeoutError:
                    self.task.cancel()
                    await asyncio.gather(self.task, return_exceptions=True)
            try:
                await self.flush_outbox()
            except RcBridgeError:
                # The service retains its dispatched receipt as unknown when
                # it cannot receive this final result. Never replay the chat.
                _log.info("RC account closed with an unacknowledged completion")
        finally:
            if self.task and not self.task.done():
                # An outer shutdown can cancel this cleanup coroutine too.
                # Keep ownership until the actual chat task reaches its end.
                self.task.add_done_callback(lambda _done: self.lease.close())
            else:
                self.lease.close()


def _retire(worker, retiring):
    worker.retiring = True
    worker.consent_observed = False
    worker.cancel.set()
    task = asyncio.create_task(worker.close())
    retiring.add(task)

    def completed(done):
        retiring.discard(done)
        if not done.cancelled() and done.exception() is not None:
            _log.warning("RC account retirement failed: %s", type(done.exception()).__name__)

    task.add_done_callback(completed)


async def _poll(worker, slots):
    async with slots:
        if worker.retiring:
            return
        try:
            await worker.tick()
        except Exception as exc:
            worker.cancel.set()
            worker.poll_failures = getattr(worker, "poll_failures", 0) + 1
            worker.next_poll_at = _now() + _retry_delay(worker.poll_failures)
            if not isinstance(exc, RcBridgeError):
                _log.info("Remote-Controller account polling failed: %s", type(exc).__name__)
        else:
            worker.poll_failures = 0
            worker.next_poll_at = _now() + (
                ACTIVE_POLL_SECONDS if getattr(worker, "active", None) else IDLE_POLL_SECONDS)


async def _revoke(profile, transport):
    try:
        try:
            await transport.run(_retry_revocation, profile)
        except RcBridgeError as exc:
            if exc.code != "not_found":
                raise
        await asyncio.to_thread(_forget_revocation, profile)
        return True
    except Exception as exc:
        if not isinstance(exc, RcBridgeError):
            _log.info("Remote-Controller revocation pending: %s", type(exc).__name__)
        return False


async def _run():
    workers = {}
    retiring = set()
    revocations = {}
    pending_revocations = {}
    revocation_failures = {}
    revocation_retry_at = {}
    transport = _NativeTransport()
    poll_slots = asyncio.Semaphore(4)
    last_problem = None
    try:
        while not _stop.is_set():
            try:
                profiles = await asyncio.to_thread(_profiles)
                tombstones = await asyncio.to_thread(_pending_revocations)
                for tombstone in tombstones:
                    pending_revocations[_identity(tombstone)] = tombstone
                enabled = {p.pk: p for p in profiles if p.enabled and p.user.is_active}
                for key in list(workers):
                    if key not in enabled or _identity(workers[key].profile) != _identity(enabled[key]):
                        previous_worker = workers[key]
                        old = previous_worker.profile
                        previous_worker.consent_observed = False
                        previous_worker.cancel.set()
                        await asyncio.to_thread(_remember_revocation, old)
                        workers.pop(key)
                        _retire(previous_worker, retiring)
                        identity = _identity(old)
                        pending_revocations[identity] = old
                for profile in profiles:
                    if not profile.enabled or not profile.user.is_active:
                        identity = _identity(profile)
                        pending_revocations[identity] = profile
                        continue
                    worker = workers.get(profile.pk)
                    if worker is None:
                        worker = AccountWorker(profile)
                        if not worker.lease.acquire():
                            continue
                        worker.transport = transport
                        worker.start_watchdog()
                        workers[profile.pk] = worker
                    worker.profile = profile
                    worker.consent_observed = True
                    if ((worker.poll_task is None or worker.poll_task.done())
                            and _now() >= getattr(worker, "next_poll_at", 0.0)):
                        worker.poll_task = asyncio.create_task(_poll(worker, poll_slots))
                # Deleted profiles cannot be rediscovered. Keep their known
                # old binding until revocation is acknowledged. New bindings
                # require this same service, whose binding set is capped at
                # 128; an outage cannot create new remotely authorized IDs.
                for identity, old in list(pending_revocations.items()):
                    previous = revocations.get(identity)
                    if previous is not None and not previous.done():
                        continue
                    if previous is not None:
                        revocations.pop(identity)
                        if previous.result():
                            pending_revocations.pop(identity)
                            revocation_failures.pop(identity, None)
                            revocation_retry_at.pop(identity, None)
                            continue
                        # The service could not be reached: wait before retrying.
                        failures = revocation_failures.get(identity, 0) + 1
                        revocation_failures[identity] = failures
                        revocation_retry_at[identity] = _now() + _retry_delay(failures)
                    if _now() >= revocation_retry_at.get(identity, 0.0):
                        revocations[identity] = asyncio.create_task(_revoke(old, transport))
                last_problem = None
            except Exception as exc:
                # A failed account lookup removes our evidence of current
                # consent. It must never leave a conversation executing.
                for worker in workers.values():
                    worker.consent_observed = False
                    worker.cancel.set()
                code = type(exc).__name__
                if code != last_problem:
                    _log.info("Remote-Controller adapter waiting: %s", code)
                    last_problem = code
            await asyncio.sleep(1)
    finally:
        for task in revocations.values():
            task.cancel()
        await asyncio.gather(*(w.close() for w in workers.values()), *retiring,
                             *revocations.values(),
                             return_exceptions=True)


def start_adapter():
    """Called only for the actual application server, never migrations/builds."""
    global _started
    if os.name != "nt":
        return False
    with _gate:
        if _started:
            return False
        _started = True
    atexit.register(_stop.set)
    threading.Thread(target=lambda: asyncio.run(_run()), name="RemoteControllerAdapter", daemon=True).start()
    return True
