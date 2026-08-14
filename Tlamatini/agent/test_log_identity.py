# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   ·   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner · do not remove (releases scrub the name automatically)
"""Behavioural tests for per-line USER attribution in ``tlamatini.log``.

These do NOT test that the code "looks right" — they exercise the real
``_TeeStream`` from ``manage.py`` and assert on the exact characters that reach
the log file, because the whole feature is a claim about those characters:

  * a line belonging to angela starts with HER tag and nobody else's,
  * a line belonging to nobody is written byte-for-byte unchanged,
  * two users in two contexts never see each other's tag,
  * and none of it can raise into the caller.

``manage.py`` cannot be imported (it configures the temp dir, brands the console
and installs the tee at import time), so ``_TeeStream`` is lifted out of it with
``ast`` and executed in an isolated namespace — the same trick
``test_django_port_config.py`` uses for the port helpers.
"""

import ast
import contextvars
import io
import os
import sys
import threading
import time

from django.test import SimpleTestCase

from agent import log_identity

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_AGENT_DIR)
MANAGE_PY = os.path.join(_PROJECT_DIR, 'manage.py')
SETTINGS_PY = os.path.join(_PROJECT_DIR, 'tlamatini', 'settings.py')
MIDDLEWARE_PY = os.path.join(_PROJECT_DIR, 'tlamatini', 'middleware.py')
CONSUMERS_PY = os.path.join(_AGENT_DIR, 'consumers.py')


def _read(path):
    with io.open(path, 'r', encoding='utf-8') as handle:
        return handle.read()


def _load_tee_namespace():
    """Lift ``_TeeStream`` out of manage.py without executing the rest of it."""
    tree = ast.parse(_read(MANAGE_PY))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == '_TeeStream'
    )
    namespace = {'threading': threading, 'time': time, '_USER_TAG_HOOK': None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), MANAGE_PY, 'exec'), namespace)
    return namespace


class _Sink:
    """A stand-in for the console / the log file that just remembers text."""

    def __init__(self):
        self.text = ''

    def write(self, data):
        self.text += data

    def flush(self):
        pass


class _IdentityTestCase(SimpleTestCase):
    """Isolate the module-level registries so tests cannot leak into each other."""

    def setUp(self):
        super().setUp()
        self._saved = (
            log_identity._STYLE,
            dict(log_identity._CODES),
            dict(log_identity._NAMES),
            dict(log_identity._TURNS),
        )
        log_identity._CODES.clear()
        log_identity._NAMES.clear()
        log_identity._TURNS.clear()
        # Pin the style so a developer's config.json can never change the
        # meaning of a test.
        log_identity._STYLE = log_identity.STYLE_SHORT
        self.addCleanup(self._restore)

    def _restore(self):
        style, codes, names, turns = self._saved
        log_identity._STYLE = style
        log_identity._CODES.clear()
        log_identity._CODES.update(codes)
        log_identity._NAMES.clear()
        log_identity._NAMES.update(names)
        log_identity._TURNS.clear()
        log_identity._TURNS.update(turns)
        log_identity._TAG.set('')


class TagRenderingTests(_IdentityTestCase):
    """What the tag actually looks like — the minimal-characters contract."""

    def test_short_style_costs_five_characters(self):
        log_identity.bind(1, 'angela')
        self.assertEqual(log_identity.current_tag(), '[a1] ')
        self.assertEqual(len(log_identity.current_tag()), 5)

    def test_each_new_user_gets_the_next_letter(self):
        log_identity.bind(1, 'angela')
        self.assertEqual(log_identity.current_tag(), '[a1] ')
        log_identity.bind(2, 'alice')
        self.assertEqual(log_identity.current_tag(), '[b1] ')
        # Coming back to the first user keeps her original letter.
        log_identity.bind(1, 'angela')
        self.assertEqual(log_identity.current_tag(), '[a1] ')

    def test_a_new_prompt_opens_a_new_turn(self):
        log_identity.begin_turn(1, 'angela')
        self.assertEqual(log_identity.current_tag(), '[a1] ')
        log_identity.begin_turn(1, 'angela')
        self.assertEqual(log_identity.current_tag(), '[a2] ')
        # Alice's turns are counted independently of Angela's.
        log_identity.begin_turn(2, 'alice')
        self.assertEqual(log_identity.current_tag(), '[b1] ')

    def test_name_style_is_self_describing(self):
        log_identity._STYLE = log_identity.STYLE_NAME
        log_identity.bind(1, 'angela', turn=3)
        self.assertEqual(log_identity.current_tag(), '[angela#3] ')

    def test_off_style_produces_no_tag_at_all(self):
        log_identity._STYLE = log_identity.STYLE_OFF
        log_identity.bind(1, 'angela')
        self.assertEqual(log_identity.current_tag(), '')

    def test_binding_nobody_clears_the_tag(self):
        log_identity.bind(1, 'angela')
        log_identity.bind(None)
        self.assertEqual(log_identity.current_tag(), '')

    def test_legend_reports_every_user_seen(self):
        log_identity.bind(1, 'angela')
        log_identity.bind(2, 'alice')
        self.assertEqual(
            log_identity.legend(), {1: ('a', 'angela'), 2: ('b', 'alice')}
        )

    def test_bad_input_never_raises(self):
        # A junk user id must degrade to "no tag", never explode in a logger.
        log_identity.bind('not-a-number', 'angela')
        self.assertEqual(log_identity.current_tag(), '')
        log_identity.begin_turn(object(), 'angela')
        self.assertEqual(log_identity.current_tag(), '')
        log_identity.reset(None)


