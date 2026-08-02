"""
GUARDA: en las pruebas, las fotos las toma SHOTER — nunca PIL.ImageGrab.
=======================================================================

Regla de Angela (2026-08-02). Este test se pone ROJO si alguien vuelve a meter
`PIL.ImageGrab` en un harness, aunque sea "nada más para esta prueba rapidita".

POR QUÉ EXISTE
    Mientras las pruebas se tomaban sus propias fotos con Pillow, Shoter nunca
    se ejercitaba — y por eso nadie notó que llamaba a `ImageGrab.grab()` SIN
    `all_screens` y perdía el segundo monitor completo, en silencio. La regla no
    es de estilo: es la que hace que los defectos de Shoter aparezcan.
"""
import os
import unittest

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), '.claude', 'skills',
    'tlamatini-daily-chat-test', 'harness')


class ShoterTakesTheScreenshots(unittest.TestCase):

    def _live_lines(self):
        """Líneas de CÓDIGO (no comentarios ni docstrings) que usan ImageGrab."""
        malas = []
        if not os.path.isdir(HARNESS):
            return malas
        for nombre in sorted(os.listdir(HARNESS)):
            if not nombre.endswith('.py'):
                continue
            ruta = os.path.join(HARNESS, nombre)
            dentro_doc = False
            with open(ruta, encoding='utf-8', errors='replace') as fh:
                for i, ln in enumerate(fh, 1):
                    s = ln.strip()
                    if s.count('"""') == 1:
                        dentro_doc = not dentro_doc
                        continue
                    if dentro_doc or s.startswith('#') or '"""' in s:
                        continue
                    if 'ImageGrab' in s:
                        malas.append('%s:%d  %s' % (nombre, i, s[:70]))
        return malas

    def test_no_harness_uses_imagegrab(self):
        malas = self._live_lines()
        self.assertEqual(
            malas, [],
            'PROHIBIDO PIL.ImageGrab en las pruebas: las fotos las toma SHOTER '
            '(ver shoter_shot.py). Encontrado en:\n  - ' + '\n  - '.join(malas))

    def test_the_shoter_launcher_exists(self):
        self.assertTrue(
            os.path.isfile(os.path.join(HARNESS, 'shoter_shot.py')),
            'falta shoter_shot.py: es el lanzador que usan todas las pruebas')

    def test_shoter_captures_the_whole_desktop(self):
        """all_screens debe seguir existiendo y venir en TRUE por default."""
        shoter = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'agents', 'shoter', 'shoter.py')
        with open(shoter, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('all_screens', src,
                      'Shoter perdió el parámetro all_screens')
        self.assertIn('ImageGrab.grab(all_screens=True)', src,
                      'Shoter volvió a capturar sólo la pantalla principal')
        cfg = os.path.join(os.path.dirname(shoter), 'config.yaml')
        with open(cfg, encoding='utf-8') as fh:
            self.assertIn('all_screens: true', fh.read(),
                          'config.yaml de Shoter ya no trae all_screens: true')
