# Tlamatini Author Banner — Angela López Mendoza
"""Explicit, account-owned Canvas context snapshots.

Only documents selected by the browser are included. An open tab is not consent
to send its content. PDF text is resolved through its existing signed account
token. Every update gets a unique persistent file inside the application.
"""
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
import asyncio
import json
import logging
import os
import re
import uuid

MAX_DOCUMENTS = 32
MAX_CONTEXT_BYTES = 32 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_LOG = logging.getLogger(__name__)
LEGACY_CONTEXT_MESSAGES = frozenset({
    "set-pdf-canvas-as-context", "set-canvas-as-context", "unset-canvas-as-context",
    "set-directory-as-context", "set-file-as-context", "clear-context",
    "reconnect-llm-agent", "clean-history-and-reconnect",
})


class CanvasContextError(ValueError):
    pass


@dataclass(frozen=True)
class CanvasContextBundle:
    directory: Path
    filename: str
    documents: list

    def discard(self):
        # Delete only our one known generated file, never a recursive tree.
        (self.directory / self.filename).unlink(missing_ok=True)
        try:
            self.directory.rmdir()
        except OSError:
            pass


def valid_request_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _metadata(document):
    if not isinstance(document, dict):
        raise CanvasContextError("Each selected document must be an object.")
    identity = document.get("document_id")
    filename = document.get("filename")
    revision = document.get("revision")
    if not valid_request_id(identity):
        raise CanvasContextError("A selected document has an invalid identity.")
    if (not isinstance(filename, str) or not filename.strip() or len(filename) > 255
            or filename in {".", ".."} or re.search(r'[\\/\x00-\x1f\x7f<>:"|?*]', filename)):
        raise CanvasContextError("Use a document filename, never a path.")
    if (isinstance(revision, bool) or not isinstance(revision, int)
            or not 0 <= revision <= 9007199254740991):
        raise CanvasContextError("A selected document has an invalid revision.")
    if ("content" in document) == ("context_token" in document):
        raise CanvasContextError("Supply text or a prepared PDF token for each document.")
    return {"document_id": identity, "filename": filename, "revision": revision}


def build_canvas_context(documents, user_id, *, root=None, pdf_resolver=None):
    """Validate everything before writing; no caller-supplied filesystem path."""
    if (not isinstance(documents, list) or not documents or len(documents) > MAX_DOCUMENTS):
        raise CanvasContextError(f"Select between 1 and {MAX_DOCUMENTS} documents.")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        raise CanvasContextError("An authenticated account is required.")
    metadata = [_metadata(document) for document in documents]
    if len({item["document_id"] for item in metadata}) != len(metadata):
        raise CanvasContextError("The same document cannot be selected twice.")
    chunks = []
    total = 0
    for document, meta in zip(documents, metadata):
        if "content" in document:
            content = document["content"]
            if not isinstance(content, str):
                raise CanvasContextError("Document text must be a string.")
            try:
                body = content.encode("utf-8")
            except UnicodeError as exc:
                raise CanvasContextError("Document text is not valid Unicode.") from exc
        else:
            token = document["context_token"]
            if not isinstance(token, str) or not token or len(token) > 8192:
                raise CanvasContextError("The prepared PDF token is invalid.")
            if pdf_resolver is None:
                from .pdf_context import resolve_pdf_context
                pdf_resolver = resolve_pdf_context
            directory, filename = pdf_resolver(token, user_id)
            with (Path(directory) / filename).open("rb") as stream:
                body = stream.read(MAX_CONTEXT_BYTES - total + 1)
            try:
                body.decode("utf-8")
            except UnicodeError as exc:
                raise CanvasContextError("Prepared PDF context is not readable UTF-8.") from exc
        header = (f'\n===== CANVAS DOCUMENT: {meta["filename"]} =====\n'
                  f'Document ID: {meta["document_id"]}; revision: {meta["revision"]}\n').encode("utf-8")
        footer = b"\n===== END CANVAS DOCUMENT =====\n"
        total += len(header) + len(body) + len(footer)
        if total > MAX_CONTEXT_BYTES:
            raise CanvasContextError("Selected Canvas context exceeds 32 MiB. Select fewer documents.")
        chunks.extend((header, body, footer))
    if root is None:
        from .path_guard import get_runtime_agent_root
        root = get_runtime_agent_root()
    root = Path(root).resolve()
    owner = root / "context_files" / "canvas_tabs" / str(user_id)
    if not owner.resolve().is_relative_to(root):
        raise CanvasContextError("The application context directory is unavailable.")
    owner.mkdir(parents=True, exist_ok=True)
    directory = owner / uuid.uuid4().hex
    directory.mkdir()
    bundle = CanvasContextBundle(directory, "documents.txt", metadata)
    try:
        with (directory / bundle.filename).open("xb") as stream:
            for chunk in chunks:
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        bundle.discard()
        raise
    return bundle


