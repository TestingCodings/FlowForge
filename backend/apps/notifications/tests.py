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
    import hashlib
    import hmac as hmac_mod
    import json

    from apps.notifications.models import WebhookSubscription
    from apps.notifications import services

    admin_user, wf, instance = setup_context
    WebhookSubscription.objects.create(
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

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = content
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(services.httpx, "post", fake_post)

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="state_transition",
        context_data={"from_state": "Draft", "to_state": "Review"},
    )

    assert len(logs) == 1
    assert logs[0].status == NotificationStatus.SENT
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
    from apps.notifications.models import WebhookSubscription
    from apps.notifications import services

    admin_user, wf, instance = setup_context
    WebhookSubscription.objects.create(
        workflow_definition=wf,
        url="https://hooks.example.com/only-comments",
        events=["comment_added"],
        created_by=admin_user,
    )

    monkeypatch.setattr(
        services.httpx, "post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="state_transition",
        context_data={},
    )
    assert logs == []


@pytest.mark.django_db
def test_webhook_failure_is_recorded_not_raised(setup_context, monkeypatch):
    from apps.notifications.models import WebhookSubscription
    from apps.notifications import services

    admin_user, wf, instance = setup_context
    WebhookSubscription.objects.create(
        url="https://down.example.com/hook",  # global subscription (no workflow)
        events=[],
        created_by=admin_user,
    )

    def fail_post(*a, **k):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(services.httpx, "post", fail_post)

    logs = queue_event_notifications(
        workflow_instance=instance,
        event_trigger="instance_created",
        context_data={},
    )
    assert len(logs) == 1
    assert logs[0].status == NotificationStatus.FAILED
    assert "connection refused" in logs[0].error_message


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