class ConcurrentUserTests(_IdentityTestCase):
    """The whole point: angela and alice at once, on one machine."""

    def test_two_users_never_see_each_others_tag(self):
        angela_ctx = contextvars.copy_context()
        alice_ctx = contextvars.copy_context()
        angela_ctx.run(log_identity.begin_turn, 1, 'angela')
        alice_ctx.run(log_identity.begin_turn, 2, 'alice')

        self.assertEqual(angela_ctx.run(log_identity.current_tag), '[a1] ')
        self.assertEqual(alice_ctx.run(log_identity.current_tag), '[b1] ')
        # And the context that owns neither of them stays untagged.
        self.assertEqual(log_identity.current_tag(), '')

    def test_a_child_thread_inherits_the_spawning_users_tag(self):
        if not log_identity._THREAD_PATCHED:
            self.skipTest('thread inheritance disabled by config')
        log_identity.begin_turn(1, 'angela')
        seen = []
        worker = threading.Thread(target=lambda: seen.append(log_identity.current_tag()))
        worker.start()
        worker.join(5)
        self.assertEqual(seen, ['[a1] '])

    def test_a_thread_started_unbound_stays_unbound(self):
        seen = []
        worker = threading.Thread(target=lambda: seen.append(log_identity.current_tag()))
        worker.start()
        worker.join(5)
        self.assertEqual(seen, [''])


