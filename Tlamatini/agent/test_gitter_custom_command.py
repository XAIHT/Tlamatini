"""Gitter `custom_command` tokenization — Windows paths must survive.

THE BUG (measured 2026-09-11, while committing the glm-5.3 switch):
`build_git_command` tokenized `custom_command` with
``shlex.split(..., posix=True)``. In POSIX mode a backslash is an ESCAPE
character, so

    commit -F C:\\Development\\XAIHT\\Tlamatini\\Temp\\commit_msg.txt

reached git as

    commit -F C:DevelopmentXAIHTTlamatiniTempcommit_msg.txt

and git died with `fatal: could not read log file ... No such file or
directory`. EVERY Windows path passed to Gitter was silently mangled.

THE FIX: on Windows tokenize with ``posix=False`` (backslashes stay
literal) and strip the surrounding quotes ourselves, since posix=False
keeps them. POSIX hosts stay on posix=True, where a backslash really IS
an escape character.

THIS FILE MUST PROVE BOTH DIRECTIONS:
  1. the Windows path is no longer mangled, AND
  2. the reason posix=True existed in the first place still holds — a
     quoted multi-word argument (`-m "Release notes with spaces"`) still
     collapses into ONE token, instead of git seeing
     "fatal: too many arguments".

A fix that repaired (1) by breaking (2) would be a regression dressed up
as an improvement, which is exactly what these tests exist to catch.

`gitter.py` is a POOL AGENT: importing it would set env vars, configure
logging and write a PID file, so the two functions are AST-lifted out of
the source instead — the same trick `test_django_port_config.py` uses on
`manage.py`.
"""

import ast
import logging
import os
import unittest
from typing import Dict

#   <repo>/Tlamatini/agent/test_gitter_custom_command.py  ->  <repo>/Tlamatini/agent
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_GITTER_PY = os.path.join(_AGENT_DIR, 'agents', 'gitter', 'gitter.py')

_WANTED_FUNCS = ('build_git_command', '_strip_wrapping_quotes')

# The exact string that broke the real commit, and the exact mangling it suffered.
_REAL_PATH = r'C:\Development\XAIHT\Tlamatini\Temp\commit_msg.txt'
_MANGLED_PATH = 'C:DevelopmentXAIHTTlamatiniTempcommit_msg.txt'


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


class _OsShim:
    """Real `os`, but with `name` forced — lets us drive BOTH branches."""

    def __init__(self, name):
        self.name = name

    def __getattr__(self, item):
        return getattr(os, item)


def _load_gitter_helpers(os_name=None):
    """Exec ONLY the tokenizer helpers out of gitter.py — never import it."""
    tree = ast.parse(_read(_GITTER_PY), filename=_GITTER_PY)
    picked = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in _WANTED_FUNCS
    ]
    namespace = {
        'os': os if os_name is None else _OsShim(os_name),
        'logging': logging,
        'Dict': Dict,
    }
    exec(compile(ast.Module(body=picked, type_ignores=[]), _GITTER_PY, 'exec'),  # noqa: S102
         namespace)
    return namespace


def _build(custom_command, os_name='nt'):
    ns = _load_gitter_helpers(os_name)
    return ns['build_git_command']({
        'command': 'custom',
        'custom_command': custom_command,
    })


class GitterHelpersAreLiftableTests(unittest.TestCase):
    """If this class fails, every other test below is meaningless."""

    def test_both_helpers_exist_in_the_source(self):
        ns = _load_gitter_helpers('nt')
        for name in _WANTED_FUNCS:
            self.assertIn(name, ns, "gitter.py no longer defines %s" % name)


class WindowsPathTokenizationTests(unittest.TestCase):
    """(1) THE FIX — a Windows path must reach git intact."""

    def test_windows_path_keeps_every_backslash(self):
        result = _build('commit -F ' + _REAL_PATH)
        self.assertEqual(result, ['git', 'commit', '-F', _REAL_PATH])

    def test_the_exact_reported_mangling_is_gone(self):
        result = _build('commit -F ' + _REAL_PATH)
        self.assertNotIn(_MANGLED_PATH, result,
                         "the POSIX-escape mangling is back")

    def test_quoted_windows_path_with_spaces_survives_whole(self):
        result = _build('commit -F "C:\\Program Files\\Tlamatini\\msg.txt"')
        self.assertEqual(
            result, ['git', 'commit', '-F', r'C:\Program Files\Tlamatini\msg.txt'])

    def test_pathspec_after_a_double_dash_survives(self):
        result = _build(r'log -1 --oneline -- C:\Development\XAIHT\README.md')
        self.assertEqual(result[-1], r'C:\Development\XAIHT\README.md')

    def test_trailing_backslash_directory_survives(self):
        result = _build(r'add C:\Development\XAIHT\Tlamatini\docs\\')
        self.assertTrue(result[-1].startswith(r'C:\Development'))
        self.assertNotIn('C:DevelopmentXAIHT', result[-1])


