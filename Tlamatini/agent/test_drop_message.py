# Tlamatini Author Banner - do not remove (releases scrub the name automatically)
"""
The chat card's DROP button (Angela Lopez Mendoza, 2026-09-30).

    "with this new button in the cards of messages the user must be able to
    delete messages from the history chat, and erase them from the history
    chain processed by the llm too ... the LLM must process the history of
    messages as if the deleted messages have never been existed and previous
    messages and posterior messages to the deleted one must stay there
    untouched, AND FOR BOTH TYPE OF MESSAGES".

WHERE THE LLM'S MEMORY LIVES: the conversation the model reads is rebuilt from
the AgentMessage table on EVERY request (DBChatHistoryLoader.load, the newest
8 rows of this user). There is no cached summary, no checkpoint and no history
inside the chain object, so deleting ONE row is the whole job - no reconnect.

These tests pin:
  * a dropped USER message and a dropped TLAMATINI answer both vanish from
    what the model reads, and every neighbour stays, in order;
  * the 8-message window slides back exactly as if the row never existed;
  * nobody can drop a row of another user's conversation;
  * a drop is refused while this connection is answering a request;
  * a successful drop reaches every tab and refreshes the context gauge;
  * the saved-message id reaches the page (first render AND live frames);
  * the frontend contract (button, themed confirm, socket frame names).
"""
import json
import os
import re

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from agent.chat_history_loader import DBChatHistoryLoader
from agent.consumers import AgentConsumer
from agent.models import AgentMessage
from agent.services import response_parser

_HERE = os.path.dirname(os.path.abspath(__file__))
_JS = os.path.join(_HERE, 'static', 'agent', 'js')
_CSS = os.path.join(_HERE, 'static', 'agent', 'css')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


class _FakeLayer:
    """Stands in for the channel layer: records every group_send."""

    def __init__(self):
        self.sent = []

    async def group_send(self, group, event):
        self.sent.append((group, event))


def _consumer_for(user):
    """A real AgentConsumer with its transport replaced by recorders."""
    consumer = AgentConsumer()
    consumer.channel_layer = _FakeLayer()
    consumer.room_group_name = f'chat_user_{user.id}'
    consumer.scope = {'user': user}
    consumer.sent_frames = []
    consumer.gauge_reasons = []

    async def _send(text_data=None, bytes_data=None, close=False):
        consumer.sent_frames.append(json.loads(text_data))

    def _gauge(reason, after_answer=False):
        consumer.gauge_reasons.append(reason)

    consumer.send = _send
    consumer._schedule_context_gauge_refresh = _gauge
    return consumer


class DropMessageFromTheLlmHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='secret123')
        self.other = User.objects.create_user(username='bob', password='secret123')
        self.bot = User.objects.create_user(username='Tlamatini', password='secret123')

    def _say(self, who, text, owner=None):
        return AgentMessage.objects.create(
            user=who, conversation_user=owner or self.user, message=text)

    def _history(self):
        """Exactly what the model is handed on the next request."""
        return [m.content for m in DBChatHistoryLoader.load(limit=8, conversation_user=self.user)]

    def _drop(self, message_id, consumer=None):
        consumer = consumer or _consumer_for(self.user)
        async_to_sync(consumer._handle_drop_message)(self.user, {'message_id': message_id})
        return consumer

    def _conversation(self):
        rows = [
            self._say(self.user, 'My favourite colour is teal.'),
            self._say(self.bot, 'Noted: your favourite colour is teal.'),
            self._say(self.user, 'The secret code word is PAPAYA-42.'),
            self._say(self.bot, 'Noted: the code word is PAPAYA-42.'),
            self._say(self.user, 'What is 2 plus 2?'),
            self._say(self.bot, '4'),
        ]
        return rows

    # -- both kinds of message --------------------------------------------
    def test_a_dropped_user_message_leaves_the_llm_history_and_neighbours_stay(self):
        rows = self._conversation()
        self._drop(rows[2].pk)
        self.assertEqual(self._history(), [
            'My favourite colour is teal.',
            'Noted: your favourite colour is teal.',
            'Noted: the code word is PAPAYA-42.',
            'What is 2 plus 2?',
            '4',
        ])
        self.assertFalse(AgentMessage.objects.filter(pk=rows[2].pk).exists())

    def test_a_dropped_tlamatini_answer_leaves_the_llm_history_and_neighbours_stay(self):
        rows = self._conversation()
        self._drop(rows[3].pk)
        self.assertEqual(self._history(), [
            'My favourite colour is teal.',
            'Noted: your favourite colour is teal.',
            'The secret code word is PAPAYA-42.',
            'What is 2 plus 2?',
            '4',
        ])

    def test_dropping_both_halves_erases_the_exchange_as_if_it_never_happened(self):
        rows = self._conversation()
        self._drop(rows[2].pk)
        self._drop(rows[3].pk)
        history = self._history()
        self.assertFalse(any('PAPAYA' in text for text in history), history)
        self.assertEqual(history, [
            'My favourite colour is teal.',
            'Noted: your favourite colour is teal.',
            'What is 2 plus 2?',
            '4',
        ])

    def test_the_window_slides_back_exactly_as_if_the_row_never_existed(self):
        rows = [self._say(self.user if i % 2 == 0 else self.bot, f'message number {i}')
                for i in range(10)]
        self.assertEqual(self._history(), [f'message number {i}' for i in range(2, 10)])
        self._drop(rows[5].pk)
        # m1 was just outside the 8-row window; with m5 gone it is read again.
        self.assertEqual(self._history(),
                         [f'message number {i}' for i in (1, 2, 3, 4, 6, 7, 8, 9)])

    # -- safety -------------------------------------------------------------
    def test_nobody_can_drop_a_row_of_another_users_conversation(self):
        foreign = self._say(self.other, 'bob private note', owner=self.other)
        consumer = self._drop(foreign.pk)
        self.assertTrue(AgentMessage.objects.filter(pk=foreign.pk).exists(),
                        "alice's Drop deleted a row of bob's conversation")
        self.assertEqual(consumer.channel_layer.sent, [],
                         'a drop that deleted nothing must not tell any tab to remove a card')

    def test_a_drop_is_refused_while_a_request_is_being_answered(self):
        rows = self._conversation()
        consumer = _consumer_for(self.user)
        consumer._active_run = (self.user.id, 1)
        self._drop(rows[2].pk, consumer)
        self.assertTrue(AgentMessage.objects.filter(pk=rows[2].pk).exists())
        self.assertEqual(len(consumer.sent_frames), 1)
        frame = consumer.sent_frames[0]
        self.assertEqual(frame['type'], 'message-dropped')
        self.assertFalse(frame['ok'])
        self.assertIn('still answering', frame['reason'])

    def test_an_invalid_id_is_refused_and_touches_nothing(self):
        rows = self._conversation()
        for bad in (None, '', 'abc', -3, 0):
            consumer = self._drop(bad)
            self.assertFalse(consumer.sent_frames[0]['ok'], bad)
            self.assertEqual(consumer.channel_layer.sent, [], bad)
        self.assertEqual(AgentMessage.objects.filter(conversation_user=self.user).count(), len(rows))

    # -- what the page receives ----------------------------------------------
    def test_a_successful_drop_reaches_every_tab_and_refreshes_the_gauge(self):
        rows = self._conversation()
        consumer = self._drop(rows[4].pk)
        self.assertEqual(consumer.channel_layer.sent, [
            (f'chat_user_{self.user.id}', {'type': 'message_dropped', 'message_id': rows[4].pk,
                                           'message_ids': [rows[4].pk]}),
        ])
        self.assertEqual(consumer.gauge_reasons, ['message dropped'])
        self.assertEqual(consumer.sent_frames, [], 'success is announced through the room, once')

    def test_the_group_handler_forwards_the_drop_to_the_browser(self):
        consumer = _consumer_for(self.user)
        async_to_sync(consumer.message_dropped)({'type': 'message_dropped', 'message_id': 7})
        self.assertEqual(consumer.sent_frames,
                         [{'type': 'message-dropped', 'message_id': 7, 'message_ids': [7], 'ok': True}])

    # -- the rephrase rows the chain saves for a prompt ------------------------
    def test_a_dropped_prompt_takes_its_rephrase_rows_but_not_the_answer(self):
        """rag/interaction.py saves 'Referenced Rephrase: <question reworded>'
        right after a prompt. The model never reads it, but a reload replays
        it - leaving it would bring the dropped words back on screen."""
        before = self._say(self.user, 'My favourite colour is teal.')
        prompt = self._say(self.user, 'The secret code word is PAPAYA-42.')
        rephrase = self._say(self.bot, 'Referenced Rephrase: Remember the code word PAPAYA-42.')
        answer = self._say(self.bot, 'Noted: the code word is PAPAYA-42.')
        consumer = self._drop(prompt.pk)
        self.assertFalse(AgentMessage.objects.filter(pk__in=[prompt.pk, rephrase.pk]).exists())
        self.assertTrue(AgentMessage.objects.filter(pk=answer.pk).exists(),
                        "dropping the prompt must not take Tlamatini's answer with it")
        self.assertTrue(AgentMessage.objects.filter(pk=before.pk).exists())
        self.assertEqual(consumer.channel_layer.sent[0][1]['message_ids'], [prompt.pk, rephrase.pk])

    def test_a_dropped_answer_leaves_the_next_prompts_rephrase_alone(self):
        answer = self._say(self.bot, 'Noted.')
        nxt = self._say(self.user, 'And what about tomorrow?')
        rephrase = self._say(self.bot, 'Referenced Rephrase: what about tomorrow?')
        self._drop(answer.pk)
        self.assertEqual(
            set(AgentMessage.objects.filter(conversation_user=self.user).values_list('pk', flat=True)),
            {nxt.pk, rephrase.pk})

    def test_an_already_gone_row_still_clears_the_card(self):
        rows = self._conversation()
        gone_id = rows[1].pk            # read it first: Django sets pk=None on delete()
        rows[1].delete()
        consumer = self._drop(gone_id)
        self.assertTrue(consumer.sent_frames[0]['ok'])
        self.assertTrue(consumer.sent_frames[0]['already_gone'])

    def test_the_socket_routes_a_drop_message_frame(self):
        rows = self._conversation()
        consumer = _consumer_for(self.user)
        async_to_sync(consumer.receive)(text_data=json.dumps({
            'message': 'drop-message', 'type': 'drop-message', 'message_id': rows[0].pk,
        }))
        self.assertFalse(AgentMessage.objects.filter(pk=rows[0].pk).exists())
        self.assertNotIn('My favourite colour is teal.', self._history())

    def test_live_frames_carry_the_saved_row_id_and_status_lines_carry_none(self):
        consumer = _consumer_for(self.user)
        async_to_sync(consumer.agent_message)(
            {'type': 'agent_message', 'message': 'hi', 'username': 'alice', 'message_id': 42})
        async_to_sync(consumer.agent_message)(
            {'type': 'agent_message', 'message': 'Processing...', 'username': 'Tlamatini'})
        self.assertEqual(consumer.sent_frames[0]['message_id'], 42)
        self.assertNotIn('message_id', consumer.sent_frames[1])

    def test_both_save_paths_return_the_new_row_id(self):
        consumer = _consumer_for(self.user)
        user_id = async_to_sync(consumer.save_message)(self.user, 'a prompt', conversation_user=self.user)
        answer_id = async_to_sync(response_parser.save_message)(
            self.bot, 'an answer', conversation_user=self.user)
        self.assertEqual(AgentMessage.objects.get(pk=user_id).message, 'a prompt')
        self.assertEqual(AgentMessage.objects.get(pk=answer_id).message, 'an answer')

    def test_the_first_render_gives_every_card_its_row_id(self):
        rows = self._conversation()
        self.client.force_login(self.user)
        response = self.client.get(reverse('agent_page'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m['id'] for m in response.context['initial_messages']],
                         [row.pk for row in rows])


