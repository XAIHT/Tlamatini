# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Closed, interactive account-wizard handoff for the shipped catalog card.

This is deliberately not an interpreter of user commands. Only an exact shipped
card (apart from its username field) enters this path. It opens this application's
own Django command, then returns control to the human; no LLM, screenshot worker,
password collection or wait-for-agent loop belongs in that interaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape, unescape
from importlib import import_module
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import unicodedata
import uuid

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_sessions: dict = {}
_pending: dict = {}
_NAME_LINE = re.compile(r"(?m)^Username:[ \t]*([^\r\n]*)")
_LEGACY_NAME = re.compile(r'\A(Tlamatini, help me step by step to create a NEW user \(a login account\) for you, named ")([^"\r\n]*)("\.)')
_USERNAME = re.compile(r"[\w.@+-]{1,150}\Z", re.UNICODE)
_ASK_NAME = "Enter the username"


def _normal(text):
    return " ".join(unicodedata.normalize("NFC", str(text)).split())


def _known_cards():
    legacy = import_module("agent.migrations.0219_user_wizard_graphical_notifications")
    yield legacy.OLD_WIZARD_PROMPT
    yield legacy.WIZARD_PROMPT
    current = import_module("agent.migrations.0223_create_superuser_console_handoff")
    yield current.WIZARD_PROMPT


def _card_shape(text):
    field = _NAME_LINE.search(text)
    if field is not None:
        if len(_NAME_LINE.findall(text)) != 1:
            return None, None
        start, end = field.span(1)
    else:
        field = _LEGACY_NAME.search(text)
        if field is None:
            return None, None
        start, end = field.span(2)
    return _normal(text[:start] + "<username>" + text[end:]), text[start:end].strip()


def catalog_request(text) -> tuple[bool, str | None]:
    """Recognize the whole known card, never a quoted example or keyword alone."""
    if not isinstance(text, str):
        return False, None
    shape, username = _card_shape(text)
    if shape is None or not any(shape == _card_shape(card)[0] for card in _known_cards()):
        return False, None
    if not username or username.startswith("[["):
        return True, None
    return True, username


def _valid_username(username):
    return isinstance(username, str) and _USERNAME.fullmatch(username) is not None


def live_pids():
    """Protect interactive consoles through owned live handles, never stale PIDs."""
    with _lock:
        return {session["process"].pid for session in _sessions.values()
                if session["process"].poll() is None}


def _authorized_user(user_id):
    from django.contrib.auth import get_user_model
    if user_id is None or isinstance(user_id, bool):
        return False
    try:
        return get_user_model().objects.filter(pk=user_id, is_active=True).exists()
    except (TypeError, ValueError):
        return False


def management_command() -> tuple[list[str], str]:
    """Derive trusted argv from this runtime; nothing comes from chat or PATH."""
    executable = str(Path(sys.executable).resolve())
    if getattr(sys, "frozen", False):
        return [executable, "createuserconsole"], str(Path(executable).parent)
    django_root = Path(__file__).resolve().parents[1]
    return [executable, str(django_root / "manage.py"), "createuserconsole"], str(django_root)


