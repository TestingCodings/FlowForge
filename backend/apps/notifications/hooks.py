"""
Action hook runner (docs/HOOKS.md Part 2).

- `after` hooks fire once a transition has committed: async, retried, and can
  write their response back into instance metadata.
- `before` hooks run *before* the state changes, synchronously, so they can
  gate the transition (on_failure=block aborts it). They reuse the rules-
  service circuit breaker so a flapping downstream fast-fails instead of
  hanging every transition.

Secrets referenced as {{secret.NAME}} are resolved from the encrypted store
and redacted from everything persisted.
"""
from __future__ import annotations

import httpx
from celery import shared_task
from django.utils import timezone

from apps.secrets.crypto import redact
from apps.secrets.models import Secret
from apps.workflows.engine import WorkflowTransitionError
from apps.workflows.rules import CircuitBreaker

from .models import HookExecutionLog, TransitionHook
from .outbound import UnsafeURLError, assert_safe_url, referenced_secret_names, render_template

MAX_HOOK_RETRIES = 5

# A flapping downstream shouldn't make every gated transition hang on a
# timeout — after repeated failures the breaker opens and before-hooks
# fast-fail per their on_failure policy.
_before_hook_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout_seconds=60)


def _resolve_secrets(hook, instance) -> dict[str, str]:
    """Fetch the plaintext for every {{secret.NAME}} the hook references."""
    cfg = hook.config or {}
    texts = [cfg.get("url", ""), cfg.get("body_template", ""), *(cfg.get("headers", {}) or {}).values()]
    resolved: dict[str, str] = {}
    for name in referenced_secret_names(*texts):
        secret = Secret.resolve(name, hook.transition.workflow_definition_id)
        if secret is not None:
            resolved[name] = secret.reveal()
            Secret.objects.filter(id=secret.id).update(last_used_at=timezone.now())
    return resolved


def _perform_request(hook, instance):
    """Render the hook's config, SSRF-check, and make the call.

    Returns (response, secret_plaintexts, request_summary). Raises on any
    failure (UnsafeURLError, transport error, or expect_status mismatch).
    """
    cfg = hook.config or {}
    secret_values = _resolve_secrets(hook, instance)
    secret_plaintexts = list(secret_values.values())

    def render(text):
        return render_template(text, instance=instance, secret_values=secret_values)

    url = render(cfg.get("url", ""))
    method = "GET" if hook.action == TransitionHook.Action.PROBE else cfg.get("method", "POST").upper()
    headers = {k: render(v) for k, v in (cfg.get("headers", {}) or {}).items()}
    body = render(cfg.get("body_template", "")) if hook.action == TransitionHook.Action.HTTP_REQUEST else ""
    timeout = float(cfg.get("timeout", 5))
    expect = cfg.get("expect_status")
    request_summary = redact(f"{method} {url}", secret_plaintexts)

    assert_safe_url(url)
    resp = httpx.request(method, url, headers=headers or None,
                         content=body.encode() if body else None, timeout=timeout)
    if expect is not None and resp.status_code != int(expect):
        raise RuntimeError(f"Expected HTTP {expect}, got {resp.status_code}")
    resp.raise_for_status()
    return resp, secret_plaintexts, request_summary


def _output_value(hook, resp):
    """Resolve the value a hook writes via output_to (JSON if possible)."""
    try:
        return resp.json()
    except Exception:
        return resp.text


# ── after hooks (async, post-commit) ──

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
            _execute_hook_impl(str(log.id))  # Celery unavailable — run inline (dev)


def _execute_hook_impl(log_id: str):
    try:
        log = HookExecutionLog.objects.select_related("hook", "workflow_instance").get(id=log_id)
    except HookExecutionLog.DoesNotExist:
        return
    hook, instance = log.hook, log.workflow_instance

    try:
        resp, secrets, req_summary = _perform_request(hook, instance)
    except Exception as exc:
        secrets = []  # secrets aren't returned on failure; error text is generic
        log.attempt += 1
        log.error_message = redact(str(exc), secrets)
        terminal = isinstance(exc, UnsafeURLError) or log.attempt >= MAX_HOOK_RETRIES
        log.status = HookExecutionLog.Status.DEAD_LETTER if terminal else HookExecutionLog.Status.FAILED
        log.save(update_fields=["status", "attempt", "error_message", "updated_at"])
        if not terminal:
            raise
        return

    log.status = HookExecutionLog.Status.SUCCEEDED
    log.http_status_code = resp.status_code
    log.request_summary = req_summary
    log.response_summary = redact((resp.text or "")[:500], secrets)

    if hook.output_to.startswith("metadata."):
        key = hook.output_to[len("metadata."):]
        merged = dict(instance.metadata_json or {})
        merged[key] = _output_value(hook, resp)
        instance.metadata_json = merged
        instance.save(update_fields=["metadata_json", "updated_at"])

    log.save(update_fields=["status", "http_status_code", "request_summary", "response_summary", "updated_at"])


@shared_task(bind=True, max_retries=MAX_HOOK_RETRIES)
def execute_hook_task(self, log_id: str):
    try:
        _execute_hook_impl(log_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


# ── before hooks (synchronous, gating) ──

def run_before_hooks(instance, transition) -> dict:
    """Run active `before` hooks synchronously; return metadata deltas to persist.

    Raises WorkflowTransitionError if an on_failure=block hook fails, aborting
    the transition. warn/ignore hooks record the failure and proceed.
    """
    hooks = TransitionHook.objects.filter(
        transition=transition, trigger=TransitionHook.Trigger.BEFORE, is_active=True
    ).order_by("order", "created_at")

    metadata_deltas: dict = {}
    for hook in hooks:
        log = HookExecutionLog.objects.create(
            hook=hook, workflow_instance=instance, status=HookExecutionLog.Status.QUEUED,
        )
        try:
            resp, secrets, req_summary = _before_hook_breaker.call(_perform_request, hook, instance)
        except Exception as exc:
            log.status = HookExecutionLog.Status.FAILED
            log.error_message = redact(str(exc), [])
            log.save(update_fields=["status", "error_message", "updated_at"])
            if hook.on_failure == TransitionHook.OnFailure.BLOCK:
                raise WorkflowTransitionError(
                    f"Blocked by hook on '{transition.name}': {log.error_message}"
                )
            continue  # warn / ignore → proceed

        log.status = HookExecutionLog.Status.SUCCEEDED
        log.http_status_code = resp.status_code
        log.request_summary = req_summary
        log.response_summary = redact((resp.text or "")[:500], secrets)
        log.save(update_fields=["status", "http_status_code", "request_summary", "response_summary", "updated_at"])

        if hook.output_to.startswith("metadata."):
            metadata_deltas[hook.output_to[len("metadata."):]] = _output_value(hook, resp)

    return metadata_deltas
