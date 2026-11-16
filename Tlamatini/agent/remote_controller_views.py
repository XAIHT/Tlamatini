# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Local, authenticated account enrollment for the independent RC service."""

import ipaddress
import logging
import uuid
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .models import RemoteControllerProfile
from .remote_controller_bridge import (
    RcBridgeError, bind_profile, enrollment_lock, service_status, unbind_profile,
)

logger = logging.getLogger(__name__)
_enrollment_lock = enrollment_lock

TEXT = {
    "language": "en", "edition": "English edition",
    "title": "Remote-Controller", "eyebrow": "TLAMATINI / TLACHIHUANI",
    "intro": "Connect this Tlamatini account to Tlamatini-RC. You choose which devices may use it in XT.",
    "back": "Back to chat", "refresh": "Refresh status",
    "service": "Remote-Controller service", "ready": "Running", "unavailable": "Not connected",
    "setup": "Setup required", "stopping": "Stopping",
    "service_help": "Right-click the XT icon → Remote-Controller to start, stop or restart the server.",
    "account": "Your account", "enabled": "Remote access enabled", "disabled": "Remote access disabled",
    "pending": "Remote access is disabled here. Service revocation will finish when Remote-Controller is reachable.",
    "enabled_help": "Approved devices can use the permissions you grant in XT. Remote chat uses this account’s history and execution approvals.",
    "disabled_help": "Enable this account before creating a device invitation in XT.",
    "password_label": "Confirm your current Tlamatini password", "enable": "Enable this account",
    "disable": "Disable remote access", "retry": "Retry service revocation",
    "consent": "Enabling makes this account available in XT. It does not approve a device or start a service.",
    "disable_help": "Disabling cancels this account’s remote work and revokes its device access. Tlamatini stays open.",
    "steps": "Connect a device", "step_one": "Enable this account here, then select it in XT’s Remote-Controller Access tab.",
    "step_two": "Choose permissions and create an invitation. Open the RC client from XT and enter the invitation.",
    "step_three": "Compare the complete device fingerprint in both places, then approve it in XT.",
    "local_profile": "This version connects on this PC only. Network access stays unavailable until its required secure transport is installed.",
    "independence": "Remote-Controller and Torrenter have separate controls. Stopping either one leaves the other independent.",
    "enabled_notice": "This account is ready for a device invitation in XT.",
    "disabled_notice": "Remote access and device grants for this account have been revoked.",
    "password_error": "The password did not match. Enter this account’s current password.",
    "request_error": "This request could not be accepted. Refresh the page and try again.",
    "local_error": "Open this page on the PC running Tlamatini to manage remote access.",
    "service_error": "Remote-Controller could not be reached or refused the change. Check its Runtime tab in XT, then try again.",
    "revoke_first": "This account still has device access that Remote-Controller has not revoked yet. Start Remote-Controller from the XT icon, then enable the account again.",
    "inactive_error": "This Tlamatini account is inactive.",
}


def _local_request(request):
    """Trust the actual connection, never a forwarded address supplied by a client."""
    try:
        return ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
    except ValueError:
        return False


def _same_origin(request):
    origin = request.META.get("HTTP_ORIGIN", "")
    try:
        parsed = urlsplit(origin)
        expected = urlsplit(request.scheme + "://" + request.get_host())
        return (
            bool(origin) and parsed.scheme in {"http", "https"}
            and not parsed.username and not parsed.password
            and not parsed.path and not parsed.query and not parsed.fragment
            and parsed.scheme == expected.scheme
            and parsed.hostname == expected.hostname
            and (parsed.port or (443 if parsed.scheme == "https" else 80))
            == (expected.port or (443 if expected.scheme == "https" else 80))
        )
    except ValueError:
        return False


def _profile_for(user):
    return RemoteControllerProfile.objects.filter(user=user).first()


