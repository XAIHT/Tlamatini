# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import logging
import threading
import uuid
from typing import Callable, Optional

from django.conf import settings
from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse

# Wired to the console handler in settings.LOGGING ("tlamatini.request"), so
# everything logged here reaches BOTH the console and tlamatini.log (the tee
# in manage.py flushes immediately on ERROR/Traceback markers).
_request_error_logger = logging.getLogger('tlamatini.request')


class NoCacheHTMLMiddleware:
    """Add no-store headers to HTML responses so browsers always revalidate pages.

    Static assets remain cached aggressively (with hashing) via WhiteNoise.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("text/html"):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response


# Friendly release 500 page. Inline (no template file dependency) so it can
# never itself fail on a missing/broken template, and deliberately free of any
# request-derived text so nothing user-controlled is ever reflected into it.
# The ONLY substitution is {error_id} (hex), applied via str.format below.
_FRIENDLY_ERROR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tlamatini — something went wrong</title>
</head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#111826;color:#e8e8e8;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:560px;padding:2.2rem 2.6rem;background:#1b2436;border:1px solid #2e3b55;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.45);">
<h1 style="margin:0 0 0.8rem 0;font-size:1.5rem;">⚠️ Something went wrong</h1>
<p style="margin:0.4rem 0;line-height:1.5;">Tlamatini hit an unexpected error while handling this request. The request was stopped safely.</p>
<p style="margin:0.9rem 0;">Error id: <code style="background:#0e1420;padding:0.15rem 0.5rem;border-radius:6px;color:#7fd1ff;">{error_id}</code></p>
<p style="margin:0.4rem 0;line-height:1.5;color:#b9c2d4;">The full technical details were written to <code>tlamatini.log</code> (next to the Tlamatini executable, or next to <code>manage.py</code> in source mode). Quote the error id when reporting the problem.</p>
<p style="margin:1.2rem 0 0 0;"><a href="javascript:history.back()" style="color:#7fd1ff;text-decoration:none;">← Go back</a></p>
</div>
</body>
</html>
"""


class FriendlyErrorMiddleware:
    """Release-mode useful-error contract (speed batch, 2026-07-02).

    With ``DEBUG=False`` Django would return a bare "Server Error (500)" page
    and — because its DEFAULT console log handler is filtered behind
    ``require_debug_true`` — the traceback could silently miss
    ``tlamatini.log``. This middleware makes every unhandled VIEW exception:

      * log the FULL traceback (plus timestamp, request method/path, thread
        name and a short error id) via the ``tlamatini.request`` logger, which
        ``settings.LOGGING`` wires to the console → the manage.py tee →
        ``tlamatini.log`` (urgent-marker flush = it hits the file instantly);
      * return a small friendly page — or JSON for API-flavored callers —
        carrying the SAME error id, and never the raw stack trace.

    Semantic exceptions (Http404 / PermissionDenied / SuspiciousOperation /
    BadRequest) pass through untouched so Django's normal 404/403/400
    conversions keep working. In DEBUG it returns None so the technical debug
    page (and Django's own django.request logging) behave exactly as before.
    Fail-open: any internal failure returns None → Django's default handling.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        try:
            # Semantic exceptions keep Django's normal 404/403/400 handling.
            if isinstance(exception, (Http404, PermissionDenied, SuspiciousOperation, BadRequest)):
                return None
            # In DEBUG stand aside entirely: Django both logs the traceback
            # (django.request) and renders the technical debug page.
            if settings.DEBUG:
                return None

            error_id = uuid.uuid4().hex[:8]
            _request_error_logger.error(
                "ERROR-ID %s: unhandled exception on %s %s [thread=%s]",
                error_id,
                getattr(request, 'method', '?'),
                getattr(request, 'path', '?'),
                threading.current_thread().name,
                exc_info=exception,
            )

            accept = request.headers.get('Accept') or ''
            req_content_type = request.headers.get('Content-Type') or ''
            wants_json = (
                'application/json' in accept
                or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or req_content_type.startswith('application/json')
            )
            if wants_json:
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'internal_server_error',
                        'error_id': error_id,
                        'message': (
                            'Tlamatini hit an unexpected error while handling this '
                            f'request. Full details are in tlamatini.log (error id {error_id}).'
                        ),
                    },
                    status=500,
                )
            return HttpResponse(
                _FRIENDLY_ERROR_HTML.format(error_id=error_id),
                status=500,
                content_type='text/html; charset=utf-8',
            )
        except Exception:
            # Fail open: let Django's default 500 handling take over — it logs
            # via django.request, which LOGGING also routes to the console.
            return None


