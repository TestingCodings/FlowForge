import hashlib
import hmac
import json

from django.core.mail import send_mail
from django.template import Context, Template
from django.utils import timezone
from decouple import config
import httpx

from .models import (
    NotificationChannel,
    NotificationLog,
    NotificationStatus,
    NotificationTemplate,
    WebhookDeliveryLog,
    WebhookDeliveryStatus,
    WebhookSubscription,
)


def _render_template(text, context):
    return Template(text or "").render(Context(context or {}))


def build_event_payload(workflow_instance, event_trigger, context_data=None):
    """Structured JSON payload delivered to webhook subscribers."""
    return {
        "event": event_trigger,
        "timestamp": timezone.now().isoformat(),
        "instance": {
            "id": str(workflow_instance.id),
            "reference_number": workflow_instance.reference_number,
            "workflow": workflow_instance.workflow_definition.name,
            "current_state": workflow_instance.current_state.name,
            "completed": workflow_instance.completed_at is not None,
        },
        "data": context_data or {},
    }


def sign_payload(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def emit_webhooks(workflow_instance, event_trigger, context_data=None):
    """Queue webhook delivery to every matching active subscription (async, non-blocking)."""
    from django.db.models import Q
    from .tasks import deliver_webhook_task, deliver_webhook

    subs = WebhookSubscription.objects.filter(is_active=True).filter(
        Q(workflow_definition=workflow_instance.workflow_definition)
        | Q(workflow_definition__isnull=True)
    )
    payload = build_event_payload(workflow_instance, event_trigger, context_data)

    logs = []
    for sub in subs:
        if sub.events and event_trigger not in sub.events:
            continue

        delivery_log = WebhookDeliveryLog.objects.create(
            webhook_subscription=sub,
            workflow_instance=workflow_instance,
            event_trigger=event_trigger,
            payload=payload,
            status=WebhookDeliveryStatus.QUEUED,
        )
        logs.append(delivery_log)

        try:
            deliver_webhook_task.delay(str(delivery_log.id))
        except Exception:
            # Fallback if Celery is unavailable
            try:
                from .tasks import deliver_webhook
                deliver_webhook(str(delivery_log.id))
            except Exception:
                delivery_log.status = WebhookDeliveryStatus.FAILED
                delivery_log.error_message = "Failed to queue delivery"
                delivery_log.save(update_fields=["status", "error_message"])

    return logs


def queue_event_notifications(workflow_instance, event_trigger, context_data=None):
    context_data = context_data or {}
    from django.db.models import Q

    templates = NotificationTemplate.objects.filter(
        event_trigger=event_trigger,
        is_active=True,
    ).filter(
        Q(workflow_definition=workflow_instance.workflow_definition)
        | Q(workflow_definition__isnull=True)
    )

    logs = emit_webhooks(workflow_instance, event_trigger, context_data)
    for template in templates:
        subject = _render_template(template.subject_template, context_data)
        body = _render_template(template.body_template, context_data)

        recipient = ""
        if template.channel == NotificationChannel.EMAIL:
            recipient = context_data.get("recipient_email", "")
        elif template.channel == NotificationChannel.SLACK:
            recipient = config("SLACK_WEBHOOK_URL", default="")
        elif template.channel == NotificationChannel.WEBHOOK:
            recipient = context_data.get("webhook_url", "")

        log = NotificationLog.objects.create(
            workflow_instance=workflow_instance,
            event_trigger=event_trigger,
            channel=template.channel,
            recipient=recipient,
            subject=subject,
            body=body,
            status=NotificationStatus.QUEUED,
        )
        logs.append(log)

        try:
            from .tasks import dispatch_notification_task

            dispatch_notification_task.delay(str(log.id))
        except Exception:
            try:
                dispatch_notification(str(log.id))
            except Exception:
                # Keep queueing non-blocking; status/error are persisted by dispatch_notification.
                pass

    return logs


def dispatch_notification(notification_log_id):
    log = NotificationLog.objects.get(id=notification_log_id)
    log.attempts += 1

    try:
        if log.channel == NotificationChannel.EMAIL:
            if not log.recipient:
                raise ValueError("Missing recipient email")
            send_mail(
                subject=log.subject or "FlowForge Notification",
                message=log.body,
                from_email=config("DEFAULT_FROM_EMAIL", default="noreply@flowforge.local"),
                recipient_list=[log.recipient],
                fail_silently=False,
            )

        elif log.channel in {NotificationChannel.SLACK, NotificationChannel.WEBHOOK}:
            if not log.recipient:
                raise ValueError("Missing webhook destination")
            response = httpx.post(log.recipient, json={"text": log.body, "subject": log.subject}, timeout=5)
            response.raise_for_status()

        log.status = NotificationStatus.SENT
        log.error_message = ""
        log.sent_at = timezone.now()
    except Exception as exc:
        log.status = NotificationStatus.FAILED
        log.error_message = str(exc)
        raise
    finally:
        log.save(update_fields=["status", "attempts", "error_message", "sent_at"])
