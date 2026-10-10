# Tlamatini Author Banner — Angela López Mendoza
"""Authenticated, read-only usage; independent of the chat operation lock."""
import logging
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from . import usage_provider, usage_tracking

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def usage_view(request):
    selected = request.GET.get("range", "7d")
    if selected not in ("7d", "30d"):
        return JsonResponse({"error": "Choose 7d or 30d."}, status=400)
    response = {"user_id": request.user.pk, "range": selected}
    try:
        response["activity"] = usage_tracking.activity(request.user.pk, int(selected[:-1]))
    except Exception:
        logger.exception("[USAGE] Cannot read usage ledger")
        response["activity_error"] = "Chat usage could not load. Check the application log and database migrations."
    try:
        response["provider"] = usage_provider.snapshot()
    except Exception:
        logger.exception("[USAGE] Cannot read Ollama account usage")
        response["provider_error"] = "Ollama could not refresh. Check its connection and try Refresh."
    return JsonResponse(response)
