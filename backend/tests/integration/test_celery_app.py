"""The Celery app must exist and register every task the code enqueues.

Before this app existed, `celery -A config worker` could not start at all.
Nothing failed loudly because every call site falls back to running inline
when .delay() raises — so webhooks and action hooks ran synchronously inside
the request, and nothing in CELERY_BEAT_SCHEDULE ever fired.

A task that is enqueued but not registered fails only on a real worker, with
"Received unregistered task". That is invisible in dev and total in
production, which is exactly why it is asserted here.
"""
import pytest


@pytest.fixture(scope="module")
def registry():
    from config.celery import app

    app.loader.import_default_modules()
    return app.tasks


def test_app_is_importable_from_the_package():
    """`celery -A config` resolves config/__init__.py, not config/celery.py."""
    import config

    assert config.celery_app is not None


def test_app_reads_settings_from_django():
    from config.celery import app

    assert app.conf.timezone == "UTC"


@pytest.mark.parametrize("name", [
    "apps.notifications.tasks.deliver_webhook_task",
    "apps.notifications.tasks.dispatch_notification_task",
    "apps.notifications.tasks.retry_failed_webhook_deliveries",
    "apps.notifications.tasks.check_slas_scheduled",
    "apps.workflows.tasks.reset_demo_scheduled",
    "tasks.mark_overdue_tasks",
])
def test_task_is_registered(registry, name):
    assert name in registry


def test_hook_task_is_registered(registry):
    """Regression: execute_hook_task lives in hooks.py, not tasks.py, so the
    default autodiscover pass misses it entirely."""
    assert "apps.notifications.hooks.execute_hook_task" in registry


def test_every_scheduled_task_actually_exists(registry):
    """A beat entry naming a task that isn't registered is a silent no-op —
    the schedule looks configured and nothing ever runs."""
    from django.conf import settings

    for entry_name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        assert entry["task"] in registry, (
            f"beat entry '{entry_name}' points at unregistered task {entry['task']!r}"
        )
