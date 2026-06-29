# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the Telegrammer dual-identity ("send as me" vs "send as the bot")
provider selection.

Telegrammer can send a Telegram message under TWO identities:
  * the BOT (Bot API), or
  * the user's OWN logged-in account (user session / MTProto).

The `provider` knob picks which one. These tests pin:
  1. `_resolve_provider` accepting plain-English words ("me", "as the bot", ...)
     and mapping them onto the canonical 'user' / 'bot' / 'auto'.
  2. `_normalize_provider_word` normalization (case, spaces/hyphens, send_/as_).
  3. `_should_use_user_provider` send-routing for each resolved provider.
  4. The two catalog demo prompts seeded by migration 0156.

The Telegrammer pool script is a standalone module (it is NOT importable as
agent.*), so it is loaded straight from disk; its module-top code chdir()s into
its own folder, so the working directory is saved and restored around the load.
"""

import importlib.util
import os

from django.test import SimpleTestCase


def _load_telegrammer():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'agents', 'telegrammer', 'telegrammer.py')
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location('telegrammer_under_test', path)
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


class TelegrammerProviderResolutionTests(SimpleTestCase):
    """`_resolve_provider` maps a free-form `provider` value onto one of the
    three canonical routes: 'user' (my account), 'bot' (the bot), 'auto'."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_telegrammer()

    def _resolve(self, value):
        return self.mod._resolve_provider({'provider': value})

    def test_bot_words_resolve_to_bot(self):
        for word in (
            'bot', 'Bot', 'BOT', 'bot_api', 'bot-api', 'telegram_bot',
            'the bot', 'as the bot', 'as a bot', 'send as the bot', 'robot',
        ):
            self.assertEqual(self._resolve(word), 'bot', f"{word!r} should be the bot")

    def test_user_words_resolve_to_user(self):
        for word in (
            'user', 'me', 'Me', 'as me', 'as myself', 'myself', 'self',
            'my account', 'my-account', 'personal', 'send as me', 'mtproto',
            'owner', 'from my account',  # 'from my account' -> normalized below
        ):
            # 'from my account' normalizes to 'from_my_account' (unknown) -> auto;
            # keep it out of the strict set. Test the supported ones explicitly.
            if word == 'from my account':
                continue
            self.assertEqual(self._resolve(word), 'user', f"{word!r} should be my account")

    def test_auto_and_empty_resolve_to_auto(self):
        for word in ('auto', 'Auto', '', '   ', None):
            self.assertEqual(self._resolve(word), 'auto', f"{word!r} should be auto")

    def test_unknown_word_falls_back_to_auto(self):
        for word in ('banana', 'whatsapp', 'sms', 'carrier_pigeon'):
            self.assertEqual(self._resolve(word), 'auto', f"{word!r} should fall back to auto")

    def test_placeholder_token_is_treated_as_empty(self):
        # _clean() drops <...> placeholder values, so a not-yet-filled config is auto.
        self.assertEqual(self._resolve('<TELEGRAM_PROVIDER goes here>'), 'auto')

    def test_nested_telegram_provider_is_read(self):
        self.assertEqual(
            self.mod._resolve_provider({'telegram': {'provider': 'me'}}), 'user'
        )
        self.assertEqual(
            self.mod._resolve_provider({'telegram': {'provider': 'bot'}}), 'bot'
        )

    def test_top_level_provider_wins_over_nested(self):
        cfg = {'provider': 'bot', 'telegram': {'provider': 'me'}}
        self.assertEqual(self.mod._resolve_provider(cfg), 'bot')

    def test_env_var_fallback(self):
        # With no provider in config, fall back to the TELEGRAM_PROVIDER env var.
        old = os.environ.get('TELEGRAM_PROVIDER')
        os.environ['TELEGRAM_PROVIDER'] = 'as me'
        try:
            self.assertEqual(self.mod._resolve_provider({}), 'user')
        finally:
            if old is None:
                os.environ.pop('TELEGRAM_PROVIDER', None)
            else:
                os.environ['TELEGRAM_PROVIDER'] = old

    def test_normalize_word_edge_cases(self):
        n = self.mod._normalize_provider_word
        self.assertEqual(n('  As   The   Bot '), 'the_bot')
        self.assertEqual(n('send-as-me'), 'me')
        self.assertEqual(n('SEND AS A BOT'), 'a_bot')
        self.assertEqual(n('user-account'), 'user_account')
        self.assertEqual(n(''), '')
        self.assertEqual(n(None), '')


