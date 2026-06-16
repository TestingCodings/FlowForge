from .base import *  # noqa: F401, F403
import dj_database_url

DEBUG = True

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": dj_database_url.config(
        default="postgres://flowforge:flowforge@localhost:5432/flowforge",
        conn_max_age=600,
    )
}

CORS_ALLOW_ALL_ORIGINS = True

# Use console email backend in development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
