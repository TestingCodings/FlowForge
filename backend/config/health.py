from django.http import JsonResponse


def health_check(request):
    return JsonResponse({"status": "ok"})


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
