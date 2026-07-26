"""Demo-mode behaviour (docs/DEPLOYMENT.md §2).

The demo hands out accounts rather than accepting them. These cover the
registration switch; the settings module itself is covered by
test_demo_settings.py.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

NEW_USER = {
    "email": "walkup@example.com",
    "password": "StrongPass123!",
    "password_confirm": "StrongPass123!",
    "first_name": "Walk",
    "last_name": "Up",
}


@pytest.mark.django_db
class TestRegistrationSwitch:
    def test_registration_is_open_by_default(self):
        """Absent the flag (i.e. every non-demo deployment) nothing changes."""
        resp = APIClient().post("/api/auth/register/", NEW_USER, format="json")
        assert resp.status_code == 201, resp.data

    @override_settings(DEMO_REGISTRATION_ENABLED=False)
    def test_registration_is_refused_when_disabled(self):
        resp = APIClient().post("/api/auth/register/", NEW_USER, format="json")
        assert resp.status_code == 403, resp.data

    @override_settings(DEMO_REGISTRATION_ENABLED=False)
    def test_refusal_points_the_visitor_at_the_demo_accounts(self):
        """A bare 403 would read as a bug; the message has to explain."""
        resp = APIClient().post("/api/auth/register/", NEW_USER, format="json")
        assert "demo" in str(resp.data).lower()

    @override_settings(DEMO_REGISTRATION_ENABLED=False)
    def test_no_user_is_created_when_refused(self):
        from apps.accounts.models import User

        APIClient().post("/api/auth/register/", NEW_USER, format="json")
        assert not User.objects.filter(email=NEW_USER["email"]).exists()

    @override_settings(DEMO_REGISTRATION_ENABLED=True)
    def test_registration_works_when_explicitly_enabled(self):
        resp = APIClient().post("/api/auth/register/", NEW_USER, format="json")
        assert resp.status_code == 201, resp.data


@pytest.mark.django_db
class TestDemoNotice:
    """The banner text must reach the frontend, and must not appear anywhere
    that isn't actually a demo."""

    def _get(self):
        from apps.accounts.models import Role, RoleName, User, UserRole

        user = User.objects.create_user(
            email="ws@example.com", password="StrongPass123!",
            first_name="W", last_name="S",
        )
        role, _ = Role.objects.get_or_create(name=RoleName.VIEWER)
        UserRole.objects.create(user=user, role=role)
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get("/api/workspace/")

    def test_notice_is_empty_on_a_normal_deployment(self):
        assert self._get().data["demo_notice"] == ""

    @override_settings(DEMO_MODE=True, DEMO_RESET_NOTICE="Resets nightly")
    def test_notice_is_exposed_in_demo_mode(self):
        assert self._get().data["demo_notice"] == "Resets nightly"

    @override_settings(DEMO_MODE=False, DEMO_RESET_NOTICE="Resets nightly")
    def test_notice_is_suppressed_when_demo_mode_is_off(self):
        """The text existing in settings must not be enough to show a banner."""
        assert self._get().data["demo_notice"] == ""
