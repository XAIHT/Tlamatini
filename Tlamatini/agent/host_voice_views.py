# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""The page side of Tlamatini's host voice (see ``host_voice.py``).

Every view is for the signed-in account only and acts on that account's own
speech. ``speak`` also accepts the form that ``navigator.sendBeacon`` posts
while a page is closing, with the CSRF token as an ordinary form field.
"""

import json

from django.http import JsonResponse

from . import host_voice

_MAX_BODY = 256 * 1024


def _payload(request):
    # Measure from the header: the CSRF check has already read a beacon's form
    # body, and Django refuses request.body after that.
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > _MAX_BODY:
            return None
    except ValueError:
        return None
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None
    try:
        data = json.loads(request.POST.get("payload", "") or "{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def settings_view(request):
    data = _payload(request)
    if data is None:
        return JsonResponse({"error": "Expected the voice settings as JSON."}, status=400)
    return JsonResponse({"settings": host_voice.update_settings(request.user.id, data),
                         "available": host_voice.available()})


def speak_view(request):
    data = _payload(request)
    if data is None or not isinstance(data.get("text", ""), str):
        return JsonResponse({"error": "Expected the text to speak."}, status=400)
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else None
    job = host_voice.speak(request.user.id, data.get("text", ""), settings, str(data.get("reason", ""))[:80])
    return JsonResponse({"job_id": job or "", "available": host_voice.available()})


def status_view(request):
    return JsonResponse(host_voice.status(request.user.id, str(request.GET.get("job", ""))[:64]))


def stop_view(request):
    return JsonResponse({"stopped": host_voice.stop(request.user.id)})
