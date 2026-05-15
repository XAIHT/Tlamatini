from django.conf import settings


def static_version(_request):
    """Expose STATIC_VERSION to templates for cache-busting query params."""
    return {"STATIC_VERSION": getattr(settings, "STATIC_VERSION", "0")}


def app_version(_request):
    """Expose the Tlamatini application version to templates.

    Resolves through ``agent.version.get_version()`` (SemVer 2.0.0 with
    git-tag fallback — see VERSIONING.md).  Used by the About dialog and
    any other template that needs the running version.
    """
    try:
        from agent.version import get_version
        return {"version": get_version()}
    except Exception:
        return {"version": "0.0.0+unknown"}


