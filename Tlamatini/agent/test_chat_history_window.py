"""Regression tests for the conversation-memory window (chat_history_loader).

Reproduces the Step-by-Step continuity bug seen with the create-user wizard:
after Clear-history, the FIRST follow-up turn loaded almost no history because the
loader shrank its window down to ``chat_hist_summarizer_counter`` (a per-TURN
count, while a turn is ~2 saved messages). On turn 2 the counter was 1 -> only
the single newest message loaded -> the executor then dropped it as the current
input -> EMPTY history -> the model treated a bare "alice" reply as a brand-new
request instead of the username it had just asked for.

The window is now a HARD UPPER bound of 8 (inclusive 0..8), independent of that
counter. Session isolation is still guaranteed because Clear-history DELETES the
rows (consumers.clear_chat_history) and the loader filters by conversation_user.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from agent.chat_history_loader import DBChatHistoryLoader
from agent.global_state import global_state
from agent.models import AgentMessage


class ChatHistoryWindowTests(TestCase):
    def setUp(self):
        self.bot = User.objects.create(username=DBChatHistoryLoader.BOT_USERNAME)
        self.human = User.objects.create(username='<REDACTED>')

    def tearDown(self):
        # Never leak the poison counter into another test.
        global_state.set_state('chat_hist_summarizer_counter', 0)

    def _say(self, sender, text):
        # conversation_user is always the human who owns the conversation.
        return AgentMessage.objects.create(
            user=sender, conversation_user=self.human, message=text,
        )

    @staticmethod
    def _join(msgs):
        return ' '.join(getattr(m, 'content', str(m)) for m in msgs)

    def test_first_followup_keeps_prior_turn_even_with_counter_1(self):
        # The exact incident: one full wizard turn, then a one-word follow-up.
        self._say(self.human, 'Tlamatini, help me step by step to create a NEW user ...')
        self._say(self.bot, 'Hi! What username would you like? Reply with the name to continue to Step 1.')
        self._say(self.human, 'alice')
        # The poison value that used to collapse the window to a single message.
        global_state.set_state('chat_hist_summarizer_counter', 1)

        msgs = DBChatHistoryLoader.load(limit=8, conversation_user=self.human)

        # All three real messages survive — the counter no longer starves it.
        self.assertEqual(len(msgs), 3)
        joined = self._join(msgs)
        self.assertIn('create a NEW user', joined)  # the original instructions
        self.assertIn('username', joined)           # the assistant's question
        self.assertIn('alice', joined)              # the follow-up answer

    def test_window_upper_bound_is_8(self):
        # 12 messages exist; the window must be AT MOST 8 (the 0..8 contract).
        for i in range(12):
            self._say(self.human if i % 2 == 0 else self.bot, f'message {i}')
        msgs = DBChatHistoryLoader.load(limit=8, conversation_user=self.human)
        self.assertEqual(len(msgs), 8)

    def test_oversize_request_is_clamped_to_8(self):
        for i in range(20):
            self._say(self.human if i % 2 == 0 else self.bot, f'm{i}')
        # A caller asking for more than the cap still gets at most 8.
        msgs = DBChatHistoryLoader.load(limit=100, conversation_user=self.human)
        self.assertEqual(len(msgs), 8)

    def test_none_limit_is_clamped_to_8_not_unbounded(self):
        for i in range(15):
            self._say(self.human if i % 2 == 0 else self.bot, f'n{i}')
        # limit=None used to mean "load everything"; the window now caps at 8.
        msgs = DBChatHistoryLoader.load(limit=None, conversation_user=self.human)
        self.assertEqual(len(msgs), 8)

    def test_fewer_messages_than_window_returns_all(self):
        # The window is an upper bound, never a minimum: 2 messages -> 2 returned.
        self._say(self.human, 'only question')
        self._say(self.bot, 'only answer')
        msgs = DBChatHistoryLoader.load(limit=8, conversation_user=self.human)
        self.assertEqual(len(msgs), 2)
