# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Scope inventory must never require a target path or an available model."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from agent.rag import directory_listing, interface
from agent.global_state import global_state


class AvailableDirectoriesTests(SimpleTestCase):
    def test_ordinary_requests_in_both_languages_need_no_classifier(self):
        requests = (
            'List available directories, please.',
            'Please show me the allowed folders.',
            'Can you list the configured paths?',
            'Tlamatini, list available directories, please.',
            'Lista los directorios disponibles, por favor.',
            'Tlamatini, por favor, lista los directorios disponibles.',
            '¿Cuáles son los directorios disponibles?',
            'Muéstrame las carpetas permitidas.',
            'Dame las rutas a las que tienes acceso.',
            '¿Me puedes mostrar los directorios disponibles?',
        )
        for text in requests:
            with self.subTest(text=text), \
                 patch.object(directory_listing, 'get_allowed_dirs_display', return_value=['C:\\Test\\Downloads']), \
                 patch.object(interface, '_validate_accesses_in_prompt', side_effect=AssertionError('intent model must not run')):
                chain = Mock()
                answer = interface.ask_rag(chain, text)
                self.assertIn('C:\\Test\\Downloads', answer)
                self.assertNotIn('paths explícitos', answer)
                chain.invoke.assert_not_called()
                self.assertTrue(global_state.get_state('rag_chain_ready'))

    def test_never_swallow_a_second_action_or_explicit_path(self):
        for text in (
            'List available directories and delete their contents.',
            'Lista los directorios disponibles y borra C:\\private.',
            'List available directories. Then read secrets.txt.',
            'Muestra las carpetas permitidas; abre ../secretos.',
            'List available directories in C:\\private.',
            'List files in Downloads.',
            'Responde exactamente "lista los directorios disponibles".',
            None,
        ):
            with self.subTest(text=text):
                self.assertIsNone(directory_listing.available_directories_reply(text))

    def test_escape_actual_roots_and_do_not_invent_roots_when_empty(self):
        with patch.object(directory_listing, 'get_allowed_dirs_display', return_value=['C:/A&B/<x>', 'C:/A&B/<x>']):
            answer = directory_listing.available_directories_reply('List available directories.')
            self.assertEqual(answer.count('<li>'), 1)
            self.assertIn('C:/A&amp;B/&lt;x&gt;', answer)
            self.assertNotIn('<x>', answer)
        with patch.object(directory_listing, 'get_allowed_dirs_display', return_value=[]):
            answer = directory_listing.available_directories_reply('Lista los directorios disponibles.')
            self.assertIn('No hay directorios permitidos resueltos', answer)
            self.assertNotIn('<li>', answer)

    def test_inventory_uses_the_enforced_snapshot(self):
        from agent import path_guard
        with patch.object(path_guard, '_ALLOWED_DIRS', ['C:/OnlyAllowed']):
            answer = directory_listing.available_directories_reply('List available directories.')
            self.assertIn('C:/OnlyAllowed', answer)
            self.assertNotIn('C:/Users', answer)
