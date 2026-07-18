import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import WorkflowInstance
from apps.notifications.models import NotificationChannel, NotificationStatus, NotificationTemplate
from apps.notifications.services import queue_event_notifications
from apps.workflows.models import State, WorkflowDefinition


@pytest.fixture
def setup_context(db):
    admin_user = User.objects.create_user(
        email="notify-admin@example.com",
        password="StrongPass123!",
        first_name="Notify",
        last_name="Admin",
    )
    role = Role.objects.create(name=RoleName.PLATFORM_ADMIN)
    UserRole.objects.create(user=admin_user, role=role)

    wf = WorkflowDefinition.objects.create(name="Notify WF", created_by=admin_user)
    State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )
    instance = WorkflowInstance.objects.create(workflow_definition=wf, created_by=admin_user)

    return admin_user, wf, instance


@pytest.mark.django_db
def test_notification_logs_endpoint_for_admin(setup_context):
    admin_user, wf, instance = setup_context

    NotificationTemplate.objects.create(
        workflow_definition=wf,
        channel=NotificationChannel.EMAIL,
        event_trigger="instance_created",
        subject_template="Created {{ instance.reference_number }}",
        body_template="Workflow created.",
    )
    queue_event_notifications(
        workflow_instance=instance,
        event_trigger="instance_created",
        context_data={"instance": {"reference_number": instance.reference_number}, "recipient_email": "x@example.com"},
    )

    client = APIClient()
    login = client.post(
        reverse("auth-login"),
        {"email": admin_user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    response = client.get("/api/notification-logs/")
    assert response.status_code == 200
    assert response.data["count"] >= 1


@pytest.mark.django_db
def test_queue_event_creates_log(setup_context):
    admin_user, wf, instance = setup_context

    NotificationTemplate.objects.create(
        workflow_definition=wf,
        channel=NotificationChannel.WEBHOOK,
        event_trigger="task_assigned",
        subject_template="Task assigned",
        body_template="Task {{ task_title }} assigned",
    )

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="task_assigned",
        context_data={"task_title": "Review", "webhook_url": "http://localhost:9999/fake"},
    )
    assert len(logs) == 1
    assert logs[0].status in {NotificationStatus.QUEUED, NotificationStatus.FAILED, NotificationStatus.SENT}


# ---------------------------------------------------------------------------
# Webhook subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webhook_subscription_fires_with_signature(setup_context, monkeypatch):
    """Webhook should be delivered with correct HMAC signature (async)."""
    import hashlib
    import hmac as hmac_mod
    import json

    from apps.notifications.models import WebhookSubscription, WebhookDeliveryLog
    from apps.notifications.tasks import _deliver_webhook_impl
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    sub = WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/flowforge",
        events=["state_transition"],
        secret="topsecret",
        created_by=admin_user,
    )

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass
        status_code = 200

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = content
        captured["headers"] = headers
        return FakeResponse()

    import apps.notifications.tasks as tasks_module
    monkeypatch.setattr(tasks_module.httpx, "post", fake_post)

    # Create a delivery log and deliver it directly
    delivery_log = WebhookDeliveryLog.objects.create(
        webhook_subscription=sub,
        workflow_instance=instance,
        event_trigger="state_transition",
        payload={"event": "state_transition", "instance": {"reference_number": instance.reference_number}, "data": {"to_state": "Review"}},
    )

    _deliver_webhook_impl(str(delivery_log.id))

    assert captured["url"] == "https://hooks.example.com/flowforge"
    assert captured["headers"]["X-FlowForge-Event"] == "state_transition"

    expected_sig = "sha256=" + hmac_mod.new(b"topsecret", captured["body"], hashlib.sha256).hexdigest()
    assert captured["headers"]["X-FlowForge-Signature"] == expected_sig

    payload = json.loads(captured["body"])
    assert payload["event"] == "state_transition"
    assert payload["instance"]["reference_number"] == instance.reference_number
    assert payload["data"]["to_state"] == "Review"


