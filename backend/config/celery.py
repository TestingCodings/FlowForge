"""Celery application.

Until this existed there was no app for `celery -A config worker` to load, so
the worker and beat processes could not start at all. Everything still
appeared to work because the call sites fall back to running inline when
`.delay()` raises (see apps/notifications/hooks.py) — which quietly meant
webhook delivery and action hooks ran synchronously inside the request, and
nothing in CELERY_BEAT_SCHEDULE (SLA checks, webhook retries) ever fired.

`autodiscover_tasks` picks up `tasks.py` in each installed app, and the
`beat_schedule` comes from settings via the CELERY_ namespace, so the
schedule differs per settings module (only demo.py adds the nightly reset).
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("flowforge")

# Every CELERY_-prefixed Django setting becomes a Celery config key:
# CELERY_BEAT_SCHEDULE -> beat_schedule, CELERY_TIMEZONE -> timezone, etc.
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# autodiscover only imports `tasks.py` per app, but `execute_hook_task` lives
# in apps/notifications/hooks.py next to the code it serves. Without this pass
# the worker would reject its own messages with "Received unregistered task",
# and action hooks would silently never run.
app.autodiscover_tasks(related_name="hooks")


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Smoke test: `celery -A config call config.celery.debug_task`."""
    print(f"Request: {self.request!r}")
