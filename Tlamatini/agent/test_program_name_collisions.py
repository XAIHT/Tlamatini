"""Two code blocks in ONE answer must never break each other's file.

REGRESSION (Angela, 2026-09-06, live on the installed build in C:\\Tlamatini):

    agent.models.LLMProgram.MultipleObjectsReturned:
        get() returned more than one LLMProgram -- it returned 2!

Clicking "Load in canvas" returned a 500, and "save files from DB" answered
``!!! ERROR while saving file: get() returned more than one LLMProgram`` for
BOTH files, so neither could ever be written to disk.

ROOT CAUSE — names carry only a one-SECOND timestamp:

    programName = get_time_stamp() + "_" + "Without_Name"     # %Y%m%d%H%M%S

Two unnamed code blocks in the SAME answer are parsed in the same second, so
both rows were created with the identical name (verified in her database:
idProgram 3 and 4, both ``20260907030945_Without_Name``, 489 and 506 bytes of
DIFFERENT content). Every reader then looked the file up by NAME with
``.get()`` — and ``MultipleObjectsReturned`` is NOT caught by
``except LLMProgram.DoesNotExist``, so it escaped as an unhandled 500.

THE FIX HAS TWO HALVES AND NEITHER MAY BE DROPPED:
  1. WRITE side — ``_uniquify_name`` gives the second block its own name, and
     ``save_program`` / ``save_snippet`` RETURN the stored name so the canvas
     link points at the row that was actually written.
  2. READ side — every lookup is ``filter(...).first()``, so a database
     written by an OLDER build (which still holds duplicates) opens the file
     instead of raising.
"""
import os
import re

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from agent.models import LLMProgram, LLMSnippet
from agent.services import response_parser
from agent.services.response_parser import _uniquify_name, save_program, save_snippet

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))


class UniquifyNameTests(TestCase):
    def test_free_name_is_returned_unchanged(self):
        self.assertEqual(_uniquify_name(LLMProgram, 'programName', 'a.py'), 'a.py')

    def test_taken_name_gets_the_next_free_suffix(self):
        LLMProgram.objects.create(programName='a.py', programLanguage='py', programContent='1')
        self.assertEqual(_uniquify_name(LLMProgram, 'programName', 'a.py'), 'a.py_2')
        LLMProgram.objects.create(programName='a.py_2', programLanguage='py', programContent='2')
        self.assertEqual(_uniquify_name(LLMProgram, 'programName', 'a.py'), 'a.py_3')

    def test_a_database_error_fails_open_to_the_original_name(self):
        class Boom:
            class objects:
                @staticmethod
                def filter(**_kwargs):
                    raise RuntimeError("database is gone")

        self.assertEqual(
            _uniquify_name(Boom, 'programName', 'a.py'), 'a.py',
            "uniquifying must FAIL-OPEN - it may never stop the user's code being saved")


class SaveReturnsTheStoredNameTests(TestCase):
    def test_two_saves_of_one_name_produce_two_rows_with_distinct_names(self):
        first = async_to_sync(save_program)('20260907030945_Without_Name', 'by-extension', 'one')
        second = async_to_sync(save_program)('20260907030945_Without_Name', 'by-extension', 'two')
        self.assertEqual(first, '20260907030945_Without_Name')
        self.assertEqual(second, '20260907030945_Without_Name_2')
        self.assertEqual(LLMProgram.objects.count(), 2)
        self.assertEqual(
            LLMProgram.objects.get(programName=second).programContent, 'two',
            "the SECOND block's own content must live under the SECOND name")

    def test_snippets_are_uniquified_too(self):
        first = async_to_sync(save_snippet)('20260907030945_python.py', 'python', 'one')
        second = async_to_sync(save_snippet)('20260907030945_python.py', 'python', 'two')
        self.assertNotEqual(first, second)
        self.assertEqual(LLMSnippet.objects.count(), 2)


