# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""HTTP surface of Terminater.

``terminater_api_view``  is the loopback API pool agents call.  It carries NO
session cookie, so it is protected the way a local-only RPC must be: the request
has to come from the loopback interface AND present the per-run token that only
a process of the same user can read.  Browsers cannot forge it (a cross-site page
cannot set the custom header, and nothing here enables CORS).

``terminater_state_view`` is the authenticated, read-only JSON the page can use
to (re)draw its tabs without a WebSocket (and what the tests inspect).
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import terminal_hub

logger = logging.getLogger(__name__)

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MAX_BODY = 2 * 1024 * 1024


def _forbidden(code: str, message: str, status: int = 403) -> JsonResponse:
    return JsonResponse({"ok": False, "status": "refused", "code": code, "message": message},
                        status=status)


@csrf_exempt
@require_POST
def terminater_api_view(request):
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    if remote not in _LOOPBACK:
        return _forbidden("not_loopback", "Terminater's API only answers on the loopback interface.")
    if not terminal_hub.token_ok(request.headers.get("X-Terminater-Token", "")):
        return _forbidden("bad_token", "Missing or wrong X-Terminater-Token.", 401)
    if len(request.body or b"") > MAX_BODY:
        return _forbidden("too_large", "Request body is too large.", 413)
    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _forbidden("bad_json", "Body must be a JSON object.", 400)
    if not isinstance(payload, dict):
        return _forbidden("bad_json", "Body must be a JSON object.", 400)
    action = str(payload.get("action") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {
        k: v for k, v in payload.items() if k not in ("action", "wait_for_job")}
    result = terminal_hub.run_action(action, params, wait=bool(payload.get("wait_for_job", False)))
    return JsonResponse(result, json_dumps_params={"default": str})


@login_required
@require_GET
def terminater_state_view(request):
    user = str(request.user.pk)
    kinds = terminal_hub.terminal_kinds()
    state = terminal_hub.hub_status(user)
    state["available_kinds"] = kinds
    state["enabled"] = terminal_hub.terminals_enabled()
    return JsonResponse(state, json_dumps_params={"default": str})
