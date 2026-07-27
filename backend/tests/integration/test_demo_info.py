"""Public /api/demo-info/ — what an unauthenticated visitor may learn.

The demo login page needs to show its own credentials, or nobody can sign in.
Hard-coding them in the frontend put them in a public source file; serving
them from deployment config keeps the repo clean and lets the deployed
credentials differ from the dev seed's.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestDemoInfo:
    def test_is_reachable_without_authentication(self):
        """It renders on the login page, so it cannot require a token."""
        assert APIClient().get("/api/demo-info/").status_code == 200

    def test_reveals_nothing_on_a_normal_deployment(self):
        resp = APIClient().get("/api/demo-info/")
        assert resp.json() == {"demo_mode": False, "notice": "", "accounts": []}

    @override_settings(DEMO_MODE=True, DEMO_RESET_NOTICE="Resets nightly",
                       DEMO_ACCOUNTS=[{"email": "a@b.dev", "password": "x", "role": "Admin"}])
    def test_serves_accounts_in_demo_mode(self):
        body = APIClient().get("/api/demo-info/").json()
        assert body["demo_mode"] is True
        assert body["notice"] == "Resets nightly"
        assert body["accounts"][0]["email"] == "a@b.dev"

    @override_settings(DEMO_MODE=False,
                       DEMO_ACCOUNTS=[{"email": "a@b.dev", "password": "x", "role": "Admin"}])
    def test_accounts_are_withheld_when_demo_mode_is_off(self):
        """Configuring accounts must not be enough to publish them — a
        misconfigured non-demo deployment would otherwise leak logins."""
        body = APIClient().get("/api/demo-info/").json()
        assert body["accounts"] == []

    @override_settings(DEMO_MODE=True)
    def test_empty_when_no_accounts_configured(self):
        assert APIClient().get("/api/demo-info/").json()["accounts"] == []
