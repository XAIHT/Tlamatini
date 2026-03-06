from typing import Callable
from django.http import HttpRequest, HttpResponse


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


