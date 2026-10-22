# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Native canvas saves: a selected destination is an expiring capability.

The browser sends bytes, never a writable host path. Save As grants access via
the native dialog. Later Save/Refresh calls need that session's random token.
An optimistic content revision prevents overwriting changes from other editors.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import queue
import secrets
import stat
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from django.http import HttpResponse, JsonResponse
from django.utils.http import content_disposition_header

from . import native_dialogs

logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 64 * 1024 * 1024
TOKEN_TTL = 12 * 60 * 60
MAX_CAPABILITIES = 512
_CAPABILITIES: OrderedDict[str, "Capability"] = OrderedDict()
_CAP_LOCK = threading.Lock()
_IO_LOCK = threading.Lock()
_PICKER_LOCK = threading.Lock()


@dataclass
class Capability:
    owner: tuple[str, str]
    path: Path
    touched: float


class SaveError(Exception):
    def __init__(self, message, code="invalid", status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def _response(payload, status=200):
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _bound_body(request, limit):
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError) as exc:
        raise SaveError("The request size is invalid.") from exc
    if length < 0 or length > limit:
        raise SaveError("This request exceeds the native-save size limit.", "too_large", 413)


def _owner(request):
    try:
        local = ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
    except ValueError:
        local = False
    if not local:
        raise SaveError("Native Save As is available on the computer running Tlamatini.", "local_only", 403)
    key = getattr(request.session, "session_key", None)
    if not request.user.is_authenticated or not key:
        raise SaveError("Sign in again before saving this file.", "session", 403)
    return str(request.user.pk), key


def _capability(token, owner):
    with _CAP_LOCK:
        now = time.monotonic()
        for old_token, item in list(_CAPABILITIES.items()):
            if now - item.touched > TOKEN_TTL:
                del _CAPABILITIES[old_token]
        item = _CAPABILITIES.get(token)
        if item is None or item.owner != owner:
            raise SaveError("This file's save access expired. Use Save as to choose it again.", "expired", 403)
        item.touched = now
        _CAPABILITIES.move_to_end(token)
        return item


def _grant(path, owner):
    token = secrets.token_urlsafe(32)
    with _CAP_LOCK:
        _CAPABILITIES[token] = Capability(owner, path, time.monotonic())
        while len(_CAPABILITIES) > MAX_CAPABILITIES:
            _CAPABILITIES.popitem(last=False)
    return token


def _check_path(path):
    # The capability names the resolved destination. A parent replaced by a
    # junction/symlink must not redirect subsequent writes to another location.
    if path.resolve() != path or path.is_symlink():
        raise SaveError("The destination moved or became a link. Choose it again with Save as.", "conflict", 409)
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SaveError("Choose an ordinary file, rather than a folder or link.")


def _snapshot(path):
    _check_path(path)
    try:
        with path.open("rb") as stream:
            if os.fstat(stream.fileno()).st_size > MAX_FILE_BYTES:
                raise SaveError("This file exceeds the 64 MiB native-save limit.", "too_large", 413)
            data = stream.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        return None, "missing"
    if len(data) > MAX_FILE_BYTES:
        raise SaveError("This file exceeds the 64 MiB native-save limit.", "too_large", 413)
    return data, hashlib.sha256(data).hexdigest()


