"""/api/health/ must reveal whether the running process is stale.

A dev server started with --noreload keeps serving the code it loaded at
boot. That has repeatedly presented as a code bug: a fix appears not to
work, a passing feature appears broken, and one nearly got reported against
someone else's pull request. The process can detect this itself — it knows
when it started, and the source files carry their own timestamps.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestHealth:
    def test_still_reports_ok(self):
        """Uptime monitoring depends on this; don't change its shape."""
        body = APIClient().get("/api/health/").json()
        assert body["status"] == "ok"

    def test_is_unauthenticated(self):
        assert APIClient().get("/api/health/").status_code == 200

    def test_reports_when_the_process_started(self):
        body = APIClient().get("/api/health/").json()
        assert body["started_at"]

    def test_reports_a_code_revision(self):
        body = APIClient().get("/api/health/").json()
        assert "revision" in body

    @override_settings(DEBUG=True)
    def test_reports_staleness_in_debug(self):
        """The whole point: say so when source is newer than the process."""
        body = APIClient().get("/api/health/").json()
        assert "stale" in body

    @override_settings(DEBUG=False)
    def test_staleness_is_not_computed_in_production(self):
        """Walking the source tree on every health check would be wasteful,
        and a production process is never hot-reloaded anyway."""
        body = APIClient().get("/api/health/").json()
        assert body.get("stale") is None