class DropMessageSourceContractTests(SimpleTestCase):
    """The wiring that a refactor could silently cut."""

    def test_the_answer_broadcast_carries_its_row_id(self):
        src = _read(os.path.join(_HERE, 'services', 'response_parser.py'))
        self.assertIn('answer_message_id = await save_message(', src)
        self.assertIn("'message_id': answer_message_id", src)

    def test_the_user_prompt_broadcast_carries_its_row_id(self):
        src = _read(os.path.join(_HERE, 'consumers.py'))
        self.assertIn("'message_id': user_message_id", src)
        self.assertIn("'message_id': greeting_id", src)

    def test_the_drop_frame_is_routed_before_any_prompt_handling(self):
        src = _read(os.path.join(_HERE, 'consumers.py'))
        drop = src.index("if type == 'drop-message':")
        prompt = src.index('re.match(constants.REGEX_GREETING')
        self.assertLess(drop, prompt, 'a drop frame could be treated as a chat prompt')

    def test_the_card_has_a_drop_button_wired_to_the_server(self):
        js = _read(os.path.join(_JS, 'agent_page_chat.js'))
        self.assertIn("dropBtn.classList.add('message-drop-btn')", js)
        self.assertIn("<i class=\"bi bi-trash3\"></i> Drop", js)
        self.assertRegex(js, r"function appendChatMessage\([^)]*messageId = null\)")
        self.assertIn("type: 'drop-message'", js)
        self.assertIn("data.type === 'message-dropped'", js)
        self.assertIn('data.message_id || null', js)
        self.assertIn('msg.id || null', js)

    def test_the_confirmation_explains_what_the_llm_will_do_and_asks(self):
        js = _read(os.path.join(_JS, 'agent_page_chat.js'))
        for needed in ('she answers as if it had never existed',
                       'Every message before and after it stays exactly as it is',
                       'No reconnection is needed',
                       'Are you sure you want to drop it?',
                       'She will forget she ever wrote this answer',
                       'She will forget you ever sent this message',
                       # Honesty (measured 2026-09-30): a fact she copied into
                       # the External MCP "memory" graph is NOT chat history.
                       'A note she saved with her memory tool'):
            self.assertIn(needed, js)
        call = re.search(r"tlmConfirm\(text\.primary, text\.secondary, 'Drop message', \{(.*?)\}\)",
                         js, re.S)
        self.assertIsNotNone(call, 'the Drop confirmation must use the themed tlmConfirm')
        body = call.group(1)
        self.assertIn("confirmLabel: 'Drop'", body)
        self.assertIn('danger: true', body)
        self.assertIn('focusCancel: true', body, 'Enter must never drop a message by accident')

    def test_tlm_confirm_accepts_destructive_options_and_still_dismisses_false(self):
        js = _read(os.path.join(_JS, 'dialog_policy.js'))
        self.assertIn('function tlmConfirm(primary, secondary, title, options)', js)
        self.assertIn("' tlmpop-btn-danger'", js)
        self.assertIn('focus: o.focusCancel === true', js)
        block = js.split('function tlmConfirm', 1)[1][:900]
        self.assertIn('dismissValue: false', block)

    def test_the_styles_exist(self):
        self.assertIn('.message-drop-btn {', _read(os.path.join(_CSS, 'agent_page.css')))
        self.assertIn('.tlmpop-btn-danger', _read(os.path.join(_CSS, 'dialog_theme.css')))
