# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Small, explicit wire contract. Positions are CodeMirror/JavaScript UTF-16 offsets."""
from __future__ import annotations

MAX_UNITS = 262_144
MAX_FRAME = 2 * 1024 * 1024
MAX_INSERT = 2_000


class InteractorError(Exception):
    def __init__(self, message, code="refused"):
        super().__init__(message)
        self.code = code


def units(text):
    return len(text.encode("utf-16-le")) // 2


def splice(text, start, end, insert):
    raw = text.encode("utf-16-le")
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(raw) // 2:
        raise InteractorError("Use the UTF-16 start/end offsets returned by read.")
    try:
        return (raw[:start * 2] + insert.encode("utf-16-le") + raw[end * 2:]).decode("utf-16-le")
    except UnicodeError as exc:
        raise InteractorError("An edit cannot split a Unicode character.") from exc


def snapshot(value):
    if not isinstance(value, dict):
        raise InteractorError("The editor did not return a document snapshot.", "invalid_reply")
    text = value.get("text")
    if not isinstance(text, str) or units(text) > MAX_UNITS:
        raise InteractorError("Live tutoring supports up to 256 Ki UTF-16 characters; no content was truncated.", "too_large")
    document_id, revision = value.get("document_id"), value.get("revision")
    if not isinstance(document_id, str) or not 1 <= len(document_id) <= 96 or type(revision) is not int or revision < 0:
        raise InteractorError("Invalid editor revision.", "invalid_reply")
    selection = value.get("selection", {})
    if not isinstance(selection, dict):
        raise InteractorError("Invalid editor selection.", "invalid_reply")
    start, end = selection.get("from"), selection.get("to")
    splice(text, start, end, "")
    return {"document_id": document_id, "revision": revision, "text": text,
            "filename": str(value.get("filename", ""))[:255],
            "language": str(value.get("language", ""))[:64],
            "active": value.get("active") is True, "dirty": value.get("dirty") is True,
            "busy": value.get("busy") is True,
            "selection": {"from": start, "to": end},
            "guide": value.get("guide") if isinstance(value.get("guide"), dict) else None,
            "offset_unit": "UTF-16", "truncated": False, "source": "live_editor"}


def expect(current, document_id, revision):
    if current["document_id"] != document_id or current["revision"] != revision:
        raise InteractorError("The document ID or revision does not match. Read the live editor again and review its current text before proposing another edit; omit IDs to use that fresh read.", "conflict")