def _focus_owned_console(session):
    """Best effort: focus only a living owned console with its unique marker."""
    if os.name != "nt" or session["process"].poll() is not None:
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]

    def find(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
            user32.GetWindowTextW(hwnd, title, len(title))
            if session["id"] in title.value:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return False
        return True

    callback = callback_type(find)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows(callback, 0)


def _launch_console(user_id, username):
    argv, cwd = management_command()
    if os.name != "nt":
        raise OSError("This edition's console wizard requires Windows.")
    if not Path(argv[0]).is_file() or (len(argv) == 3 and not Path(argv[1]).is_file()):
        raise OSError("This instance's executable was not found.")
    environment = os.environ.copy()
    marker = uuid.uuid4().hex
    environment["TLAMATINI_USER_WIZARD"] = "1"
    environment["TLAMATINI_USER_WIZARD_ID"] = marker
    process = subprocess.Popen(
        argv, cwd=cwd, env=environment, shell=False,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    session = {"process": process, "id": marker, "username": username,
               "started": datetime.now(timezone.utc), "argv": argv, "cwd": cwd}
    _sessions[user_id] = session
    logger.info("[USER-WIZARD] requested interactive console pid=%s id=%s", process.pid, marker)
    return session


def _normalized_reply(text):
    # The DB history loader strips HTML; END-RESPONSE is also removed for display.
    return _normal(unescape(re.sub(r"<[^>]+>", "", str(text))).replace("END-RESPONSE", ""))


def _last_assistant_reply(history, current_text):
    messages = []
    for item in history or ():
        if isinstance(item, dict):
            role, content = item.get("type", item.get("role", "")), item.get("content", "")
        else:
            role, content = getattr(item, "type", ""), getattr(item, "content", "")
        if role in ("human", "user", "ai", "assistant"):
            messages.append((role, str(content)))
    if (messages and messages[-1][0] in ("human", "user")
            and _normalized_reply(messages[-1][1]) == _normalized_reply(current_text)):
        messages.pop()
    if not messages or messages[-1][0] not in ("ai", "assistant"):
        return None
    return _normalized_reply(messages[-1][1])


def _owns_reply(state, history, current_text):
    return (isinstance(state, dict) and bool(state.get("last_reply"))
            and _last_assistant_reply(history, current_text) == state["last_reply"])


def _status_kind(text):
    value = text.strip().upper()
    prefix = value.partition(":")[0]
    if prefix in ("HECHO", "DONE"):
        return "done"
    if prefix == "ERROR":
        return "error"
    if value in ("SIN VENTANA", "NOWINDOW"):
        return "nowindow"
    return None


def request_candidate(text, *, user_id, multi_turn_enabled=False):
    """Cheap admission only; handle_request still verifies history and authority."""
    if not multi_turn_enabled or not isinstance(text, str):
        return False
    if catalog_request(text)[0]:
        return True
    with _lock:
        pending = _pending.get(user_id)
        session = _sessions.get(user_id)
    if pending:
        # A malformed answer must reach the name validator, not the LLM.
        return True
    return bool(session and session.get("awaiting_reply", True) and _status_kind(text))


def _retire_context(user_id, session=None):
    with _lock:
        _pending.pop(user_id, None)
        if session is not None:
            # Retain the live process handle for cleanup ownership, independently
            # of whether this wizard still owns the next conversation response.
            session["awaiting_reply"] = False


def _result(output, *, status="waiting_for_user", session=None, denied=None, user_id=None):
    metadata = {"multi_turn_used": True, "exec_report_enabled": False,
                "tool_calls_log": [], "exec_report_entries": [],
                "exec_report_denied": denied, "user_creation_wizard": {"status": status}}
    if session:
        metadata["user_creation_wizard"].update(pid=session["process"].pid, console_id=session["id"])
        session["last_reply"] = _normalized_reply(output)
        session["awaiting_reply"] = status != "completed"
    if status == "username_required" and user_id is not None:
        with _lock:
            _pending[user_id] = {"last_reply": _normalized_reply(output)}
    return {"output": output + "\nEND-RESPONSE", "metadata": metadata}


def _previous_exchange(history, current_text):
    items = []
    for item in history or ():
        if isinstance(item, dict):
            role = item.get("type", item.get("role", ""))
            content = item.get("content", "")
        else:
            role, content = getattr(item, "type", ""), getattr(item, "content", "")
        if role in ("human", "user", "ai", "assistant"):
            items.append((role, str(content)))
    if items and items[-1][0] in ("human", "user") and items[-1][1].strip() == current_text.strip():
        items.pop()
    if len(items) < 2 or items[-1][0] not in ("ai", "assistant"):
        return False
    previous = items[-2]
    match, name = catalog_request(previous[1])
    return (previous[0] in ("human", "user") and match and not _valid_username(name)
            and _ASK_NAME in items[-1][1])


def _created_account(session):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(
        username=session["username"], is_active=True, is_superuser=True,
        date_joined__gte=session["started"],
    ).exists()


def handle_request(text, *, user_id, chat_history=(), multi_turn_enabled=False,
                   ask_execs_enabled=False, run_epoch=None):
    """Return a deterministic result for this wizard, or None for ordinary chat."""
    if not multi_turn_enabled or not isinstance(text, str):
        return None
    matched, username = catalog_request(text)
    with _lock:
        pending = _pending.get(user_id)
        session = _sessions.get(user_id)
    continuation = _status_kind(text)
    name_reply = bool(pending and (
        _owns_reply(pending, chat_history, text)
        or (pending is True and _previous_exchange(chat_history, text))))
    status_reply = bool(session and session.get("awaiting_reply", True)
                        and continuation and _owns_reply(session, chat_history, text))
    if not matched and not name_reply and not status_reply:
        if pending or session:
            _retire_context(user_id, session)
        return None
    if not _authorized_user(user_id):
        _retire_context(user_id, session)
        return _result("I cannot open the console without an active signed-in user.", status="refused")
    from .cancellation import is_run_cancelled
    if is_run_cancelled(user_id, run_epoch):
        _retire_context(user_id, session)
        return _result("The request was cancelled; I did not open another console.", status="cancelled")
    if status_reply and not matched:
        if continuation == "done":
            if _created_account(session):
                return _result("Administrative user <b>" + escape(session["username"])
                               + "</b> created and verified in this instance. You can sign out "
                               "and sign in with it at this same address, without restarting.", status="completed",
                               session=session)
            return _result("Account creation is not yet confirmed in this instance. Complete "
                           "the console; reply DONE after it confirms success, or ERROR with the "
                           "message without your password.", session=session)
        if continuation == "nowindow":
            try:
                _focus_owned_console(session)
            except OSError:
                logger.exception("[USER-WIZARD] could not focus the owned console")
            return _result("I tried to bring the existing console forward; I did not open another. "
                           "Look for Tlamatini's user-creation window. If it "
                           "closed, send the card again to retry.", session=session)
        return _result("Account creation is not confirmed. Read the console error and correct "
                       "the requested field; do not enter your password in chat. I did not open another "
                       "window.", status="error_reported", session=session)
    if name_reply:
        username = text.strip()
    if username is None or not _valid_username(username):
        return _result(_ASK_NAME + " (1–150 letters, numbers or @ . + - _). "
                       "This account will have administrative permissions. Enter your password "
                       "only in the console.", status="username_required", user_id=user_id)
    with _lock:
        if session and session["process"].poll() is None:
            try:
                _focus_owned_console(session)
            except OSError:
                logger.exception("[USER-WIZARD] could not focus the owned console")
            return _result("A user-creation console is already open for this session. "
                           "Complete its fields and reply DONE after success; I did not open another.",
                           session=session)
    if ask_execs_enabled:
        from .exec_permission import get_broker
        argv, _ = management_command()
        detail = {"tool_name": "user_creation_console", "agent_display": "Create user",
                  "kind": "Wizard", "program": subprocess.list2cmdline(argv),
                  "shell": "native", "parameters": "createsuperuser (interactive)"}
        broker = get_broker(user_id)
        if broker is None or broker.request_permission(detail) != "proceed":
            _retire_context(user_id, session)
            return _result("I did not open the console: execution was not authorized.", status="denied", denied=detail)
    if is_run_cancelled(user_id, run_epoch):
        _retire_context(user_id, session)
        return _result("The request was cancelled; I did not open another console.", status="cancelled")
    with _lock:
        session = _sessions.get(user_id)
        if session is None or session["process"].poll() is not None:
            try:
                session = _launch_console(user_id, username)
            except OSError as error:
                logger.exception("[USER-WIZARD] launch failed")
                return _result("I could not open this instance's console: " + escape(str(error)),
                               status="launch_failed")
        _pending.pop(user_id, None)
        username = session["username"]
    return _result("I requested this instance's interactive user-creation console. "
                   "Enter <b>" + escape(username) + "</b>, the email and the password there. "
                   "I am waiting for your reply: <b>DONE</b> after it confirms creation, "
                   "<b>ERROR</b> with the non-secret error, or <b>NOWINDOW</b> if it does not appear. "
                   "The account is not yet confirmed.", session=session)
