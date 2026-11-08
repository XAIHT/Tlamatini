# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Answer a pure scope-inventory question without an LLM intent decision.

This is the same directory list enforced by path_guard, not a disk scan or a
permission grant. Mixed requests continue through the normal access checks.
"""
import html
import re
import unicodedata

from ..path_guard import get_allowed_dirs_display


_EN = re.compile(
    r"(?:list|show(?: me)?|display|enumerate|tell me|what are|which are) "
    r"(?:the |all (?:the )?)?(?:available|allowed|permitted|configured|authorized) "
    r"(?:directories|folders|paths|locations)"
)
_ES = re.compile(
    r"(?:lista(?:me)?|listar|muestra(?:me)?|mostrar|dame|dime|enumera|enumerar|cuales son|que) "
    r"(?:todos? (?:los )?|todas? (?:las )?|los |las )?"
    r"(?:directorios|carpetas|rutas|paths|ubicaciones) "
    r"(?:disponibles|permitidos|permitidas|configurados|configuradas|autorizados|autorizadas|"
    r"a los que tienes acceso|a las que tienes acceso)"
)


def directory_listing_language(question):
    """Recognize only an entire inventory request, never a substring."""
    if not isinstance(question, str):
        return None
    text = ''.join(c for c in unicodedata.normalize('NFKD', question.casefold())
                   if not unicodedata.combining(c))
    text = re.sub(r'\s+', ' ', text).strip(' \t\r\n¿¡?!.')
    text = re.sub(r'^tlamatini(?:-spanish)?\s*[,!:—-]\s*', '', text)
    text = re.sub(r'^(?:por favor|please)[, ]+', '', text)
    text = re.sub(r'[, ]+(?:por favor|please)$', '', text).strip(' ,¿?!.')
    text = re.sub(r'^(?:puedes|podrias|me puedes|me podrias|can you|could you) ', '', text)
    if _ES.fullmatch(text):
        return 'es'
    if _EN.fullmatch(text):
        return 'en'
    return None


def available_directories_reply(question):
    language = directory_listing_language(question)
    if language is None:
        return None
    # Use the active guard's exact roots. Do not reread a new config while the
    # guard still enforces an older one; listing and enforcement must agree.
    directories = list(dict.fromkeys(get_allowed_dirs_display()))
    spanish = language == 'es'
    title = 'Directorios disponibles' if spanish else 'Available directories'
    intro = ('Estos son los directorios permitidos por la configuración activa de esta instancia.'
             if spanish else 'These are the directories allowed by this instance’s active configuration.')
    if directories:
        body = '<ul>' + ''.join('<li><code>' + html.escape(path) + '</code></li>'
                               for path in directories) + '</ul>'
    else:
        body = ('<p>No hay directorios permitidos resueltos en la configuración activa. '
                'Revisa allowed_paths en Config.</p>' if spanish else
                '<p>No allowed directories are resolved in the active configuration. '
                'Check allowed_paths in Config.</p>')
    note = ('No necesitas proporcionar una ruta para consultar esta lista. Las operaciones '
            'sobre archivos siguen sujetas a los permisos de Windows.' if spanish else
            'You do not need to provide a path to view this list. File operations remain '
            'subject to Windows permissions.')
    return f'<h3>{title}</h3><p>{intro}</p>{body}<p>{note}</p>\nEND-RESPONSE'
