"""Ensure the Celery app is loaded whenever Django starts.

`@shared_task` binds to the *current* app, so this import has to happen at
Django startup — otherwise tasks registered by the apps attach to a default
app that the worker never sees.
"""
from .celery import app as celery_app

__all__ = ("celery_app",)
