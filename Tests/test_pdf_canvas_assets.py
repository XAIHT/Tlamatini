# Tlamatini Author Banner — Angela López Mendoza
"""Check real Django/WhiteNoise MIME handling and collected PDF assets in isolation."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pdf_assets_collect_and_serve_with_correct_mime_types(tmp_path):
    script = r'''
import mimetypes
import sys
from pathlib import Path

root, destination = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'Tlamatini'))
# Reproduce the problematic Windows association before importing app settings.
mimetypes.add_type('text/plain', '.mjs')
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
from django.conf import settings
settings.INSTALLED_APPS = ['django.contrib.staticfiles']
settings.STATIC_ROOT = destination
settings.STATICFILES_DIRS = [root / 'Tlamatini/agent/static']
import django
django.setup()
from django.core.management import call_command
call_command('collectstatic', interactive=False, verbosity=0)
from django.test import RequestFactory
from django.views.static import serve
from whitenoise import WhiteNoise
from wsgiref.util import setup_testing_defaults

files = {
    'agent/vendor/pdfjs/build/pdf.mjs': 'text/javascript',
    'agent/vendor/pdfjs/build/pdf.worker.mjs': 'text/javascript',
    'agent/vendor/pdfjs/web/pdf_viewer.mjs': 'text/javascript',
    'agent/vendor/pdfjs/wasm/openjpeg.wasm': 'application/wasm',
    'agent/pdf/canvas.html': 'text/html',
}
app = WhiteNoise(lambda *_args: [], root=destination, mimetypes=settings.WHITENOISE_MIMETYPES)
for path, expected in files.items():
    assert (destination / path).is_file(), path
    response = serve(RequestFactory().get('/' + path), path, document_root=destination)
    assert response['Content-Type'].split(';')[0] == expected, (path, dict(response.headers))
    response.close()
    environ = {}
    setup_testing_defaults(environ)
    environ['PATH_INFO'] = '/' + path
    headers = []
    body = app(environ, lambda status, values: headers.extend(values))
    assert dict(headers)['Content-Type'].split(';')[0] == expected, (path, headers)
    if hasattr(body, 'close'):
        body.close()
for path in ['agent/js/agent_page_pdf.js', 'agent/js/pdf_canvas_viewer.js',
             'agent/js/pdf_context_progress.js', 'agent/css/pdf_context_progress.css',
             'agent/css/pdf_canvas.css', 'agent/vendor/pdfjs/LICENSE',
             'agent/vendor/pdfjs/cmaps/Adobe-Japan1-UCS2.bcmap',
             'agent/vendor/pdfjs/standard_fonts/FoxitSerif.pfb']:
    assert (destination / path).read_bytes() == (root / 'Tlamatini/agent/static' / path).read_bytes(), path
print('PDF assets collect and serve correctly in Django and WhiteNoise')
'''
    result = subprocess.run([sys.executable, "-c", script, str(ROOT), str(tmp_path / "static")],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