async def context_result(consumer, request_id, success, documents=None, message=None):
    payload = {"type": "canvas-documents-context-result", "request_id": request_id,
               "success": success, "documents": documents or []}
    if message:
        payload["message"] = message
    await consumer.send(text_data=json.dumps(payload))


async def apply_canvas_documents(consumer, user, payload):
    """Own the account's execution lane through preparation, commit and reply.

    Reuse the desktop/remote chat guard with a distinct owner: a ready message
    from the rebuild cannot start a chat before the new selection is persisted.
    """
    from .remote_controller_guard import reserve_chat, release_chat
    owner = object()
    if not reserve_chat(user.pk, owner):
        await context_result(consumer, payload.get("request_id"), False,
                             message="Wait for the current account operation before changing context.")
        return
    consumer._canvas_context_owner = owner
    try:
        await _apply_canvas_documents_owned(consumer, user, payload)
    finally:
        release_chat(user.pk, owner)
        if getattr(consumer, "_canvas_context_owner", None) is owner:
            consumer._canvas_context_owner = None


async def _apply_canvas_documents_owned(consumer, user, payload):
    """Commit the selected set only after the real context chain is usable."""
    from .global_state import global_state
    request_id = payload.get("request_id")
    if not valid_request_id(request_id):
        await context_result(consumer, None, False, message="Invalid Canvas context request identity.")
        return
    documents = payload.get("documents")
    if not isinstance(documents, list) or len(documents) > MAX_DOCUMENTS:
        await context_result(consumer, request_id, False, message="Invalid selected Canvas documents.")
        return
    if getattr(consumer, "_active_run", None) or consumer.rag_lock.locked():
        await context_result(consumer, request_id, False, message="Wait for the current operation before changing context.")
        return
    previous_chain = consumer.rag_chain
    cache_key = f"rag_chain_{user.pk}"
    path_key = f"context_path_{user.pk}"
    previous_cache = global_state.get_state(cache_key)
    previous_path = global_state.get_state(path_key)
    bundle = None
    committed = False
    success = False
    try:
        if documents:
            preparation = asyncio.create_task(asyncio.to_thread(build_canvas_context, documents, user.pk))
            try:
                bundle = await asyncio.shield(preparation)
            except asyncio.CancelledError:
                # The worker owns one generated file. Wait for it so cancellation
                # cannot strand a partial or complete unpublished snapshot.
                bundle = await preparation
                raise
            success = await consumer.setup_contextual_rag_chain(str(bundle.directory), bundle.filename)
        else:
            success = await consumer.setup_rag_chain()
        if success is not True:
            raise CanvasContextError("The selected context could not be prepared. The previous context is retained.")
        if bundle:
            await consumer.save_session_state(user, str(bundle.directory), "file", bundle.filename)
            consumer._canvas_documents_metadata = bundle.documents
        else:
            await consumer.clear_session_state(user)
            consumer._canvas_documents_metadata = []
        # No await between publication and marking committed: reconnects see a
        # cache that agrees with the durable selection, never its preparation.
        global_state.set_state(cache_key, consumer.rag_chain)
        global_state.set_state(path_key, str(bundle.directory) if bundle else None)
        committed = True
        global_state.set_state("chat_hist_summarizer_counter", 0)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _LOG.warning("Canvas context selection failed for account %s: %s", user.pk, exc)
        await context_result(consumer, request_id, False, message=str(exc))
    finally:
        if not committed:
            consumer.rag_chain = previous_chain
            global_state.set_state(cache_key, previous_cache)
            global_state.set_state(path_key, previous_path)
            global_state.set_state("rag_chain_ready", previous_chain is not None)
            if bundle:
                bundle.discard()
    if committed:
        # Sending an acknowledgement may fail after a browser disconnect. That
        # does not undo an already persisted, successfully prepared selection.
        metadata = consumer._canvas_documents_metadata
        if bundle:
            await consumer.send(text_data=json.dumps({
                "type": "context-path-set",
                "context_path": str(bundle.directory / bundle.filename),
                "context_type": "file", "context_filename": bundle.filename,
                "canvas_documents": metadata, "request_id": request_id,
            }))
        await context_result(consumer, request_id, True, metadata)


