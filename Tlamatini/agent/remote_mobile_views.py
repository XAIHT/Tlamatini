# Tlamatini — Created by Angela López Mendoza · XAIHT
"""Touch-friendly selection of host files using existing application permissions.

This module does not implement or change database backup/restore. It returns a
user-selected path to those existing dialogs. Canvas saves reuse the existing
revision/capability boundary and atomic writer.
"""
from pathlib import Path
import os

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import path_guard
from .remote_controller_views import _local_request, _profile_for

def _say(english, spanish):
    """This edition's wording for a message shown on the phone."""
    from .remote_controller_bridge import EDITION
    return spanish if EDITION == "spanish" else english


def _authorized(request):
    profile = _profile_for(request.user)
    return (_local_request(request) and request.user.is_active
            and profile is not None and profile.enabled and bool(profile.binding_id))


def _resolve(value, *, directory=False):
    if not isinstance(value, str) or len(value) > 4096 or '\x00' in value:
        return None
    resolved = path_guard.resolve_runtime_agent_path(value, must_exist=True,
                                                    expect_dir=directory)
    if not resolved:
        return None
    path = Path(resolved)
    if path.is_symlink() or getattr(path.stat(), 'st_file_attributes', 0) & 0x400:
        return None
    return path


@login_required
@never_cache
@require_http_methods(['GET'])
def files(request):
    if not _authorized(request):
        return JsonResponse({'error': _say('Remote access is disabled for this account.', 'El acceso remoto está deshabilitado para esta cuenta.')}, status=403)
    roots = list(dict.fromkeys([path_guard._get_application_root(),
                               *path_guard.get_allowed_dirs_display()]))
    try:
        folder = _resolve(request.GET.get('path') or roots[0], directory=True)
        if folder is None:
            return JsonResponse({'error': _say('Choose a folder permitted by Tlamatini configuration.', 'Elige una carpeta permitida por la configuración de Tlamatini.')}, status=403)
        offset = int(request.GET.get('offset', '0'))
        if offset < 0 or offset > 100000:
            raise ValueError()
        entries = []
        with os.scandir(folder) as scan:
            for index, item in enumerate(scan):
                if index < offset:
                    continue
                if len(entries) >= 200:
                    break
                try:
                    if item.is_symlink() or getattr(item.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400:
                        continue
                    is_dir = item.is_dir(follow_symlinks=False)
                    if not is_dir and not item.is_file(follow_symlinks=False):
                        continue
                    entries.append({'name': item.name, 'path': item.path,
                                    'directory': is_dir})
                except OSError:
                    continue
            else:
                index = -1
        parent = _resolve(str(folder.parent), directory=True)
        return JsonResponse({'path': str(folder), 'parent': str(parent) if parent and parent != folder else None,
                             'roots': roots, 'entries': sorted(entries, key=lambda e: (not e['directory'], e['name'].casefold())),
                             'next_offset': index if index >= 0 and len(entries) == 200 else None})
    except (OSError, ValueError):
        return JsonResponse({'error': _say('This folder cannot be listed. Check its path and access permissions.', 'No se puede mostrar esta carpeta. Revisa su ruta y sus permisos de acceso.')}, status=400)


@login_required
@never_cache
@require_http_methods(['POST'])
def canvas_selection(request):
    """Observe the revision before explicit mobile Save As confirmation."""
    if not _authorized(request):
        return JsonResponse({'error': _say('Remote access is disabled for this account.', 'El acceso remoto está deshabilitado para esta cuenta.')}, status=403)
    from . import canvas_file_views as canvas
    try:
        owner = canvas._owner(request)
        canvas._bound_body(request, 8192)
        folder = _resolve(request.POST.get('directory', ''), directory=True)
        name = request.POST.get('name', '')
        if folder is None or not name or len(name) > 240 or name in {'.', '..'} or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name):
            raise canvas.SaveError(_say('Choose a permitted folder and valid file name.', 'Elige una carpeta permitida y un nombre de archivo válido.'))
        path = folder / name
        canvas._check_path(path)
        with canvas._IO_LOCK:
            _, revision = canvas._snapshot(path)
            token = canvas._grant(path, owner)
        return canvas._response({'token': token, 'revision': revision, 'path': str(path), 'exists': revision != 'missing'})
    except canvas.SaveError as error:
        return canvas._response({'error': str(error), 'code': error.code}, error.status)
    except OSError:
        return canvas._response({'error': _say('This destination cannot be selected.', 'No se puede seleccionar este destino.')}, 400)


@login_required
@never_cache
@require_http_methods(['POST'])
def canvas_save(request):
    """Commit only a session-owned selected destination and observed revision."""
    if not _authorized(request):
        return JsonResponse({'error': _say('Remote access is disabled for this account.', 'El acceso remoto está deshabilitado para esta cuenta.')}, status=403)
    from . import canvas_file_views as canvas
    try:
        owner = canvas._owner(request)
        canvas._bound_body(request, canvas.MAX_FILE_BYTES + 65536)
        token = request.POST.get('token', '')
        path = canvas._capability(token, owner).path
        # Recheck current path permissions, including links and configuration.
        if _resolve(str(path.parent), directory=True) is None:
            raise canvas.SaveError(_say('This destination is no longer permitted.', 'Este destino ya no está permitido.'), 'forbidden', 403)
        upload = request.FILES.get('file')
        if upload is None or upload.size > canvas.MAX_FILE_BYTES:
            raise canvas.SaveError(_say('Choose a file within the 64 MiB limit.', 'Elige un archivo dentro del límite de 64 MiB.'), 'too_large', 413)
        data = upload.read(canvas.MAX_FILE_BYTES + 1)
        if len(data) > canvas.MAX_FILE_BYTES:
            raise canvas.SaveError(_say('Choose a file within the 64 MiB limit.', 'Elige un archivo dentro del límite de 64 MiB.'), 'too_large', 413)
        with canvas._IO_LOCK:
            revision = canvas._commit(path, data, request.POST.get('revision', ''))
        return canvas._response({'saved': True, 'token': token, 'revision': revision,
                                 'filename': path.name, 'path': str(path), 'bytes': len(data)})
    except canvas.SaveError as error:
        return canvas._response({'saved': False, 'error': str(error), 'code': error.code}, error.status)
    except OSError:
        return canvas._response({'saved': False, 'error': _say('The file could not be saved.', 'No se pudo guardar el archivo.')}, 400)
