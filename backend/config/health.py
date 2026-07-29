"""Health and build introspection.

`health_check` is the uptime probe, but it does one more job: it reports
whether the running process is serving stale code. A dev server started with
--noreload keeps whatever it loaded at boot, which has repeatedly looked like
a code bug — a fix that "doesn't work", a feature that "broke", once nearly
blamed on someone else's pull request. The process can answer this itself.
"""
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Captured once, at import — i.e. when this process loaded its code.
STARTED_AT = datetime.now(timezone.utc)


def _revision() -> str:
    """The commit this process is running, best-effort.

    Env var first: a container image is built from a known commit and has no
    .git directory. Falls back to asking git, which is what makes it useful
    in development.
    """
    env = os.environ.get("GIT_SHA") or os.environ.get("SOURCE_COMMIT")
    if env:
        return env[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _newest_source_mtime() -> float:
    """Most recent mtime across the backend's Python sources."""
    newest = 0.0
    for path in BACKEND_ROOT.rglob("*.py"):
        # Skip noise that changes without the served code changing.
        if any(part in {"__pycache__", ".venv", "node_modules", "htmlcov"} for part in path.parts):
            continue
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
    return newest


def health_check(request):
    body = {
        "status": "ok",
        "started_at": STARTED_AT.isoformat(),
        "revision": _revision(),
    }

    # Only in development: walking the tree per request would be wasteful,
    # and a production process is never hot-reloaded in place.
    if settings.DEBUG:
        newest = _newest_source_mtime()
        stale = newest > STARTED_AT.timestamp()
        body["stale"] = stale
        if stale:
            body["stale_hint"] = (
                "Source files are newer than this process. It was likely started "
                "with --noreload; restart it before trusting these results."
            )

    return JsonResponse(body)


def demo_info(request):
    """Public metadata for the demo login page.

    Unauthenticated by necessity: it renders *before* sign-in, so a visitor
    can see which account to use. That makes it the one endpoint that
    deliberately serves credentials, which is why both guards matter —

      * `DEMO_MODE` must be on. Configuring accounts is not sufficient, so a
        stray DEMO_ACCOUNTS on a real deployment publishes nothing.
      * The accounts come from deployment config (an env var read in
        config/settings/demo.py), never from source. The login page used to
        hard-code them, which put working credentials in a public file.

    Everything here is empty on any non-demo deployment.
    """
    from django.conf import settings

    demo_mode = bool(getattr(settings, "DEMO_MODE", False))
    return JsonResponse({
        "demo_mode": demo_mode,
        "notice": getattr(settings, "DEMO_RESET_NOTICE", "") if demo_mode else "",
        "accounts": list(getattr(settings, "DEMO_ACCOUNTS", [])) if demo_mode else [],
    })