class TeeTaggingTests(_IdentityTestCase):
    """End-to-end: exactly what lands in the log file."""

    def setUp(self):
        super().setUp()
        self.namespace = _load_tee_namespace()
        self.console = _Sink()
        self.logfile = _Sink()
        self.tee = self.namespace['_TeeStream'](self.console, self.logfile)

    def _arm(self):
        self.namespace['_USER_TAG_HOOK'] = log_identity.current_tag

    def test_a_single_line_is_tagged_once(self):
        self._arm()
        log_identity.begin_turn(1, 'angela')
        self.logfile.text = ''
        self.tee.write('--- Loading context\n')
        self.assertEqual(self.logfile.text, '[a1] --- Loading context\n')

    def test_every_line_of_a_multi_line_chunk_is_tagged(self):
        self._arm()
        log_identity.begin_turn(1, 'angela')
        self.logfile.text = ''
        self.tee.write('first\nsecond\nthird\n')
        self.assertEqual(
            self.logfile.text, '[a1] first\n[a1] second\n[a1] third\n'
        )

    def test_print_writes_text_and_newline_separately_and_is_tagged_once(self):
        # print() calls write() TWICE. Exactly one tag must appear.
        self._arm()
        log_identity.begin_turn(1, 'angela')
        self.logfile.text = ''
        self.tee.write('half a line')
        self.tee.write('\n')
        self.assertEqual(self.logfile.text, '[a1] half a line\n')

    def test_a_blank_line_spends_no_characters(self):
        self._arm()
        log_identity.begin_turn(1, 'angela')
        self.logfile.text = ''
        self.tee.write('\n')
        self.assertEqual(self.logfile.text, '\n')

    def test_two_users_interleaved_stay_separable(self):
        self._arm()
        angela_ctx = contextvars.copy_context()
        alice_ctx = contextvars.copy_context()
        angela_ctx.run(log_identity.begin_turn, 1, 'angela')
        alice_ctx.run(log_identity.begin_turn, 2, 'alice')
        self.logfile.text = ''
        angela_ctx.run(self.tee.write, 'angela step 1\n')
        alice_ctx.run(self.tee.write, 'alice step 1\n')
        angela_ctx.run(self.tee.write, 'angela step 2\n')
        self.assertEqual(
            self.logfile.text,
            '[a1] angela step 1\n[b1] alice step 1\n[a1] angela step 2\n',
        )

    def test_an_unattributed_line_is_byte_identical(self):
        self._arm()
        self.logfile.text = ''
        self.tee.write('--- [TEMP] Temporary files pinned\n')
        self.assertEqual(self.logfile.text, '--- [TEMP] Temporary files pinned\n')

    def test_no_hook_installed_means_no_change(self):
        self.logfile.text = ''
        log_identity.begin_turn(1, 'angela')
        self.tee.write('startup line\n')
        self.assertEqual(self.logfile.text, 'startup line\n')

    def test_write_returns_the_length_the_caller_passed(self):
        self._arm()
        log_identity.begin_turn(1, 'angela')
        payload = 'a tagged line\n'
        self.assertEqual(self.tee.write(payload), len(payload))

    def test_a_hook_that_raises_never_breaks_logging(self):
        def exploding_hook():
            raise RuntimeError('boom')

        self.namespace['_USER_TAG_HOOK'] = exploding_hook
        self.logfile.text = ''
        self.tee.write('the log must still work\n')
        self.assertEqual(self.logfile.text, 'the log must still work\n')

    def test_console_and_log_file_receive_the_same_text(self):
        self._arm()
        log_identity.begin_turn(1, 'angela')
        self.console.text = ''
        self.logfile.text = ''
        self.tee.write('same on both\n')
        self.assertEqual(self.console.text, self.logfile.text)
        self.assertEqual(self.console.text, '[a1] same on both\n')


    def test_the_legend_line_never_wears_a_tag(self):
        # The legend explains the tags, so it must not wear one -- not even the
        # tag of whoever happened to be bound when the new user was first seen.
        self._arm()
        log_identity.begin_turn(1, 'angela')
        self.logfile.text = ''
        original_stdout = sys.stdout
        sys.stdout = self.tee
        try:
            log_identity.begin_turn(2, 'alice')
        finally:
            sys.stdout = original_stdout
        self.assertEqual(self.logfile.text, '--- [WHO] b = alice (user id 2)\n')


class WiringContractTests(SimpleTestCase):
    """The surfaces that must stay aligned, pinned so a refactor cannot drop one."""

    def test_manage_py_exposes_the_hook_slot_and_consults_it(self):
        source = _read(MANAGE_PY)
        self.assertIn('_USER_TAG_HOOK = None', source)
        self.assertIn('if _USER_TAG_HOOK is not None and data:', source)
        self.assertIn('def _tag_lines(self, data, tag):', source)

    def test_manage_py_never_imports_the_agent_package_for_tagging(self):
        # The tee runs BEFORE Django exists; importing agent.* there would drag
        # protobuf/gRPC into startup. The coupling MUST stay inverted.
        source = _read(MANAGE_PY)
        self.assertNotIn('from agent.log_identity', source)
        self.assertNotIn('import agent.log_identity', source)

    def test_log_identity_installs_itself_on_import(self):
        self.assertTrue(log_identity._INSTALLED)

    def test_consumers_bind_the_user_on_connect_receive_and_run(self):
        source = _read(CONSUMERS_PY)
        self.assertIn('from . import log_identity', source)
        self.assertIn('log_identity.bind(user.id, user.username)', source)
        self.assertIn('log_identity.begin_turn(user.id, user.username)', source)
        self.assertIn('log_identity.bind(broker_key,', source)

    def test_http_requests_are_attributed_too(self):
        self.assertIn('class UserLogTagMiddleware:', _read(MIDDLEWARE_PY))
        self.assertIn(
            "MIDDLEWARE.append('tlamatini.middleware.UserLogTagMiddleware')",
            _read(SETTINGS_PY),
        )

    def test_the_knobs_are_documented_in_the_module(self):
        source = _read(os.path.join(_AGENT_DIR, 'log_identity.py'))
        for key in (
            'log_user_tags',
            'log_user_tag_style',
            'log_user_tag_thread_inherit',
        ):
            self.assertIn(key, source)
