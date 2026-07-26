"""Scheduled workflow tasks."""
import logging

from celery import shared_task
from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name="apps.workflows.tasks.reset_demo_scheduled")
def reset_demo_scheduled():
    """Nightly public-demo reset (docs/DEPLOYMENT.md §2.1).

    Guarded by DEMO_MODE so that scheduling it can never destroy data on a
    real deployment: only config/settings/demo.py sets that flag, and this
    task only appears in the Beat schedule there. The guard is the second
    lock — a misconfigured Beat entry elsewhere becomes a logged no-op
    rather than a wipe.
    """
    if not getattr(settings, "DEMO_MODE", False):
        logger.warning("reset_demo_scheduled fired outside demo mode; skipping.")
        return "skipped: not demo mode"

    call_command("reset_demo", "--story")
    return "demo reset"
