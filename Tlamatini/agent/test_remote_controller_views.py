# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Account-enrollment boundary tests; native service and ORM are isolated mocks.

Run through the repository's visible execution launcher with isolated Django
settings. These tests do not create users, start the application or contact SCM.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from . import remote_controller_views as views


@override_settings(ALLOWED_HOSTS=["127.0.0.1", "localhost", "[::1]"],
                   LOGIN_URL="/login/")
class RemoteControllerAccountTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            pk=7, is_authenticated=True, is_active=True,
            check_password=Mock(return_value=True), get_username=lambda: "account-one",
        )
        self.profile = SimpleNamespace(
            user=self.user, account=uuid.uuid4(), adapter=uuid.uuid4(),
            enabled=False, binding_id="", save=Mock(),
        )
        self.manager = Mock()
        self.manager.filter.return_value.first.return_value = self.profile
        self.manager.get_or_create.return_value = (self.profile, False)
        self.manager_patch = patch.object(views.RemoteControllerProfile, "objects", self.manager)
        self.manager_patch.start()
        self.addCleanup(self.manager_patch.stop)
        self.bind = self._patch("bind_profile", return_value={"id": "1" * 32})
        self.unbind = self._patch("unbind_profile", return_value={"disabled": True})
        self.status = self._patch("service_status", return_value={"health": "ready", "listener": True})
        self.render = self._patch("render", side_effect=self._render)

    def _patch(self, name, **kwargs):
        patcher = patch.object(views, name, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    @staticmethod
    def _render(request, template, context, status=200):
        response = HttpResponse("account page", status=status)
        response.context_data = context
        return response

    def request(self, action=None, *, data=None, origin="http://127.0.0.1:8000",
                address="127.0.0.1", csrf=True, method=None):
        if action is None and method is None:
            request = self.factory.get("/remote-controller/", HTTP_HOST="127.0.0.1:8000",
                                       REMOTE_ADDR=address)
        else:
            payload = data if data is not None else {"action": action, "password": "rc-unit-test-only"}
            request = self.factory.generic(
                method or "POST", "/remote-controller/", urlencode(payload, doseq=True),
                content_type="application/x-www-form-urlencoded", HTTP_HOST="127.0.0.1:8000",
                REMOTE_ADDR=address, HTTP_ORIGIN=origin,
            )
        request.user = self.user
        request._dont_enforce_csrf_checks = csrf
        return request

    def test_get_does_not_create_or_bind_account(self):
        self.manager.filter.return_value.first.return_value = None
        self.assertEqual(views.account(self.request()).status_code, 200)
        self.manager.get_or_create.assert_not_called()
        self.bind.assert_not_called()

    def test_get_shows_verified_running_listener(self):
        response = views.account(self.request())
        self.assertTrue(response.context_data["service_ready"])
        self.assertEqual(response.context_data["service_label"], views.TEXT["ready"])

    def test_health_without_listener_does_not_claim_running(self):
        self.status.return_value = {"health": "ready", "listener": False}
        self.assertFalse(views.account(self.request()).context_data["service_ready"])

    def test_setup_state_is_distinct_from_stopped(self):
        self.status.return_value = {"health": "setup_required", "listener": False}
        self.assertEqual(views.account(self.request()).context_data["service_label"], views.TEXT["setup"])

    def test_stopping_state_is_visible(self):
        self.status.return_value = {"health": "stopping", "listener": False}
        self.assertEqual(views.account(self.request()).context_data["service_label"], views.TEXT["stopping"])

    def test_missing_service_keeps_account_page_available(self):
        self.status.side_effect = views.RcBridgeError("unavailable", "isolated fixture")
        response = views.account(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["service_label"], views.TEXT["unavailable"])

    def test_account_response_cannot_be_cached_or_framed(self):
        response = views.account(self.request())
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_nonlocal_read_is_forbidden(self):
        self.assertEqual(views.account(self.request(address="192.0.2.10")).status_code, 403)
        self.status.assert_not_called()

    def test_forwarded_address_cannot_grant_local_authority(self):
        request = self.request(address="192.0.2.10")
        request.META["HTTP_X_FORWARDED_FOR"] = "127.0.0.1"
        self.assertEqual(views.account(request).status_code, 403)

    def test_ipv6_loopback_is_local(self):
        self.assertEqual(views.account(self.request(address="::1")).status_code, 200)

    def test_malformed_address_is_forbidden(self):
        self.assertEqual(views.account(self.request(address="localhost")).status_code, 403)

    def test_inactive_account_is_forbidden(self):
        self.user.is_active = False
        self.assertEqual(views.account(self.request()).status_code, 403)
        self.manager.filter.assert_not_called()

    def test_enable_confirms_current_password_and_owns_binding(self):
        response = views.account(self.request("enable"))
        self.assertEqual(response.status_code, 200)
        self.user.check_password.assert_called_once_with("rc-unit-test-only")
        self.bind.assert_called_once_with(self.profile)
        self.assertTrue(self.profile.enabled)
        self.assertEqual(self.profile.binding_id, "1" * 32)
        self.manager.filter.assert_called_with(user=self.user)

    def test_first_enable_creates_only_authenticated_profile(self):
        self.manager.filter.return_value.first.return_value = None
        self.assertEqual(views.account(self.request("enable")).status_code, 200)
        self.manager.get_or_create.assert_called_once_with(user=self.user)

    def test_incorrect_password_never_binds_or_creates(self):
        self.user.check_password.return_value = False
        self.assertEqual(views.account(self.request("enable")).status_code, 403)
        self.bind.assert_not_called()
        self.manager.get_or_create.assert_not_called()

    def test_empty_password_is_refused(self):
        self.assertEqual(views.account(self.request("enable", data={"action": "enable", "password": ""})).status_code, 403)
        self.bind.assert_not_called()
        self.user.check_password.assert_not_called()

    def test_oversized_password_is_refused_before_hashing(self):
        response = views.account(self.request("enable", data={"action": "enable", "password": "<REDACTED>" * 4097}))
        self.assertEqual(response.status_code, 403)
        self.user.check_password.assert_not_called()
        self.bind.assert_not_called()

    def test_missing_origin_is_refused(self):
        self.assertEqual(views.account(self.request("enable", origin="")).status_code, 403)
        self.bind.assert_not_called()

    def test_cross_origin_is_refused(self):
        self.assertEqual(views.account(self.request("enable", origin="http://example.invalid")).status_code, 403)
        self.bind.assert_not_called()

    def test_origin_path_is_refused(self):
        self.assertEqual(views.account(self.request("enable", origin="http://127.0.0.1:8000/other")).status_code, 403)

    def test_origin_credentials_are_refused(self):
        self.assertEqual(views.account(self.request("enable", origin="http://user@127.0.0.1:8000")).status_code, 403)

    def test_origin_port_must_match(self):
        self.assertEqual(views.account(self.request("enable", origin="http://127.0.0.1:8001")).status_code, 403)

    def test_origin_scheme_must_match(self):
        self.assertEqual(views.account(self.request("enable", origin="https://127.0.0.1:8000")).status_code, 403)

    def test_origin_query_is_refused(self):
        self.assertEqual(views.account(self.request("enable", origin="http://127.0.0.1:8000?q=1")).status_code, 403)

    def test_invalid_origin_port_is_refused(self):
        self.assertEqual(views.account(self.request("enable", origin="http://127.0.0.1:bad")).status_code, 403)

    def test_unknown_action_is_refused(self):
        self.assertEqual(views.account(self.request("start-service")).status_code, 400)
        self.bind.assert_not_called()
        self.unbind.assert_not_called()

    def test_browser_cannot_select_another_account(self):
        data = {"action": "enable", "password": "<REDACTED>", "account_id": "2" * 32}
        self.assertEqual(views.account(self.request("enable", data=data)).status_code, 400)
        self.bind.assert_not_called()

    def test_duplicate_action_is_refused(self):
        data = {"action": ["enable", "disable"], "password": "<REDACTED>"}
        self.assertEqual(views.account(self.request("enable", data=data)).status_code, 400)
        self.bind.assert_not_called()

    def test_put_is_not_an_enrollment_action(self):
        self.assertEqual(views.account(self.request("enable", method="PUT")).status_code, 405)

    def test_password_is_not_copied_into_template_context(self):
        response = views.account(self.request("enable"))
        self.assertNotIn("password", response.context_data)
        self.assertNotIn("current-secret", str(response.context_data))

    def test_disable_persists_denial_before_native_call(self):
        self.profile.enabled = True
        self.profile.binding_id = "1" * 32
        def native_call(profile):
            self.assertFalse(profile.enabled)
            profile.save.assert_called_with(update_fields=["enabled"])
        self.unbind.side_effect = native_call
        self.assertEqual(views.account(self.request("disable")).status_code, 200)
        self.assertFalse(self.profile.enabled)
        self.assertEqual(self.profile.binding_id, "")
        self.user.check_password.assert_not_called()

    def test_disable_keeps_retry_identity_when_service_is_unreachable(self):
        self.profile.enabled = True
        self.profile.binding_id = "1" * 32
        self.unbind.side_effect = views.RcBridgeError("unavailable", "isolated fixture")
        response = views.account(self.request("disable"))
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.profile.enabled)
        self.assertEqual(self.profile.binding_id, "1" * 32)
        self.assertTrue(response.context_data["pending_revocation"])

    def test_disable_absent_profile_is_idempotent(self):
        self.manager.filter.return_value.first.return_value = None
        self.assertEqual(views.account(self.request("disable")).status_code, 200)
        self.unbind.assert_not_called()
        self.manager.get_or_create.assert_not_called()

    def test_disable_already_disabled_profile_is_idempotent(self):
        self.assertEqual(views.account(self.request("disable")).status_code, 200)
        self.unbind.assert_not_called()

    def test_invalid_native_binding_does_not_enable(self):
        self.bind.return_value = {"id": "invalid"}
        self.assertEqual(views.account(self.request("enable")).status_code, 503)
        self.assertFalse(self.profile.enabled)
        self.profile.save.assert_not_called()

    def test_zero_native_binding_does_not_enable(self):
        self.bind.return_value = {"id": "0" * 32}
        self.assertEqual(views.account(self.request("enable")).status_code, 503)
        self.assertFalse(self.profile.enabled)

    def test_nonhex_native_binding_does_not_enable(self):
        self.bind.return_value = {"id": "z" * 32}
        self.assertEqual(views.account(self.request("enable")).status_code, 503)
        self.assertFalse(self.profile.enabled)

    def test_native_refusal_does_not_enable(self):
        self.bind.side_effect = views.RcBridgeError("forbidden", "isolated fixture")
        self.assertEqual(views.account(self.request("enable")).status_code, 503)
        self.assertFalse(self.profile.enabled)
        self.profile.save.assert_not_called()

    def test_csrf_is_required_in_addition_to_password_and_origin(self):
        self.assertEqual(views.account(self.request("enable", csrf=False)).status_code, 403)
        self.bind.assert_not_called()

    def test_remote_post_is_refused_even_with_valid_local_credentials(self):
        self.assertEqual(views.account(self.request("enable", address="192.0.2.10")).status_code, 403)
        self.user.check_password.assert_not_called()
        self.bind.assert_not_called()

    def test_body_bound_is_enforced(self):
        data = {"action": "enable", "password": "<REDACTED>" * 8200}
        self.assertEqual(views.account(self.request("enable", data=data)).status_code, 403)
        self.user.check_password.assert_not_called()

    def test_json_cannot_bypass_form_validation(self):
        request = self.factory.post("/remote-controller/", '{"action":"enable"}',
                                    content_type="application/json", HTTP_HOST="127.0.0.1:8000",
                                    REMOTE_ADDR="127.0.0.1", HTTP_ORIGIN="http://127.0.0.1:8000")
        request.user = self.user
        request._dont_enforce_csrf_checks = True
        self.assertEqual(views.account(request).status_code, 403)
        self.bind.assert_not_called()
