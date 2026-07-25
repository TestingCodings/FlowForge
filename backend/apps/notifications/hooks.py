"""
Action hook runner (docs/HOOKS.md Part 2).

`after` hooks fire once a transition has committed: they call an external
system, redact secrets from what's logged, and optionally write the response
back into instance metadata. Delivery is async with retries, mirroring the
webhook machinery.

`before` (gating) hooks are a later step; this module runs `after` hooks only.
"""
from __future__ import annotations

import httpx
from celery import shared_task
from django.utils import timezone

from apps.secrets.crypto import redact
from apps.secrets.models import Secret

from .models import HookExecutionLog, TransitionHook
from .outbound import UnsafeURLError, assert_safe_url, referenced_secret_names, render_template

MAX_HOOK_RETRIES = 5


def run_after_hooks(instance, transition):
    """Queue every active `after` hook on this transition. Call post-commit."""
    hooks = TransitionHook.objects.filter(
        transition=transition, trigger=TransitionHook.Trigger.AFTER, is_active=True
    ).order_by("order", "created_at")
    for hook in hooks:
        log = HookExecutionLog.objects.create(
            hook=hook, workflow_instance=instance, status=HookExecutionLog.Status.QUEUED,
        )
        try:
            execute_hook_task.delay(str(log.id))
        except Exception:
            # Celery unavailable — run inline so behaviour is preserved in dev.
            _execute_hook_impl(str(log.id))


def _resolve_secrets(hook, instance) -> dict[str, str]:
    """Fetch the plaintext for every {{secret.NAME}} the hook references."""
    cfg = hook.config or {}
    texts = [cfg.get("url", ""), cfg.get("body_template", ""), *(cfg.get("headers", {}) or {}).values()]
    names = referenced_secret_names(*texts)
    resolved: dict[str, str] = {}
    for name in names:
        secret = Secret.resolve(name, hook.transition.workflow_definition_id)
        if secret is not None:
            resolved[name] = secret.reveal()
            Secret.objects.filter(id=secret.id).update(last_used_at=timezone.now())
    return resolved


def _execute_hook_impl(log_id: str):
    try:
        log = HookExecutionLog.objects.select_related("hook", "workflow_instance").get(id=log_id)
    except HookExecutionLog.DoesNotExist:
        return

    hook = log.hook
    instance = log.workflow_instance
    cfg = hook.config or {}
    secret_values = _resolve_secrets(hook, instance)
    secret_plaintexts = list(secret_values.values())

    def render(text):
        return render_template(text, instance=instance, secret_values=secret_values)

    url = render(cfg.get("url", ""))
    method = "GET" if hook.action == TransitionHook.Action.PROBE else (cfg.get("method", "POST").upper())
    headers = {k: render(v) for k, v in (cfg.get("headers", {}) or {}).items()}
    body = render(cfg.get("body_template", "")) if hook.action == TransitionHook.Action.HTTP_REQUEST else ""
    timeout = float(cfg.get("timeout", 5))
    expect = cfg.get("expect_status")

    # Log the request with secrets scrubbed.
    log.request_summary = redact(f"{method} {url}", secret_plaintexts)

    try:
        assert_safe_url(url)
        resp = httpx.request(method, url, headers=headers or None,
                             content=body.encode() if body else None, timeout=timeout)
        if expect is not None and resp.status_code != int(expect):
            raise RuntimeError(f"Expected HTTP {expect}, got {resp.status_code}")
        resp.raise_for_status()
    except (UnsafeURLError, Exception) as exc:
        log.attempt += 1
        log.error_message = redact(str(exc), secret_plaintexts)
        if isinstance(exc, UnsafeURLError) or log.attempt >= MAX_HOOK_RETRIES:
            log.status = HookExecutionLog.Status.DEAD_LETTER
            log.save(update_fields=["status", "attempt", "error_message", "updated_at"])
            return
        log.status = HookExecutionLog.Status.FAILED
        log.save(update_fields=["status", "attempt", "error_message", "updated_at"])
        raise

    log.status = HookExecutionLog.Status.SUCCEEDED
    log.http_status_code = resp.status_code
    log.response_summary = redact((resp.text or "")[:500], secret_plaintexts)

    # output_to: write the response into metadata so it feeds rules/computed fields.
    if hook.output_to and hook.output_to.startswith("metadata."):
        key = hook.output_to[len("metadata."):]
        try:
            value = resp.json()
        except Exception:
            value = resp.text
        merged = dict(instance.metadata_json or {})
        merged[key] = value
        instance.metadata_json = merged
        instance.save(update_fields=["metadata_json", "updated_at"])

    log.save(update_fields=["status", "http_status_code", "response_summary", "updated_at"])


@shared_task(bind=True, max_retries=MAX_HOOK_RETRIES)
def execute_hook_task(self, log_id: str):
    try:
        _execute_hook_impl(log_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