class QuotedArgumentStillCollapsesTests(unittest.TestCase):
    """(2) NO REGRESSION — the reason posix=True was chosen must still hold."""

    def test_quoted_multiword_message_stays_one_token(self):
        result = _build('tag -a v1.0 -m "Release notes with spaces"')
        self.assertEqual(
            result, ['git', 'tag', '-a', 'v1.0', '-m', 'Release notes with spaces'])

    def test_quoted_message_does_not_keep_its_quote_characters(self):
        result = _build('commit -m "hello world"')
        self.assertEqual(result[-1], 'hello world')
        self.assertNotIn('"', result[-1],
                         "posix=False left the quotes in the token")

    def test_single_quoted_argument_is_also_unwrapped(self):
        result = _build("commit -m 'hello world'")
        self.assertEqual(result[-1], 'hello world')

    def test_unquoted_command_is_split_on_spaces_as_before(self):
        self.assertEqual(_build('status --short --branch'),
                         ['git', 'status', '--short', '--branch'])

    def test_leading_git_token_is_still_stripped(self):
        self.assertEqual(_build('git status --short'),
                         ['git', 'status', '--short'])


class FailSafeTokenizationTests(unittest.TestCase):
    """Malformed input must degrade, never raise."""

    def test_unbalanced_quote_does_not_raise(self):
        result = _build('commit -m "unterminated message')
        self.assertIsNotNone(result)
        self.assertEqual(result[:2], ['git', 'commit'])

    def test_empty_custom_command_returns_none(self):
        self.assertIsNone(_build(''))


class PosixHostBehaviourTests(unittest.TestCase):
    """The POSIX branch is deliberately unchanged."""

    def test_posix_host_still_collapses_quoted_arguments(self):
        result = _build('commit -m "hello world"', os_name='posix')
        self.assertEqual(result, ['git', 'commit', '-m', 'hello world'])

    def test_posix_host_still_treats_backslash_as_an_escape(self):
        # Documents the intentional platform split: on POSIX a backslash is
        # an escape character and SHOULD be consumed. Windows is the outlier.
        result = _build(r'add a\ b', os_name='posix')
        self.assertEqual(result, ['git', 'add', 'a b'])


class StripWrappingQuotesUnitTests(unittest.TestCase):

    def setUp(self):
        self.strip = _load_gitter_helpers('nt')['_strip_wrapping_quotes']

    def test_removes_one_matching_pair(self):
        self.assertEqual(self.strip('"abc"'), 'abc')
        self.assertEqual(self.strip("'abc'"), 'abc')

    def test_leaves_unquoted_token_untouched(self):
        self.assertEqual(self.strip(r'C:\Dev\x.txt'), r'C:\Dev\x.txt')

    def test_leaves_mismatched_quotes_untouched(self):
        self.assertEqual(self.strip('"abc\''), '"abc\'')

    def test_handles_short_and_empty_tokens(self):
        self.assertEqual(self.strip(''), '')
        self.assertEqual(self.strip('"'), '"')

    def test_strips_only_the_outer_pair(self):
        self.assertEqual(self.strip('""abc""'), '"abc"')


class SourceContractTests(unittest.TestCase):
    """Pin the fix so a later 'simplification' cannot silently undo it."""

    def test_windows_branch_uses_posix_false(self):
        src = _read(_GITTER_PY)
        self.assertIn("shlex.split(custom_command, posix=False)", src,
                      "the Windows branch no longer uses posix=False")

    def test_posix_branch_is_still_present(self):
        src = _read(_GITTER_PY)
        self.assertIn("shlex.split(custom_command, posix=True)", src,
                      "the POSIX branch was removed")

    def test_the_bug_is_documented_next_to_the_code(self):
        src = _read(_GITTER_PY)
        self.assertIn("WINDOWS PATHS", src,
                      "the explanation of why posix=False is required is gone")


if __name__ == '__main__':
    unittest.main(verbosity=2)