@pytest.mark.django_db
def test_webhook_subscription_respects_event_filter(setup_context, monkeypatch):
    """Webhook should not be queued if event is not in the subscription's event filter."""
    from apps.notifications.models import WebhookSubscription
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/only-comments",
        events=["comment_added"],
        created_by=admin_user,
    )

    # Mock Celery to avoid Redis
    import apps.notifications.tasks as tasks_module
    mock_task = MagicMock()
    monkeypatch.setattr(tasks_module, "deliver_webhook_task", mock_task)

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="state_transition",
        context_data={},
    )
    assert logs == []
    # Should not have queued any tasks
    assert not mock_task.delay.called


@pytest.mark.django_db
def test_webhook_failure_is_recorded_not_raised(setup_context, monkeypatch):
    """Webhook delivery failure should be recorded in delivery log (async)."""
    from apps.notifications.models import WebhookSubscription, WebhookDeliveryLog, WebhookDeliveryStatus
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    sub = WebhookSubscription.objects.create(
        url="https://down.example.com/hook",  # global subscription (no workflow)
        events=[],
        created_by=admin_user,
    )

    # Mock Celery to avoid Redis
    import apps.notifications.tasks as tasks_module
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=MagicMock(id="task-123"))
    monkeypatch.setattr(tasks_module, "deliver_webhook_task", mock_task)

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="instance_created",
        context_data={},
    )
    assert len(logs) == 1
    assert logs[0].status == WebhookDeliveryStatus.QUEUED  # Queued initially

    # Now simulate delivery failure
    delivery_log = logs[0]
    monkeypatch.setattr(tasks_module.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("connection refused")))

    try:
        tasks_module._deliver_webhook_impl(str(delivery_log.id))
    except Exception:
        pass

    delivery_log.refresh_from_db()
    assert delivery_log.status == WebhookDeliveryStatus.FAILED
    assert "connection refused" in delivery_log.error_message


# ---------------------------------------------------------------------------
# SLA breach command
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_slas_notifies_once_per_state_entry(setup_context):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from apps.notifications.models import EventTrigger, NotificationLog

    admin_user, wf, instance = setup_context

    # Give the current state a 1-hour SLA and backdate the instance
    state = instance.current_state
    state.sla_config = {"sla_hours": 1}
    state.save(update_fields=["sla_config"])
    WorkflowInstance.objects.filter(id=instance.id).update(
        created_at=timezone.now() - timedelta(hours=3)
    )

    from unittest.mock import patch

    from apps.audit.models import AuditActionType, AuditLog
    from apps.notifications.models import WebhookSubscription

    WebhookSubscription.objects.create(
        url="https://hooks.example.com/sla", events=["sla_breached"], created_by=admin_user
    )

    class FakeResponse:
        def raise_for_status(self):
            pass

    with patch("apps.notifications.services.httpx.post", return_value=FakeResponse()):
        call_command("check_slas")
        call_command("check_slas")  # second run must not duplicate

    # Exactly one delivery and one immutable audit marker per state entry
    breach_logs = NotificationLog.objects.filter(
        workflow_instance=instance, event_trigger=EventTrigger.SLA_BREACHED
    )
    assert breach_logs.count() == 1
    assert (
        AuditLog.objects.filter(
            workflow_instance=instance, action_type=AuditActionType.SLA_BREACHED
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Async webhook delivery with retries
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_emit_webhooks_creates_async_delivery_logs(setup_context, monkeypatch):
    """Webhooks should be queued asynchronously, not delivered sync."""
    from apps.notifications.models import WebhookSubscription, WebhookDeliveryLog, WebhookDeliveryStatus
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    sub = WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/async",
        events=["state_transition"],
        created_by=admin_user,
    )

    # Mock Celery task to avoid needing Redis
    import apps.notifications.tasks as tasks_module
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=MagicMock(id="task-123"))
    monkeypatch.setattr(tasks_module, "deliver_webhook_task", mock_task)

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="state_transition",
        context_data={"from_state": "Draft", "to_state": "Review"},
    )

    # Should create a WebhookDeliveryLog (async)
    delivery_log = WebhookDeliveryLog.objects.get(webhook_subscription=sub)
    assert delivery_log.status == WebhookDeliveryStatus.QUEUED
    assert delivery_log.attempt == 0
    assert delivery_log.payload["event"] == "state_transition"
    # Should have queued the task
    assert mock_task.delay.called


