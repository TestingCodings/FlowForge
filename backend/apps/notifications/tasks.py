import hashlib
import hmac
import json
import logging

from celery import shared_task
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import IntegrityError, OperationalError
import httpx

from .models import WebhookDeliveryLog, WebhookDeliveryStatus, EventTrigger
from .services import dispatch_notification, sign_payload, queue_event_notifications
from apps.audit.models import AuditActionType, AuditLog
from apps.instances.models import WorkflowInstance
from apps.instances.serializers import _sla_status

logger = logging.getLogger(__name__)


MAX_WEBHOOK_RETRIES = 6
# Exponential backoff: 2^attempt seconds (1s, 2s, 4s, 8s, 16s, 32s)
def get_retry_delay(attempt):
    return 2 ** attempt


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def dispatch_notification_task(self, notification_log_id: str):
    try:
        dispatch_notification(notification_log_id)
    except Exception as exc:
        raise self.retry(exc=exc)


def _deliver_webhook_impl(delivery_log_id: str):
    """Implementation of webhook delivery with exponential backoff retries.

    Exponential backoff: attempt 0→1s, 1→2s, 2→4s, 3→8s, 4→16s, 5→32s, then dead-letter.
    """
    try:
        log = WebhookDeliveryLog.objects.get(id=delivery_log_id)
    except WebhookDeliveryLog.DoesNotExist:
        return

    sub = log.webhook_subscription
    body = json.dumps(log.payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-FlowForge-Event": log.event_trigger,
    }
    if sub.secret:
        headers["X-FlowForge-Signature"] = sign_payload(sub.secret, body)

    try:
        response = httpx.post(sub.url, content=body, headers=headers, timeout=5)
        response.raise_for_status()

        log.status = WebhookDeliveryStatus.DELIVERED
        log.http_status_code = response.status_code
        log.delivered_at = timezone.now()
        log.save(update_fields=["status", "http_status_code", "delivered_at", "updated_at"])
        return

    except Exception as exc:
        log.attempt += 1
        log.error_message = str(exc)

        if log.attempt >= MAX_WEBHOOK_RETRIES:
            log.status = WebhookDeliveryStatus.DEAD_LETTER
            log.save(update_fields=["status", "attempt", "error_message", "updated_at"])
            raise  # Re-raise for Celery's final error handling

        log.status = WebhookDeliveryStatus.FAILED
        retry_delay = get_retry_delay(log.attempt)
        log.next_retry_at = timezone.now() + timezone.timedelta(seconds=retry_delay)
        log.save(update_fields=["status", "attempt", "error_message", "next_retry_at", "updated_at"])

        raise exc


@shared_task(bind=True)
def deliver_webhook_task(self, delivery_log_id: str):
    """Celery task wrapper for webhook delivery with retry handling."""
    try:
        _deliver_webhook_impl(delivery_log_id)
    except Exception as exc:
        if _should_retry_webhook(delivery_log_id):
            # Get retry delay from current attempt
            log = WebhookDeliveryLog.objects.get(id=delivery_log_id)
            retry_delay = get_retry_delay(log.attempt)
            raise self.retry(exc=exc, countdown=retry_delay)
        raise


def _should_retry_webhook(delivery_log_id: str) -> bool:
    """Check if a webhook delivery should be retried."""
    try:
        log = WebhookDeliveryLog.objects.get(id=delivery_log_id)
        return log.attempt < MAX_WEBHOOK_RETRIES and log.status == WebhookDeliveryStatus.FAILED
    except WebhookDeliveryLog.DoesNotExist:
        return False


# Alias for direct calls (non-Celery fallback)
deliver_webhook = _deliver_webhook_impl


# Celery Beat task to retry failed deliveries
@shared_task
def retry_failed_webhook_deliveries():
    """Find queued/failed webhooks past their retry time and re-queue them."""
    from django.db.models import Q

    now = timezone.now()
    retry_logs = WebhookDeliveryLog.objects.filter(
        status=WebhookDeliveryStatus.FAILED,
        next_retry_at__lte=now,
    )[:100]  # Batch process

    for log in retry_logs:
        try:
            deliver_webhook.delay(str(log.id))
        except Exception:
            pass


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_slas_scheduled(self):
    """Celery Beat task to scan open instances for SLA breaches and fire notifications.

    Runs periodically and is idempotent: an instance is notified at most once per state entry.
    Retries on transient DB lock failures (IntegrityError, OperationalError).
    """
    try:
        open_instances = WorkflowInstance.objects.filter(
            completed_at__isnull=True
        ).select_related("workflow_definition", "current_state")

        checked = breached = notified = 0
        for instance in open_instances:
            sla = _sla_status(instance)
            checked += 1
            if not sla or sla["status"] != "breached":
                continue
            breached += 1

            # Dedupe: the audit log records one breach per entry into the state
            try:
                already_notified = AuditLog.objects.filter(
                    workflow_instance=instance,
                    action_type=AuditActionType.SLA_BREACHED,
                    created_at__gte=parse_datetime(sla["entered_at"]),
                ).exists()
                if already_notified:
                    continue

                AuditLog.objects.create(
                    workflow_instance=instance,
                    actor=None,
                    action_type=AuditActionType.SLA_BREACHED,
                    from_state=instance.current_state.name,
                    payload={
                        "sla_hours": sla["sla_hours"],
                        "elapsed_hours": sla["elapsed_hours"],
                    },
                )
                queue_event_notifications(
                    workflow_instance=instance,
                    event_trigger=EventTrigger.SLA_BREACHED,
                    context_data={
                        "instance": {"reference_number": instance.reference_number},
                        "state": instance.current_state.name,
                        "sla_hours": sla["sla_hours"],
                        "elapsed_hours": sla["elapsed_hours"],
                    },
                )
                notified += 1
                logger.info(
                    f"SLA breached: {instance.reference_number} in "
                    f"'{instance.current_state.name}' "
                    f"({sla['elapsed_hours']}h / {sla['sla_hours']}h SLA)"
                )
            except (IntegrityError, OperationalError) as e:
                logger.warning(
                    f"Transient DB error processing SLA for instance {instance.id}: {e}. "
                    f"Will retry."
                )
                continue

        logger.info(
            f"SLA check complete: checked {checked} open instances, "
            f"{breached} breached, {notified} newly notified."
        )
    except (IntegrityError, OperationalError) as exc:
        logger.warning(f"SLA scheduler encountered transient DB lock: {exc}. Retrying...")
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error(f"SLA scheduler failed: {exc}", exc_info=True)
        raise
