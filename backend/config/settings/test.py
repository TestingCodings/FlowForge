from .base import *  # noqa: F401, F403

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

import tempfile

# Uploads go to a temp dir in tests so artefacts never land in the repo tree.
MEDIA_ROOT = tempfile.mkdtemp(prefix="flowforge_test_media_")