def _page(request, *, error="", notice="", status=200):
    profile = _profile_for(request.user)
    service_label = TEXT["unavailable"]
    service_ready = False
    try:
        observed = service_status()
        health = observed.get("health")
        service_ready = health == "ready" and observed.get("listener") is True
        service_label = TEXT["ready"] if service_ready else TEXT.get(
            {"stopping": "stopping", "setup_required": "setup"}.get(health, "unavailable")
        )
    except RcBridgeError:
        pass
    response = render(request, "agent/remote_controller.html", {
        "copy": TEXT, "profile": profile, "error": error, "notice": notice,
        "service_label": service_label, "service_ready": service_ready,
        "pending_revocation": bool(profile and not profile.enabled and profile.binding_id),
    }, status=status)
    response["Cache-Control"] = "no-store, private"
    # Same-origin form posts must retain their Origin for strict CSRF checks.
    # No account detail or password is placed in the page URL.
    response["Referrer-Policy"] = "same-origin"
    response["X-Frame-Options"] = "DENY"
    return response


@login_required
@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def account(request):
    if not _local_request(request):
        return HttpResponseForbidden(TEXT["local_error"])
    if not request.user.is_active:
        return HttpResponseForbidden(TEXT["inactive_error"])
    if request.method == "GET":
        return _page(request)
    if (not _same_origin(request) or request.content_type != "application/x-www-form-urlencoded"
            or len(request.body) > 8192):
        return HttpResponseForbidden(TEXT["request_error"])
    if (set(request.POST) - {"action", "password", "csrfmiddlewaretoken"}
            or any(len(request.POST.getlist(key)) != 1 for key in request.POST)):
        return _page(request, error=TEXT["request_error"], status=400)
    action = request.POST.get("action")
    if action not in {"enable", "disable"}:
        return _page(request, error=TEXT["request_error"], status=400)
    if action == "enable":
        password = request.POST.get("password", "")
        if not password or len(password) > 4096 or not request.user.check_password(password):
            return _page(request, error=TEXT["password_error"], status=403)

    # Enrollment is rare. Serialize local changes so two tabs cannot race a
    # successful enable against a disable for the same authenticated account.
    with _enrollment_lock:
        profile = _profile_for(request.user)
        if action == "enable":
            if profile is None:
                profile, _ = RemoteControllerProfile.objects.get_or_create(user=request.user)
            if not profile.enabled and profile.binding_id:
                # A disable whose service revocation never finished must finish
                # first. Binding again could otherwise restore the old device
                # grants that disabling promised to revoke.
                try:
                    unbind_profile(profile)
                except RcBridgeError as exc:
                    if exc.code != "not_found":
                        logger.warning("Remote-Controller re-enable is waiting for a pending revocation")
                        return _page(request, error=TEXT["revoke_first"], status=503)
                profile.binding_id = ""
                profile.save(update_fields=["binding_id"])
            try:
                binding = bind_profile(profile)
                binding_id = binding.get("id", "")
                if len(binding_id) != 32 or uuid.UUID(hex=binding_id).int == 0:
                    raise ValueError("Invalid native account binding")
                profile.binding_id = binding_id
                profile.enabled = True
                profile.save(update_fields=["binding_id", "enabled"])
            except (RcBridgeError, ValueError, TypeError):
                logger.warning("Remote-Controller account enrollment was not completed")
                return _page(request, error=TEXT["service_error"], status=503)
            return _page(request, notice=TEXT["enabled_notice"])

        if profile is not None:
            # Persist local denial before any native request. The worker also
            # retries disabled profiles with an outstanding service binding.
            profile.enabled = False
            profile.save(update_fields=["enabled"])
            if profile.binding_id:
                try:
                    unbind_profile(profile)
                    profile.binding_id = ""
                    profile.save(update_fields=["binding_id"])
                except RcBridgeError:
                    return _page(request, error=TEXT["pending"], status=503)
        return _page(request, notice=TEXT["disabled_notice"])


@never_cache
@require_http_methods(["GET"])
def session_identity(request):
    """Confirm a normal Django login against an enrolled immutable RC account.

    The mobile gateway uses this read-only check; it never fabricates a Django
    session or substitutes a display name for the account identity.
    """
    from django.http import JsonResponse
    from .remote_controller_bridge import EDITION
    if not _local_request(request):
        return HttpResponseForbidden(TEXT["local_error"])
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)
    profile = _profile_for(request.user)
    return JsonResponse({
        "authenticated": True, "active": bool(request.user.is_active),
        "enabled": bool(profile and profile.enabled), "edition": EDITION,
        "account_id": profile.account.hex if profile else None,
        "binding_id": profile.binding_id if profile else None,
    })
