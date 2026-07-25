from .base import *  # noqa: F401, F403
import tempfile

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",  # noqa: F405
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CORS_ALLOW_ALL_ORIGINS = True

# Disable select_for_update restrictions on SQLite in tests
# (select_for_update is a no-op on SQLite but raises if nowait=True)

# Use a temp directory for media uploads in tests so artefacts don't land
# in the repository tree.
MEDIA_ROOT = tempfile.mkdtemp(prefix="flowforge_test_media_")
