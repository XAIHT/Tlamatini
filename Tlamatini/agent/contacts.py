# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tlamatini Contacts book — resolve a person's NAME to their messaging handles.

A small, config-driven directory so the user can say "send a WhatsApp / Telegram
to <name>" instead of pasting a phone number or @username every time. It is the
contacts analogue of ``external_mcps.json``: a plain JSON file resolved NEXT TO
``config.json`` (``CONFIG_PATH`` > frozen install root > source ``agent/``), so it
is USER STATE that survives a self-update.

Shape (``contacts.json``)::

    {
      "contacts": [
        {"name": "Ana Ricardo Lazcano",
         "aliases": ["Ana", "Ana Lazcano"],
         "telegram": "@ana_lazcano",      # @username, +phone, or numeric id
         "whatsapp": "+5215555555555",    # phone with country code
         "email": "ana@example.com"}
      ]
    }

The two messaging agents (Telegrammer / Whatsapper) carry an INLINE copy of this
resolver, because they are self-contained pool subprocesses that cannot import
``agent.*``. Keep ``agents/telegrammer/telegrammer.py::_resolve_contact`` and
``agents/whatsapper/whatsapper.py::_resolve_contact`` in sync with
``resolve_contact()`` here. This module is the Django-side source of truth plus
the LLM-/UI-facing helpers.
"""
from __future__ import annotations

import json
import os
import sys
import unicodedata
from typing import Any, Dict, List, Optional

CONTACTS_FILENAME = "contacts.json"
# Channels we know how to resolve -> the contact field that holds the identifier.
CONTACT_CHANNELS = ("telegram", "whatsapp", "email")


def get_contacts_path() -> str:
    """Resolve ``contacts.json`` next to ``config.json`` (CONFIG_PATH > frozen > source)."""
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path:
        base = os.path.dirname(env_path)
    elif getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, CONTACTS_FILENAME)


def _norm(value: Any) -> str:
    """Lower-case, collapse whitespace, and STRIP ACCENTS — forgiving, accent-
    insensitive name matching (so 'angela lopez mendoza' finds 'Ángela López
    Mendoza', and 'COCHAmpi' finds 'Cochampi')."""
    s = " ".join(str(value or "").strip().lower().split())
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _contact_names(contact: Dict[str, Any]) -> List[str]:
    raw = [contact.get("name", "")] + list(contact.get("aliases", []) or [])
    return [_norm(n) for n in raw if str(n or "").strip()]


def load_contacts() -> List[Dict[str, Any]]:
    """Return the contacts list. Fail-open to ``[]`` (BOM-tolerant read)."""
    try:
        with open(get_contacts_path(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception:
        return []
    if isinstance(data, dict):
        contacts = data.get("contacts", [])
    elif isinstance(data, list):
        contacts = data
    else:
        contacts = []
    return [c for c in contacts if isinstance(c, dict)]


def find_contact(query: str) -> Optional[Dict[str, Any]]:
    """First contact whose name/alias matches ``query`` (exact first, then fuzzy)."""
    q = _norm(query)
    if not q:
        return None
    contacts = load_contacts()
    # 1) exact name/alias match (deterministic).
    for contact in contacts:
        if q in _contact_names(contact):
            return contact
    # 2) forgiving: substring either way, or every query token present in a name
    #    (so "ana lazcano" finds "Ana Ricardo Lazcano").
    for contact in contacts:
        for name in _contact_names(contact):
            tokens = name.split()
            if q in name or name in q or (q.split() and all(t in tokens for t in q.split())):
                return contact
    return None


def resolve_contact(query: str, channel: str) -> Optional[str]:
    """Return the contact's identifier for ``channel`` (telegram/whatsapp/email), or None."""
    contact = find_contact(query)
    if not contact:
        return None
    value = contact.get(channel)
    value = str(value).strip() if value is not None else ""
    return value or None


def list_contacts() -> List[Dict[str, str]]:
    """Compact summary for the LLM / UI: name + which channels are populated."""
    summary: List[Dict[str, str]] = []
    for contact in load_contacts():
        summary.append({
            "name": str(contact.get("name", "")).strip(),
            "aliases": ", ".join(str(a) for a in (contact.get("aliases") or [])),
            "telegram": str(contact.get("telegram", "")).strip(),
            "whatsapp": str(contact.get("whatsapp", "")).strip(),
            "email": str(contact.get("email", "")).strip(),
        })
    return summary


def list_contacts_full() -> List[Dict[str, str]]:
    """Full per-contact view for the CRUD dialog (aliases joined, note included)."""
    rows: List[Dict[str, str]] = []
    for contact in load_contacts():
        rows.append({
            "name": str(contact.get("name", "")).strip(),
            "aliases": ", ".join(str(a) for a in (contact.get("aliases") or [])),
            "telegram": str(contact.get("telegram", "")).strip(),
            "whatsapp": str(contact.get("whatsapp", "")).strip(),
            "email": str(contact.get("email", "")).strip(),
            "note": str(contact.get("note", "")).strip(),
        })
    return rows


def _read_raw_contacts_doc() -> Dict[str, Any]:
    """Read the raw contacts document (to preserve ``_README`` etc.). Fail-open."""
    try:
        with open(get_contacts_path(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _clean_contact(entry: Any) -> Optional[Dict[str, Any]]:
    """Normalize one posted contact; drop it entirely if it has no usable name."""
    if not isinstance(entry, dict):
        return None
    name = str(entry.get("name", "")).strip()
    if not name:
        return None
    cleaned: Dict[str, Any] = {"name": name}
    aliases = entry.get("aliases", [])
    if isinstance(aliases, str):
        aliases = aliases.split(",")
    if isinstance(aliases, list):
        cleaned["aliases"] = [str(a).strip() for a in aliases if str(a).strip()]
    for field in ("telegram", "whatsapp", "email", "note"):
        value = str(entry.get(field, "")).strip()
        if value:
            cleaned[field] = value
    return cleaned


def save_contacts(contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist the full contacts list to ``contacts.json`` (preserving ``_README``).

    Every kept entry must have a non-empty ``name``; nameless entries are dropped.
    Writes atomically (temp file + ``os.replace``). Returns a small envelope
    ``{"ok": True, "count": n}`` or ``{"ok": False, "error": ...}``.
    """
    if not isinstance(contacts, list):
        return {"ok": False, "error": "contacts must be a list"}
    cleaned = [c for c in (_clean_contact(e) for e in contacts) if c]
    doc = _read_raw_contacts_doc()
    if not isinstance(doc, dict):
        doc = {}
    doc["contacts"] = cleaned
    path = get_contacts_path()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "count": len(cleaned)}


# Export the resolved path so spawned pool agents (Telegrammer / Whatsapper) can
# find contacts.json via the inherited environment, exactly like TLAMATINI_TEMP.
try:
    os.environ.setdefault("TLAMATINI_CONTACTS", get_contacts_path())
except Exception:
    pass
