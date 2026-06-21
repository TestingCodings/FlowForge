"""
Local development settings using SQLite — no Docker/PostgreSQL required.
Usage: python manage.py runserver --settings=config.settings.local_sqlite
"""
from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dev.sqlite3",  # noqa: F405
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CORS_ALLOW_ALL_ORIGINS = True

# Point at local rules service instead of Docker hostname
RULES_SERVICE_URL = "http://localhost:8001"
