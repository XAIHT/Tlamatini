# Tlamatini Author Banner — Angela López Mendoza
"""Authenticated, read-only usage; independent of the chat operation lock."""
import logging
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from . import usage_provider, usage_tracking

logger = logging.getLogger(__name__)


def readiness(response):
    """Enable Usage for verified report data, independently of account naming.

    An empty local ledger alone cannot make a failed cloud report look ready.
    Real zero-valued cloud totals are valid, as is previously measured chat
    activity when Ollama is temporarily unavailable.
    """
    provider = response.get("provider") or {}
    cloud = (provider.get("ranges") or {}).get(response["range"], {}).get("data") or {}
    balance = (provider.get("balance") or {}).get("data") or {}
    activity = response.get("activity") or {}
    cloud_ready = bool(balance.get("kind")) or any(
        usage_provider.number((cloud.get("totals") or {}).get(metric)) is not None
        for metric in usage_provider.METRICS)
    calls = usage_provider.number((activity.get("totals") or {}).get("calls"))
    chat_ready = calls is not None and calls > 0 and not activity.get("pending")
    ready = cloud_ready or chat_ready
    return {"ready": ready, "default_tab": "account" if cloud_ready else "activity",
            "state": "ready" if ready else "checking" if provider.get("pending") or activity.get("pending") else "unavailable",
            "message": "Ready" if cloud_ready else "Chat activity available" if chat_ready else
                       "Checking usage…" if provider.get("pending") or activity.get("pending") else
                       "Usage is temporarily unavailable. Checking again automatically.",
            "retry_after_seconds": max(1, min(60, provider.get("retry_after_seconds") or (60 if ready else 15)))}


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
        response["provider"] = usage_provider.snapshot(refresh=request.GET.get("refresh") == "1")
    except Exception:
        logger.exception("[USAGE] Cannot read Ollama account usage")
        response["provider_error"] = "Ollama could not refresh. Check its connection and try Refresh."
    response["readiness"] = readiness(response)
    return JsonResponse(response)
