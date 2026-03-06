from django.conf import settings


def static_version(_request):
    """Expose STATIC_VERSION to templates for cache-busting query params."""
    return {"STATIC_VERSION": getattr(settings, "STATIC_VERSION", "0")}