async def begin_canvas_documents(consumer, user, payload):
    pending = getattr(consumer, "_canvas_documents_task", None)
    if pending and not pending.done():
        await context_result(consumer, payload.get("request_id"), False,
                             message="A Canvas context update is already running.")
        return
    async def run():
        try:
            await apply_canvas_documents(consumer, user, payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOG.exception("Canvas context acknowledgement failed.")
    consumer._canvas_documents_task = asyncio.create_task(run())


async def cancel_canvas_context_tasks(consumer):
    """Finish owned context work before disconnect, without awaiting ourselves."""
    for name in ("_canvas_documents_task", "_canvas_legacy_context_task"):
        pending = getattr(consumer, name, None)
        if pending and pending is not asyncio.current_task() and not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise


def serialize_context_mutations(receive):
    """Keep legacy context rebuilds in the same account lane as Canvas sets.

    Run the complete legacy operation in one tracked task so Channels can keep
    receiving cancellation/control messages while its awaited rebuild finishes.
    """
    @wraps(receive)
    async def dispatch(consumer, text_data):
        try:
            payload = json.loads(text_data)
        except (TypeError, ValueError):
            return await receive(consumer, text_data)
        message_type = payload.get("type") if isinstance(payload, dict) else None
        user = consumer.scope.get("user")
        if (not isinstance(message_type, str) or message_type not in LEGACY_CONTEXT_MESSAGES
                or user is None or not getattr(user, "is_authenticated", False)):
            return await receive(consumer, text_data)
        from . import constants
        from .remote_controller_guard import chat_busy, owns_chat, reserve_chat, release_chat
        async def refuse():
            await consumer.agent_message({"username": "Tlamatini",
                                          "message": consumer._say(constants.MSG_ACCOUNT_BUSY)})
        context_owner = getattr(consumer, "_canvas_context_owner", None)
        if chat_busy(user.pk) and not (context_owner and owns_chat(user.pk, context_owner)):
            await refuse()
            return None
        pending = getattr(consumer, "_canvas_documents_task", None)
        if pending and not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
        # Recheck atomically after rollback; another browser may have reserved
        # the account while cancellation was awaited. It wins in that case.
        owner = object()
        if not reserve_chat(user.pk, owner):
            await refuse()
            return None
        consumer._canvas_mutation_owner = owner
        consumer._canvas_documents_metadata = []
        def release():
            release_chat(user.pk, owner)
            if getattr(consumer, "_canvas_mutation_owner", None) is owner:
                consumer._canvas_mutation_owner = None
        async def run():
            try:
                await receive(consumer, text_data)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOG.exception("Legacy context update failed for account %s.", user.pk)
            finally:
                release()
        try:
            task = asyncio.create_task(run())
        except BaseException:
            release()
            raise
        consumer._canvas_legacy_context_task = task
        # A task cancelled before its first instruction never enters finally.
        task.add_done_callback(lambda _task: release())
        return None
    return dispatch
