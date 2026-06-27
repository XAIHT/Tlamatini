"""Tests for the Whatsapper dual-identity ("send as me" vs the official business
number) provider selection.

Whatsapper can send a WhatsApp message under TWO identities:
  * 'cloud' -> the official Meta Cloud API (business number, templates, System User), or
  * 'web'   -> the user's OWN personal number, by automating WhatsApp Web (unofficial).

The `provider` knob picks which one. These tests pin the DETERMINISTIC parts:
  1. `_resolve_provider` mapping plain-English words onto 'web' / 'cloud'.
  2. `_normalize_provider_word` normalization.
  3. `_build_wa_web_send_url` (the WhatsApp Web deep link).
  4. `WhatsAppWebClient.send_text` early-exit guards (empty recipient / empty text)
     that must NOT launch a browser.
  5. The catalog demo prompt seeded by migration 0157.

The live QR-login + real send is intentionally NOT unit-tested (it needs a phone
scan); it is verified interactively. The Whatsapper pool script chdir()s into its
own folder at import, so the working directory is saved and restored.
"""

import importlib.util
import os

from django.test import SimpleTestCase


def _load_whatsapper():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'agents', 'whatsapper', 'whatsapper.py')
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location('whatsapper_under_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
    return module


def _load_identity_migration():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'migrations', '0158_redesign_messaging_demo_prompts.py')
    spec = importlib.util.spec_from_file_location('messaging_demo_redesign_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


class WhatsapperProviderResolutionTests(SimpleTestCase):
    """`_resolve_provider` maps a free-form `provider` onto 'web' (my number) or
    'cloud' (the business number). Default / unknown -> 'cloud'."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_whatsapper()

    def _resolve(self, value):
        return self.mod._resolve_provider({'provider': value})

    def test_web_words_resolve_to_web(self):
        for word in (
            'web', 'me', 'Me', 'as me', 'myself', 'as myself', 'personal',
            'my number', 'my account', 'send as me', 'whatsapp web', 'my-whatsapp',
        ):
            self.assertEqual(self._resolve(word), 'web', f"{word!r} should be my own number")

    def test_cloud_words_resolve_to_cloud(self):
        for word in (
            'cloud', 'Cloud', 'cloud_api', 'official', 'business', 'as the business',
            'meta', 'bot', 'company', 'graph',
        ):
            self.assertEqual(self._resolve(word), 'cloud', f"{word!r} should be the business")

    def test_auto_and_empty_resolve_to_cloud(self):
        # The historical default is the official Cloud API.
        for word in ('auto', 'Auto', '', '   ', None):
            self.assertEqual(self._resolve(word), 'cloud', f"{word!r} should default to cloud")

    def test_unknown_word_falls_back_to_cloud(self):
        for word in ('banana', 'sms', 'telegram', 'pigeon'):
            self.assertEqual(self._resolve(word), 'cloud', f"{word!r} should fall back to cloud")

    def test_placeholder_token_is_treated_as_empty(self):
        self.assertEqual(self._resolve('<WHATSAPP_PROVIDER goes here>'), 'cloud')

    def test_nested_whatsapp_provider_is_read(self):
        self.assertEqual(self.mod._resolve_provider({'whatsapp': {'provider': 'me'}}), 'web')
        self.assertEqual(self.mod._resolve_provider({'whatsapp': {'provider': 'cloud'}}), 'cloud')

    def test_top_level_provider_wins_over_nested(self):
        cfg = {'provider': 'cloud', 'whatsapp': {'provider': 'me'}}
        self.assertEqual(self.mod._resolve_provider(cfg), 'cloud')

    def test_env_var_fallback(self):
        old = os.environ.get('WHATSAPP_PROVIDER')
        os.environ['WHATSAPP_PROVIDER'] = 'as me'
        try:
            self.assertEqual(self.mod._resolve_provider({}), 'web')
        finally:
            if old is None:
                os.environ.pop('WHATSAPP_PROVIDER', None)
            else:
                os.environ['WHATSAPP_PROVIDER'] = old

    def test_normalize_word_edge_cases(self):
        n = self.mod._normalize_provider_word
        self.assertEqual(n('  As   Me '), 'me')
        self.assertEqual(n('send-as-myself'), 'myself')
        self.assertEqual(n('WhatsApp Web'), 'whatsapp_web')
        self.assertEqual(n(''), '')
        self.assertEqual(n(None), '')


class WhatsappWebDeepLinkTests(SimpleTestCase):
    """`_build_wa_web_send_url` builds the official web.whatsapp.com/send link:
    digits-only phone, URL-encoded text."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_whatsapper()

    def test_phone_is_digits_only(self):
        url = self.mod._build_wa_web_send_url('+52 1 (55) 5555-5555', 'hi')
        self.assertTrue(url.startswith('https://web.whatsapp.com/send?'))
        self.assertIn('phone=5215555555555', url)

    def test_text_is_url_encoded(self):
        url = self.mod._build_wa_web_send_url('5215555555555', 'hola mundo & test')
        self.assertIn('text=hola+mundo+%26+test', url)

    def test_empty_text_ok(self):
        url = self.mod._build_wa_web_send_url('5215555555555', '')
        self.assertIn('text=', url)


class WhatsappWebClientGuardTests(SimpleTestCase):
    """`WhatsAppWebClient.send_text` must early-exit (no browser) on an empty
    recipient or empty text."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_whatsapper()

    def _client(self):
        return self.mod.WhatsAppWebClient('ignored_profile_dir', headless=True)

    def test_empty_recipient_fails_without_browser(self):
        ok, info, mid = self._client().send_text('', 'hello')
        self.assertFalse(ok)
        # Either Playwright is missing OR the recipient guard fired — both are
        # failures that never launch a browser.
        self.assertTrue('recipient' in info.lower() or 'playwright' in info.lower())

    def test_empty_text_is_noop(self):
        if not _has_playwright():
            self.skipTest('Playwright not installed; empty-text guard runs after the import.')
        ok, info, mid = self._client().send_text('5215555555555', '')
        self.assertTrue(ok)
        self.assertEqual(info, 'empty message')


class WhatsapperIdentityDemoPromptTests(SimpleTestCase):
    """The redesigned 'as me' WhatsApp demo (migration 0158) uses a CLEAR fill-in
    [[ ]] placeholder for the target contact and states the name must be in
    contacts.json — no hardcoded 'me'."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mig = _load_identity_migration()

    def test_prompt_uses_web_provider_with_fill_in_recipient(self):
        text = self.mig.WA_AS_ME
        self.assertIn('chat_agent_whatsapper', text)
        self.assertIn("provider='me'", text)
        self.assertIn('END-RESPONSE', text)
        # A clear, fill-in placeholder for the recipient + the contacts rule...
        self.assertIn('[[', text)
        self.assertIn('SEND TO', text)
        self.assertIn('contacts.json', text)
        # ...and the confusing hardcoded self-recipient is GONE.
        self.assertNotIn("contact_name='me'", text)
