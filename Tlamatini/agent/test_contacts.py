# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the Contacts book (agent/contacts.py) — name -> messaging handle.

Reproduces Angela's use case ("send a WhatsApp and a Telegram to Ana Ricardo
Lazcano"): a person's NAME resolves to their Telegram handle + WhatsApp number.
The two pool agents (Telegrammer / Whatsapper) carry an INLINE copy of this
resolver; this suite pins the shared logic AND that the shipped contacts.json is
valid and resolvable.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from agent import contacts

_SAMPLE = {
    "contacts": [
        {"name": "Ana Ricardo Lazcano", "aliases": ["Ana", "Ana Lazcano"],
         "telegram": "@ana_lazcano", "whatsapp": "+5215555555555"},
        {"name": "Bob Stone", "telegram": "@bobstone", "whatsapp": "+15551230000"},
    ]
}


class _TempContacts:
    """Context manager: point contacts.get_contacts_path at a temp contacts.json."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        self._dir = tempfile.mkdtemp(prefix="tlam_contacts_")
        self._path = os.path.join(self._dir, "contacts.json")
        with open(self._path, "w", encoding="utf-8") as handle:
            json.dump(self._payload, handle)
        self._patch = mock.patch.object(contacts, "get_contacts_path", return_value=self._path)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        try:
            os.remove(self._path)
            os.rmdir(self._dir)
        except OSError:
            pass


class ContactsResolverTests(unittest.TestCase):
    def test_exact_full_name(self):
        with _TempContacts(_SAMPLE):
            self.assertEqual(contacts.resolve_contact("Ana Ricardo Lazcano", "telegram"), "@ana_lazcano")
            self.assertEqual(contacts.resolve_contact("Ana Ricardo Lazcano", "whatsapp"), "+5215555555555")

    def test_alias(self):
        with _TempContacts(_SAMPLE):
            self.assertEqual(contacts.resolve_contact("Ana Lazcano", "telegram"), "@ana_lazcano")

    def test_case_insensitive(self):
        with _TempContacts(_SAMPLE):
            self.assertEqual(contacts.resolve_contact("ANA RICARDO LAZCANO", "whatsapp"), "+5215555555555")

    def test_subset_tokens_match(self):
        # "ana lazcano" (a subset of the tokens) finds "Ana Ricardo Lazcano".
        with _TempContacts(_SAMPLE):
            self.assertEqual(contacts.resolve_contact("ana lazcano", "telegram"), "@ana_lazcano")

    def test_not_found_returns_none(self):
        with _TempContacts(_SAMPLE):
            self.assertIsNone(contacts.resolve_contact("Carlos Nobody", "telegram"))

    def test_missing_channel_returns_none(self):
        with _TempContacts({"contacts": [{"name": "NoChan"}]}):
            self.assertIsNone(contacts.resolve_contact("NoChan", "telegram"))

    def test_empty_query_returns_none(self):
        with _TempContacts(_SAMPLE):
            self.assertIsNone(contacts.resolve_contact("", "telegram"))
            self.assertIsNone(contacts.resolve_contact("   ", "whatsapp"))

    def test_distinct_people_do_not_cross_match(self):
        with _TempContacts(_SAMPLE):
            self.assertEqual(contacts.resolve_contact("Bob Stone", "telegram"), "@bobstone")
            self.assertEqual(contacts.resolve_contact("Bob Stone", "whatsapp"), "+15551230000")

    def test_list_contacts(self):
        with _TempContacts(_SAMPLE):
            names = [c["name"] for c in contacts.list_contacts()]
            self.assertIn("Ana Ricardo Lazcano", names)
            self.assertIn("Bob Stone", names)

    def test_missing_file_fails_open(self):
        with mock.patch.object(contacts, "get_contacts_path", return_value="/no/such/contacts.json"):
            self.assertEqual(contacts.load_contacts(), [])
            self.assertIsNone(contacts.resolve_contact("Ana", "telegram"))


class ShippedContactsFileTests(unittest.TestCase):
    """The contacts.json next to config.json must be valid JSON and resolvable
    end-to-end (proves the data file + resolver work together).

    ⚠️ DATA-INDEPENDENT ON PURPOSE (Angela, 2026-07-26). This file is her LIVE
    contacts book, not a shipped sample: it holds real people's real handles and
    phone numbers, and it changes whenever she adds a contact. The test used to
    assert `resolve_contact("Ana Ricardo Lazcano", "telegram") == "@ana_lazcano"`,
    which (a) failed the moment the real entry differed and (b) hardcoded a
    person's identifier into the test suite. Assert the CONTRACT against
    whatever the file actually contains instead — never a specific person.
    """

    def test_shipped_file_loads_and_resolves_example(self):
        path = contacts.get_contacts_path()
        if not os.path.isfile(path):
            self.skipTest("contacts.json not present in this layout")
        entries = contacts.load_contacts()
        self.assertTrue(entries, "contacts.json should hold at least one contact")

        for entry in entries:
            self.assertIn("name", entry, f"every contact needs a name: {entry!r}")
            self.assertTrue(str(entry["name"]).strip(), "a contact name must not be blank")

        # Round-trip the resolver against the file's OWN data: for every channel
        # a contact declares, resolve_contact(name, channel) must return exactly
        # the stored value. No real handle is written into this test.
        checked = 0
        for entry in entries:
            name = entry["name"]
            for channel in ("telegram", "whatsapp", "email", "sms"):
                stored = entry.get(channel)
                if not stored:
                    continue
                self.assertEqual(
                    contacts.resolve_contact(name, channel), stored,
                    f"resolver disagreed with contacts.json for channel {channel!r}")
                checked += 1
        self.assertGreater(
            checked, 0,
            "no contact declares a telegram/whatsapp/email/sms channel, so the "
            "resolver was never exercised")

        # An unknown name must fail closed (None), not return someone else.
        self.assertIsNone(
            contacts.resolve_contact("Definitely Not In The Book 9f3a", "telegram"))
