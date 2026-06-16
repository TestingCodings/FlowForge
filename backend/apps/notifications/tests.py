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
