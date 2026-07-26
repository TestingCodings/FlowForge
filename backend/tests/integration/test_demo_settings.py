"""The demo settings module must import and differ from production correctly.

A settings module that only gets exercised on the server is a settings module
that breaks on the server. These assert the deltas that matter, so a later
edit to production.py can't silently take the demo with it.
"""
import importlib
import os

import pytest


@pytest.fixture(scope="module")
def demo_settings():
    """Import config.settings.demo in isolation, with the env it expects."""
    os.environ.setdefault("DATABASE_URL", "postgres://demo:demo@db:5432/flowforge")
    os.environ.setdefault("AWS_STORAGE_BUCKET_NAME", "unused-in-demo")
    os.environ.setdefault("EMAIL_HOST_PASSWORD", "unused-in-demo")
    return importlib.import_module("config.settings.demo")


def test_module_imports(demo_settings):
    """The whole point: catch an ImportError here, not on the VPS."""
    assert demo_settings is not None


def test_debug_is_off(demo_settings):
    assert demo_settings.DEBUG is False


def test_registration_is_disabled(demo_settings):
    assert demo_settings.DEMO_REGISTRATION_ENABLED is False


def test_database_does_not_require_ssl(demo_settings):
    """Demo Postgres is a same-network container with no TLS; requiring SSL
    (as production does) would simply fail to connect."""
    opts = demo_settings.DATABASES["default"].get("OPTIONS", {})
    assert opts.get("sslmode") != "require"


def test_email_cannot_leave_the_box(demo_settings):
    """No SMTP credentials exist in demo, so a notification bug can never
    become outbound spam."""
    assert demo_settings.EMAIL_BACKEND.endswith("console.EmailBackend")


def test_uploads_use_local_disk_not_s3(demo_settings):
    """Single VPS with a named volume — there is no bucket to talk to."""
    assert "s3" not in demo_settings.STORAGES["default"]["BACKEND"].lower()


def test_anonymous_throttle_is_set(demo_settings):
    rates = demo_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert rates["anon"] == "20/min"
    assert rates["user"] == "120/min"


def test_existing_throttle_scopes_are_preserved(demo_settings):
    """Demo adds anon/user rates; it must not drop the inbound-trigger scope
    that base.py defines, or triggers become unthrottled."""
    assert "trigger" in demo_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


def test_throttle_classes_are_enabled(demo_settings):
    classes = demo_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
    assert any("AnonRateThrottle" in c for c in classes)


def test_outbound_allow_list_is_not_empty(demo_settings):
    """An empty allow-list means 'any public host'. On a public demo where
    visitors author their own hooks, that must be an explicit choice."""
    assert demo_settings.OUTBOUND_ALLOWED_HOSTS
    assert "webhook.site" in demo_settings.OUTBOUND_ALLOWED_HOSTS


def test_upload_cap_is_tighter_than_default(demo_settings):
    from config.settings import base

    assert demo_settings.MEDIA_UPLOAD_MAX_BYTES < base.MEDIA_UPLOAD_MAX_BYTES


def test_nightly_reset_is_scheduled(demo_settings):
    entry = demo_settings.CELERY_BEAT_SCHEDULE["reset-demo-nightly"]
    assert entry["task"] == "apps.workflows.tasks.reset_demo_scheduled"


def test_existing_schedules_are_preserved(demo_settings):
    """Demo adds the reset; it must not drop SLA checks or webhook retries."""
    schedule = demo_settings.CELERY_BEAT_SCHEDULE
    assert "check-slas-every-minute" in schedule
    assert "retry-failed-webhook-deliveries" in schedule


def test_reset_is_not_scheduled_outside_demo():
    """The single most dangerous possible misconfiguration: a nightly wipe
    running against real data."""
    from config.settings import base, production

    for module in (base, production):
        assert "reset-demo-nightly" not in getattr(module, "CELERY_BEAT_SCHEDULE", {})