class TelegrammerSendRoutingTests(SimpleTestCase):
    """`_should_use_user_provider` decides, for a resolved provider, whether the
    SEND goes through the user-session API (True) or the Bot API (False)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_telegrammer()

    CONFIGURED = {'api_id': '12345', 'api_hash': 'deadbeef', 'session_name': 'sess'}
    UNCONFIGURED = {'api_id': '', 'api_hash': '', 'session_name': ''}

    def _route(self, provider, user_cfg, recipient, source):
        return self.mod._should_use_user_provider(provider, user_cfg, recipient, source)

    def test_provider_user_always_user_route(self):
        # provider='user' forces the user route regardless of recipient/session.
        self.assertTrue(self._route('user', self.UNCONFIGURED, '12345', 'chat_id'))
        self.assertTrue(self._route('user', self.CONFIGURED, '@ana', 'contact_name'))

    def test_provider_bot_always_bot_route(self):
        self.assertFalse(self._route('bot', self.CONFIGURED, '@ana', 'contact_name'))
        self.assertFalse(self._route('bot', self.CONFIGURED, '12345', 'chat_id'))

    def test_auto_username_with_session_uses_user(self):
        self.assertTrue(self._route('auto', self.CONFIGURED, '@ana', 'contact_name'))

    def test_auto_phone_with_session_uses_user(self):
        self.assertTrue(self._route('auto', self.CONFIGURED, '+5215555555555', 'chat_id'))

    def test_auto_numeric_uses_bot(self):
        self.assertFalse(self._route('auto', self.CONFIGURED, '123456789', 'chat_id'))

    def test_auto_username_without_session_uses_bot(self):
        # No user session configured -> auto can only use the Bot API route.
        self.assertFalse(self._route('auto', self.UNCONFIGURED, '@ana', 'contact_name'))

    def test_plain_words_integration_route(self):
        # End-to-end: plain word -> resolved provider -> send route.
        as_me = self.mod._resolve_provider({'provider': 'as me'})
        self.assertEqual(as_me, 'user')
        self.assertTrue(self._route(as_me, self.UNCONFIGURED, '12345', 'chat_id'))

        as_bot = self.mod._resolve_provider({'provider': 'as the bot'})
        self.assertEqual(as_bot, 'bot')
        self.assertFalse(self._route(as_bot, self.CONFIGURED, '@ana', 'contact_name'))


class TelegrammerIdentityDemoPromptTests(SimpleTestCase):
    """The redesigned catalog prompts (migration 0158) drive chat_agent_telegrammer
    with the right provider and a CLEAR fill-in [[ ]] placeholder for the target
    contact, stating the name must be saved in contacts.json (no hardcoded 'me')."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mig = _load_identity_migration()

    def test_two_distinct_telegram_prompts(self):
        self.assertNotEqual(self.mig.TG_AS_ME, self.mig.TG_AS_BOT)

    def _assert_common(self, text):
        self.assertIn('chat_agent_telegrammer', text)
        self.assertIn('END-RESPONSE', text)
        # A clear, fill-in placeholder for the recipient...
        self.assertIn('[[', text)
        self.assertIn('SEND TO', text)
        # ...and the explicit "must be in the contacts book" rule.
        self.assertIn('contacts.json', text)
        # The confusing hardcoded self-recipient is GONE.
        self.assertNotIn("contact_name='me'", text)

    def test_as_me_prompt_uses_user_provider(self):
        text = self.mig.TG_AS_ME
        self._assert_common(text)
        self.assertIn("provider='me'", text)

    def test_as_bot_prompt_uses_bot_provider(self):
        text = self.mig.TG_AS_BOT
        self._assert_common(text)
        self.assertIn("provider='bot'", text)
