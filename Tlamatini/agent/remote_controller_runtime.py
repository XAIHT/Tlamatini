# Tlamatini — Created by Angela López Mendoza · @angelahack1
"""Native Remote-Controller adapter for the authenticated main chat engine.

No browser session is forged and no second model pipeline is introduced. A
session owns one real AgentConsumer and uses its normal receive/retrieval paths.
Its channel-layer proxy observes only frames emitted by that consumer, while
forwarding them to the normal account room. It never subscribes to another tab.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import inspect
import json
import re
import uuid
from typing import Any

from .remote_controller_guard import chat_loop, owns_chat, release_chat, reserve_chat

MAX_TEXT_BYTES = 12000
MAX_PROGRESS_BYTES = 16000
MAX_RESULT_BYTES = 30000

MODE_DEFAULTS = {
    "multi_turn_enabled": True, "exec_report_enabled": True,
    "acpx_enabled": False, "ask_execs_enabled": True,
    "step_by_step_enabled": False,
}

def execution_options(value=None):
    if value is None:
        return dict(MODE_DEFAULTS)
    if (not isinstance(value, dict)
            or any(key not in {*MODE_DEFAULTS, "self_modify_enabled"}
                   or type(enabled) is not bool for key, enabled in value.items())):
        raise RuntimeFault("invalid_execution_options")
    result = {**MODE_DEFAULTS, **value}
    if not result["multi_turn_enabled"]:
        for key in ("exec_report_enabled", "acpx_enabled", "ask_execs_enabled",
                    "step_by_step_enabled"):
            if value.get(key) is True:
                raise RuntimeFault("multiturn_required")
            result[key] = False
    return result



def execution_capabilities():
    from . import compact_mode
    state = compact_mode.state()
    # The running server publishes its own endpoint; browsers cannot choose it.
    import __main__
    resolver = getattr(__main__, "_resolve_django_port", None)
    port = resolver() if callable(resolver) else 0
    return {
        "web_port": port,
        "execution_options": True,
        "self_modify_available": bool(state["self_modify_available"]),
        "self_modify_active": bool(state["self_modify_active"]),
        "self_modify_locked": bool(state["self_modify_locked"]),
        "model": str(state.get("model") or "")[:256],
    }


class _AssistantText(HTMLParser):
    """Extract display text without executing or reparsing decoded markup."""
    blocks = {"address", "article", "aside", "blockquote", "dd", "div", "dl", "dt",
              "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
              "h4", "h5", "h6", "header", "li", "main", "nav", "ol", "p", "pre",
              "section", "table", "tr", "ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def separate(self):
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden.append(tag)
            return
        if self.hidden:
            return
        if tag in self.blocks or tag in {"br", "hr"}:
            self.separate()
        elif tag in {"td", "th"} and self.parts and not self.parts[-1].endswith(("\n", "\t")):
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag in self.blocks:
            self.separate()

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _assistant_text(value: Any) -> str:
    """Convert a main-consumer HTML answer to inert, once-decoded plain text.

    User messages are already literal text and must never pass through this
    conversion. Escaped angle brackets become text, not a second HTML parse.
    """
    parser = _AssistantText()
    parser.feed(value if isinstance(value, str) else str(value or ""))
    parser.close()
    return "".join(parser.parts).strip()


def _wire_size(value: Any) -> int:
    """Conservative size for Python JSON and .NET's default HTML-safe encoder."""
    if isinstance(value, str):
        size = len(json.dumps(value, ensure_ascii=True))
        # STJ can use six-character Unicode escapes for these ASCII values.
        # Python already escapes a quote in two characters; the others in one.
        return size + value.count('"') * 4 + sum(value.count(c) * 5 for c in "<>&'+`")
    if isinstance(value, dict):
        return 2 + max(0, len(value) - 1) + sum(_wire_size(k) + 1 + _wire_size(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return 2 + max(0, len(value) - 1) + sum(_wire_size(item) for item in value)
    return len(json.dumps(value, ensure_ascii=True))


class RuntimeFault(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _bounded_text(value: Any, maximum: int = MAX_TEXT_BYTES) -> tuple[str, bool]:
    text = value if isinstance(value, str) else str(value or "")
    # Budget the native wire's escaped JSON, including surrogate pairs and
    # control-character escapes, rather than only the unescaped UTF-8 text.
    if _wire_size(text) <= maximum:
        return text, False
    low, high = 0, min(len(text), maximum)
    while low < high:
        middle = (low + high + 1) // 2
        if _wire_size(text[:middle]) <= maximum:
            low = middle
        else:
            high = middle - 1
    return text[:low], True


class _OwnedChannelLayer:
    def __init__(self, layer, room: str, session):
        self._layer = layer
        self._room = room
        self._session = session

    def capture_source_answer(self, group, source, system_html):
        if group != self._room or self._session._closed or not self._session._capturing:
            return
        # Keep model-authored markup literal. Only the terminal protocol marker
        # is removed; system-generated reports still use their display text.
        text = re.sub(r'\s*END-RESPONSE\s*$', '', source).rstrip()
        system = _assistant_text(system_html)
        self._session._source_answer = text + ('\n' + system if system else '')

    async def group_send(self, group, event):
        if group == self._room:
            await self._session._capture(event)
        desktop_loop = chat_loop()
        if desktop_loop is not None and desktop_loop is not asyncio.get_running_loop():
            forwarded = asyncio.run_coroutine_threadsafe(self._layer.group_send(group, event), desktop_loop)
            await asyncio.wrap_future(forwarded)
        else:
            await self._layer.group_send(group, event)

    def __getattr__(self, name):
        return getattr(self._layer, name)


def _consumer_type():
    # Lazy import: the main consumer imports the independent guard at execution
    # entry. Importing this public module never initializes Django or a model.
    from .consumers import AgentConsumer

    class RemoteConsumer(AgentConsumer):
        async def send(self, text_data=None, bytes_data=None, close=False):
            # Catalog setup normally writes directly to the browser; it is not
            # an RC reply. Actual reply/permission frames travel through the
            # owned group proxy and are captured exactly once there.
            return None

        def _schedule_context_gauge_refresh(self, *args, **kwargs):
            # No local page/gauge was opened. Do not create a persistent sink
            # or make an extra model probe for a nonexistent remote gauge.
            return None

        def _restore_connection_gauge_sink(self):
            return None

        async def queue_llm_retrieval(self, message, conversation_user, multi_turn_enabled=False,
                                      exec_report_enabled=False, acpx_enabled=False,
                                      ask_execs_enabled=False, step_by_step_enabled=False,
                                      interactor_client_id="", canvas_explanation=None):
            self.rc_session._execution_task = asyncio.current_task()
            if self.rc_session._cancel_requested:
                return
            try:
                # Preserve the original consumer's positional API, then send
                # the explicitly selected execution modes downstream.
                await super().queue_llm_retrieval(
                    message, conversation_user,
                    multi_turn_enabled=self.rc_session.options["multi_turn_enabled"],
                    ask_execs_enabled=self.rc_session.options["ask_execs_enabled"],
                    exec_report_enabled=self.rc_session.options["exec_report_enabled"],
                    acpx_enabled=self.rc_session.options["acpx_enabled"],
                    step_by_step_enabled=(self.rc_session.options["step_by_step_enabled"]
                                          if "step_by_step_enabled" in self.rc_session.explicit_options
                                          else step_by_step_enabled),
                    interactor_client_id=interactor_client_id, canvas_explanation=canvas_explanation,
                )
            finally:
                self.rc_session._execution_finished.set()

        async def setup_rag_chain(self):
            task = asyncio.current_task()
            if task is not self.rc_session._run_task:
                self.rc_session._setup_tasks.add(task)
            try:
                return await super().setup_rag_chain()
            finally:
                self.rc_session._setup_tasks.discard(task)

    return RemoteConsumer


class RuntimeSession:
    """One operation; keep this object to answer its permission requests.

    ``on_progress`` is an async callable accepting a bounded JSON-safe object.
    Call all methods on the worker's event loop. ``request_cancel`` is synchronous;
    cancellation closes this session's broker and latches only its owned epoch.
    """

    def __init__(self, user, on_progress, options=None):
        self.options = execution_options(options)
        self.explicit_options = set(options or {})
        self.user = user
        self.on_progress = on_progress
        self.ready = False
        self.status = "created"
        self.error = None
        self._consumer = None
        self._execution_task = None
        self._preparation_task = None
        self._execution_finished = asyncio.Event()
        self._cancel_requested = False
        self._closed = False
        self._capturing = False
        self._used = False
        self._permission_ids: set[str] = set()
        self._final_message = None
        self._source_answer = None
        self._immediate_message = None
        self._progress_failed = False
        self._run_task = None
        self._setup_tasks = set()

    async def _emit(self, payload):
        if self._closed or self._progress_failed or self._cancel_requested:
            return
        try:
            if _wire_size(payload) > MAX_PROGRESS_BYTES:
                raise RuntimeFault("progress_too_large")
            pending = self.on_progress(payload)
            if inspect.isawaitable(pending):
                await pending
        except Exception:
            # A missing approval channel must deny, never leave the executor
            # parked indefinitely or turn a missing prompt into consent.
            self._progress_failed = True
            self.error = "progress_unavailable"
            self.request_cancel()

    async def _capture(self, event):
        if not self._capturing or self._closed:
            return
        kind = event.get("type")
        if kind == "exec_permission_request":
            detail = event.get("detail") or {}
            request_id = detail.get("request_id")
            if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
                self.request_cancel()
                raise RuntimeFault("invalid_permission_request")
            # These are the existing Ask Execs display fields, never commands
            # accepted by this adapter. A large prompt cannot be approved from
            # incomplete information: deny it and identify the truncation.
            safe = {"type": "permission", "request_id": request_id}
            truncated = False
            for key in ("tool_name", "agent_display", "kind", "program", "shell", "parameters"):
                safe[key], cut = _bounded_text(detail.get(key), 1600)
                truncated |= cut
            safe["truncated"] = truncated
            if truncated or len(self._permission_ids) >= 128:
                broker = getattr(self._consumer, "_active_broker", None)
                if broker is not None:
                    broker.resolve(request_id, "deny")
                safe["decision"] = "deny"
                if not truncated:
                    safe["reason"] = "permission_limit"
            else:
                self._permission_ids.add(request_id)
            await self._emit(safe)
        elif kind == "exec_permission_resolved":
            detail = event.get("detail") or {}
            request_id, decision = detail.get("request_id"), detail.get("decision")
            if (isinstance(request_id, str) and re.fullmatch(r"[0-9a-f]{32}", request_id)
                    and decision in {"proceed", "deny"}):
                self._permission_ids.discard(request_id)
                await self._emit({"type": "permission", "request_id": request_id,
                                  "decision": decision})
        elif kind == "agent_message" and event.get("username") == "Tlamatini":
            message_id = event.get("message_id")
            final = isinstance(message_id, int) and not isinstance(message_id, bool) and message_id > 0
            value = (self._source_answer if final and self._source_answer is not None
                     else _assistant_text(event.get("message")))
            text, truncated = _bounded_text(value)
            payload = {"type": "message", "text": text, "truncated": truncated}
            # The desktop history already owns the canonical HTML formatting.
            # Keep it intact instead of asking RC to reinterpret raw Markdown.
            from .remote_response_files import content_ticket, render_response
            rendered = await asyncio.to_thread(render_response, self.user.pk,
                                               message_id if final else None,
                                               str(event.get("message") or ""))
            rich = {**payload, "format": "html", "html": rendered, "truncated": False}
            if _wire_size(rich) <= MAX_RESULT_BYTES - 1024:
                payload = rich
            else:
                payload["truncated"] = True
                ticket = await asyncio.to_thread(content_ticket, self.user.pk,
                                                     message_id if final else None,
                                                     str(event.get("message") or ""))
                if ticket:
                    payload["content_ticket"] = ticket
            if final:
                payload["message_id"] = message_id
                self._final_message = dict(payload)
                self._source_answer = None
            self._immediate_message = dict(payload)
            # Progress has a smaller envelope. Never slice HTML mid-tag.
            progress = dict(payload)
            if _wire_size(progress) > MAX_PROGRESS_BYTES - 512:
                progress.pop("html", None)
                progress.pop("format", None)
                progress["truncated"] = True
            await self._emit(progress)

    async def respond_permission(self, request_id: str, decision: str) -> bool:
        if (self._closed or self._cancel_requested or decision not in {"proceed", "deny"}
                or request_id not in self._permission_ids):
            return False
        consumer = self._consumer
        if consumer is None or not owns_chat(self.user.pk, consumer):
            return False
        broker = getattr(consumer, "_active_broker", None)
        if broker is None:
            return False
        # Resolve the exact object we own, never the per-user registry lookup
        # which could point at a later operation after a reconnect.
        resolved = broker.resolve(request_id, decision)
        self._permission_ids.discard(request_id)
        return bool(resolved)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        consumer = self._consumer
        if consumer is None:
            return
        broker = getattr(consumer, "_active_broker", None)
        if broker is not None:
            broker.close()
        active = getattr(consumer, "_active_run", None)
        if active and owns_chat(self.user.pk, consumer):
            from .cancellation import clear_cancel_generation, current_run_epoch, request_cancel_generation
            if active[0] == self.user.pk and active[1] == current_run_epoch(self.user.pk):
                request_cancel_generation(self.user.pk)
                # The durable epoch remains latched. The legacy global flag
                # must not cancel another account's independent model request.
                clear_cancel_generation()

    async def _prepare(self):
        from channels.layers import get_channel_layer
        from .global_state import global_state

        consumer = _consumer_type()()
        self._consumer = consumer
        consumer.rc_session = self
        consumer.scope = {"type": "websocket", "user": self.user, "session": None}
        consumer.channel_name = "remote.controller." + uuid.uuid4().hex
        consumer.room_name = f"user_{self.user.pk}"
        consumer.room_group_name = f"chat_{consumer.room_name}"
        layer = get_channel_layer()
        if layer is None:
            raise RuntimeFault("application_unavailable")
        consumer.channel_layer = _OwnedChannelLayer(layer, consumer.room_group_name, self)
        if not reserve_chat(self.user.pk, consumer):
            raise RuntimeFault("account_busy")
        if "self_modify_enabled" in self.options:
            from . import compact_mode
            wanted = self.options["self_modify_enabled"]
            observe = getattr(compact_mode, "state", None)
            current = await asyncio.to_thread(observe) if callable(observe) else None
            # Write the shared desktop switch only when this request changes
            # it. A choice that is already in effect must not rewrite it.
            unchanged = (isinstance(current, dict)
                         and bool(current.get("self_modify")) is wanted
                         and (not wanted or (current.get("self_modify_available")
                                             and not current.get("self_modify_locked"))))
            if not unchanged:
                changed = await asyncio.to_thread(
                    compact_mode.set_self_modify, wanted,
                    f"Remote-Controller user {self.user.pk}",
                )
                if not changed.get("ok"):
                    raise RuntimeFault("self_modify_" + str(changed.get("refused") or "unavailable"))
        consumer.rag_chain = global_state.get_state(f"rag_chain_{self.user.pk}")
        if consumer.rag_chain is None:
            session_state = await consumer.get_session_state(self.user)
            if session_state and session_state.context_path and not session_state.is_expired():
                if session_state.context_type == "directory":
                    await consumer.setup_contextual_rag_chain(session_state.context_path)
                elif session_state.context_type == "file":
                    await consumer.setup_contextual_rag_chain(
                        session_state.context_path, session_state.context_filename,
                    )
                else:
                    raise RuntimeFault("context_unavailable")
            else:
                await consumer.setup_rag_chain()
        if consumer.rag_chain is None:
            raise RuntimeFault("model_unavailable")
        self.ready = True
        self.status = "ready"
        await self._emit({"type": "status", "status": "ready"})

    async def run(self, text: str, cancel_event=None):
        if self._used:
            raise RuntimeFault("session_already_used")
        self._used = True
        self._run_task = asyncio.current_task()
        if not getattr(self.user, "is_authenticated", False) or not getattr(self.user, "is_active", False):
            raise RuntimeFault("account_unavailable")
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise RuntimeFault("invalid_request")
        watcher = None
        try:
            self.status = "preparing"
            if cancel_event is not None:
                async def watch_cancel():
                    await cancel_event.wait()
                    self.request_cancel()
                watcher = asyncio.create_task(watch_cancel())
            self._preparation_task = asyncio.create_task(self._prepare())
            await asyncio.shield(self._preparation_task)
            if self._progress_failed:
                raise RuntimeFault("progress_unavailable")
            if self._cancel_requested:
                return {"text": "", "cancelled": True, "truncated": False}
            self.status = "running"
            self._capturing = True
            await self._consumer.receive(json.dumps({
                "message": text, **{key: self.options[key] for key in MODE_DEFAULTS},
            }))
            # receive schedules queue_llm_retrieval. Let that child register
            # before deciding whether this was the normal immediate greeting.
            await asyncio.sleep(0)
            if self._execution_task is not None:
                await asyncio.shield(self._execution_task)
                if getattr(self._consumer, "_rc_chat_claim_refused", False):
                    raise RuntimeFault("account_busy")
            if self._progress_failed:
                raise RuntimeFault("progress_unavailable")
            if self._cancel_requested:
                self.status = "cancelled"
                return {"text": "", "cancelled": True, "truncated": False}
            answer = self._final_message
            if answer is None and self._execution_task is None:
                from . import constants
                if re.match(constants.REGEX_GREETING, text, flags=re.IGNORECASE):
                    answer = self._immediate_message
            if answer is None:
                raise RuntimeFault("chat_no_answer")
            self.status = "completed"
            return {"text": answer["text"], "truncated": answer["truncated"],
                    **({"html": answer["html"], "format": "html"} if "html" in answer else {}),
                    **({"content_ticket": answer["content_ticket"]} if "content_ticket" in answer else {}),
                    "message_id": answer.get("message_id"), "cancelled": False,
                    "options": dict(self.options)}
        except asyncio.CancelledError:
            self.request_cancel()
            # Cancelling the awaiting coroutine cannot stop a sync model worker.
            # Retain ownership until its normal cancellation-aware path exits.
            if self._preparation_task is not None:
                await asyncio.shield(self._preparation_task)
            if self._execution_task is not None:
                await asyncio.shield(self._execution_task)
            self.status = "cancelled"
            raise
        except RuntimeFault as exc:
            self.error = exc.code
            self.status = "failed"
            raise
        except Exception as exc:
            self.error = "chat_failed"
            self.status = "failed"
            raise RuntimeFault("chat_failed") from exc
        finally:
            self.ready = False
            self._closed = True
            self._permission_ids.clear()
            if self._execution_task is not None and not self._execution_task.done():
                self.request_cancel()
                await asyncio.gather(asyncio.shield(self._execution_task), return_exceptions=True)
            if watcher is not None:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
            if self._consumer is not None:
                broker = getattr(self._consumer, "_active_broker", None)
                if broker is not None:
                    broker.close()
                if self._setup_tasks:
                    await asyncio.gather(*tuple(self._setup_tasks), return_exceptions=True)
                release_chat(self.user.pk, self._consumer)


async def execute_chat(user, text, on_progress, cancel_event=None):
    """Convenience for callers that only need chat and cancellation.

    Use RuntimeSession directly when permission replies need to be routed back.
    """
    return await RuntimeSession(user, on_progress).run(text, cancel_event)