@pytest.mark.django_db
def test_webhook_delivery_task_success(setup_context, monkeypatch):
    """Webhook delivery should mark log as delivered on HTTP 200."""
    from apps.notifications.models import WebhookSubscription, WebhookDeliveryLog, WebhookDeliveryStatus
    from apps.notifications.tasks import _deliver_webhook_impl
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    sub = WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/success",
        secret="mysecret",
        created_by=admin_user,
    )

    delivery_log = WebhookDeliveryLog.objects.create(
        webhook_subscription=sub,
        workflow_instance=instance,
        event_trigger="state_transition",
        payload={"event": "state_transition", "instance": {"id": str(instance.id)}},
        status=WebhookDeliveryStatus.QUEUED,
    )

    fake_response = MagicMock()
    fake_response.status_code = 200

    import apps.notifications.tasks as tasks_module
    monkeypatch.setattr(tasks_module.httpx, "post", lambda *a, **k: fake_response)

    _deliver_webhook_impl(str(delivery_log.id))

    delivery_log.refresh_from_db()
    assert delivery_log.status == WebhookDeliveryStatus.DELIVERED
    assert delivery_log.http_status_code == 200
    assert delivery_log.delivered_at is not None


@pytest.mark.django_db
def test_webhook_delivery_retry_with_exponential_backoff(setup_context, monkeypatch):
    """Webhook failures should retry with exponential backoff (1s, 2s, 4s, etc.)."""
    from datetime import timedelta
    from apps.notifications.models import WebhookSubscription, WebhookDeliveryLog, WebhookDeliveryStatus
    from apps.notifications.tasks import _deliver_webhook_impl, MAX_WEBHOOK_RETRIES, get_retry_delay
    from django.utils import timezone
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    sub = WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/flaky",
        created_by=admin_user,
    )

    delivery_log = WebhookDeliveryLog.objects.create(
        webhook_subscription=sub,
        workflow_instance=instance,
        event_trigger="state_transition",
        payload={"event": "state_transition"},
        status=WebhookDeliveryStatus.QUEUED,
        attempt=0,
    )

    # Simulate HTTP error
    import apps.notifications.tasks as tasks_module
    monkeypatch.setattr(tasks_module.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("timeout")))

    # First retry
    try:
        _deliver_webhook_impl(str(delivery_log.id))
    except Exception:
        pass  # Expected to raise for retry

    delivery_log.refresh_from_db()
    assert delivery_log.status == WebhookDeliveryStatus.FAILED
    assert delivery_log.attempt == 1
    assert delivery_log.next_retry_at is not None

    # Check exponential backoff: 2^1 = 2 seconds
    expected_retry = timezone.now() + timedelta(seconds=get_retry_delay(1))
    assert abs((delivery_log.next_retry_at - expected_retry).total_seconds()) < 5  # Within 5s tolerance


@pytest.mark.django_db
def test_webhook_delivery_dead_letter_after_max_retries(setup_context, monkeypatch):
    """Webhooks should move to dead-letter after MAX_WEBHOOK_RETRIES."""
    from apps.notifications.models import WebhookSubscription, WebhookDeliveryLog, WebhookDeliveryStatus
    from apps.notifications.tasks import _deliver_webhook_impl, MAX_WEBHOOK_RETRIES
    from unittest.mock import MagicMock

    admin_user, wf, instance = setup_context
    sub = WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/dead",
        created_by=admin_user,
    )

    delivery_log = WebhookDeliveryLog.objects.create(
        webhook_subscription=sub,
        workflow_instance=instance,
        event_trigger="state_transition",
        payload={"event": "state_transition"},
        status=WebhookDeliveryStatus.FAILED,
        attempt=MAX_WEBHOOK_RETRIES - 1,  # One before limit
    )

    import apps.notifications.tasks as tasks_module
    monkeypatch.setattr(tasks_module.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("still down")))

    try:
        _deliver_webhook_impl(str(delivery_log.id))
    except Exception:
        pass

    delivery_log.refresh_from_db()
    assert delivery_log.status == WebhookDeliveryStatus.DEAD_LETTER
    assert delivery_log.attempt == MAX_WEBHOOK_RETRIES
    assert delivery_log.next_retry_at is None  # No further retries