def _remove_save_temporary(path):
    """Best-effort cleanup of a staging/backup file created by this save only."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except PermissionError:
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(path)
        except OSError:
            logger.warning("[CANVAS-SAVE] Could not remove save temporary %s", path)
    except OSError:
        logger.warning("[CANVAS-SAVE] Could not remove save temporary %s", path)


def _win_replace_file(path, temporary, backup):
    """Replace data while retaining the destination's Windows file metadata."""
    import ctypes
    from ctypes import wintypes

    def native_path(value):
        value = str(value)
        if value.startswith("\\\\?\\"):
            return value
        return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    replace = kernel32.ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    # Do not ignore metadata/ACL merge failures. The backup makes the original
    # recoverable even for ReplaceFileW's partial-failure codes 1176 and 1177.
    if not replace(native_path(path), native_path(temporary), native_path(backup), 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def _replace_existing_windows(path, temporary):
    descriptor, backup_name = tempfile.mkstemp(prefix=".tlamatini-backup-", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    backup = Path(backup_name)
    backup.unlink()  # Reserve a unique name; ReplaceFileW creates the backup.
    try:
        _win_replace_file(path, temporary, backup)
    except OSError as error:
        # 1175/1176 leave the original at its old name; 1177 can move it to
        # backup. Recover only into an absent name: never clobber a third-party
        # file that appeared meanwhile. Windows rename fails if it now exists.
        if backup.exists() and not path.exists():
            try:
                os.rename(backup, path)
            except OSError as recovery_error:
                raise OSError(f"The save failed and its original could not be restored. "
                              f"The original is preserved at {backup}. "
                              f"Recovery error: {recovery_error}") from error
        if backup.exists():
            # An unexpected partial outcome is not permission to erase the
            # recovery copy. Surface its exact path for the user.
            raise OSError(f"The save failed. Its original recovery copy is preserved at {backup}. "
                          f"Windows error: {error}") from error
        raise
    else:
        _remove_save_temporary(backup)


def _replace_destination(path, temporary, existing):
    if existing and os.name == "nt":
        _replace_existing_windows(path, temporary)
    else:
        os.replace(temporary, path)


def _commit(path, data, revision):
    """Stage beside the destination, then replace only the expected contents.

    The sibling is a save transaction, not application scratch: staying on the
    target volume is necessary for an atomic replacement. It is always removed.
    """
    _old, current = _snapshot(path)
    if current != revision:
        raise SaveError("This file changed outside the canvas. Refresh it or use Save as to keep your edits.", "conflict", 409)
    descriptor, temporary = tempfile.mkstemp(prefix=".tlamatini-save-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        _old, current = _snapshot(path)
        if current != revision:
            raise SaveError("This file changed while saving. Refresh it or use Save as to keep your edits.", "conflict", 409)
        _replace_destination(path, temporary, current != "missing")
    finally:
        _remove_save_temporary(temporary)
    return hashlib.sha256(data).hexdigest()


def _pick(filename):
    """Own an STA thread, matching the established native picker architecture."""
    if not native_dialogs.is_supported():
        raise SaveError("Native Save As requires Windows. Choose a browser save location instead.", "non_windows", 503)
    if not _PICKER_LOCK.acquire(blocking=False):
        raise SaveError("A Save As window is already open. Finish or cancel it first.", "busy", 409)
    results = queue.Queue()

    def choose():
        try:
            results.put((native_dialogs.pick_save_file("Save canvas file as", filename), None))
        except Exception as exc:  # pass errors back to the request, never lose them in a thread
            results.put((None, exc))

    try:
        worker = threading.Thread(target=choose, name="tlamatini-canvas-save-picker", daemon=True)
        worker.start()
        worker.join()
        selected, error = results.get_nowait()
        if error:
            raise error
        return selected
    finally:
        _PICKER_LOCK.release()


def _filename(upload):
    # Suggested name only. No directory, ADS, device prefix or embedded NUL may
    # become an initial path; the native dialog chooses the actual destination.
    name = str(upload.name or "untitled.txt").replace("\\", "/").rsplit("/", 1)[-1]
    if not name or len(name) > 240 or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name):
        raise SaveError("Choose a valid file name.")
    return name


def save(request):
    """POST multipart ``file``, optional ``token`` and matching ``revision``."""
    try:
        owner = _owner(request)
        _bound_body(request, MAX_FILE_BYTES + 65536)
        if request.POST.get("path"):
            raise SaveError("Choose the destination in Save As; a browser path is not accepted.")
        upload = request.FILES.get("file")
        if upload is None:
            raise SaveError("No file content was supplied.")
        if upload.size > MAX_FILE_BYTES:
            raise SaveError("Native saves support files up to 64 MiB.", "too_large", 413)
        data = upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise SaveError("Native saves support files up to 64 MiB.", "too_large", 413)
        filename = _filename(upload)
        token = request.POST.get("token", "")
        if token:
            path = _capability(token, owner).path
            revision = request.POST.get("revision", "")
            if not revision or revision == "missing":
                raise SaveError("The file revision is missing. Refresh it or use Save as.", "conflict", 409)
        else:
            selected = _pick(filename)
            if not selected:
                return _response({"saved": False, "canceled": True})
            path = Path(selected)
            if not path.is_absolute() or path.is_symlink():
                raise SaveError("Choose an absolute destination that is not a link.")
            path = path.resolve()
            with _IO_LOCK:
                _previous, revision = _snapshot(path)
        with _IO_LOCK:
            revision = _commit(path, data, revision)
            if not token:
                token = _grant(path, owner)
        logger.info("[CANVAS-SAVE] Saved %s bytes for user %s", len(data), request.user.pk)
        return _response({"saved": True, "token": token, "revision": revision,
                          "filename": path.name, "path": str(path), "bytes": len(data)})
    except SaveError as exc:
        return _response({"saved": False, "error": str(exc), "code": exc.code}, exc.status)
    except native_dialogs.NativeDialogUnavailable:
        return _response({"saved": False, "error": "The native Save As dialog is unavailable.", "code": "unavailable"}, 503)
    except (OSError, RuntimeError) as exc:
        logger.warning("[CANVAS-SAVE] Save failed: %s", exc)
        return _response({"saved": False, "error": "Could not save the file: " + str(exc), "code": "write_failed"}, 400)


def read(request):
    """POST ``token`` to read only a destination this session already chose."""
    try:
        owner = _owner(request)
        _bound_body(request, 8192)
        path = _capability(request.POST.get("token", ""), owner).path
        with _IO_LOCK:
            data, revision = _snapshot(path)
        if data is None:
            raise SaveError("The saved file was moved or deleted.", "missing", 404)
        response = HttpResponse(data, content_type="application/octet-stream")
        response["Cache-Control"] = "no-store"
        response["Content-Disposition"] = content_disposition_header(True, path.name)
        response["X-Canvas-Revision"] = revision
        return response
    except SaveError as exc:
        return _response({"error": str(exc), "code": exc.code}, exc.status)
    except OSError as exc:
        return _response({"error": "Could not read the saved file: " + str(exc), "code": "read_failed"}, 400)
