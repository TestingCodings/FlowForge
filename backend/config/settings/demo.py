"""
Settings for the public demo at flowforge.cortexa.solutions
(docs/DEPLOYMENT.md §2).

Demo mode is settings plus a management command — never a code fork. The
demo runs the same code paths a real deployment does; it just runs them
with the blast radius turned down.

Differences from production, and why each one exists:

* **Postgres without SSL.** `production.py` sets `ssl_require=True`, which is
  right when the database is a managed service across a network. The demo's
  Postgres is a container on the same private Docker network, with no TLS
  configured, so requiring SSL simply fails to connect.
* **Local disk for uploads.** Production expects S3/R2. The demo is a single
  VPS with a named volume, and its data is disposable by design.
* **No SMTP.** There are no mail credentials on the box at all — the console
  backend means a notification bug can never become outbound spam.
* **Registration off, throttles on.** The demo hands out accounts; it doesn't
  accept them.
* **SSRF allow-list.** Action hooks and webhooks let a visitor make the server
  issue HTTP requests. `outbound.py` already refuses private/loopback/
  link-local addresses; here we additionally restrict to an explicit host
  allow-list, so a demo visitor cannot use the VPS as a proxy at all.
"""
from .production import *  # noqa: F401, F403

import dj_database_url
from decouple import config

# ── Database ────────────────────────────────────────────────────────────────
# Same-network container: no TLS to require. Everything else (conn_max_age,
# env-driven URL) matches production.
DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=False,
    )
}

# ── Storage ─────────────────────────────────────────────────────────────────
# Single VPS with a named volume; no object store to talk to. Uploads are
# served through the authenticated API either way, so this changes where
# bytes land, not who can read them.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_ROOT = config("MEDIA_ROOT", default="/data/media")

# ── Email ───────────────────────────────────────────────────────────────────
# No credentials exist on the demo box. Console backend keeps notification
# code exercised end-to-end while making outbound mail physically impossible.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "demo@flowforge.cortexa.solutions"

# ── Demo behaviour flags ────────────────────────────────────────────────────
# The demo issues accounts rather than accepting them; the register page
# points visitors at the seeded credentials instead.
DEMO_MODE = True
DEMO_REGISTRATION_ENABLED = config("DEMO_REGISTRATION_ENABLED", default=False, cast=bool)

# Shown in the UI banner so nobody mistakes a nightly wipe for data loss.
DEMO_RESET_NOTICE = "Public demo — data resets nightly at 03:00 UTC"

# ── Abuse hardening ─────────────────────────────────────────────────────────
# Throttles are the main defence against scraping and API abuse from an
# unauthenticated visitor. Values from DEPLOYMENT.md §2.2.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        **REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),  # noqa: F405
        "anon": config("DEMO_THROTTLE_ANON", default="20/min"),
        "user": config("DEMO_THROTTLE_USER", default="120/min"),
    },
}

# Keep request bodies small. Caddy caps this again at the edge (5 MB) so a
# large body is rejected before it ever reaches gunicorn.
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=2 * 1024 * 1024, cast=int
)
MEDIA_UPLOAD_MAX_BYTES = config(
    "MEDIA_UPLOAD_MAX_BYTES", default=5 * 1024 * 1024, cast=int
)

# ── Outbound (SSRF) ─────────────────────────────────────────────────────────
# Action hooks and webhooks are visitor-configurable, which makes them the
# demo's sharpest edge: they cause the *server* to make requests. The
# private/loopback/link-local guard in apps/notifications/outbound.py always
# applies; this allow-list narrows it further to hosts that exist to receive
# test traffic. Empty would mean "any public host" — deliberately not the
# default here.
OUTBOUND_ALLOWED_HOSTS = [
    h.strip()
    for h in config(
        "OUTBOUND_ALLOWED_HOSTS",
        default="webhook.site,httpbin.org,example.com",
    ).split(",")
    if h.strip()
]

# ── Nightly reset ───────────────────────────────────────────────────────────
# Deliberately scheduled here and nowhere else. The task also re-checks
# DEMO_MODE at runtime, so even a stray Beat entry on another deployment
# would log and return rather than delete anything.
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    **CELERY_BEAT_SCHEDULE,  # noqa: F405
    "reset-demo-nightly": {
        "task": "apps.workflows.tasks.reset_demo_scheduled",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC; CELERY_TIMEZONE=UTC
    },
}

# ── Demo accounts shown on the login page ───────────────────────────────────
# Served by /api/demo-info/ so the login page doesn't have to hard-code them.
# Format: "email:password:Label,email:password:Label" — supplied as an env var
# at deploy time, so working credentials never live in the repository.
#
# Empty by default: a demo that forgets to set this shows no accounts, which
# is a visible, harmless failure. The alternative default — the seed's own
# passwords — would put them back in source, which is the thing this exists
# to avoid.
def _parse_demo_accounts(raw: str) -> list[dict]:
    accounts = []
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 2 and parts[0] and parts[1]:
            accounts.append({
                "email": parts[0],
                "password": parts[1],
                "role": parts[2] if len(parts) > 2 else "",
            })
    return accounts


DEMO_ACCOUNTS = _parse_demo_accounts(config("DEMO_ACCOUNTS", default=""))
