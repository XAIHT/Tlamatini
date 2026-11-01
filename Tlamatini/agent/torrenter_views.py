# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Stage private torrent metadata directly from the authenticated browser to Jobs."""

import base64
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .agents.torrenter import client
from .agents.torrenter.sources import stage
from .agents.torrenter.contract import TorrentError
from .torrenter_bridge import profile_for


_ASSETS = {"workspace.html": "text/html; charset=utf-8", "workspace.css": "text/css",
           "layout.js": "text/javascript", "workspace.js": "text/javascript"}
_RESOURCES = frozenset(("torrents", "inspections", "operations", "events", "capabilities", "statistics",
                        "settings", "categories", "tags", "batch-operations", "content-deletion-previews",
                        "content-deletions"))


def recover_job_log(profile, job_id):
    """Reconstruct current evidence for older flow files whose temporary pool has gone."""
    from .agents.torrenter.activity import ActivityLog
    from .agents.torrenter.torrenter import describe_assets
    key = "torrenter-recovered:" + profile + ":" + job_id
    lines = cache.get(key)
    if lines is None:
        route = "torrents/" + job_id
        try:
            _, manifest = client.request("GET", route + "/manifest", bearer=client.session(profile))
        except TorrentError as exc:
            return JsonResponse({"success": False, "message": str(exc)}, status=getattr(exc, "status", 503))
        with TemporaryDirectory() as temp:
            log = ActivityLog(Path(temp), "manifest", False)
            describe_assets(profile, route, log, manifest)
            lines = ["Current report from Jobs. The original run log is unavailable.",
                     *log.path.read_text(encoding="utf-8").splitlines()[4:]]
        cache.set(key, lines, 15)
    response = JsonResponse({"success": True, "complete": True, "lines": lines, "total_lines": len(lines)})
    response["Cache-Control"] = "private, no-store"
    return response


def _asset(name):
    if name not in _ASSETS:
        raise Http404
    try:
        # Do not execute JavaScript supplied by whichever process happens to bind
        # port 12064 on the Django origin. Use the assets verified with this edition.
        # Source-mode integration tests can render the exact frontend under
        # development. The setting is server-side and never read from requests.
        root = getattr(settings, "TORRENTER_WORKSPACE_ROOT", None) if settings.DEBUG else None
        if root is None:
            root = Path(__file__).resolve().parent / "torrenter_workspace"
        path = Path(root) / name
        with path.open("rb") as stream:
            data = stream.read(512 * 1024 + 1)
        if len(data) > 512 * 1024:
            raise OSError
    except OSError:
        return HttpResponse("The Torrenter workspace files are missing from this Tlamatini installation.", status=503)
    response = HttpResponse(data, content_type=_ASSETS[name])
    response["Content-Security-Policy"] = ("default-src 'self'; object-src 'none'; base-uri 'none'; "
                                          "frame-ancestors 'none'; form-action 'none'")
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


@never_cache
@login_required
@require_http_methods(["GET"])
def workspace(request):
    return _asset("workspace.html")


@never_cache
@login_required
@require_http_methods(["GET"])
def workspace_asset(request, asset):
    return _asset(asset)


@never_cache
@require_http_methods(["GET"])
def workspace_session(request):
    if not request.user.is_authenticated:
        response = JsonResponse({"error": "Sign in to Tlamatini."}, status=401)
        response["X-Torrenter-Controller"] = "1"
        return response
    return JsonResponse({"username": request.user.get_username(), "edition": settings.LANGUAGE_CODE,
                         "profile": profile_for(request.user.pk),
                         "csrf": get_token(request)})


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST", "PATCH", "DELETE"])
def workspace_api(request, route):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to Tlamatini."}, status=401)
    profile = profile_for(request.user.pk)
    if request.headers.get("X-Torrenter-Profile") != profile:
        return JsonResponse({"code": "account_changed", "error": "Account changed. Reload the workspace."}, status=403)
    if route.split("/", 1)[0] not in _RESOURCES or not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9-]+){0,3}", route):
        raise Http404
    query = request.GET.urlencode()
    if len(query) > 4096:
        return JsonResponse({"error": "Query too long."}, status=400)
    body = None
    if request.method != "GET":
        if request.content_type == "multipart/form-data" and request.method == "POST" and route == "inspections":
            upload = request.FILES.get("file")
            if not upload or not 0 < upload.size <= 1024 * 1024:
                return JsonResponse({"error": "Invalid torrent file."}, status=400)
            body = {"metainfo": base64.b64encode(upload.read()).decode("ascii")}
        elif request.content_type == "application/json":
            try:
                body = json.loads(request.body)
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, UnicodeError):
                return JsonResponse({"error": "Expected a JSON object."}, status=400)
        elif request.method != "DELETE" or request.body:
            return JsonResponse({"error": "Unsupported content type."}, status=415)
    # Only the authenticated server crosses the Windows operator pipe. The browser
    # cannot choose a host, supply a bearer, or mint a token for a different account.
    tag = hashlib.sha256((request.session.session_key + ":" + profile).encode()).hexdigest()
    key = "torrenter-workspace:" + tag
    try:
        revision = request.headers.get("If-Match")
        if revision is not None:
            if not re.fullmatch(r'"?[0-9]{1,16}"?', revision):
                return JsonResponse({"error": "Invalid revision."}, status=400)
            revision = int(revision.strip('"'))
        token = cache.get(key)
        for attempt in range(2):
            if not token:
                token = client.session(profile)
                cache.set(key, token, 240)
            try:
                code, result = client.request(request.method, route + ("?" + query if query else ""), body,
                                              bearer=token, key=request.headers.get("Idempotency-Key"), revision=revision)
                break
            except client.JobsHttpError as exc:
                # Jobs checks credentials before dispatch. An expired credential
                # can safely be minted again without repeating an accepted write.
                if exc.status != 401 or attempt:
                    raise
                cache.delete(key)
                token = None
        return JsonResponse(result, status=code)
    except TorrentError as exc:
        code = getattr(exc, "status", 503)
        if code == 401:
            cache.delete(key)
            code = 503
        return JsonResponse({"error": str(exc)}, status=code)


@login_required
@never_cache
@csrf_protect
@sensitive_post_parameters("magnet", "endpoints")
@require_http_methods(["GET", "POST"])
def sources(request):
    context = {}
    status = 200
    if request.method == "POST":
        try:
            profile = profile_for(request.user.pk)
            if request.POST.get("source_kind") in ("trackers", "web_seeds"):
                kind = request.POST["source_kind"]
                context["source_ref"] = stage(
                    profile, kind, request.POST.get("endpoints", "")
                )
                context["source_action"] = "set_" + kind
                return render(request, "agent/torrenter_sources.html", context)
            upload = request.FILES.get("torrent")
            magnet = request.POST.get("magnet", "").strip()
            if bool(upload) == bool(magnet):
                raise TorrentError("Choose a .torrent file or enter one magnet link.")
            if upload:
                if not 0 < upload.size <= 1024 * 1024:
                    raise TorrentError("The torrent metadata must be 1 byte to 1 MiB.")
                body = {"metainfo": base64.b64encode(upload.read()).decode("ascii")}
            else:
                if len(magnet) > 8192 or not magnet.lower().startswith("magnet:?"):
                    raise TorrentError(
                        "Enter a valid magnet link of up to 8192 characters."
                    )
                body = {"magnet": magnet}
            _, context["inspection"] = client.request(
                "POST", "inspections", body, bearer=client.session(profile)
            )
        except TorrentError as exc:
            context["error"] = str(exc)
            status = 400
    return render(request, "agent/torrenter_sources.html", context, status=status)