class TwoUnnamedBlocksEndToEndTests(TestCase):
    """The exact shape of Angela's answer: two DIFFERENT unnamed code blocks."""

    def _process(self, raw):
        return async_to_sync(response_parser.process_llm_response)(
            raw, None, None, None,
            conversation_user=None, tool_calls_log=None, multi_turn_used=False,
            exec_report_enabled=False, exec_report_entries=None,
        )

    def test_each_block_gets_its_own_name_and_its_own_link(self):
        raw = (
            "Here are the two files.\n"
            "BEGIN-CODE\nprint('ONE')\nEND-CODE\n"
            "BEGIN-CODE\nprint('TWO')\nEND-CODE\n"
            "END-RESPONSE"
        )
        final = self._process(raw)

        names = list(LLMProgram.objects.values_list('programName', flat=True))
        self.assertEqual(len(names), 2, "both blocks must be saved")
        self.assertEqual(len(set(names)), 2,
                         "the two blocks must NOT share one name - that is the bug")

        linked = re.findall(r"---Load in canvas: ([^-]+)---", final)
        self.assertEqual(len(set(linked)), 2,
                         "each link must point at its OWN row, not both at the first")
        self.assertEqual(set(linked), set(names))

        # And the contents did not swap.
        for name in names:
            row = LLMProgram.objects.get(programName=name)
            self.assertIn(row.programContent.strip(), ("print('ONE')", "print('TWO')"))


class DuplicatesAlreadyInTheDatabaseStillLoadTests(TestCase):
    """A database written by an OLDER build still carries duplicate names."""

    def setUp(self):
        self.user = User.objects.create_user('angela', password='x')
        self.factory = RequestFactory()
        LLMProgram.objects.create(idProgram=3, programName='dup', programLanguage='by-extension',
                                  programContent='FIRST')
        LLMProgram.objects.create(idProgram=4, programName='dup', programLanguage='by-extension',
                                  programContent='SECOND')

    def test_load_canvas_view_serves_the_newest_instead_of_raising_500(self):
        from agent.views import load_canvas_view
        request = self.factory.get('/agent/load_canvas/dup/')
        request.user = self.user
        response = load_canvas_view(request, 'dup')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'SECOND')

    def test_missing_name_is_still_a_404(self):
        from agent.views import load_canvas_view
        request = self.factory.get('/agent/load_canvas/nope/')
        request.user = self.user
        response = load_canvas_view(request, 'nope')
        self.assertEqual(response.status_code, 404)

    def test_snippet_fallback_still_works(self):
        from agent.views import load_canvas_view
        LLMSnippet.objects.create(idSnippet=1, snippetName='snip', snippetLanguage='python',
                                  snippetContent='SNIPPET')
        request = self.factory.get('/agent/load_canvas/snip/')
        request.user = self.user
        response = load_canvas_view(request, 'snip')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'SNIPPET')

    def test_rag_interface_lookup_does_not_raise(self):
        from agent.rag.interface import get_program_by_name
        self.assertEqual(get_program_by_name('dup').programContent, 'SECOND')
        self.assertIsNone(get_program_by_name('nope'))


class NoLookupMayUseGetAgainTests(TestCase):
    """SOURCE CONTRACT: a single `.get(programName=...)` anywhere re-arms the bug."""

    _FILES = (
        'views.py',
        'consumers.py',
        os.path.join('services', 'filesystem.py'),
        os.path.join('services', 'response_parser.py'),
        os.path.join('rag', 'interface.py'),
    )

    def test_no_get_by_name_lookup_survives(self):
        offenders = []
        for rel in self._FILES:
            path = os.path.join(_AGENT_DIR, rel)
            with open(path, 'r', encoding='utf-8') as handle:
                for lineno, line in enumerate(handle, 1):
                    code = line.split('#', 1)[0]
                    if re.search(r"objects\.get\(\s*(programName|snippetName)\s*=", code):
                        offenders.append(f"{rel}:{lineno}")
        self.assertEqual(
            offenders, [],
            "name lookups must be filter(...).first() - `.get()` raises "
            "MultipleObjectsReturned on a database that already holds duplicates: "
            + ", ".join(offenders))
