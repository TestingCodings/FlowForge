"""
Django settings — base configuration shared across all environments.
"""
from pathlib import Path
from corsheaders.defaults import default_headers as cors_default_headers
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY")

# ── Secret store encryption (docs/HOOKS.md) ──
# Versioned Fernet keys so secrets can be rotated without downtime. Distinct
# from DJANGO_SECRET_KEY. Absent = the secret store fails closed (refuses to
# store) rather than persisting plaintext. Provide via env, e.g.
#   SECRETS_ENCRYPTION_KEY_V1=<urlsafe-base64 32-byte key>
# Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_secret_key_v1 = config("SECRETS_ENCRYPTION_KEY_V1", default="")
SECRETS_ENCRYPTION_KEYS = {1: _secret_key_v1} if _secret_key_v1 else {}
SECRETS_ENCRYPTION_KEY_CURRENT = config("SECRETS_ENCRYPTION_KEY_CURRENT", default=1, cast=int)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    # Local
    "apps.accounts",
    "apps.workflows",
    "apps.instances",
    "apps.forms",
    "apps.tasks",
    "apps.audit",
    "apps.notifications",
    "apps.secrets",
    "apps.media",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# CORS: `If-Match` is not a browser-safelisted request header, so the optimistic
# locking on PATCH /instances/<id>/metadata/ triggers a preflight. Without this
# the browser blocks the request and metadata edits fail in the UI even though
# the API accepts them.
CORS_ALLOW_HEADERS = (*cors_default_headers, "if-match")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django 5.1 removed STATICFILES_STORAGE; STORAGES is the replacement.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ── Media uploads (docs/MEDIA.md) ──
# Local dev/tests: files land on disk under MEDIA_ROOT (no cloud creds needed).
# Production: override STORAGES["default"] with django-storages' S3Boto3Storage
# pointed at Cloudflare R2 (private ACL + signed URLs). FileField picks it up
# automatically — no model change required.
MEDIA_ROOT = BASE_DIR / "media_uploads"
MEDIA_URL = "/media/"  # local dev only; assets are served via the authenticated API
MEDIA_UPLOAD_MAX_BYTES = config("MEDIA_UPLOAD_MAX_BYTES", default=20 * 1024 * 1024, cast=int)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Inbound trigger fire endpoint (unauthenticated, token-addressed) is
    # rate-limited per client IP.
    "DEFAULT_THROTTLE_RATES": {
        "trigger": "60/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Celery
CELERY_BROKER_URL = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "mark-overdue-tasks-hourly": {
        "task": "tasks.mark_overdue_tasks",
        "schedule": timedelta(hours=1),
    },
    "retry-failed-webhook-deliveries": {
        "task": "apps.notifications.tasks.retry_failed_webhook_deliveries",
        "schedule": timedelta(minutes=5),
    },
    "check-slas-every-minute": {
        "task": "apps.notifications.tasks.check_slas_scheduled",
        "schedule": timedelta(minutes=1),
    },
}

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "django.utils.log.ServerFormatter",
            "format": '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
