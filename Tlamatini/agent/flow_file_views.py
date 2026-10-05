# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Authenticated browser handoff and loopback instance identification."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from . import flow_file_open as files


@require_GET
def status(request):
    if request.META.get('REMOTE_ADDR') not in ('127.0.0.1', '::1'):
        return JsonResponse({'error': 'Local requests only.'}, status=403)
    response = JsonResponse(files.status_payload())
    response['Cache-Control'] = 'no-store'
    return response


def upload(request, *, validate_only=False):
    file = request.FILES.get('file')
    if file is None:
        return JsonResponse({'error': 'Choose a flow file.'}, status=400)
    if file.size > files.MAX_FILE_BYTES:
        return JsonResponse({'error': 'The flow file must be no larger than 5 MiB.'}, status=400)
    try:
        data = file.read(files.MAX_FILE_BYTES + 1)
        if validate_only:
            return JsonResponse({'flow': files.decode_file(data, file.name)})
        token = files.create_request(data, file.name,
                                     user_id=request.user.pk)
        return JsonResponse({'url': files.opening_path(file.name, token)})
    except (files.FlowError, OSError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)


def opening_context(request, extension):
    token = request.GET.get('open')
    if not token:
        return {}
    try:
        opened = files.consume_request(token, request.user.pk, extension)
        prefix = 'flw' if extension == '.flw' else 'fpmt'
        return {prefix + '_data': opened['flow'], prefix + '_filename': opened['filename']}
    except (files.FlowError, OSError) as exc:
        return {'flow_open_error': str(exc)}


def validate(request):
    return upload(request, validate_only=True)
